"""Feature: Sơ đồ kho - các khu, ô chứa, mức lấp đầy."""
from flask import Blueprint, jsonify

from ..core import zone_used
from ..db import BINS, db, day, rows

bp = Blueprint("layout", __name__)


@bp.get("/api/layout")
def api_layout():
    con = db()
    zs = rows(con, "SELECT * FROM zones")
    for z in zs:
        z["used"] = zone_used(con, z["code"])
        z["pct"] = round(z["used"] / z["cap"] * 100, 1)
        z["bins"] = rows(con, """SELECT b.bin, b.batch_no, b.exp, b.qty, b.reserved, p.sku, p.name
                                 FROM batches b JOIN products p ON p.id=b.product_id
                                 WHERE b.zone=? AND b.qty>0""", (z["code"],))
    con.close()
    return jsonify(zones=zs, bins=BINS, today=day(), near=day(30))
