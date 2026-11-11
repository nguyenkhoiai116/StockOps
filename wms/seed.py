"""Tạo bảng và nạp dữ liệu mẫu có liên kết.

Muốn làm lại dữ liệu từ đầu: tắt server, xóa file wms.db, chạy lại.
"""
from .core import do_pick, do_ship
from .db import db, day, log

# Cấu trúc các bảng. CHECK (qty>=0) để DB tự chặn tồn kho âm.
SCHEMA = """
CREATE TABLE IF NOT EXISTS products (
  id INTEGER PRIMARY KEY, sku TEXT UNIQUE NOT NULL, name TEXT NOT NULL, cat TEXT, unit TEXT,
  storage TEXT NOT NULL,            -- dry | chilled | frozen | cosmetics
  price INTEGER DEFAULT 0, safety INTEGER DEFAULT 0, supplier TEXT);
CREATE TABLE IF NOT EXISTS zones (
  code TEXT PRIMARY KEY, name TEXT, storage TEXT, cap INTEGER,
  tmin REAL, tmax REAL, temp REAL, hum REAL);
CREATE TABLE IF NOT EXISTS batches (
  id INTEGER PRIMARY KEY, product_id INTEGER REFERENCES products(id), batch_no TEXT, exp TEXT,
  qty INTEGER NOT NULL CHECK (qty >= 0),
  reserved INTEGER NOT NULL DEFAULT 0 CHECK (reserved >= 0 AND reserved <= qty),
  zone TEXT REFERENCES zones(code), bin INTEGER);
CREATE TABLE IF NOT EXISTS pos (
  id INTEGER PRIMARY KEY, po_no TEXT, product_id INTEGER REFERENCES products(id), qty INTEGER,
  eta TEXT, status TEXT DEFAULT 'pending', recv INTEGER DEFAULT 0, dmg INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS sos (
  id INTEGER PRIMARY KEY, so_no TEXT, customer TEXT, product_id INTEGER REFERENCES products(id),
  qty INTEGER, due TEXT, status TEXT DEFAULT 'new', plate TEXT, on_time INTEGER);
CREATE TABLE IF NOT EXISTS picks (
  id INTEGER PRIMARY KEY, so_id INTEGER REFERENCES sos(id), batch_id INTEGER REFERENCES batches(id), qty INTEGER);
CREATE TABLE IF NOT EXISTS vehicles (plate TEXT PRIMARY KEY, driver TEXT, kind TEXT);
CREATE TABLE IF NOT EXISTS txs (
  id INTEGER PRIMARY KEY, ts TEXT, kind TEXT, product_id INTEGER, batch_no TEXT, qty INTEGER, note TEXT);
"""


def init_db():
    """Tạo bảng; nạp dữ liệu mẫu chỉ khi database còn trống."""
    con = db()
    con.executescript(SCHEMA)
    if con.execute("SELECT COUNT(*) FROM products").fetchone()[0]:
        con.close()
        return
    with con:   # mọi lệnh bên trong là 1 transaction
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
        con.executemany("INSERT INTO zones VALUES (?,?,?,?,?,?,?,?)", [
            ("DRY", "Kho khô", "dry", 3000, 15, 30, 27.5, 60),
            ("CHL", "Kho mát 2-8°C", "chilled", 800, 2, 8, 9.1, 75),      # 9.1°C: cố ý vượt ngưỡng để có cảnh báo
            ("FRZ", "Kho đông -18°C", "frozen", 500, -25, -18, -18.6, 55),
            ("COS", "Kho mỹ phẩm", "cosmetics", 400, 15, 28, 24.0, 50),
        ])
        for pid, no, d, q, z, b in [
            (1, "L2401", 150, 400, "DRY", 1), (1, "L2402", 260, 500, "DRY", 2), (2, "L2403", 200, 600, "DRY", 3),
            (3, "L2404", 5, 60, "CHL", 1), (3, "L2405", 25, 120, "CHL", 2), (4, "L2406", 12, 120, "CHL", 3),
            (5, "L2407", 120, 150, "FRZ", 1), (6, "L2408", -3, 40, "FRZ", 2), (6, "L2409", 90, 100, "FRZ", 3),
            (7, "L2410", 400, 45, "COS", 1), (8, "L2411", 500, 120, "COS", 2),
            (9, "L2412", 300, 200, "DRY", 4), (10, "L2413", 20, 180, "DRY", 5),
        ]:
            con.execute("INSERT INTO batches (product_id,batch_no,exp,qty,zone,bin) VALUES (?,?,?,?,?,?)",
                        (pid, no, day(d), q, z, b))
        con.executemany("INSERT INTO pos (po_no,product_id,qty,eta,status,recv) VALUES (?,?,?,?,?,?)", [
            ("PO-001", 4, 300, day(0), "pending", 0), ("PO-002", 7, 100, day(1), "pending", 0),
            ("PO-003", 1, 400, day(-2), "received", 400),
        ])
        con.executemany("INSERT INTO sos (so_no,customer,product_id,qty,due,status,plate,on_time) VALUES (?,?,?,?,?,?,?,?)", [
            ("SO-001", "Siêu thị An Phú", 1, 450, day(1), "new", None, None),      # cần 2 lô -> thấy FEFO chia lô
            ("SO-002", "Tạp hóa Minh Tâm", 3, 100, day(1), "new", None, None),
            ("SO-003", "Nhà hàng Biển Xanh", 6, 120, day(2), "new", None, None),   # thiếu hàng -> thấy bị từ chối
            ("SO-004", "Cửa hàng Bình Minh", 5, 40, day(1), "new", None, None),
            ("SO-005", "Siêu thị An Phú", 10, 60, day(0), "new", None, None),
            ("SO-006", "Đại lý Hòa Bình", 2, 100, day(-1), "delivered", "51C-123.45", 1),
            ("SO-007", "Tạp hóa Minh Tâm", 9, 50, day(-2), "delivered", "51C-123.45", 0),
            ("SO-008", "Mỹ phẩm Hoa Mai", 8, 30, day(-1), "delivered", "51C-123.45", 1),
        ])
        con.executemany("INSERT INTO vehicles VALUES (?,?,?)", [
            ("51C-123.45", "Nguyễn Văn An", "dry"), ("51D-678.90", "Trần Minh Bảo", "cold"),
        ])
        for i, (a, b) in enumerate([(420, 310), (300, 380), (500, 290), (260, 410), (380, 350), (400, 180)]):
            ts = f"{day(i - 6)}T10:00:00"
            log(con, "IN", 1, "L24xx", a, "Nhập hàng (lịch sử mẫu)", ts)
            log(con, "OUT", 2, "L24xx", -b, "Xuất hàng (lịch sử mẫu)", ts)
        do_pick(con, 4)                 # SO-004: đã soạn (dùng đúng hàm nghiệp vụ -> số liệu khớp)
        do_pick(con, 5)
        do_ship(con, 5, "51C-123.45")   # SO-005: đang giao
    con.close()
