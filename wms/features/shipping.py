"""Feature: Xuất kho & Vận chuyển (Nhóm 4 Outbound: CV1–CV5).

Gồm 3 phân khu nối tiếp:
1. Đơn hàng & Chứng từ (CV1A/1B): Bóc tách đơn, Đối chiếu 3 chiều (SO ↔ Thực đóng ↔ % HSD kênh), In chứng từ QR.
2. Điều phối Chuyến xe, Sơ đồ xếp tải 2D LIFO & Lịch Cửa xuất (CV2 & CV3).
3. Khu chờ xuất Staging, Trạm Quét mã QR lên xe & Giám sát Giao vận ETA + Nhiệt độ thùng xe (CV5 trước CV4).
"""
import json
from datetime import datetime

from flask import Blueprint, jsonify, request

from ..core import audit, do_ship, notify_team, now_iso, run
from ..db import bad, day, db, rows
from ..outbound_ai import (analyze_truck_temp, audit_so_3way, auto_schedule_docks, build_lifo_plan,
                           consolidate_orders, parse_order_text, staging_monitor)
from ..xlsx import extract_text_from_upload

bp = Blueprint("shipping", __name__)


@bp.get("/api/outbound/board")
def api_outbound_board():
    """Toàn bộ dữ liệu cho Outbound Control Tower (3 mục CV1, CV2–CV3, CV5–CV4 + 2 thanh KPI kinh tế)."""
    con = db()
    custs = rows(con, "SELECT * FROM customers ORDER BY name")
    vehicles = rows(con, "SELECT * FROM vehicles ORDER BY plate")

    # CV1B: Hàng đợi kiểm duyệt 3 chiều cho các đơn Nhóm 3 đã soạn (status='picked')
    picked_ids = [r["id"] for r in rows(con, "SELECT id FROM sos WHERE status='picked' ORDER BY due, id")]
    ready_queue = [audit_so_3way(con, sid) for sid in picked_ids]

    # CV2 & CV3 & CV4: Danh sách chuyến xe kèm đơn hàng, sơ đồ LIFO 2D và chuỗi nhiệt độ thùng xe
    trips_raw = rows(con, "SELECT * FROM trips ORDER BY id DESC")
    trips = []
    tot_saved = 0
    trips_saved = 0
    fill_list = []
    blocked_risks = 0
    for t in trips_raw:
        t_orders = rows(
            con,
            """SELECT s.*, p.sku, p.name AS pname, p.storage, p.price, p.weight_kg, p.vol_m3, p.fragile
               FROM sos s JOIN products p ON p.id=s.product_id WHERE s.trip_id=? ORDER BY s.due, s.id""",
            (t["id"],),
        )
        veh = next((v for v in vehicles if v["plate"] == t["plate"]), vehicles[0] if vehicles else None)
        plan = None
        if t_orders and veh:
            plan = build_lifo_plan(t_orders, veh)
        elif t["load_plan_json"]:
            try:
                plan = json.loads(t["load_plan_json"])
            except ValueError:
                plan = None
        temp_info = analyze_truck_temp(t)
        tot_saved += t["saved_vnd"] or 0
        if len(t_orders) > 1:
            trips_saved += len(t_orders) - 1
        if t["fill_pct"]:
            fill_list.append(t["fill_pct"])
        if plan and plan.get("warnings"):
            blocked_risks += len(plan["warnings"])
        cargo_val = sum(o["qty"] * o["price"] for o in t_orders)
        tot_qty = sum(o["qty"] for o in t_orders)
        scanned = sum(o["scanned_qty"] for o in t_orders)
        trips.append({
            **t, "orders": t_orders, "plan": plan, "temp": temp_info,
            "cargo_val": cargo_val, "tot_qty": tot_qty, "scanned_qty": scanned,
        })

    # CV5: Giám sát khu chờ xuất Staging
    staging = staging_monitor(con)
    # Thanh KPI tối ưu chi phí Outbound (Mục 2)
    avg_fill = round(sum(fill_list) / len(fill_list), 1) if fill_list else 0.0
    detention_saved = sum(350000 for t in trips if t["dock"])
    hsd_blocks = sum(1 for q in ready_queue if not q["checks"]["hsd_ok"])
    cost_kpi = {
        "avg_fill_pct": avg_fill,
        "trips_saved": trips_saved,
        "saved_vnd": tot_saved + detention_saved,
        "risks_blocked": blocked_risks + hsd_blocks,
    }

    # Thanh KPI thực thi & bảo toàn giá trị (Mục 3)
    done = con.execute("SELECT COUNT(*) FROM sos WHERE status='delivered'").fetchone()[0]
    on_time = con.execute("SELECT COUNT(*) FROM sos WHERE on_time=1").fetchone()[0]
    otif = round(on_time / done * 100, 1) if done else 100.0
    active_alerts = sum(1 for s in staging if s["is_cold"] and s["level"] != "ok") + sum(
        1 for t in trips if t["status"] == "in_transit" and (t["temp"]["has_anomaly"] or t["sla_risk_pct"] >= 30)
    )
    prevented_vnd = sum(q["avoided_penalty_vnd"] for q in ready_queue if not q["can_approve"]) + sum(
        t["cargo_val"] for t in trips if t["status"] == "in_transit" and t["temp"]["has_anomaly"]
    )
    exec_kpi = {
        "loading_acc": 100.0,
        "otif": otif,
        "active_alerts": active_alerts,
        "prevented_vnd": prevented_vnd,
    }

    # Toàn bộ đơn đã soạn trở đi (phục vụ tương thích & tra cứu lịch sử giao)
    all_orders = rows(
        con,
        """SELECT s.*, p.sku, p.name, p.storage, p.price FROM sos s JOIN products p ON p.id=s.product_id
           WHERE s.status!='new' ORDER BY s.id DESC""",
    )
    con.close()
    return jsonify(
        customers=custs, vehicles=vehicles, ready_queue=ready_queue,
        trips=trips, staging=staging, orders=all_orders,
        cost_kpi=cost_kpi, exec_kpi=exec_kpi,
    )


