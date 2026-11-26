"""Vai trò (role) và quyền. Nơi DUY NHẤT định nghĩa role nào được làm gì.

Thêm API mới thì phải khai báo ở PERMS, nếu không tests/test_roles.py sẽ báo lỗi.
Việc chặn nằm ở guard() trong wms/features/auth.py.
"""
ROLES = {
    "admin": "Quản trị",
    "inbound": "Nhập kho",
    "storage": "Lưu kho",
    "picking": "Soạn hàng",
    "shipping": "Xuất kho",
}
ALL = set(ROLES)

# quyền -> (mô tả, các role được dùng, các API thuộc quyền này)
PERMS = {
    "dash.view": ("Xem Tổng quan: chỉ số, cảnh báo", ALL, {"GET /api/dashboard"}),
    "chat.use": ("Hỏi trợ lý Kvis", ALL, {"GET /api/chat/status", "POST /api/chat"}),
    "sku.view": ("Xem danh mục SKU", ALL, {"GET /api/products"}),
    "sku.edit": ("Thêm, xóa SKU", {"admin"}, {"POST /api/products", "DELETE /api/products/<int:pid>"}),
    "po.view": ("Xem đơn mua (PO)", {"admin", "inbound", "storage"}, {"GET /api/pos"}),
    "po.create": ("Tạo đơn mua (PO)", {"admin"}, {"POST /api/pos"}),
    "po.receive": ("Nhận hàng vào kho theo lô", {"admin", "inbound"}, {"POST /api/pos/<int:po_id>/receive"}),
    "map.view": ("Xem sơ đồ kho 2D, 3D", {"admin", "inbound", "storage", "picking"}, {"GET /api/layout"}),
    "inv.view": ("Xem tồn kho theo lô, lịch sử giao dịch", {"admin", "inbound", "storage", "picking"}, {"GET /api/inventory"}),
    "inv.adjust": ("Điều chỉnh số lượng tồn", {"admin", "storage"}, {"POST /api/inventory/<int:bid>/adjust"}),
    "inv.export": ("Xuất file CSV tồn kho", {"admin", "storage"}, {"GET /api/export/inventory.csv"}),
    "so.view": ("Xem đơn bán và đội xe", {"admin", "picking", "shipping"}, {"GET /api/orders"}),
    "so.create": ("Tạo đơn bán", {"admin"}, {"POST /api/orders"}),
    "so.pick": ("Soạn hàng theo FEFO, soạn lại", {"admin", "picking"},
                {"POST /api/orders/<int:so_id>/pick", "POST /api/orders/<int:so_id>/unpick"}),
    "so.cancel": ("Hủy đơn bán chưa xuất kho", {"admin", "picking"}, {"POST /api/orders/<int:so_id>/cancel"}),
    "so.ship": ("Chọn xe và xuất kho", {"admin", "shipping"}, {"POST /api/orders/<int:so_id>/ship"}),
    "so.deliver": ("Xác nhận đã giao", {"admin", "shipping"}, {"POST /api/orders/<int:so_id>/deliver"}),
    "ana.view": ("Xem trang Phân tích", {"admin"}, {"GET /api/analytics"}),
}
PUBLIC = {"GET /api/me", "POST /api/login", "POST /api/logout"}   # API không cần đăng nhập
ANY = {"POST /api/password"}   # API chỉ cần đăng nhập, role nào cũng được
_BY_API = {a: p for p, (_, _, apis) in PERMS.items() for a in apis}


def perm_of(api):
    """Quyền cần có để gọi API (vd "POST /api/pos"); API chưa khai báo thì None."""
    return _BY_API.get(api)


def can(role, perm):
    """role có quyền perm không. Role hoặc quyền lạ thì từ chối."""
    return perm in PERMS and role in PERMS[perm][1]


def table():
    """Bảng quyền dạng Markdown cho docs/roles.md (chạy: python -m wms.roles)."""
    out = ["| Chức năng | " + " | ".join(ROLES.values()) + " |", "|---|" + ":---:|" * len(ROLES)]
    for text, who, _ in PERMS.values():
        out.append(f"| {text} | " + " | ".join("✓" if r in who else "" for r in ROLES) + " |")
    return "\n".join(out)


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    print(table())
