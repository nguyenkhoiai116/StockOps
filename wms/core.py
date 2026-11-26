"""Nghiệp vụ lõi dùng chung: FEFO, xuất kho, cảnh báo, tính KPI.

Đây là "bộ não" của kho. Các feature chỉ gọi lại các hàm ở đây,
nhờ vậy quy tắc (vd không cho tồn âm) nằm 1 chỗ duy nhất.
"""
import sqlite3
from datetime import date

from .db import NEAR, bad, day, db, lock, log, rows


# ---------- Vị trí / sức chứa ----------
def zone_used(con, code):
    """Tổng số lượng đang nằm trong 1 khu kho."""
    return con.execute("SELECT COALESCE(SUM(qty),0) FROM batches WHERE zone=?", (code,)).fetchone()[0]


def zone_bins(z):
    """Số ô chứa của khu = số dãy kệ x số ô mỗi dãy x số tầng (z là dict hoặc Row)."""
    return z["racks"] * z["bays"] * z["levels"]


def free_bin(con, code):
    """Tìm ô trống đầu tiên trong khu (ô đang có lô qty>0 là bận); None nếu khu hết ô."""
    z = con.execute("SELECT racks, bays, levels FROM zones WHERE code=?", (code,)).fetchone()
    if not z:
        return None
    used = {r[0] for r in con.execute("SELECT bin FROM batches WHERE zone=? AND qty>0", (code,))}
    return next((i for i in range(1, zone_bins(z) + 1) if i not in used), None)


def zone_status(con):
    """Mọi khu kèm used (số thùng đang chứa), pct (% sức chứa) và bins (số ô).
    Nơi DUY NHẤT tính % lấp đầy: Dashboard, Sơ đồ kho, Phân tích, cảnh báo và Kvis đều gọi hàm này."""
    zs = rows(con, "SELECT * FROM zones")
    for z in zs:
        z["used"] = zone_used(con, z["code"])
        z["pct"] = round(z["used"] / z["cap"] * 100, 1) if z["cap"] else 0
        z["bins"] = zone_bins(z)
    return zs


def pick_zone(con, storage, qty, code=None):
    """Chọn chỗ cất lô mới: khu đúng loại kho (dry/chilled/frozen/cosmetics), còn đủ sức chứa, còn ô trống.
    Có nhiều khu hợp lệ (vd DRY và DRY2) thì chọn khu còn trống nhiều thùng nhất để chia đều tải.
    code: khu người dùng chỉ định (bỏ trống = tự chọn). Trả về (khu, số ô); không khu nào nhận được thì ValueError."""
    zs = [z for z in zone_status(con) if z["storage"] == storage and (not code or z["code"] == code)]
    if not zs:
        raise ValueError(f"Khu {code} không có hoặc không chứa được loại hàng này" if code
                         else "Chưa có khu nào chứa được loại hàng này")
    why = []
    for z in sorted(zs, key=lambda z: (z["used"] - z["cap"], z["code"])):   # còn trống nhiều nhất xếp trước
        if z["used"] + qty > z["cap"]:
            why.append(f"{z['name']} không đủ sức chứa cho {qty} thùng")
            continue
        b = free_bin(con, z["code"])
        if b is None:
            why.append(f"{z['name']} đã hết ô trống")
            continue
        return z, b
    raise ValueError("; ".join(why))


