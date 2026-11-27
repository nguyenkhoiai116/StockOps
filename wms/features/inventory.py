"""Feature: Lưu trữ & Kiểm soát tồn kho (Nhóm 2: CV1–CV5) — Slotting, Dự báo/ROP, Kiểm kê RCA, Điều chuyển 2 đầu, SLOB."""
import csv
import io

from flask import Blueprint, Response, jsonify, request

from ..core import actor, audit, notify_team, now_iso, run, shelf_pct, zone_bins, zone_used
from ..db import bad, day, db, log, rows
from ..storage_ai import (capacity_and_reslot, cycle_count_risk, demand_and_replenishment,
                          picking_route_suggest, rca_analyze, slob_analysis, slotting_recommend)

bp = Blueprint("inventory", __name__)


@bp.get("/api/inventory")
def api_inv():
    """Danh sách lô còn hàng (kèm % HSD, trạng thái QC, khóa kiểm kê), giao dịch, điều chuyển và đợt kiểm kê."""
    con = db()
    out = rows(
        con,
        """SELECT b.*, p.sku, p.name, p.storage, p.shelf_days, p.price
           FROM batches b JOIN products p ON p.id=b.product_id
           WHERE b.qty>0 ORDER BY b.exp""",
    )
    for b in out:
        b["shelf_pct"] = shelf_pct(b["exp"], b["shelf_days"])
    txs = rows(
        con,
        """SELECT t.*, p.sku FROM txs t JOIN products p ON p.id=t.product_id
           ORDER BY t.id DESC LIMIT 20""",
    )
    zs = rows(con, "SELECT * FROM zones ORDER BY code")
    trs = rows(con, "SELECT * FROM transfers ORDER BY id DESC LIMIT 20")
    cnts = rows(con, "SELECT * FROM cycle_counts ORDER BY id DESC LIMIT 20")
    routes = picking_route_suggest(con)
    con.close()
    return jsonify(batches=out, txs=txs, zones=zs, transfers=trs, counts=cnts, routes=routes, today=day(), near=day(30))


@bp.get("/api/storage/intel")
def api_storage_intel():
    """Tổng hợp phân tích tự động cho Storage & Inventory: Sức chứa/Re-slotting (CV1), Dự báo/ROP (CV2), Rủi ro kiểm kê (CV3), SLOB (CV5)."""
    con = db()
    try:
        cap = capacity_and_reslot(con)
        dem = demand_and_replenishment(con)
        risk = cycle_count_risk(con)
        slob = slob_analysis(con)
    finally:
        con.close()
    return jsonify(capacity=cap, demand=dem, risks=risk, slob=slob)


@bp.post("/api/storage/slot-suggest")
def api_slot_suggest():
    """CV1: Đề xuất Top 3 vị trí kệ tối ưu theo ràng buộc cứng + ABC + COI + Golden Zone + FEFO."""
    d = request.get_json(silent=True) or {}
    try:
        pid = int(d.get("product_id") or 0)
        qty = int(d.get("qty") or 0)
    except (TypeError, ValueError):
        return bad("Dữ liệu sản phẩm hoặc số lượng không hợp lệ")
    if pid <= 0 or qty <= 0:
        return bad("Cần chọn sản phẩm và số lượng > 0")
    con = db()
    try:
        res = slotting_recommend(con, pid, qty, (d.get("exp") or "").strip())
    except ValueError as e:
        con.close()
        return bad(str(e))
    con.close()
    return jsonify(res)


