"""Lời dặn hệ thống (system prompt) cho Kvis và ảnh chụp nhanh số liệu kho cá nhân hóa theo Role.

Kvis tự động nhận diện vai trò đang đăng nhập để chỉ cung cấp số liệu đúng phạm vi quyền
(bảo mật tầng 2) và đưa ra đề xuất ưu tiên công việc phù hợp với bộ phận đó.
"""
from ..core import get_alerts, get_kpis, stock_by_sku
from ..db import rows
from ..roles import ROLES, can

ROLE_FOCUS = {
    "admin": "Quản lý toàn bộ kho: KPI tổng hợp, cảnh báo đa khu, điều phối liên phòng ban, đề xuất đặt hàng và tối ưu chi phí.",
    "inbound": "Bộ phận Nhập hàng (Inbound): rà soát PO/ASN, ưu tiên cờ đỏ hàng lạnh/HSD ngắn, xếp khung giờ Dock N1-N4, chuẩn bị mặt bằng QC và cấp thẻ cổng.",
    "storage": "Bộ phận Lưu trữ & Kiểm soát tồn kho (Storage): đề xuất vị trí Slotting (COI/Golden Zone/FEFO), dự báo nhu cầu & ROP, kiểm kê theo rủi ro, điều chuyển 2 đầu và xử lý hàng chậm luân chuyển (SLOB).",
    "picking": "Bộ phận Soạn hàng & Đóng gói (Picking): ưu tiên lấy hàng đúng FEFO, kiểm soát hạn dùng theo kênh khách hàng, xử lý đơn bị Xuất kho trả về và tối ưu lộ trình lấy hàng.",
    "shipping": "Bộ phận Xuất hàng & Giao vận (Shipping): đối chiếu 3 chiều (SO/Thực đóng/Chứng từ + % HSD kênh), ghép chuyến tối ưu LIFO 2D, chống sốc nhiệt Staging, quét mã QR lên xe và giám sát ETA/nhiệt độ thùng xe.",
}

SYSTEM = """Bạn là Kvis, trợ lý AI của hệ thống quản lý kho FMCG StockOps.

Quy tắc:
- Trả lời bằng tiếng Việt, ngắn gọn, đi thẳng vào ý chính và ưu tiên công việc theo đúng vai trò người dùng.
- Khung chat hiển thị chữ thường: KHÔNG dùng markdown (**, #, bảng). Liệt kê bằng "-" và xuống dòng.
- Chỉ dùng số liệu trong phần "SỐ LIỆU KHO HIỆN TẠI" bên dưới. Không bịa số.
  Nếu câu hỏi cần dữ liệu không thuộc quyền của người dùng hoặc chưa có ở đó, hãy nói rõ.
- Bạn KHÔNG thể tự thay đổi dữ liệu tồn kho (nguyên tắc AI gợi ý - con người quyết định).
  Hãy hướng dẫn người dùng xác nhận trên màn hình chức năng tương ứng.
- Đơn vị số lượng là "thùng"; tiền là đồng (VND).
- Hàng mát bảo quản 2-8°C, hàng đông -18°C trở xuống; xuất kho theo FEFO và chuẩn % HSD từng kênh."""


def snapshot(con, user=None):
    """Tóm tắt số liệu kho hiện tại lọc đúng theo vai trò và quyền của người đang đăng nhập."""
    role = user["role"] if user else "admin"
    name = user["name"] if user else "Quản trị"
    role_name = ROLES.get(role, role)

    lines = [
        f"NGƯỜI DÙNG ĐANG HỎI: {name} | Vai trò: {role_name} ({role})",
        f"TRỌNG TÂM HỖ TRỢ: {ROLE_FOCUS.get(role, '')}",
        "",
        "SỐ LIỆU KHO HIỆN TẠI (đã lọc theo quyền):",
    ]

    k = get_kpis(con)
    if role == "admin":
        lines.extend([
            f"- Giá trị tồn: {k['value']:,} đ; tổng {k['total']} thùng / sức chứa {k['cap']} ({k['cap_pct']}%)",
            f"- Tỉ lệ cận date: {k['near_pct']}%; giá trị hàng hết hạn: {k['expired_value']:,} đ",
            f"- OTIF: {k['otif']}%; tỉ lệ đáp ứng đơn: {k['fill']}%",
            f"- PO chờ nhận: {k['po_wait']}; đơn bán chưa giao xong: {k['so_open']}",
        ])
    else:
        lines.append(f"- Tổng tồn kho: {k['total']} thùng ({k['cap_pct']}% sức chứa); tỉ lệ cận date: {k['near_pct']}%")

    if can(role, "po.view"):
        pos = rows(con, """SELECT o.po_no, o.qty, o.eta, o.plan_status, o.priority, o.asn_no, p.sku
                           FROM pos o JOIN products p ON p.id=o.product_id WHERE o.status='pending' ORDER BY o.id""")
        lines.append("")
        lines.append(f"ĐƠN NHẬP CHỜ XỬ LÝ ({len(pos)}):")
        for o in pos[:10]:
            flag = "Cờ Đỏ" if o["priority"] == "urgent" else "Cờ Xanh"
            asn = o["asn_no"] or "THIẾU ASN"
            lines.append(f"- {o['po_no']} ({o['sku']}, {o['qty']} thùng, ETA {o['eta']}): bước={o['plan_status']}, {flag}, {asn}")

    if can(role, "inv.view"):
        lines.append("")
        lines.append("TỒN KHẢ DỤNG THEO SKU (lô còn hạn & đạt chất lượng):")
        for p in stock_by_sku(con):
            flag = " <- DƯỚI TỒN AN TOÀN" if p["av"] < p["safety"] else ""
            lines.append(f"- {p['sku']} {p['name']}: {p['av']} / {p['safety']}{flag}")

    if can(role, "so.view"):
        sos = rows(con, """SELECT s.so_no, s.customer, s.channel, s.min_shelf_pct, s.qty, s.due, s.status, s.audit_status, p.sku
                           FROM sos s JOIN products p ON p.id=s.product_id WHERE s.status!='delivered' ORDER BY s.id""")
        lines.append("")
        lines.append(f"ĐƠN XUẤT ĐANG MỞ ({len(sos)}):")
        for s in sos[:12]:
            lines.append(f"- {s['so_no']} ({s['customer']} - {s['channel']} ≥{s['min_shelf_pct']}% HSD): {s['sku']} x{s['qty']}, hạn {s['due']}, trạng thái={s['status']}, kiểm duyệt={s['audit_status']}")

    al = get_alerts(con)
    lines.append("")
    lines.append(f"CẢNH BÁO HIỆN TẠI ({len(al)}):" if al else "CẢNH BÁO: không có")
    for a in al[:12]:
        lines.append(f"- [{a['level']}] {a['msg']}")
    return "\n".join(lines)