def do_receive(con, po_id, no, exp, ok, dmg, zone=None):
    """Nhận hàng cho 1 PO: tạo lô mới ở khu đúng nhiệt độ, kiểm sức chứa, cộng tồn và ghi sổ IN.
    ok: số thùng đạt (nhập kho), dmg: số thùng hỏng (ghi lên PO, không nhập kho)."""
    if ok <= 0 or dmg < 0 or not no:
        raise ValueError("Cần số lô và số lượng đạt > 0")
    if exp <= day():
        raise ValueError("Hạn dùng phải sau hôm nay (không nhận hàng hết hạn)")
    po = con.execute("SELECT o.*, p.storage FROM pos o JOIN products p ON p.id=o.product_id WHERE o.id=?",
                     (po_id,)).fetchone()
    if not po or po["status"] != "pending":
        raise ValueError("PO không tồn tại hoặc đã nhận")
    z, b = pick_zone(con, po["storage"], ok, zone)
    bid = con.execute("INSERT INTO batches (product_id,batch_no,exp,qty,zone,bin) VALUES (?,?,?,?,?,?)",
                      (po["product_id"], no, exp, ok, z["code"], b)).lastrowid
    con.execute("UPDATE pos SET status='received', recv=?, dmg=? WHERE id=?", (ok, dmg, po_id))
    log(con, "IN", po["product_id"], no, ok, f"Nhận {po['po_no']} vào {z['code']}-{b:02d}", bid=bid)


# ---------- FEFO & xuất kho ----------
def do_pick(con, so_id):
    """FEFO (First Expired, First Out): giữ hàng cho đơn, ưu tiên lô hết hạn sớm nhất.

    Bỏ qua lô đã hết hạn. Một đơn có thể chia ra nhiều lô. Thiếu hàng thì từ chối cả đơn.
    """
    so = con.execute("SELECT * FROM sos WHERE id=?", (so_id,)).fetchone()
    if not so or so["status"] != "new":
        raise ValueError("Đơn không tồn tại hoặc đã được soạn")
    bs = rows(con, """SELECT id, batch_no, qty - reserved AS av FROM batches
                      WHERE product_id=? AND exp>=? AND qty-reserved>0 ORDER BY exp, id""",
              (so["product_id"], day()))
    need, have = so["qty"], sum(b["av"] for b in bs)
    if have < need:
        raise ValueError(f"Không đủ hàng khả dụng: cần {need}, chỉ có {have} (đã loại lô hết hạn)")
    for b in bs:
        if need == 0:
            break
        take = min(need, b["av"])
        con.execute("UPDATE batches SET reserved=reserved+? WHERE id=?", (take, b["id"]))
        con.execute("INSERT INTO picks (so_id,batch_id,qty) VALUES (?,?,?)", (so_id, b["id"], take))
        need -= take
    con.execute("UPDATE sos SET status='picked' WHERE id=?", (so_id,))


def release(con, so_id):
    """Trả hàng đơn đang giữ về lô (reserved giảm) và đánh dấu các dòng picks là đã trả (released=1).
    Giữ bất biến: reserved của 1 lô = tổng picks còn hiệu lực (released=0) của các đơn 'picked'."""
    for pk in rows(con, "SELECT batch_id, qty FROM picks WHERE so_id=? AND released=0", (so_id,)):
        con.execute("UPDATE batches SET reserved=reserved-? WHERE id=?", (pk["qty"], pk["batch_id"]))
    con.execute("UPDATE picks SET released=1 WHERE so_id=? AND released=0", (so_id,))


def do_unpick(con, so_id):
    """Bỏ phần đã soạn để soạn lại theo FEFO (vd lô hết hạn trước khi kịp xuất): trả hàng giữ, đơn về 'new'."""
    so = con.execute("SELECT status FROM sos WHERE id=?", (so_id,)).fetchone()
    if not so or so["status"] != "picked":
        raise ValueError("Chỉ soạn lại được đơn đã soạn và chưa xuất kho")
    release(con, so_id)
    con.execute("UPDATE sos SET status='new' WHERE id=?", (so_id,))


def do_cancel(con, so_id):
    """Hủy đơn chưa xuất kho: đơn đã soạn thì trả hàng giữ về lô trước. Đơn đã xuất kho không hủy được."""
    so = con.execute("SELECT status FROM sos WHERE id=?", (so_id,)).fetchone()
    if not so or so["status"] not in ("new", "picked"):
        raise ValueError("Chỉ hủy được đơn chưa xuất kho")
    release(con, so_id)
    con.execute("UPDATE sos SET status='cancelled' WHERE id=?", (so_id,))


