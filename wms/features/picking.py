"""Feature: Soạn hàng - đơn bán và FEFO."""
from flask import Blueprint, jsonify

from ..core import create_so, do_pick, run
from ..db import as_int, bad, body, db, day, rows, text

bp = Blueprint("picking", __name__)


@bp.get("/api/orders")
def api_orders():
    """Danh sách đơn bán kèm các lô đã chọn cho từng đơn, và danh sách xe."""
    con = db()
    out = rows(con, """SELECT s.*, p.sku, p.name, p.storage FROM sos s JOIN products p ON p.id=s.product_id
                       ORDER BY s.id DESC""")
    for o in out:
        o["picks"] = rows(con, """SELECT k.qty, b.batch_no, b.exp, b.zone, b.bin FROM picks k
                                  JOIN batches b ON b.id=k.batch_id WHERE k.so_id=?""", (o["id"],))
    vs = rows(con, "SELECT * FROM vehicles")
    con.close()
    return jsonify(orders=out, vehicles=vs)


@bp.post("/api/orders")
def api_order_add():
    """Tạo đơn bán mới, tự đánh số SO-xxx; hạn giao mặc định là ngày mai."""
    d = body()   # body hỏng -> {} -> báo lỗi 400 thay vì lỗi 500
    try:
        pid, qty = as_int(d.get("product_id"), "Sản phẩm"), as_int(d.get("qty") or 0, "Số lượng")
    except ValueError as e:
        return bad(str(e))
    # run() khóa trước khi đếm số SO, nên 2 đơn tạo cùng lúc không trùng số; luật nằm ở core.create_so
    return run(create_so, pid, qty, text(d.get("customer")), text(d.get("due")) or day(1))


@bp.post("/api/orders/<int:so_id>/pick")
def api_pick(so_id):
    """Soạn hàng cho 1 đơn theo FEFO (xem core.do_pick)."""
    return run(do_pick, so_id)
