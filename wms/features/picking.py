"""Feature: Soạn hàng - đơn bán, phân loại kênh khách hàng, FEFO và lộ trình lấy hàng."""
from flask import Blueprint, jsonify, request

from ..core import audit, do_pick, run, stock_by_sku
from ..db import bad, day, db, rows
from ..outbound_ai import CHANNEL_INFO
from ..storage_ai import picking_route_suggest

bp = Blueprint("picking", __name__)


@bp.get("/api/orders")
def api_orders():
    """Danh sách đơn bán kèm các lô đã chọn cho từng đơn, đội xe, danh mục khách hàng và lộ trình lấy hàng."""
    con = db()
    out = rows(
        con,
        """SELECT s.*, p.sku, p.name, p.storage, p.shelf_days, p.price
           FROM sos s JOIN products p ON p.id=s.product_id ORDER BY s.id DESC""",
    )
    for o in out:
        o["picks"] = rows(
            con,
            """SELECT k.qty, b.batch_no, b.exp, b.zone, b.bin FROM picks k
               JOIN batches b ON b.id=k.batch_id WHERE k.so_id=?""",
            (o["id"],),
        )
    vs = rows(con, "SELECT * FROM vehicles")
    custs = rows(con, "SELECT * FROM customers ORDER BY name")
    routes = picking_route_suggest(con)
    con.close()
    return jsonify(orders=out, vehicles=vs, customers=custs, routes=routes)


@bp.post("/api/orders")
def api_order_add():
    """Tạo đơn bán mới (chặng 1A), tự nạp chuẩn % HSD kênh khách hàng và tùy chọn chặn tồn 100% từ cổng."""
    d = request.get_json(silent=True) or {}
    try:
        qty = int(d.get("qty") or 0)
        pid = int(d.get("product_id") or 0)
    except (TypeError, ValueError):
        return bad("Sản phẩm hoặc số lượng không hợp lệ")
    cust_name = str(d.get("customer") or "").strip()
    if qty <= 0 or pid <= 0 or not cust_name:
        return bad("Cần tên khách hàng, sản phẩm và số lượng > 0")
    con = db()
    p = con.execute("SELECT * FROM products WHERE id=?", (pid,)).fetchone()
    if not p:
        con.close()
        return bad("Sản phẩm không tồn tại")

    # Kiểm tra tồn khả dụng 100% ngay từ cổng khi tạo từ Outbound Intake (strict_stock)
    if d.get("strict_stock"):
        sk = next((x for x in stock_by_sku(con) if x["id"] == pid), None)
        av = sk["av"] if sk else 0
        if av < qty:
            con.close()
            return bad(f"Chặn ngay từ cổng (Rule 100%): {p['sku']} cần {qty} thùng nhưng khả dụng chỉ có {av} thùng")

    # Tra cứu phân loại khách hàng & chuẩn % HSD tối thiểu
    c_row = con.execute("SELECT * FROM customers WHERE name=?", (cust_name,)).fetchone()
    channel = (d.get("channel") or (c_row["channel"] if c_row else "taphoa")).strip()
    if channel not in CHANNEL_INFO:
        channel = "taphoa"
    min_pct = int(d.get("min_shelf_pct") or (c_row["min_shelf_pct"] if c_row else CHANNEL_INFO[channel]["min_shelf_pct"]))
    route_zone = (d.get("route_zone") or (c_row["route_zone"] if c_row else "Q1")).strip()

    with con:
        n = con.execute("SELECT COUNT(*) FROM sos").fetchone()[0] + 1
        so_no = f"SO-{n:03d}"
        con.execute(
            """INSERT INTO sos (so_no,customer,product_id,qty,due,channel,min_shelf_pct,route_zone)
               VALUES (?,?,?,?,?,?,?,?)""",
            (so_no, cust_name, pid, qty, d.get("due") or day(1), channel, min_pct, route_zone),
        )
        audit(con, "picking", "Tạo đơn bán (SO)", so_no,
              f"{cust_name} ({CHANNEL_INFO[channel]['name']}, ≥{min_pct}% HSD, tuyến {route_zone}): {qty} thùng {p['sku']}")
    con.close()
    return jsonify(ok=True, so_no=so_no)


@bp.post("/api/orders/<int:so_id>/pick")
def api_pick(so_id):
    """Soạn hàng cho 1 đơn theo FEFO (xem core.do_pick)."""
    return run(do_pick, so_id)