@bp.post("/api/outbound/parse")
def api_outbound_parse():
    """CV1A: Tự động bóc tách & chuẩn hóa file Excel (.xlsx) / CSV / văn bản đơn đặt hàng của khách, check tồn 100%."""
    if "file" in request.files and request.files["file"].filename:
        try:
            raw = extract_text_from_upload(request.files["file"])
        except ValueError as e:
            return bad(str(e))
    else:
        d = request.get_json(silent=True) or {}
        raw = str(d.get("text") or "").strip()
    if not raw.strip():
        return bad("Nội dung đơn hàng đang trống")
    con = db()
    items = parse_order_text(con, raw)
    con.close()
    return jsonify(items=items)


@bp.post("/api/outbound/orders/<int:so_id>/audit")
def api_outbound_audit(so_id):
    """CV1B: Duyệt chứng từ 3 chiều (đạt 3 điều kiện cứng) hoặc Trả về Nhóm 3 kèm gợi ý hoán đổi lô."""
    d = request.get_json(silent=True) or {}
    action = (d.get("action") or "approve").strip()
    note = (d.get("note") or "").strip()

    def work(con):
        res = audit_so_3way(con, so_id)
        so = res["so"]
        if so["status"] != "picked":
            raise ValueError("Chỉ kiểm duyệt các đơn đang ở trạng thái Đã soạn (Picked)")
        if action == "return":
            # Trả về Nhóm 3: hoàn trả phần reserved và đưa đơn về 'new' để soạn lại / hoán đổi lô
            for pk in rows(con, "SELECT * FROM picks WHERE so_id=?", (so_id,)):
                con.execute("UPDATE batches SET reserved=MAX(0, reserved-?) WHERE id=?", (pk["qty"], pk["batch_id"]))
            con.execute("DELETE FROM picks WHERE so_id=?", (so_id,))
            reason = note or res["swap_hint"] or "Không đạt kiểm duyệt 3 chiều (SL/HSD kênh)"
            con.execute("UPDATE sos SET status='new', audit_status='returned', audit_note=?, trip_id=NULL WHERE id=?", (reason, so_id))
            audit(con, "shipping", "Trả đơn về Nhóm 3", so["so_no"], reason)
            notify_team(con, "picking", f"[Trả đơn từ Xuất kho] {so['so_no']} ({so['customer']}) bị chặn kiểm duyệt: {reason}", so["so_no"])
            return
        if not res["can_approve"]:
            raise ValueError("Chưa đạt đủ 3 điều kiện cứng (100% SL / chuẩn % HSD kênh / chứng từ) — không thể duyệt xuất!")
        con.execute("UPDATE sos SET audit_status='approved', audit_note=? WHERE id=?", (note or "Đạt chuẩn 3 chiều", so_id))
        audit(con, "shipping", "Duyệt chứng từ 3 chiều", so["so_no"], f"Đã khóa đơn & phát hành Phiếu xuất + QR cho {so['customer']}")

    return run(work)


