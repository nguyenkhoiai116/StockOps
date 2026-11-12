"""Feature: Xuất kho & vận chuyển - chọn xe, giao hàng.

Lưu ý: đọc đơn hàng dùng chung API /api/orders của feature picking.
"""
from flask import Blueprint, request

from ..core import do_ship, run
from ..db import day

bp = Blueprint("shipping", __name__)


@bp.post("/api/orders/<int:so_id>/ship")
def api_ship(so_id):
    """Xuất kho 1 đơn đã soạn lên xe được chọn (xem core.do_ship)."""
    return run(do_ship, so_id, (request.get_json() or {}).get("plate"))


@bp.post("/api/orders/<int:so_id>/deliver")
def api_deliver(so_id):
    """Xác nhận đơn đã giao tới khách."""
    def work(con, i):
        """Chuyển đơn đang giao sang đã giao và ghi nhận đúng hạn / trễ hạn."""
        so = con.execute("SELECT * FROM sos WHERE id=?", (i,)).fetchone()
        if not so or so["status"] != "shipping":
            raise ValueError("Đơn chưa xuất kho")
        # Đúng hạn nếu giao trong hoặc trước ngày hẹn (dùng để tính OTIF)
        con.execute("UPDATE sos SET status='delivered', on_time=? WHERE id=?", (1 if day() <= so["due"] else 0, i))

    return run(work, so_id)
