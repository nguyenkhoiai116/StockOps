"""Nghiệp vụ lõi dùng chung: FEFO, xuất kho, cảnh báo, tính KPI.

Đây là "bộ não" của kho. Các feature chỉ gọi lại các hàm ở đây,
nhờ vậy quy tắc (vd không cho tồn âm) nằm 1 chỗ duy nhất.
"""
from datetime import date

from .db import NEAR, bad, day, db, log, rows


# ---------- Vị trí / sức chứa ----------
def zone_used(con, code):
    """Tổng số lượng đang nằm trong 1 khu kho."""
    return con.execute("SELECT COALESCE(SUM(qty),0) FROM batches WHERE zone=?", (code,)).fetchone()[0]


def free_bin(con, code, bins):
    """Tìm ô trống đầu tiên trong khu (ô đang có lô qty>0 là bận)."""
    used = {r[0] for r in con.execute("SELECT bin FROM batches WHERE zone=? AND qty>0", (code,))}
    return next((i for i in range(1, bins + 1) if i not in used), None)


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
    for pk in rows(con, "SELECT p.*, b.batch_no FROM picks p JOIN batches b ON b.id=p.batch_id WHERE so_id=?", (so_id,)):
        con.execute("UPDATE batches SET qty=qty-?, reserved=reserved-? WHERE id=?", (pk["qty"], pk["qty"], pk["batch_id"]))
        log(con, "OUT", so["product_id"], pk["batch_no"], -pk["qty"], f"Xuất cho {so['so_no']}")
    con.execute("UPDATE sos SET status='shipping', plate=? WHERE id=?", (plate, so_id))


# ---------- Tồn kho & chỉ số ----------
def stock_by_sku(con):
    """Tồn khả dụng theo sản phẩm (chỉ tính lô còn hạn)."""
    return rows(con, """SELECT p.id, p.sku, p.name, p.safety, p.price,
                               COALESCE(SUM(CASE WHEN b.exp>=? THEN b.qty-b.reserved END),0) AS av
                        FROM products p LEFT JOIN batches b ON b.product_id=p.id GROUP BY p.id""", (day(),))


def get_alerts(con):
    """Quét dữ liệu thật để sinh cảnh báo (không lưu sẵn, luôn khớp hiện trạng)."""
    out = []
    for z in rows(con, "SELECT * FROM zones"):
        if not z["tmin"] <= z["temp"] <= z["tmax"]:
            out.append({"kind": "temp", "level": "high",
                        "msg": f"{z['name']} đang {z['temp']}°C, ngoài ngưỡng {z['tmin']:g}..{z['tmax']:g}°C"})
        pct = zone_used(con, z["code"]) / z["cap"] * 100
        if pct >= 85:
            out.append({"kind": "cap", "level": "med", "msg": f"{z['name']} đã lấp đầy {pct:.0f}%"})
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
            out.append({"kind": "stock", "level": "high" if p["av"] < p["safety"] / 2 else "med",
                        "msg": f"{p['sku']} còn {p['av']} thùng khả dụng, dưới tồn an toàn ({p['safety']})"})
    order = {"high": 0, "med": 1, "low": 2}
    return sorted(out, key=lambda a: order[a["level"]])


def get_kpis(con):
    """Các chỉ số chung, dùng cho cả Dashboard và Phân tích."""
    one = lambda sql, a=(): con.execute(sql, a).fetchone()[0] or 0
    total = one("SELECT SUM(qty) FROM batches")
    cap = one("SELECT SUM(cap) FROM zones")
    near = one("SELECT SUM(qty) FROM batches WHERE exp>=? AND exp<=?", (day(), day(NEAR)))
    n_so = one("SELECT COUNT(*) FROM sos")
    done = one("SELECT COUNT(*) FROM sos WHERE status='delivered'")
    return {
        "value": one("SELECT SUM(b.qty*p.price) FROM batches b JOIN products p ON p.id=b.product_id"),
        "total": total, "cap": cap,
        "cap_pct": round(total / cap * 100, 1) if cap else 0,
        "near_pct": round(near / total * 100, 1) if total else 0,
        "otif": round(one("SELECT COUNT(*) FROM sos WHERE on_time=1") / done * 100, 1) if done else 0,
        "fill": round(one("SELECT COUNT(*) FROM sos WHERE status!='new'") / n_so * 100, 1) if n_so else 0,
        "po_wait": one("SELECT COUNT(*) FROM pos WHERE status='pending'"),
        "so_open": one("SELECT COUNT(*) FROM sos WHERE status!='delivered'"),
        "expired_value": one("SELECT SUM(b.qty*p.price) FROM batches b JOIN products p ON p.id=b.product_id WHERE b.exp<?", (day(),)),
    }


# ---------- Khung chạy nghiệp vụ trong transaction ----------
def run(fn, *args):
    """Chạy 1 nghiệp vụ trong 1 transaction.

    Lỗi nghiệp vụ (ValueError) -> tự hoàn tác và trả lời cho giao diện.
    Dùng chung cho các route: soạn hàng, xuất kho, điều chỉnh...
    """
    con = db()
    try:
        with con:              # with con = 1 transaction, lỗi thì rollback toàn bộ
            fn(con, *args)
    except ValueError as e:
        return bad(str(e))
    finally:
        con.close()
    from flask import jsonify
    return jsonify(ok=True)