def do_ship(con, so_id, plate):
    """Xuất kho: kiểm tra xe phù hợp, trừ tồn thật (On Hand) và ghi sổ."""
    so = con.execute("SELECT s.*, p.storage FROM sos s JOIN products p ON p.id=s.product_id WHERE s.id=?",
                     (so_id,)).fetchone()
    v = con.execute("SELECT * FROM vehicles WHERE plate=?", (plate,)).fetchone()
    if not so or so["status"] != "picked":
        raise ValueError("Đơn chưa được soạn hàng")
    if not v:
        raise ValueError("Chưa chọn xe")
    if so["storage"] in ("chilled", "frozen") and v["kind"] != "cold":
        raise ValueError("Cảnh báo xếp hàng: hàng mát/đông lạnh phải đi xe lạnh")
    pks = rows(con, """SELECT p.*, b.batch_no, b.exp FROM picks p JOIN batches b ON b.id=p.batch_id
                       WHERE so_id=? AND p.released=0""", (so_id,))   # bỏ các lần soạn đã trả lại
    # Lô có thể hết hạn trong lúc đơn nằm chờ xuất (soạn hôm qua, xuất hôm nay) -> chặn, bắt soạn lại theo FEFO
    old = [pk["batch_no"] for pk in pks if pk["exp"] < day()]
    if old:
        raise ValueError(f"Lô {', '.join(old)} đã hết hạn sau khi soạn. Bấm 'Soạn lại' để chọn lô còn hạn theo FEFO")
    for pk in pks:
        con.execute("UPDATE batches SET qty=qty-?, reserved=reserved-? WHERE id=?", (pk["qty"], pk["qty"], pk["batch_id"]))
        log(con, "OUT", so["product_id"], pk["batch_no"], -pk["qty"], f"Xuất cho {so['so_no']}", bid=pk["batch_id"])
    con.execute("UPDATE sos SET status='shipping', plate=? WHERE id=?", (plate, so_id))


# ---------- Tồn kho & chỉ số ----------
def stock_by_sku(con):
    """Tồn khả dụng theo sản phẩm (chỉ tính lô còn hạn)."""
    return rows(con, """SELECT p.id, p.sku, p.name, p.safety, p.price,
                               COALESCE(SUM(CASE WHEN b.exp>=? THEN b.qty-b.reserved END),0) AS av
                        FROM products p LEFT JOIN batches b ON b.product_id=p.id GROUP BY p.id""", (day(),))


def stock_status(av, safety):
    """Trạng thái tồn: crit (hết hoặc dưới nửa tồn an toàn) | low (dưới tồn an toàn) | ok."""
    if av <= 0 or av < safety / 2:
        return "crit"
    return "low" if av < safety else "ok"


def reorder_qty(av, safety, pending=0):
    """Số thùng nên đặt: đưa tồn về gấp đôi tồn an toàn, trừ phần PO đang chờ nhận. Không âm."""
    return max(0, safety * 2 - av - pending)


def reorder(con):
    """SKU dưới tồn an toàn kèm PO đang chờ nhận và số nên đặt (qty = 0: PO đang chờ đã đủ bù).
    Dùng chung cho gợi ý trên Dashboard và câu hỏi "nên nhập gì?" của Kvis."""
    wait = {r["product_id"]: r["q"] for r in rows(
        con, "SELECT product_id, SUM(qty) AS q FROM pos WHERE status='pending' GROUP BY product_id")}
    out = []
    for p in stock_by_sku(con):
        if p["av"] < p["safety"]:
            n = wait.get(p["id"], 0)
            out.append({"sku": p["sku"], "name": p["name"], "av": p["av"], "safety": p["safety"],
                        "pending": n, "qty": reorder_qty(p["av"], p["safety"], n)})
    return out