@bp.post("/api/outbound/consolidate")
def api_outbound_consolidate():
    """CV2: Tự động ghép các đơn đã duyệt thành Chuyến xe tối ưu (cùng tuyến + cùng nhiệt độ)."""
    con = db()
    try:
        with con:
            created = consolidate_orders(con)
            if not created:
                return bad("Không có đơn đã duyệt chứng từ nào chờ ghép chuyến")
            audit(con, "shipping", "Ghép chuyến tối ưu", ", ".join(created), f"Đã gom đơn thành {len(created)} chuyến xe tối ưu Fill Rate")
    finally:
        con.close()
    return jsonify(ok=True, trips=created)


@bp.post("/api/outbound/trips/<int:tid>/safety-check")
def api_trip_safety(tid):
    """CV3: Safety Guard — kiểm tra đổi xe hoặc thử xếp kèm hóa mỹ phẩm; chặn cứng rủi ro & báo giá trị bảo toàn."""
    d = request.get_json(silent=True) or {}
    plate = (d.get("plate") or "").strip()
    test_cos = bool(d.get("simulate_cosmetics"))
    con = db()
    t = con.execute("SELECT * FROM trips WHERE id=?", (tid,)).fetchone()
    if not t:
        con.close()
        return bad("Không tìm thấy chuyến xe")
    veh = con.execute("SELECT * FROM vehicles WHERE plate=?", (plate or t["plate"],)).fetchone()
    if not veh:
        con.close()
        return bad("Không tìm thấy phương tiện")
    t_orders = rows(
        con,
        """SELECT s.*, p.sku, p.name AS pname, p.storage, p.price, p.weight_kg, p.vol_m3, p.fragile
           FROM sos s JOIN products p ON p.id=s.product_id WHERE s.trip_id=?""",
        (tid,),
    )
    if test_cos:
        t_orders.append({
            "id": 0, "so_no": "THỬ-MỸ-PHẨM", "customer": "Kiểm thử nhiễm chéo",
            "sku": "SKU-007", "pname": "Dầu gội / Hóa mỹ phẩm (mô phỏng)", "qty": 20, "due": day(1),
            "storage": "cosmetics", "price": 1450000, "weight_kg": 8.4, "vol_m3": 0.026, "fragile": 0,
        })
    plan = build_lifo_plan(t_orders, veh)
    if not plan["blocked"] and not test_cos and plate and plate != t["plate"]:
        with con:
            con.execute("UPDATE trips SET plate=?, load_plan_json=?, fill_pct=? WHERE id=?",
                        (plate, json.dumps(plan, ensure_ascii=False), plan["fill_pct"], tid))
            audit(con, "shipping", "Đổi phương tiện chuyến xe", t["trip_no"], f"Đổi sang xe {plate} (đạt Safety Guard)")
    con.close()
    return jsonify(plan=plan)


@bp.post("/api/outbound/schedule-docks")
def api_schedule_docks():
    """CV2: Tự động phân bổ cửa xuất (X1-X4) & khung giờ theo EDF + Cold-Chain + Slot Smoothing."""
    con = db()
    try:
        with con:
            n = auto_schedule_docks(con)
            if n == 0:
                return bad("Không có chuyến xe nào đang chờ xếp lịch cửa xuất")
            audit(con, "shipping", "Xếp lịch cửa xuất (Dock)", f"{n} chuyến", "Đã san tải khung giờ 06:00–18:00 theo EDF & ưu tiên chuỗi lạnh")
    finally:
        con.close()
    return jsonify(ok=True, scheduled=n)


@bp.post("/api/outbound/trips/<int:tid>/start-load")
def api_trip_start_load(tid):
    """CV2→CV5: Chốt lệnh Điều xe & Bàn giao Bốc xếp (đưa xe vào Dock để quét QR lên xe)."""
    def work(con):
        t = con.execute("SELECT * FROM trips WHERE id=?", (tid,)).fetchone()
        if not t or t["status"] not in ("planned", "scheduled"):
            raise ValueError("Chuyến xe không ở trạng thái chờ bốc xếp")
        dock = t["dock"] or ("X1" if t["storage"] in ("chilled", "frozen") else "X3")
        con.execute("UPDATE trips SET status='loading', dock=? WHERE id=?", (dock, tid))
        audit(con, "shipping", "Chốt lệnh bốc xếp tại Dock", t["trip_no"], f"Xe {t['plate']} đã vào cửa {dock}, sẵn sàng quét QR lên xe")

    return run(work)


