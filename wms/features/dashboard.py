"""Feature: Dashboard tổng quan vận hành."""
from flask import Blueprint, jsonify, request

from ..core import get_alerts, get_kpis, reorder, stock_by_sku, stock_status, zone_status
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
    zs = zone_status(con)   # sức chứa từng khu
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
    for r in reorder(con):   # số gợi ý đã trừ PO đang chờ nhận (xem core.reorder)
        if r["qty"]:
            wait = f", PO đang chờ {r['pending']}" if r["pending"] else ""
            tips.append({"title": f"Nên nhập thêm {r['sku']}",
                         "detail": f"Khả dụng {r['av']}, tồn an toàn {r['safety']}{wait}. Gợi ý đặt {r['qty']} thùng."})
        else:
            tips.append({"title": f"{r['sku']} đã có PO chờ nhận",
                         "detail": f"Khả dụng {r['av']}, dưới tồn an toàn {r['safety']}; PO đang chờ {r['pending']} thùng đã đủ bù."})
    if any(a["kind"] == "expiry" and a["level"] == "high" for a in al):
        tips.append({"title": "Có lô đã hết hạn", "detail": "Vào Tồn kho, điều chỉnh về 0 để hủy lô hết hạn."})
    if any(a["kind"] == "temp" for a in al):
        tips.append({"title": "Kiểm tra thiết bị làm lạnh", "detail": "Nhiệt độ ngoài ngưỡng có thể làm hỏng hàng."})
    acts = rows(con, """SELECT t.ts, t.kind, t.qty, t.note, p.sku FROM txs t JOIN products p ON p.id=t.product_id
                        ORDER BY t.id DESC LIMIT 6""")
    con.close()
    return jsonify(kpi=k, alerts=al, zones=zs, flow=flow, items=items, tips=tips[:5], acts=acts)
