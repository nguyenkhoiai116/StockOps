"""Nạp dữ liệu mẫu có liên kết (cấu trúc bảng nằm ở wms/migrations/).

Muốn làm lại dữ liệu từ đầu: tắt server, xóa file wms.db, chạy lại.
"""
from .core import do_pick, do_ship
from .db import db, day, lock, log
from .migrate import migrate

# Tài khoản mẫu (tên người là giả). KHÔNG có mật khẩu sẵn, nên chưa đăng nhập được cho tới khi đặt mật khẩu.
USERS = [
    ("admin", "Phạm Quốc Huy", "admin"),
    ("nhap01", "Lê Thị Hạnh", "inbound"), ("nhap02", "Đỗ Minh Tuấn", "inbound"),
    ("luu01", "Vũ Đức Long", "storage"), ("luu02", "Ngô Thu Trang", "storage"),
    ("soan01", "Bùi Văn Khang", "picking"), ("soan02", "Hoàng Ngọc Mai", "picking"),
    ("xuat01", "Đặng Hữu Phước", "shipping"), ("xuat02", "Trịnh Kim Oanh", "shipping"),
]


def seed_users(con):
    """Nạp tài khoản mẫu khi bảng users còn trống."""
    with con:
        lock(con)   # kiểm "còn trống" và nạp trong cùng 1 transaction: 2 worker khởi động cùng lúc không nạp 2 lần
        if con.execute("SELECT COUNT(*) FROM users").fetchone()[0]:
            return
        con.executemany("INSERT OR IGNORE INTO users (username,name,role,created_at) VALUES (?,?,?,?)",
                        [(*u, day()) for u in USERS])


def init_db():
    """Tạo bảng; nạp dữ liệu mẫu chỉ khi database còn trống."""
    con = db()
    migrate(con)
    seed_users(con)
    with con:   # mọi lệnh bên trong là 1 transaction
        lock(con)   # nhiều worker khởi động cùng lúc: chỉ 1 worker nạp dữ liệu mẫu
        if not con.execute("SELECT COUNT(*) FROM products").fetchone()[0]:
            sample(con)
    con.close()


def sample(con):
    """Dữ liệu mẫu có liên kết: SKU, khu, lô, PO, đơn bán, xe, sổ giao dịch."""
    con.executemany("INSERT INTO products (sku,name,cat,unit,storage,price,safety,supplier) VALUES (?,?,?,?,?,?,?,?)", [
        ("SKU-001", "Mì gói tôm chua cay (thùng 30)", "Thực phẩm khô", "thùng", "dry", 115000, 200, "NCC Thực Phẩm Á Châu"),
        ("SKU-002", "Nước ngọt có ga 330ml (thùng 24)", "Đồ uống", "thùng", "dry", 190000, 150, "NCC Giải Khát Sài Gòn"),
        ("SKU-003", "Sữa chua có đường (thùng 48)", "Sữa", "thùng", "chilled", 260000, 100, "NCC Sữa Việt"),
        ("SKU-004", "Sữa tươi tiệt trùng 1L (thùng 12)", "Sữa", "thùng", "chilled", 380000, 200, "NCC Sữa Việt"),
        ("SKU-005", "Kem que socola (thùng 40)", "Đông lạnh", "thùng", "frozen", 310000, 80, "NCC Đông Lạnh Miền Nam"),
        ("SKU-006", "Há cảo đông lạnh 500g (thùng 20)", "Đông lạnh", "thùng", "frozen", 420000, 60, "NCC Đông Lạnh Miền Nam"),
        ("SKU-007", "Dầu gội 650ml (thùng 12)", "Hóa mỹ phẩm", "thùng", "cosmetics", 1450000, 50, "NCC Hóa Phẩm Xanh"),
        ("SKU-008", "Sữa tắm 850ml (thùng 12)", "Hóa mỹ phẩm", "thùng", "cosmetics", 1200000, 50, "NCC Hóa Phẩm Xanh"),
        ("SKU-009", "Nước mắm 750ml (thùng 12)", "Gia vị", "thùng", "dry", 560000, 80, "NCC Thực Phẩm Á Châu"),
        ("SKU-010", "Bánh quy bơ 400g (thùng 24)", "Bánh kẹo", "thùng", "dry", 240000, 100, "NCC Thực Phẩm Á Châu"),
    ])
    con.executemany("INSERT INTO zones (code,name,storage,cap,tmin,tmax,temp,hum,racks,bays,levels) VALUES (?,?,?,?,?,?,?,?,?,?,?)", [
        ("DRY", "Kho khô", "dry", 20000, 15, 30, 27.5, 60, 4, 6, 4),
        ("CHL", "Kho mát 2-8°C", "chilled", 3000, 2, 8, 9.1, 75, 2, 4, 3),      # 9.1°C: cố ý vượt ngưỡng để có cảnh báo
        ("FRZ", "Kho đông -18°C", "frozen", 2000, -25, -18, -18.6, 55, 2, 4, 3),
        ("COS", "Kho mỹ phẩm", "cosmetics", 6000, 15, 28, 24.0, 50, 3, 5, 4),
    ])
    con.executemany("INSERT INTO pos (po_no,product_id,qty,eta,status,recv) VALUES (?,?,?,?,?,?)", [
        ("PO-001", 4, 300, day(0), "pending", 0), ("PO-002", 7, 100, day(1), "pending", 0),
        ("PO-003", 1, 400, day(-6), "received", 400),   # đã nhận thành lô L2401 (xem bên dưới)
    ])
    con.executemany("INSERT INTO sos (so_no,customer,product_id,qty,due,status,plate,on_time) VALUES (?,?,?,?,?,?,?,?)", [
        ("SO-001", "Siêu thị An Phú", 1, 450, day(1), "new", None, None),      # cần 2 lô -> thấy FEFO chia lô
        ("SO-002", "Tạp hóa Minh Tâm", 3, 100, day(1), "new", None, None),
        ("SO-003", "Nhà hàng Biển Xanh", 6, 120, day(2), "new", None, None),   # thiếu hàng -> thấy bị từ chối
        ("SO-004", "Cửa hàng Bình Minh", 5, 40, day(1), "new", None, None),
        ("SO-005", "Siêu thị An Phú", 10, 60, day(0), "new", None, None),
        ("SO-006", "Đại lý Hòa Bình", 2, 100, day(-1), "delivered", "51C-123.45", 1),   # 3 đơn đã giao: history() soạn
        ("SO-007", "Tạp hóa Minh Tâm", 9, 50, day(-2), "delivered", "51C-123.45", 0),   # và xuất thật để có dòng OUT
        ("SO-008", "Mỹ phẩm Hoa Mai", 8, 30, day(-1), "delivered", "51C-123.45", 1),
    ])
    con.executemany("INSERT INTO vehicles VALUES (?,?,?)", [
        ("51C-123.45", "Nguyễn Văn An", "dry"), ("51D-678.90", "Trần Minh Bảo", "cold"),
    ])
    history(con)
    do_pick(con, 4)                 # SO-004: đã soạn (dùng đúng hàm nghiệp vụ -> số liệu khớp)
    do_pick(con, 5)
    do_ship(con, 5, "51C-123.45")   # SO-005: đang giao


