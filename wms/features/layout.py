"""Feature: Sơ đồ kho - các khu, ô chứa, mức lấp đầy và luồng hàng (xe, đơn, cách ly)."""
from flask import Blueprint, g, jsonify

from ..core import zone_bins, zone_used
from ..db import db, day, rows
from ..roles import can

bp = Blueprint("layout", __name__)


def flow_of(con, role):
    """Luồng hàng quanh kho; mỗi phần chỉ có khi role có quyền xem (không có quyền thì bỏ hẳn key)."""
    f = {}
    if can(role, "po.view"):
        f["inbound"] = rows(con, """SELECT o.po_no, p.sku, o.qty, o.eta FROM pos o JOIN products p ON p.id=o.product_id
                                    WHERE o.status='pending' AND o.eta<=? ORDER BY o.eta, o.po_no""", (day(),))
    if can(role, "so.view"):
        so = """SELECT s.so_no, s.customer, p.sku, s.qty, s.due{} FROM sos s JOIN products p ON p.id=s.product_id
                WHERE s.status=? ORDER BY s.due, s.so_no"""
        f["topick"] = rows(con, so.format(""), ("new",))
        f["staged"] = rows(con, so.format(""), ("picked",))
        f["shipping"] = [{k: r[k] for k in ("so_no", "customer", "sku", "qty", "plate")}
                         for r in rows(con, so.format(", s.plate"), ("shipping",))]
        f["fleet"] = rows(con, """SELECT v.plate, v.driver, v.kind,
                                  EXISTS(SELECT 1 FROM sos s WHERE s.plate=v.plate AND s.status='shipping') AS busy
                                  FROM vehicles v ORDER BY v.plate""")
        for v in f["fleet"]:
            v["busy"] = bool(v["busy"])
    q = {"expired": rows(con, """SELECT b.batch_no, p.sku, b.zone, b.bin, b.qty, b.exp
                                 FROM batches b JOIN products p ON p.id=b.product_id
                                 WHERE b.exp<? AND b.qty>0 ORDER BY b.exp""", (day(),))}
    if can(role, "po.view"):
        q["dmg"] = rows(con, """SELECT o.po_no, p.sku, o.dmg FROM pos o JOIN products p ON p.id=o.product_id
                                WHERE o.status='received' AND o.dmg>0 ORDER BY o.po_no""")
    f["quarantine"] = q
    return f


@bp.get("/api/layout")
def api_layout():
    """Thông tin từng khu kho: kích thước kệ, sức chứa đã dùng, các ô đang có hàng, và luồng hàng theo quyền."""
    con = db()
    zs = rows(con, "SELECT * FROM zones")
    for z in zs:
        z["bins"] = zone_bins(z)   # tổng số ô (int)
        z["used"] = zone_used(con, z["code"])
        z["pct"] = round(z["used"] / z["cap"] * 100, 1)
        z["items"] = rows(con, """SELECT b.bin, b.batch_no, b.exp, b.qty, b.reserved, p.sku, p.name
                                  FROM batches b JOIN products p ON p.id=b.product_id
                                  WHERE b.zone=? AND b.qty>0""", (z["code"],))
    flow = flow_of(con, g.user["role"])
    con.close()
    return jsonify(zones=zs, today=day(), near=day(30), flow=flow)