def get_alerts(con):
    """Quét dữ liệu thật để sinh cảnh báo (không lưu sẵn, luôn khớp hiện trạng)."""
    out = []
    for z in zone_status(con):
        if not z["tmin"] <= z["temp"] <= z["tmax"]:
            out.append({"kind": "temp", "level": "high",
                        "msg": f"{z['name']} đang {z['temp']}°C, ngoài ngưỡng {z['tmin']:g}..{z['tmax']:g}°C"})
        if z["pct"] >= 85:
            out.append({"kind": "cap", "level": "med", "msg": f"{z['name']} đã lấp đầy {z['pct']:.0f}%"})
    for b in rows(con, """SELECT b.*, p.sku FROM batches b JOIN products p ON p.id=b.product_id
                          WHERE b.qty>0 AND b.exp<=? ORDER BY b.exp""", (day(NEAR),)):
        left = (date.fromisoformat(b["exp"]) - date.today()).days
        if left < 0:
            out.append({"kind": "expiry", "level": "high",
                        "msg": f"Lô {b['batch_no']} ({b['sku']}) ĐÃ HẾT HẠN {-left} ngày, còn {b['qty']} thùng"})
        else:
            out.append({"kind": "expiry", "level": "med",
                        "msg": f"Lô {b['batch_no']} ({b['sku']}) còn {left} ngày hết hạn"})
    for p in stock_by_sku(con):
        if p["av"] == 0:
            out.append({"kind": "stock", "level": "high", "msg": f"{p['sku']} {p['name']} HẾT HÀNG"})
        elif p["av"] < p["safety"]:
            out.append({"kind": "stock", "level": "high" if stock_status(p["av"], p["safety"]) == "crit" else "med",
                        "msg": f"{p['sku']} còn {p['av']} thùng khả dụng, dưới tồn an toàn ({p['safety']})"})
    order = {"high": 0, "med": 1, "low": 2}
    return sorted(out, key=lambda a: order[a["level"]])


def get_kpis(con):
    """Các chỉ số chung, dùng cho cả Dashboard và Phân tích."""
    one = lambda sql, a=(): con.execute(sql, a).fetchone()[0] or 0
    total = one("SELECT SUM(qty) FROM batches")
    cap = one("SELECT SUM(cap) FROM zones")
    near = one("SELECT SUM(qty) FROM batches WHERE exp>=? AND exp<=?", (day(), day(NEAR)))
    n_so = one("SELECT COUNT(*) FROM sos WHERE status!='cancelled'")   # đơn đã hủy không tính vào tỉ lệ đáp ứng
    done = one("SELECT COUNT(*) FROM sos WHERE status='delivered'")
    return {
        "value": one("SELECT SUM(b.qty*p.price) FROM batches b JOIN products p ON p.id=b.product_id"),
        "total": total, "cap": cap,
        "cap_pct": round(total / cap * 100, 1) if cap else 0,
        "near_pct": round(near / total * 100, 1) if total else 0,
        "otif": round(one("SELECT COUNT(*) FROM sos WHERE on_time=1") / done * 100, 1) if done else 0,
        "fill": round(one("SELECT COUNT(*) FROM sos WHERE status NOT IN ('new','cancelled')") / n_so * 100, 1) if n_so else 0,
        "po_wait": one("SELECT COUNT(*) FROM pos WHERE status='pending'"),
        "so_open": one("SELECT COUNT(*) FROM sos WHERE status NOT IN ('delivered','cancelled')"),
        "expired_value": one("SELECT SUM(b.qty*p.price) FROM batches b JOIN products p ON p.id=b.product_id WHERE b.exp<?", (day(),)),
    }


# ---------- Đặt hàng & điều chỉnh tồn ----------
# Hai hàm ghi này KHÔNG tự gọi lock(con): nơi gọi (core.run() hoặc nút xác nhận đề xuất của Kvis)
# giữ khóa, vì BEGIN IMMEDIATE không gọi lồng nhau được.
def create_po(con, pid, qty, eta):
    """Tạo PO chờ nhận, tự đánh số PO-xxx; trả về số PO."""
    if qty <= 0:
        raise ValueError("Số lượng phải lớn hơn 0")
    if not con.execute("SELECT 1 FROM products WHERE id=?", (pid,)).fetchone():
        raise ValueError("Sản phẩm không tồn tại")
    no = f"PO-{con.execute('SELECT COUNT(*) FROM pos').fetchone()[0] + 1:03d}"
    con.execute("INSERT INTO pos (po_no,product_id,qty,eta) VALUES (?,?,?,?)", (no, pid, qty, eta))
    return no


