"""Feature: Dashboard tổng quan vận hành."""
from flask import Blueprint, jsonify, request

from ..core import get_alerts, get_kpis, stock_by_sku, stock_status, zone_used
from ..db import db, day, rows

bp = Blueprint("dashboard", __name__)


@bp.get("/api/dashboard")
def api_dash():
    """Số liệu Dashboard: KPI, cảnh báo, sức chứa từng khu, nhập/xuất ?days=7|14|30 ngày,
    tồn và trạng thái từng SKU, gợi ý xử lý và 6 giao dịch gần nhất."""
    n = request.args.get("days", 7, type=int)
    n = n if n in (7, 14, 30) else 7
    con = db()
    k = get_kpis(con)
    al = get_alerts(con)
    # Sức chứa từng khu
    zs = rows(con, "SELECT code, name, cap FROM zones")
    for z in zs:
        z["used"] = zone_used(con, z["code"])
        z["pct"] = round(z["used"] / z["cap"] * 100, 1)
    # Nhập/xuất n ngày gần nhất, cộng từ sổ giao dịch
    sums = {(r["d"], r["kind"]): abs(r["q"]) for r in rows(con, """
        SELECT substr(ts,1,10) AS d, kind, SUM(qty) AS q FROM txs WHERE substr(ts,1,10)>=? GROUP BY d, kind""", (day(1 - n),))}
    flow = []
    for i in range(1 - n, 1):
        d = day(i)
        flow.append({"day": d[8:] + "/" + d[5:7], "inb": sums.get((d, "IN"), 0), "out": sums.get((d, "OUT"), 0)})
    # Tồn từng SKU: thực có, khả dụng (chỉ lô còn hạn), các khu đang chứa, trạng thái
    have = {r["product_id"]: r for r in rows(con, """
        SELECT product_id, SUM(qty) AS qty, GROUP_CONCAT(DISTINCT zone) AS zones FROM batches WHERE qty>0 GROUP BY product_id""")}
    items = [{"sku": p["sku"], "name": p["name"], "av": p["av"], "safety": p["safety"],
              "qty": have[p["id"]]["qty"] if p["id"] in have else 0,
              "zones": have[p["id"]]["zones"].split(",") if p["id"] in have else [],
              "status": stock_status(p["av"], p["safety"])} for p in stock_by_sku(con)]
    # Gợi ý xử lý sinh theo luật if-then; chỉ để người dùng tham khảo, không tự thay đổi dữ liệu
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
    return jsonify(kpi=k, alerts=al, zones=zs, flow=flow, items=items, tips=tips[:5], acts=acts)
