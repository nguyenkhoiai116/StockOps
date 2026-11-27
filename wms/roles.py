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
    "collab.use": ("Chat nội bộ và xem nhật ký thao tác liên phòng ban", ALL, {
        "GET /api/collab/audit", "GET /api/collab/messages", "POST /api/collab/messages",
    }),
    "sku.view": ("Xem danh mục SKU", ALL, {"GET /api/products"}),
    "sku.edit": ("Thêm, xóa SKU", {"admin"}, {"POST /api/products", "DELETE /api/products/<int:pid>"}),
    "po.view": ("Xem đơn mua (PO), kế hoạch nhập và biên bản từ chối tại Dock", {"admin", "inbound", "storage"}, {
        "GET /api/pos", "GET /api/pos/rejections",
    }),
    "po.create": ("Tạo đơn mua (PO) và tải file Excel/CSV PO", {"admin", "inbound", "storage"}, {
        "POST /api/pos", "POST /api/pos/parse",
    }),
    "po.receive": ("Lập kế hoạch ASN/Dock, cấp thẻ cổng, nhận hàng và từ chối tại Dock", {"admin", "inbound"}, {
        "POST /api/pos/<int:po_id>/asn",
        "POST /api/pos/<int:po_id>/validate",
        "POST /api/pos/<int:po_id>/schedule",
        "POST /api/pos/<int:po_id>/area-ready",
        "POST /api/pos/<int:po_id>/arrive",
        "POST /api/pos/<int:po_id>/receive",
        "POST /api/pos/<int:po_id>/reject",
    }),
    "map.view": ("Xem sơ đồ kho 2D, 3D", {"admin", "inbound", "storage", "picking"}, {"GET /api/layout"}),
    "inv.view": ("Xem tồn kho, phân tích Slotting/ROP/SLOB và gợi ý vị trí", {"admin", "inbound", "storage", "picking"}, {
        "GET /api/inventory", "GET /api/storage/intel", "POST /api/storage/slot-suggest",
    }),
    "inv.adjust": ("Điều chỉnh tồn, kiểm kê ABC/RCA, đổi QC và điều chuyển 2 đầu", {"admin", "storage"}, {
        "POST /api/inventory/<int:bid>/adjust",
        "POST /api/inventory/<int:bid>/quality",
        "POST /api/storage/transfers",
        "POST /api/storage/transfers/<int:tid>/confirm",
        "POST /api/storage/counts",
        "POST /api/storage/counts/<int:cid>/submit",
        "POST /api/storage/counts/<int:cid>/approve",
    }),
    "inv.export": ("Xuất file CSV tồn kho", {"admin", "storage"}, {"GET /api/export/inventory.csv"}),
    "so.view": ("Xem đơn bán, đội xe và bảng điều phối xuất", {"admin", "picking", "shipping"}, {
        "GET /api/orders", "GET /api/outbound/board",
    }),
    "so.create": ("Tạo đơn bán (SO) và bóc tách file đơn hàng", {"admin", "shipping"}, {
        "POST /api/orders", "POST /api/outbound/parse",
    }),
    "so.pick": ("Soạn hàng theo FEFO", {"admin", "picking"}, {"POST /api/orders/<int:so_id>/pick"}),
    "so.ship": ("Đối chiếu 3 chiều, ghép chuyến LIFO, xếp Dock, quét QR và xuất kho", {"admin", "shipping"}, {
        "POST /api/orders/<int:so_id>/ship",
        "POST /api/outbound/orders/<int:so_id>/audit",
        "POST /api/outbound/consolidate",
        "POST /api/outbound/trips/<int:tid>/safety-check",
        "POST /api/outbound/schedule-docks",
        "POST /api/outbound/trips/<int:tid>/start-load",
        "POST /api/outbound/trips/<int:tid>/scan",
        "POST /api/outbound/trips/<int:tid>/dispatch",
        "POST /api/outbound/staging/<int:so_id>/action",
    }),
    "so.deliver": ("Xác nhận đã giao (e-POD) và xử lý cảnh báo giao vận", {"admin", "shipping"}, {
        "POST /api/orders/<int:so_id>/deliver",
        "POST /api/outbound/trips/<int:tid>/alert",
    }),
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