def create_so(con, pid, qty, customer, due):
    """Tạo đơn bán mới, tự đánh số SO-xxx; trả về số SO. Chưa giữ hàng (giữ hàng ở do_pick)."""
    if qty <= 0 or not customer:
        raise ValueError("Cần tên khách hàng và số lượng > 0")
    if not con.execute("SELECT 1 FROM products WHERE id=?", (pid,)).fetchone():
        raise ValueError("Sản phẩm không tồn tại")
    no = f"SO-{con.execute('SELECT COUNT(*) FROM sos').fetchone()[0] + 1:03d}"
    con.execute("INSERT INTO sos (so_no,customer,product_id,qty,due) VALUES (?,?,?,?,?)", (no, customer, pid, qty, due))
    return no


def do_adjust(con, bid, delta, note):
    """Điều chỉnh tồn 1 lô (kiểm kê lệch, hàng vỡ, hủy lô); delta âm = giảm.
    Luật: không âm, không thấp hơn phần đã giữ cho đơn, không vượt sức chứa khu."""
    b = con.execute("SELECT b.*, z.cap, z.name AS zname FROM batches b JOIN zones z ON z.code=b.zone WHERE b.id=?",
                    (bid,)).fetchone()
    if not b or delta == 0:
        raise ValueError("Không có gì để điều chỉnh")
    new = b["qty"] + delta
    if new < 0:
        raise ValueError("Không cho phép tồn kho âm")
    if new < b["reserved"]:
        raise ValueError(f"Lô đang giữ {b['reserved']} thùng cho đơn hàng, không giảm thấp hơn được")
    if delta > 0 and zone_used(con, b["zone"]) + delta > b["cap"]:
        raise ValueError(f"{b['zname']} không đủ sức chứa")
    # Lô đã về 0 thì ô của nó đã được coi là trống và có thể đã cấp cho lô khác -> không cho "hồi sinh" vào ô đó
    if b["qty"] == 0 and delta > 0 and con.execute(
            "SELECT 1 FROM batches WHERE zone=? AND bin=? AND qty>0 AND id!=?", (b["zone"], b["bin"], bid)).fetchone():
        raise ValueError(f"Ô {b['zone']}-{b['bin']:02d} đã có lô khác. Lô đã về 0 không tăng lại được, hãy nhận hàng thành lô mới")
    con.execute("UPDATE batches SET qty=? WHERE id=?", (new, bid))
    log(con, "ADJ", b["product_id"], b["batch_no"], delta, note, bid=bid)


def ledger_gaps(con):
    """Đối soát sổ giao dịch với tồn: các lô có SUM(txs.qty) khác batches.qty. Rỗng = sổ khớp.
    Dùng cho test và lệnh `python database.py check`."""
    return rows(con, """SELECT b.id, b.batch_no, b.qty, COALESCE(SUM(t.qty), 0) AS ledger
                        FROM batches b LEFT JOIN txs t ON t.batch_id = b.id
                        GROUP BY b.id HAVING b.qty != COALESCE(SUM(t.qty), 0) ORDER BY b.id""")


# ---------- Khung chạy nghiệp vụ trong transaction ----------
def run(fn, *args):
    """Chạy 1 nghiệp vụ trong 1 transaction.

    Lỗi nghiệp vụ (ValueError) -> tự hoàn tác và trả lời cho giao diện.
    Dùng chung cho các route: soạn hàng, xuất kho, điều chỉnh...
    """
    con = db()
    try:
        with con:              # with con = 1 transaction, lỗi thì rollback toàn bộ
            lock(con)
            fn(con, *args)
    except ValueError as e:
        return bad(str(e))
    except sqlite3.IntegrityError:   # DB tự chặn (vd tồn âm) -> báo dễ hiểu thay vì lỗi 500
        return bad("Dữ liệu vừa thay đổi, hãy tải lại trang rồi thử lại", 409)
    finally:
        con.close()
    from flask import jsonify
    return jsonify(ok=True)
