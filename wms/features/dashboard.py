"""Feature: Dashboard tổng quan vận hành — cá nhân hóa gợi ý công việc theo từng vai trò (5 role)."""
from flask import Blueprint, g, jsonify, request

from ..core import get_alerts, get_kpis, stock_by_sku, stock_status, zone_used
from ..db import db, day, rows

bp = Blueprint("dashboard", __name__)


def _role_tips(con, role, al):
    """Gợi ý nhiệm vụ ưu tiên theo đúng vai trò đang đăng nhập."""
    tips = []
    if role in ("inbound", "admin"):
        no_asn = con.execute("SELECT COUNT(*) FROM pos WHERE status='pending' AND (asn_no IS NULL OR asn_exp IS NULL)").fetchone()[0]
        urg = con.execute("SELECT COUNT(*) FROM pos WHERE status='pending' AND priority='urgent'").fetchone()[0]
        if urg:
            tips.append({"title": f"[Nhập kho] {urg} PO Cờ Đỏ (hàng lạnh/HSD ngắn)", "detail": "Ưu tiên rà soát ASN, xếp cửa N1/N2 sát kho lạnh và đo nhiệt độ thùng xe trước khi dỡ."})
        if no_asn:
            tips.append({"title": f"[Nhập kho] {no_asn} PO thiếu ASN / HSD dự kiến", "detail": "Vào Nhập hàng → CV1 để bổ sung chứng từ NCC trước khi chốt Time-slot."})
    if role in ("storage", "admin"):
        if any(a["kind"] == "temp" for a in al):
            tips.append({"title": "[Lưu kho] Kiểm tra sự cố nhiệt độ kho lạnh", "detail": "Khu mát/đông đang vượt ngưỡng; cân nhắc chuyển lô bị ảnh hưởng sang trạng thái Chờ kiểm (Hold)."})
        if any(a["kind"] == "expiry" and a["level"] == "high" for a in al):
            tips.append({"title": "[Lưu kho] Có lô đã hết hạn cần xử lý", "detail": "Vào Tồn kho → CV5 (SLOB) hoặc Kiểm kê để lập biên bản hủy lô."})
        for p in stock_by_sku(con):
            if p["av"] < p["safety"]:
                tips.append({"title": f"[Lưu kho] Nên nhập thêm {p['sku']}", "detail": f"Khả dụng {p['av']}, tồn an toàn {p['safety']}. Xem ROP & gợi ý lượng đặt ở Tồn kho → CV2."})
                break
    if role in ("picking", "admin"):
        ret = con.execute("SELECT COUNT(*) FROM sos WHERE audit_status='returned'").fetchone()[0]
        new_n = con.execute("SELECT COUNT(*) FROM sos WHERE status='new'").fetchone()[0]
        if ret:
            tips.append({"title": f"[Soạn hàng] {ret} đơn bị Xuất kho trả về", "detail": "Kiểm tra lý do lệch % HSD kênh hoặc thiếu kiện để hoán đổi lô FEFO."})
        if new_n:
            tips.append({"title": f"[Soạn hàng] {new_n} đơn mới đang chờ soạn FEFO", "detail": "Lấy hàng khô trước, hàng mát/đông lạnh lấy sau cùng để giữ chuỗi lạnh."})
    if role in ("shipping", "admin"):
        pend_aud = con.execute("SELECT COUNT(*) FROM sos WHERE status='picked' AND audit_status='pending'").fetchone()[0]
        app_wait = con.execute("SELECT COUNT(*) FROM sos WHERE status='picked' AND audit_status='approved' AND trip_id IS NULL").fetchone()[0]
        if pend_aud:
            tips.append({"title": f"[Xuất kho] {pend_aud} đơn chờ đối chiếu 3 chiều", "detail": "Vào Xuất kho → Mục 1 kiểm tra đủ 100% SL, chuẩn % HSD kênh và phát hành bộ chứng từ QR."})
        if app_wait >= 2:
            tips.append({"title": f"[Xuất kho] {app_wait} đơn sẵn sàng ghép chuyến", "detail": "Chạy Ghép chuyến tự động để tăng Fill Rate và cắt giảm chi phí vận tải."})
    return tips[:6]


@bp.get("/api/dashboard")
def api_dash():
    """Số liệu Dashboard: KPI, cảnh báo, sức chứa từng khu, nhập/xuất ?days=7|14|30 ngày,
    tồn và trạng thái từng SKU, gợi ý xử lý theo role và 6 hoạt động gần nhất."""
    n = request.args.get("days", 7, type=int)
    n = n if n in (7, 14, 30) else 7
    role = g.user["role"] if getattr(g, "user", None) else "admin"
    con = db()
    k = get_kpis(con)
    al = get_alerts(con)
    zs = rows(con, "SELECT code, name, cap FROM zones")
    for z in zs:
        z["used"] = zone_used(con, z["code"])
        z["pct"] = round(z["used"] / z["cap"] * 100, 1)
    sums = {(r["d"], r["kind"]): abs(r["q"]) for r in rows(con, """
        SELECT substr(ts,1,10) AS d, kind, SUM(qty) AS q FROM txs WHERE substr(ts,1,10)>=? GROUP BY d, kind""", (day(1 - n),))}
    flow = []
    for i in range(1 - n, 1):
        d = day(i)
        flow.append({"day": d[8:] + "/" + d[5:7], "inb": sums.get((d, "IN"), 0), "out": sums.get((d, "OUT"), 0)})
    have = {r["product_id"]: r for r in rows(con, """
        SELECT product_id, SUM(qty) AS qty, GROUP_CONCAT(DISTINCT zone) AS zones FROM batches WHERE qty>0 GROUP BY product_id""")}
    items = [{"sku": p["sku"], "name": p["name"], "av": p["av"], "safety": p["safety"],
              "qty": have[p["id"]]["qty"] if p["id"] in have else 0,
              "zones": have[p["id"]]["zones"].split(",") if p["id"] in have else [],
              "status": stock_status(p["av"], p["safety"])} for p in stock_by_sku(con)]
    tips = _role_tips(con, role, al)
    acts = rows(con, """SELECT t.ts, t.kind, t.qty, t.note, p.sku FROM txs t JOIN products p ON p.id=t.product_id
                        ORDER BY t.id DESC LIMIT 6""")
    audits = rows(con, "SELECT ts, user_name, role, action, ref_no, detail FROM audit_logs ORDER BY id DESC LIMIT 6")
    con.close()
    return jsonify(kpi=k, alerts=al, zones=zs, flow=flow, items=items, tips=tips, acts=acts, audits=audits, role=role)