@bp.post("/api/inventory/<int:bid>/adjust")
def api_adjust(bid):
    """Điều chỉnh tồn (kiểm kê lệch, hàng vỡ, hủy lô). delta âm = giảm."""
    d = request.get_json(silent=True) or {}
    try:
        delta = int(d.get("delta"))
    except (TypeError, ValueError):
        return bad("Số điều chỉnh không hợp lệ")

    def work(con):
        b = con.execute(
            "SELECT b.*, p.sku, z.cap, z.name AS zname FROM batches b JOIN products p ON p.id=b.product_id JOIN zones z ON z.code=b.zone WHERE b.id=?",
            (bid,),
        ).fetchone()
        if not b or delta == 0:
            raise ValueError("Không có gì để điều chỉnh")
        if b["locked"]:
            raise ValueError("Vị trí đang tạm khóa kiểm kê (cut-off), hãy hoàn tất đợt kiểm kê trước")
        new = b["qty"] + delta
        if new < 0:
            raise ValueError("Không cho phép tồn kho âm")
        if new < b["reserved"]:
            raise ValueError(f"Lô đang giữ {b['reserved']} thùng cho đơn hàng, không giảm thấp hơn được")
        if delta > 0 and zone_used(con, b["zone"]) + delta > b["cap"]:
            raise ValueError(f"{b['zname']} không đủ sức chứa")
        note = d.get("note") or "Điều chỉnh tồn"
        con.execute("UPDATE batches SET qty=? WHERE id=?", (new, bid))
        log(con, "ADJ", b["product_id"], b["batch_no"], delta, note)
        audit(con, "storage", "Điều chỉnh tồn kho", b["batch_no"], f"{b['sku']}: {delta:+d} thùng ({note})")

    return run(work)


@bp.post("/api/inventory/<int:bid>/quality")
def api_batch_quality(bid):
    """CV4: Đổi trạng thái chất lượng lô (ok | hold | quarantine) khi sự cố nhiệt độ hoặc cần QC."""
    d = request.get_json(silent=True) or {}
    st = (d.get("q_status") or "").strip()
    if st not in ("ok", "hold", "quarantine"):
        return bad("Trạng thái chất lượng không hợp lệ (ok / hold / quarantine)")

    def work(con):
        b = con.execute("SELECT b.*, p.sku FROM batches b JOIN products p ON p.id=b.product_id WHERE b.id=?", (bid,)).fetchone()
        if not b:
            raise ValueError("Không tìm thấy lô hàng")
        if st != "ok" and b["reserved"] > 0:
            raise ValueError(f"Lô đang giữ {b['reserved']} thùng cho đơn hàng, không thể chuyển sang {st}")
        con.execute("UPDATE batches SET q_status=? WHERE id=?", (st, bid))
        note = d.get("note") or f"Chuyển trạng thái lô sang {st}"
        audit(con, "storage", "Cập nhật trạng thái QC", b["batch_no"], f"{b['sku']} ({b['zone']}-{b['bin']:02d}) → {st}: {note}")
        if st != "ok":
            notify_team(con, "picking", f"Lô {b['batch_no']} ({b['sku']}) vừa chuyển sang '{st}' — tạm loại khỏi danh sách lấy FEFO.", b["batch_no"])

    return run(work)


