"""Feature: Dashboard tổng quan vận hành."""
from flask import Blueprint, jsonify

from ..core import get_alerts, get_kpis, stock_by_sku, zone_used
from ..db import db, day, rows

bp = Blueprint("dashboard", __name__)


@bp.get("/api/dashboard")
def api_dash():
    con = db()
    k = get_kpis(con)
    al = get_alerts(con)
    # Sức chứa từng khu
    zs = rows(con, "SELECT code, name, cap FROM zones")
    for z in zs:
        z["used"] = zone_used(con, z["code"])
        z["pct"] = round(z["used"] / z["cap"] * 100, 1)
    # Nhập/xuất 7 ngày gần nhất, cộng từ sổ giao dịch
    flow = []
    for i in range(-6, 1):
        d = day(i)
        s = lambda kd: abs(con.execute("SELECT COALESCE(SUM(qty),0) FROM txs WHERE kind=? AND substr(ts,1,10)=?", (kd, d)).fetchone()[0])
        flow.append({"day": d[8:] + "/" + d[5:7], "inb": s("IN"), "out": s("OUT")})
    # Gợi ý kiểu "AI" bằng luật if-then. Chỉ GỢI Ý, không tự thay đổi dữ liệu.
    tips = []
    for p in stock_by_sku(con):
        if p["av"] < p["safety"]:
            tips.append({"title": f"Nên nhập thêm {p['sku']}",
                         "detail": f"Khả dụng {p['av']}, tồn an toàn {p['safety']}. Gợi ý đặt {p['safety'] * 2 - p['av']} thùng."})
    if any(a["kind"] == "expiry" and a["level"] == "high" for a in al):
        tips.append({"title": "Có lô đã hết hạn", "detail": "Vào Tồn kho, điều chỉnh về 0 để hủy lô hết hạn."})
    if any(a["kind"] == "temp" for a in al):
        tips.append({"title": "Kiểm tra thiết bị làm lạnh", "detail": "Nhiệt độ ngoài ngưỡng có thể làm hỏng hàng."})
    acts = rows(con, """SELECT t.ts, t.kind, t.qty, t.note, p.sku FROM txs t JOIN products p ON p.id=t.product_id
                        ORDER BY t.id DESC LIMIT 6""")
    con.close()
    return jsonify(kpi=k, alerts=al, zones=zs, flow=flow, tips=tips[:5], acts=acts)
