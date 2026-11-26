"""Feature: Nhập hàng - PO và nhận hàng theo lô."""
from flask import Blueprint, jsonify

from ..core import create_po, do_receive, run
from ..db import as_int, bad, body, day, db, rows, text

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
    """Nhận hàng: tạo lô mới, cất vào đúng khu nhiệt độ, kiểm tra sức chứa, cộng tồn (xem core.do_receive).
    Body: {batch_no, exp, qty, dmg, zone?}; zone bỏ trống = tự chọn khu còn trống nhiều nhất."""
    d = body()
    try:
        ok, dmg = as_int(d.get("qty") or 0, "Số lượng đạt"), as_int(d.get("dmg") or 0, "Số lượng hỏng")
    except ValueError as e:
        return bad(str(e))
    # run() khóa trước khi kiểm PO, nên bấm đúp không nhận 1 PO 2 lần
    return run(do_receive, po_id, text(d.get("batch_no")), text(d.get("exp")), ok, dmg, text(d.get("zone")) or None)