# ---------- CV4: Điều chuyển vị trí / khu xác nhận 2 đầu ----------
@bp.post("/api/storage/transfers")
def api_transfer_create():
    """Tạo lệnh điều chuyển (bước 1: xác nhận xuất nguồn -> trạng thái 'in_transit')."""
    d = request.get_json(silent=True) or {}
    try:
        bid = int(d.get("batch_id") or 0)
        to_bin = int(d.get("to_bin") or 0)
    except (TypeError, ValueError):
        return bad("Dữ liệu lô hoặc ô đích không hợp lệ")
    to_zone = (d.get("to_zone") or "").strip().upper()
    if bid <= 0 or to_bin <= 0 or not to_zone:
        return bad("Cần chọn lô hàng, khu đích và số ô đích")

    def work(con):
        b = con.execute("SELECT b.*, p.sku, p.storage FROM batches b JOIN products p ON p.id=b.product_id WHERE b.id=?", (bid,)).fetchone()
        if not b or b["qty"] <= 0:
            raise ValueError("Lô hàng không tồn tại hoặc đã hết")
        if b["locked"]:
            raise ValueError("Lô đang khóa kiểm kê, không thể điều chuyển")
        z = con.execute("SELECT * FROM zones WHERE code=?", (to_zone,)).fetchone()
        if not z:
            raise ValueError("Khu đích không tồn tại")
        if z["storage"] != b["storage"]:
            raise ValueError(f"Vi phạm ràng buộc cứng: hàng '{b['storage']}' không được chuyển sang {z['name']} ({z['storage']})")
        if to_bin > zone_bins(z):
            raise ValueError(f"Ô {to_bin} vượt quá số ô ({zone_bins(z)}) của {z['name']}")
        if b["zone"] == to_zone and b["bin"] == to_bin:
            raise ValueError("Vị trí đích trùng với vị trí hiện tại")
        busy = con.execute("SELECT batch_no FROM batches WHERE zone=? AND bin=? AND qty>0 AND id!=?", (to_zone, to_bin, bid)).fetchone()
        if busy:
            raise ValueError(f"Ô {to_zone}-{to_bin:02d} đang chứa lô {busy['batch_no']}")
        un, _, _ = actor()
        con.execute("UPDATE batches SET locked=1 WHERE id=?", (bid,))
        con.execute(
            """INSERT INTO transfers (batch_id,sku,batch_no,from_zone,from_bin,to_zone,to_bin,qty,status,note,created_by,created_at)
               VALUES (?,?,?,?,?,?,?,?,'in_transit',?,?,?)""",
            (bid, b["sku"], b["batch_no"], b["zone"], b["bin"], to_zone, to_bin, b["qty"],
             (d.get("note") or "Tối ưu vị trí / Re-slotting").strip(), un, now_iso()),
        )
        audit(con, "storage", "Tạo lệnh điều chuyển (Xuất nguồn)", b["batch_no"],
              f"Chuyển {b['qty']} thùng {b['sku']} từ {b['zone']}-{b['bin']:02d} → {to_zone}-{to_bin:02d} (đang vận chuyển)")

    return run(work)


@bp.post("/api/storage/transfers/<int:tid>/confirm")
def api_transfer_confirm(tid):
    """Bước 2 điều chuyển: xác nhận nhập đích (hoặc hủy lệnh) -> cập nhật vị trí & mở khóa lô."""
    d = request.get_json(silent=True) or {}
    action = (d.get("action") or "complete").strip()

    def work(con):
        tr = con.execute("SELECT * FROM transfers WHERE id=?", (tid,)).fetchone()
        if not tr or tr["status"] != "in_transit":
            raise ValueError("Lệnh điều chuyển không tồn tại hoặc đã xử lý")
        un, _, _ = actor()
        if action == "cancel":
            con.execute("UPDATE transfers SET status='cancelled', confirmed_by=?, completed_at=? WHERE id=?", (un, now_iso(), tid))
            con.execute("UPDATE batches SET locked=0 WHERE id=?", (tr["batch_id"],))
            audit(con, "storage", "Hủy điều chuyển", tr["batch_no"], f"Hủy lệnh chuyển sang {tr['to_zone']}-{tr['to_bin']:02d}")
            return
        busy = con.execute("SELECT batch_no FROM batches WHERE zone=? AND bin=? AND qty>0 AND id!=?",
                           (tr["to_zone"], tr["to_bin"], tr["batch_id"])).fetchone()
        if busy:
            raise ValueError(f"Ô đích {tr['to_zone']}-{tr['to_bin']:02d} hiện đã bị chiếm bởi {busy['batch_no']}")
        con.execute("UPDATE batches SET zone=?, bin=?, locked=0 WHERE id=?", (tr["to_zone"], tr["to_bin"], tr["batch_id"]))
        con.execute("UPDATE transfers SET status='completed', confirmed_by=?, completed_at=? WHERE id=?", (un, now_iso(), tid))
        b = con.execute("SELECT product_id FROM batches WHERE id=?", (tr["batch_id"],)).fetchone()
        if b:
            log(con, "ADJ", b["product_id"], tr["batch_no"], 0, f"Chuyển vị trí {tr['from_zone']}-{tr['from_bin']:02d} → {tr['to_zone']}-{tr['to_bin']:02d}")
        audit(con, "storage", "Xác nhận nhập đích điều chuyển", tr["batch_no"],
              f"Hoàn tất chuyển {tr['sku']} vào {tr['to_zone']}-{tr['to_bin']:02d}")

    return run(work)


