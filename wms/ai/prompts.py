"""Lời dặn hệ thống (system prompt) cho Kvis và ảnh chụp nhanh số liệu kho.

GIAI ĐOẠN TẠM: chưa có tool calling (Phase 5), nên mỗi câu hỏi ta "chụp" số liệu
hiện tại (KPI, cảnh báo, tồn theo SKU) rồi đưa vào prompt. Cách này đơn giản và
số liệu luôn mới, nhưng chỉ phù hợp khi dữ liệu nhỏ. Khi có tools, phần snapshot
sẽ được thay bằng các hàm agent tự gọi khi cần.
"""
from ..core import get_alerts, get_kpis, stock_by_sku

SYSTEM = """Bạn là Kvis, trợ lý AI của hệ thống quản lý kho FMCG StockOps.

Quy tắc:
- Trả lời bằng tiếng Việt, ngắn gọn, đi thẳng vào ý chính.
- Khung chat hiển thị chữ thường: KHÔNG dùng markdown (**, #, bảng). Liệt kê bằng "-" và xuống dòng.
- Chỉ dùng số liệu trong phần "SỐ LIỆU KHO HIỆN TẠI" bên dưới. Không bịa số.
  Nếu câu hỏi cần dữ liệu không có ở đó, nói rõ là bạn chưa xem được dữ liệu đó.
- Bạn KHÔNG thể tự thay đổi dữ liệu (nhập, xuất, điều chỉnh tồn). Nếu người dùng muốn,
  hãy hướng dẫn họ làm trên trang tương ứng: Nhập hàng, Tồn kho, Soạn hàng, Xuất kho.
- Đơn vị số lượng là "thùng"; tiền là đồng (VND).
- Hàng mát bảo quản 2-8°C, hàng đông -18°C trở xuống; xuất kho theo FEFO
  (lô hết hạn trước xuất trước)."""


def snapshot(con):
    """Tóm tắt số liệu kho hiện tại thành đoạn chữ ngắn để đưa vào prompt."""
    k = get_kpis(con)
    lines = [
        "SỐ LIỆU KHO HIỆN TẠI:",
        f"- Giá trị tồn: {k['value']:,} đ; tổng {k['total']} thùng / sức chứa {k['cap']} ({k['cap_pct']}%)",
        f"- Tỉ lệ cận date: {k['near_pct']}%; giá trị hàng đã hết hạn: {k['expired_value']:,} đ",
        f"- OTIF: {k['otif']}%; tỉ lệ đáp ứng đơn: {k['fill']}%",
        f"- PO chờ nhận: {k['po_wait']}; đơn bán chưa giao xong: {k['so_open']}",
        "",
        "TỒN KHẢ DỤNG THEO SKU (chỉ tính lô còn hạn; khả dụng / tồn an toàn):",
    ]
    for p in stock_by_sku(con):
        flag = " <- DƯỚI TỒN AN TOÀN" if p["av"] < p["safety"] else ""
        lines.append(f"- {p['sku']} {p['name']}: {p['av']} / {p['safety']}{flag}")
    al = get_alerts(con)
    lines.append("")
    lines.append(f"CẢNH BÁO ({len(al)}):" if al else "CẢNH BÁO: không có")
    for a in al[:15]:   # giới hạn 15 dòng cho prompt gọn
        lines.append(f"- [{a['level']}] {a['msg']}")
    return "\n".join(lines)