def history(con):
    """6 ngày lịch sử mẫu, chạy THEO THỨ TỰ THỜI GIAN bằng đúng hàm nghiệp vụ, nên sổ txs khớp tồn từng lô:
    mỗi lô có 1 dòng IN lúc nhập; 3 đơn đã giao có dòng OUT thật (FEFO chọn lô).
    Số nhập đầu = tồn hiện tại + phần đã xuất cho 3 đơn cũ (L2403 +100, L2411 +30, L2412 +50)."""
    # (sản phẩm, số lô, hạn dùng sau n ngày, số nhập, khu, ô, nhập cách đây n ngày, ghi chú)
    lots = [
        (1, "L2401", 150, 400, "DRY", 1, 6, "Nhận PO-003 vào DRY-01"), (1, "L2402", 260, 500, "DRY", 2, 6, ""),
        (2, "L2403", 200, 700, "DRY", 3, 6, ""), (3, "L2404", 5, 60, "CHL", 1, 5, ""),
        (3, "L2405", 25, 120, "CHL", 2, 5, ""), (4, "L2406", 12, 120, "CHL", 3, 5, ""),
        (5, "L2407", 120, 150, "FRZ", 1, 4, ""), (6, "L2408", -3, 40, "FRZ", 2, 4, ""),
        (6, "L2409", 90, 100, "FRZ", 3, 4, ""), (7, "L2410", 400, 45, "COS", 1, 3, ""),
        (8, "L2411", 500, 150, "COS", 2, 3, ""), (9, "L2412", 300, 250, "DRY", 4, 3, ""),
        (10, "L2413", 20, 180, "DRY", 5, 2, ""),
    ]
    for pid, no, d, q, z, b, ago, note in lots:
        bid = con.execute("INSERT INTO batches (product_id,batch_no,exp,qty,zone,bin) VALUES (?,?,?,?,?,?)",
                          (pid, no, day(d), q, z, b)).lastrowid
        log(con, "IN", pid, no, q, note or f"Nhập kho vào {z}-{b:02d} (dữ liệu mẫu)", f"{day(-ago)}T08:30:00", bid=bid)
    # 3 đơn đã giao: soạn FEFO + xuất bằng hàm thật, rồi lùi giờ các dòng OUT về ngày xuất trong quá khứ
    for so_id, ago, on_time in [(7, 2, 0), (6, 1, 1), (8, 1, 1)]:   # SO-007 giao trễ để OTIF < 100%
        last = con.execute("SELECT COALESCE(MAX(id),0) FROM txs").fetchone()[0]
        con.execute("UPDATE sos SET status='new' WHERE id=?", (so_id,))
        do_pick(con, so_id)
        do_ship(con, so_id, "51C-123.45")
        con.execute("UPDATE sos SET status='delivered', on_time=? WHERE id=?", (on_time, so_id))
        con.execute("UPDATE txs SET ts=? WHERE id>?", (f"{day(-ago)}T14:00:00", last))
