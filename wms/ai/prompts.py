"""Lời dặn hệ thống (system prompt) cho Kvis và ảnh chụp nhanh số liệu kho.

- AGENT + agent_system(): lời dặn cho cách chính, Kvis tự gọi tool (wms/ai/tools.py) để tra số liệu.
- SYSTEM + snapshot(): đường lui khi model không gọi được tool (hoặc LLM_TOOLS=0): "chụp" số liệu
  hiện tại (KPI, cảnh báo, tồn theo SKU) rồi dán vào prompt. Đơn giản, nhưng chỉ hợp khi dữ liệu nhỏ.
"""
from ..core import get_alerts, get_kpis, stock_by_sku
from ..db import day
from ..roles import PERMS, ROLES, can
from .tools import TOOLS

AGENT = """Bạn là Kvis, trợ lý AI của hệ thống quản lý kho FMCG StockOps.

Quy tắc:
- Trả lời bằng tiếng Việt, ngắn gọn, đi thẳng vào ý chính.
- Khung chat hiển thị chữ thường: KHÔNG dùng markdown (**, #, bảng). Liệt kê bằng "-" và xuống dòng.
- Cần số liệu thì GỌI TOOL. Mọi con số trong câu trả lời phải lấy từ kết quả tool trong lượt này, không bịa, không đoán.
  Không có tool nào cho dữ liệu đó thì nói thẳng là bạn không tra được.
- Tool trả về lỗi "Không có quyền" thì nói rõ người dùng không có quyền xem dữ liệu đó. Không đoán số.
- Kết quả có "truncated": true là danh sách đã bị cắt bớt; muốn đủ thì gọi lại với tham số lọc (sku, zone, status...).
- Bạn KHÔNG thể tự thay đổi dữ liệu (nhập, xuất, điều chỉnh tồn, tạo PO). Nếu người dùng muốn,
  hãy hướng dẫn họ làm trên trang tương ứng: Nhập hàng, Tồn kho, Soạn hàng, Xuất kho.
- Đơn vị số lượng là "thùng"; tiền là đồng (VND).
- Hàng mát bảo quản 2-8°C, hàng đông -18°C trở xuống; xuất kho theo FEFO
  (lô hết hạn trước xuất trước)."""


def agent_system(user):
    """Lời dặn cho 1 người hỏi: thêm ngày hôm nay, tên, role và các nhóm dữ liệu role này KHÔNG được xem.
    Tool bị cấm đã bị giấu hẳn khỏi danh sách (tools.specs), nên phải nói ra ở đây thì Kvis mới biết
    "không tra được" là do quyền, để trả lời đúng thay vì nói chung chung."""
    role = user["role"]
    deny = [PERMS[p][0] for p in dict.fromkeys(t["perm"] for t in TOOLS.values()) if not can(role, p)]
    out = [AGENT, "", f"Hôm nay: {day()}. Người hỏi: {user['name']} (vai trò: {ROLES.get(role, role)})."]
    if deny:
        out.append("Role này KHÔNG được xem: " + "; ".join(deny) + ". Hỏi tới các dữ liệu đó thì trả lời là không có quyền xem.")
    return "\n".join(out)

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


def kpi_part(con):
    """Chỉ số chung (giống thẻ KPI trên Dashboard)."""
    k = get_kpis(con)
    return [
        f"- Giá trị tồn: {k['value']:,} đ; tổng {k['total']} thùng / sức chứa {k['cap']} ({k['cap_pct']}%)",
        f"- Tỉ lệ cận date: {k['near_pct']}%; giá trị hàng đã hết hạn: {k['expired_value']:,} đ",
        f"- OTIF: {k['otif']}%; tỉ lệ đáp ứng đơn: {k['fill']}%",
        f"- PO chờ nhận: {k['po_wait']}; đơn bán chưa giao xong: {k['so_open']}",
    ]


def stock_part(con):
    """Tồn khả dụng theo SKU (giống bảng "Tồn theo sản phẩm" trên Dashboard)."""
    out = ["TỒN KHẢ DỤNG THEO SKU (chỉ tính lô còn hạn; khả dụng / tồn an toàn):"]
    for p in stock_by_sku(con):
        flag = " <- DƯỚI TỒN AN TOÀN" if p["av"] < p["safety"] else ""
        out.append(f"- {p['sku']} {p['name']}: {p['av']} / {p['safety']}{flag}")
    return out


def alert_part(con):
    """Cảnh báo (giống khung "Cảnh báo" trên Dashboard), tối đa 15 dòng cho prompt gọn."""
    al = get_alerts(con)
    return [f"CẢNH BÁO ({len(al)}):" if al else "CẢNH BÁO: không có", *(f"- [{a['level']}] {a['msg']}" for a in al[:15])]


# Mỗi phần số liệu đưa cho Kvis kèm QUYỀN cần có để xem đúng phần đó ở nơi khác trong web.
# Thêm phần mới (vd tồn theo lô cần inv.view, danh sách PO cần po.view) thì PHẢI khai quyền ở đây,
# nếu không Kvis thành đường vòng qua phân quyền: hỏi chat thấy được thứ mà trang web chặn.
PARTS = [("dash.view", kpi_part), ("dash.view", stock_part), ("dash.view", alert_part)]


def snapshot(con, role):
    """Tóm tắt số liệu kho hiện tại thành đoạn chữ cho prompt, CHỈ gồm các phần role được xem (xem PARTS)."""
    parts = [fn(con) for perm, fn in PARTS if can(role, perm)]
    if not parts:
        return "SỐ LIỆU KHO HIỆN TẠI: tài khoản này không có quyền xem số liệu kho, hãy nói rõ điều đó nếu được hỏi."
    lines = ["SỐ LIỆU KHO HIỆN TẠI:"]
    for p in parts:
        lines += [*p, ""]
    return "\n".join(lines).rstrip()
