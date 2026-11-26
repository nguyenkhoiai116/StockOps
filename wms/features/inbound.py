"""Feature: Nhập hàng - PO và nhận hàng theo lô."""
from flask import Blueprint, jsonify

from ..core import create_po, free_bin, run, zone_used
from ..db import as_int, bad, body, day, db, lock, log, rows, text

bp = Blueprint("inbound", __name__)


@bp.get("/api/pos")
def api_pos():
    """Danh sách PO kèm thông tin sản phẩm; PO đang chờ nhận xếp lên trước."""
    con = db()
    out = rows(con, """SELECT o.*, p.sku, p.name, p.supplier, p.storage FROM pos o
                       JOIN products p ON p.id=o.product_id ORDER BY o.status DESC, o.id DESC""")
    con.close()
    return jsonify(out)


@bp.post("/api/pos")
def api_po_add():
    """Tạo PO mới, tự đánh số PO-xxx; ngày đến mặc định là ngày mai."""
    d = body()   # body hỏng -> {} -> báo lỗi 400 thay vì lỗi 500
    try:
        pid, qty = as_int(d.get("product_id"), "Sản phẩm"), as_int(d.get("qty") or 0, "Số lượng")
    except ValueError:
        return bad("Cần chọn sản phẩm và nhập số lượng")
    # run() khóa trước khi đếm số PO, nên 2 PO tạo cùng lúc không trùng số; luật nằm ở core.create_po
    return run(create_po, pid, qty, text(d.get("eta")) or day(1))


@bp.post("/api/pos/<int:po_id>/receive")
def api_po_receive(po_id):
    """Nhận hàng: tạo lô mới, cất vào đúng khu nhiệt độ, kiểm tra sức chứa, cộng tồn."""
    d = body()
    try:
        ok, dmg = as_int(d.get("qty") or 0, "Số lượng đạt"), as_int(d.get("dmg") or 0, "Số lượng hỏng")
    except ValueError as e:
        return bad(str(e))
    exp, no = text(d.get("exp")), text(d.get("batch_no"))
    if ok <= 0 or dmg < 0 or not no:
        return bad("Cần số lô và số lượng đạt > 0")
    if exp <= day():
        return bad("Hạn dùng phải sau hôm nay (không nhận hàng hết hạn)")
    con = db()
    try:
        with con:
            lock(con)   # khóa trước khi kiểm PO, để bấm đúp không nhận 1 PO 2 lần
            po = con.execute("SELECT o.*, p.storage FROM pos o JOIN products p ON p.id=o.product_id WHERE o.id=?",
                             (po_id,)).fetchone()
            if not po or po["status"] != "pending":
                raise ValueError("PO không tồn tại hoặc đã nhận")
            z = con.execute("SELECT * FROM zones WHERE storage=?", (po["storage"],)).fetchone()  # đúng vùng nhiệt
            if zone_used(con, z["code"]) + ok > z["cap"]:
                raise ValueError(f"{z['name']} không đủ sức chứa cho {ok} thùng")
            b = free_bin(con, z["code"])
            if b is None:
                raise ValueError(f"{z['name']} đã hết ô trống")
            bid = con.execute("INSERT INTO batches (product_id,batch_no,exp,qty,zone,bin) VALUES (?,?,?,?,?,?)",
                              (po["product_id"], no, exp, ok, z["code"], b)).lastrowid
            con.execute("UPDATE pos SET status='received', recv=?, dmg=? WHERE id=?", (ok, dmg, po_id))
            log(con, "IN", po["product_id"], no, ok, f"Nhận {po['po_no']} vào {z['code']}-{b:02d}", bid=bid)
    except ValueError as e:
        return bad(str(e))
    finally:
        con.close()
    return jsonify(ok=True)