@bp.post("/api/outbound/trips/<int:tid>/scan")
def api_trip_scan(tid):
    """CV5: Trạm Quét mã QR kiện hàng lên xe theo thứ tự LIFO; chặn ngay nếu quét nhầm kiện của đơn khác."""
    d = request.get_json(silent=True) or {}
    code = str(d.get("code") or "").strip().upper()
    step_qty = int(d.get("qty") or 0)
    if not code:
        return bad("Cần nhập hoặc quét mã QR kiện hàng")
    con = db()
    t = con.execute("SELECT * FROM trips WHERE id=?", (tid,)).fetchone()
    if not t or t["status"] not in ("loading", "scheduled"):
        con.close()
        return bad("Chuyến xe chưa ở trạng thái bốc xếp tại Dock")
    so = con.execute("SELECT * FROM sos WHERE trip_id=? AND UPPER(so_no)=?", (tid, code)).fetchone()
    if not so:
        con.close()
        return bad(f"BÁO ĐỎ – QUÉT NHẦM KIỆN: Mã '{code}' KHÔNG thuộc chuyến {t['trip_no']}! Đã chặn lên xe.")
    add = step_qty if step_qty > 0 else (so["qty"] - so["scanned_qty"])
    new_q = min(so["qty"], so["scanned_qty"] + max(1, add))
    with con:
        con.execute("UPDATE sos SET scanned_qty=? WHERE id=?", (new_q, so["id"]))
        if t["status"] == "scheduled":
            con.execute("UPDATE trips SET status='loading' WHERE id=?", (tid,))
        audit(con, "shipping", "Quét mã QR bốc lên xe", so["so_no"], f"Chuyến {t['trip_no']}: đã quét {new_q}/{so['qty']} thùng")
    con.close()
    return jsonify(ok=True, so_no=so["so_no"], scanned=new_q, qty=so["qty"])


@bp.post("/api/outbound/trips/<int:tid>/dispatch")
def api_trip_dispatch(tid):
    """CV5→CV4: Xác nhận Xuất cổng. Khóa cứng nếu chưa quét đủ 100% kiện; đủ thì gọi do_ship trừ tồn thật."""
    d = request.get_json(silent=True) or {}
    proof = (d.get("proof_note") or "Đã chụp ảnh niêm phong thùng xe (Proof of Loading)").strip()

    def work(con):
        t = con.execute("SELECT * FROM trips WHERE id=?", (tid,)).fetchone()
        if not t or t["status"] not in ("loading", "scheduled"):
            raise ValueError("Chuyến xe chưa sẵn sàng xuất cổng")
        os = rows(con, "SELECT * FROM sos WHERE trip_id=? AND status='picked'", (tid,))
        if not os:
            raise ValueError("Chuyến xe không còn đơn chờ xuất")
        tot = sum(o["qty"] for o in os)
        sc = sum(o["scanned_qty"] for o in os)
        if sc < tot:
            raise ValueError(f"KHÓA XUẤT CỔNG: mới quét QR {sc}/{tot} thùng (chưa đạt 100%). Hãy quét đủ kiện trước!")
        for o in os:
            do_ship(con, o["id"], t["plate"])
        base = -19.0 if t["storage"] == "frozen" else (4.5 if t["storage"] == "chilled" else 25.5)
        now_hm = datetime.now().strftime("%H:%M")
        tlog = [
            {"t": now_hm, "temp": base, "event": "Xuất cổng an toàn", "anomaly": False},
            {"t": "+15p", "temp": round(base + 0.3, 1), "event": "", "anomaly": False},
            {"t": "+30p", "temp": round(base + 1.8, 1), "event": "Mở cửa dỡ hàng (An toàn)", "anomaly": False},
            {"t": "+45p", "temp": round(base + 0.4, 1), "event": "Ổn định", "anomaly": False},
        ]
        con.execute(
            "UPDATE trips SET status='in_transit', proof_note=?, temp_log_json=? WHERE id=?",
            (proof, json.dumps(tlog, ensure_ascii=False), tid),
        )
        audit(con, "shipping", "Xác nhận xuất cổng", t["trip_no"], f"Xe {t['plate']} xuất cổng ({tot}/{tot} thùng, {proof})")

    return run(work)


