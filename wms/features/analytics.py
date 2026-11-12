"""Feature: Phân tích - KPI và báo cáo tổng hợp."""
from flask import Blueprint, jsonify

from ..core import get_kpis, zone_used
from ..db import db, rows

bp = Blueprint("analytics", __name__)


@bp.get("/api/analytics")
def api_ana():
    """Số liệu trang Phân tích: KPI, giá trị tồn theo nhóm hàng, tồn theo SKU,
    số đơn theo trạng thái và % lấp đầy từng khu."""
    con = db()
    out = {
        "kpi": get_kpis(con),
        "by_cat": rows(con, """SELECT p.cat AS name, SUM(b.qty*p.price) AS val FROM batches b
                               JOIN products p ON p.id=b.product_id GROUP BY p.cat ORDER BY val DESC"""),
        "by_sku": rows(con, """SELECT p.sku || ' ' || p.name AS name, COALESCE(SUM(b.qty),0) AS val FROM products p
                               LEFT JOIN batches b ON b.product_id=p.id GROUP BY p.id ORDER BY val DESC"""),
        "by_status": rows(con, "SELECT status AS name, COUNT(*) AS val FROM sos GROUP BY status"),
        "by_zone": [{"name": z["name"], "val": round(zone_used(con, z["code"]) / z["cap"] * 100, 1)}
                    for z in rows(con, "SELECT * FROM zones")],
    }
    con.close()
    return jsonify(out)