# ---------- CV3: Kiểm kê ABC Risk-based, Recount & RCA ----------
@bp.post("/api/storage/counts")
def api_count_create():
    """Tạo đợt kiểm kê cho 1 lô (Cut-off & tạm khóa vị trí để không bị di chuyển/soạn hàng khi đang đếm)."""
    d = request.get_json(silent=True) or {}
    try:
        bid = int(d.get("batch_id") or 0)
    except (TypeError, ValueError):
        return bad("Mã lô không hợp lệ")
    if bid <= 0:
        return bad("Cần chọn lô để mở đợt kiểm kê")

    def work(con):
        b = con.execute("SELECT b.*, p.sku FROM batches b JOIN products p ON p.id=b.product_id WHERE b.id=?", (bid,)).fetchone()
        if not b or b["qty"] <= 0:
            raise ValueError("Lô hàng không tồn tại hoặc hết tồn")
        if b["locked"]:
            raise ValueError("Lô này đang được khóa trong một đợt kiểm kê/điều chuyển khác")
        un, _, _ = actor()
        con.execute("UPDATE batches SET locked=1 WHERE id=?", (bid,))
        con.execute(
            """INSERT INTO cycle_counts (batch_id,zone,bin,sku,batch_no,q_system,status,note,created_by,created_at)
               VALUES (?,?,?,?,?,?,'open',?,?,?)""",
            (bid, b["zone"], b["bin"], b["sku"], b["batch_no"], b["qty"], (d.get("note") or "Kiểm kê theo điểm rủi ro ABC").strip(), un, now_iso()),
        )
        audit(con, "storage", "Mở đợt kiểm kê (Khóa vị trí)", b["batch_no"], f"Khóa {b['zone']}-{b['bin']:02d} ({b['sku']}, tồn hệ thống {b['qty']})")

    return run(work)


@bp.post("/api/storage/counts/<int:cid>/submit")
def api_count_submit(cid):
    """Nhập số lượng đếm thực tế -> tính Variance, dung sai, yêu cầu Recount nếu lệch vượt ngưỡng, chạy luật RCA."""
    d = request.get_json(silent=True) or {}
    try:
        q_phy = int(d.get("q_physical"))
    except (TypeError, ValueError):
        return bad("Cần nhập số lượng đếm thực tế hợp lệ (≥ 0)")
    if q_phy < 0:
        return bad("Số lượng thực tế không được âm")

    def work(con):
        c = con.execute("SELECT * FROM cycle_counts WHERE id=?", (cid,)).fetchone()
        if not c or c["status"] not in ("open", "recount"):
            raise ValueError("Đợt kiểm kê không ở trạng thái chờ nhập số đếm")
        b = con.execute("SELECT b.*, p.price, p.fragile FROM batches b JOIN products p ON p.id=b.product_id WHERE b.id=?", (c["batch_id"],)).fetchone()
        if not b:
            raise ValueError("Không tìm thấy lô tương ứng")
        var = q_phy - c["q_system"]
        val_diff = var * b["price"]
        rca, lvl = rca_analyze(con, b, var, val_diff)
        # Dung sai: lệch <= 1 thùng và < 500k hoặc khớp 0 -> không cần đếm lại
        tol_ok = var == 0 or (abs(var) <= 1 and abs(val_diff) < 500000)
        if c["status"] == "open" and not tol_ok:
            new_st = "recount"
        elif var == 0:
            new_st = "approved"
            con.execute("UPDATE batches SET locked=0 WHERE id=?", (c["batch_id"],))
        else:
            new_st = "pending_approve"
        con.execute(
            """UPDATE cycle_counts SET q_physical=?, variance=?, val_diff=?, status=?, rca_hint=?, approval_level=?
               WHERE id=?""",
            (q_phy, var, val_diff, new_st, rca, lvl, cid),
        )
        audit(con, "storage", "Nhập kết quả kiểm kê", c["batch_no"],
              f"Thực tế {q_phy} vs Hệ thống {c['q_system']} (lệch {var:+d}) → {new_st}. RCA: {rca}")

    return run(work)


