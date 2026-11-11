"""Feature: Soạn hàng - đơn bán và FEFO."""
from flask import Blueprint, jsonify, request

from ..core import do_pick, run
from ..db import db, day, rows

bp = Blueprint("picking", __name__)


@bp.get("/api/orders")
def api_orders():
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
    d = request.get_json()
    qty = int(d.get("qty") or 0)
    if qty <= 0 or not d.get("customer"):
        from ..db import bad
        return bad("Cần tên khách hàng và số lượng > 0")
    con = db()
    with con:
        n = con.execute("SELECT COUNT(*) FROM sos").fetchone()[0] + 1
        con.execute("INSERT INTO sos (so_no,customer,product_id,qty,due) VALUES (?,?,?,?,?)",
                    (f"SO-{n:03d}", d["customer"].strip(), int(d["product_id"]), qty, d.get("due") or day(1)))
    con.close()
    return jsonify(ok=True)


@bp.post("/api/orders/<int:so_id>/pick")
def api_pick(so_id):
    return run(do_pick, so_id)