@bp.post("/api/outbound/staging/<int:so_id>/action")
def api_staging_action(so_id):
    """CV5: Hành động nhanh tại Khu 6 Staging chống sốc nhiệt (đưa tạm vào Kho lạnh hoặc ưu tiên bốc ngay)."""
    d = request.get_json(silent=True) or {}
    act = (d.get("action") or "return_cold").strip()

    def work(con):
        so = con.execute("SELECT * FROM sos WHERE id=?", (so_id,)).fetchone()
        if not so or so["status"] != "picked":
            raise ValueError("Đơn không còn nằm ở khu chờ xuất Staging")
        if act == "return_cold":
            con.execute("UPDATE sos SET staged_at=? WHERE id=?", (now_iso(), so_id))
            audit(con, "shipping", "Chống sốc nhiệt Staging", so["so_no"], "Đưa tạm hàng lạnh trở lại Kho lạnh (Khu 2) bảo toàn nhiệt độ")
            notify_team(con, "storage", f"[Chống sốc nhiệt] Đơn {so['so_no']} đã được đưa tạm vào phòng đệm Kho lạnh chờ xe cập Dock.", so["so_no"])
        else:
            audit(con, "shipping", "Đẩy ưu tiên bốc hàng lạnh", so["so_no"], "Đẩy ưu tiên bốc ngay tại cửa lạnh X1")
            notify_team(con, "shipping", f"[Ưu tiên khẩn] Đẩy đơn lạnh {so['so_no']} ({so['customer']}) vào cửa X1 bốc hàng ngay!", so["so_no"])

    return run(work)


@bp.post("/api/outbound/trips/<int:tid>/alert")
def api_trip_alert(tid):
    """CV4: Gửi lệnh khẩn nhiệt độ/SLA tới tài xế & quản lý, hoặc mô phỏng sự cố nhiệt độ thùng xe."""
    d = request.get_json(silent=True) or {}
    mode = (d.get("mode") or "notify").strip()

    def work(con):
        t = con.execute("SELECT * FROM trips WHERE id=?", (tid,)).fetchone()
        if not t:
            raise ValueError("Không tìm thấy chuyến xe")
        if mode == "sim_fault":
            info = analyze_truck_temp(t)
            pts = list(info["points"])
            last = pts[-1]["temp"]
            pts.append({"t": "+60p", "temp": round(last + 2.3, 1), "event": "Tăng nhiệt bất thường khi đóng cửa", "anomaly": True})
            pts.append({"t": "+75p", "temp": round(last + 4.5, 1), "event": "Cảnh báo: Nghi hỏng lốc lạnh!", "anomaly": True})
            con.execute("UPDATE trips SET temp_log_json=?, sla_risk_pct=75 WHERE id=?",
                        (json.dumps(pts, ensure_ascii=False), tid))
            audit(con, "shipping", "Cảnh báo bất thường nhiệt độ xe", t["trip_no"], f"Xe {t['plate']} nhiệt độ thùng tăng lên {pts[-1]['temp']}°C")
            return
        msg = (d.get("msg") or f"[Lệnh khẩn giao vận] Chuyến {t['trip_no']} (xe {t['plate']}): kiểm tra ngay nhiệt độ thùng xe / khung giờ SLA và phản hồi về kho!").strip()
        audit(con, "shipping", "Gửi cảnh báo khẩn giao vận", t["trip_no"], msg)
        notify_team(con, "admin", msg, t["trip_no"])

    return run(work)


@bp.post("/api/orders/<int:so_id>/ship")
def api_ship(so_id):
    """Xuất kho nhanh 1 đơn đã soạn lên xe được chọn (tương thích hoàn toàn với API cũ)."""
    return run(do_ship, so_id, (request.get_json(silent=True) or {}).get("plate"))


@bp.post("/api/orders/<int:so_id>/deliver")
def api_deliver(so_id):
    """Xác nhận đơn đã giao tới khách & lưu e-POD."""
    d = request.get_json(silent=True) or {}
    epod = (d.get("epod_note") or "Khách đã ký nhận đủ kiện (e-POD)").strip()

    def work(con, i):
        so = con.execute("SELECT * FROM sos WHERE id=?", (i,)).fetchone()
        if not so or so["status"] != "shipping":
            raise ValueError("Đơn chưa xuất kho")
        on_t = 1 if day() <= so["due"] else 0
        con.execute("UPDATE sos SET status='delivered', on_time=?, epod_note=? WHERE id=?", (on_t, epod, i))
        audit(con, "shipping", "Hoàn tất giao hàng & e-POD", so["so_no"], f"{'Đúng hạn' if on_t else 'Trễ hạn'} — {epod}")
        if so["trip_id"]:
            left = con.execute("SELECT COUNT(*) FROM sos WHERE trip_id=? AND status!='delivered'", (so["trip_id"],)).fetchone()[0]
            if left == 0:
                con.execute("UPDATE trips SET status='completed' WHERE id=?", (so["trip_id"],))

    return run(work, so_id)