@bp.post("/api/storage/counts/<int:cid>/approve")
def api_count_approve(cid):
    """Phê duyệt (hoặc từ chối) điều chỉnh tồn kho sau kiểm kê, mở khóa vị trí và ghi sổ."""
    d = request.get_json(silent=True) or {}
    action = (d.get("action") or "approve").strip()

    def work(con):
        c = con.execute("SELECT * FROM cycle_counts WHERE id=?", (cid,)).fetchone()
        if not c or c["status"] not in ("pending_approve", "recount", "open"):
            raise ValueError("Đợt kiểm kê đã đóng")
        un, _, _ = actor()
        if action == "reject":
            con.execute("UPDATE cycle_counts SET status='rejected', approved_by=? WHERE id=?", (un, cid))
            con.execute("UPDATE batches SET locked=0 WHERE id=?", (c["batch_id"],))
            audit(con, "storage", "Từ chối điều chỉnh kiểm kê", c["batch_no"], "Giữ nguyên tồn hệ thống và mở khóa vị trí")
            return
        if c["q_physical"] is None:
            raise ValueError("Chưa nhập số lượng đếm thực tế")
        b = con.execute("SELECT * FROM batches WHERE id=?", (c["batch_id"],)).fetchone()
        if c["q_physical"] < b["reserved"]:
            raise ValueError(f"Số lượng mới ({c['q_physical']}) thấp hơn số đã giữ ({b['reserved']}) cho đơn hàng")
        con.execute("UPDATE batches SET qty=?, locked=0 WHERE id=?", (c["q_physical"], c["batch_id"]))
        con.execute("UPDATE cycle_counts SET status='approved', approved_by=? WHERE id=?", (un, cid))
        if c["variance"]:
            log(con, "ADJ", b["product_id"], c["batch_no"], c["variance"], f"Duyệt kiểm kê #{cid}: {c['rca_hint'] or ''}")
        audit(con, "storage", "Phê duyệt kiểm kê", c["batch_no"],
              f"Cập nhật tồn {c['q_system']} → {c['q_physical']} ({c['variance']:+d} thùng, cấp duyệt: {c['approval_level']})")

    return run(work)


@bp.get("/api/export/inventory.csv")
def api_export():
    """Xuất tồn kho ra file CSV (mở được bằng Excel)."""
    con = db()
    f = io.StringIO()
    w = csv.writer(f)
    w.writerow(["SKU", "Tên", "Số lô", "Hạn dùng", "Vị trí", "Trạng thái QC", "Thực có", "Đã giữ", "Khả dụng"])
    for b in rows(con, "SELECT b.*, p.sku, p.name FROM batches b JOIN products p ON p.id=b.product_id WHERE b.qty>0 ORDER BY p.sku, b.exp"):
        w.writerow([b["sku"], b["name"], b["batch_no"], b["exp"], f"{b['zone']}-{b['bin']:02d}",
                    b["q_status"], b["qty"], b["reserved"], b["qty"] - b["reserved"]])
    con.close()
    return Response("\ufeff" + f.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=ton-kho.csv"})
