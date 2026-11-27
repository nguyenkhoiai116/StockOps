"""Nạp dữ liệu mẫu có liên kết (cấu trúc bảng nằm ở wms/migrations/).

Muốn làm lại dữ liệu từ đầu: tắt server, xóa file wms.db, chạy lại.
"""
import json
from datetime import datetime, timedelta

from .core import do_pick, do_ship
from .db import db, day, log
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
    if con.execute("SELECT COUNT(*) FROM users").fetchone()[0]:
        return
    with con:
        con.executemany("INSERT OR IGNORE INTO users (username,name,role,created_at) VALUES (?,?,?,?)",
                        [(*u, day()) for u in USERS])


def init_db():
    """Tạo bảng; nạp dữ liệu mẫu chỉ khi database còn trống."""
    con = db()
    migrate(con)
    seed_users(con)
    if con.execute("SELECT COUNT(*) FROM products").fetchone()[0]:
        con.close()
        return
    now = datetime.now()
    t_iso = lambda mins: (now - timedelta(minutes=mins)).isoformat(timespec="seconds")
    with con:   # mọi lệnh bên trong là 1 transaction
        con.executemany(
            """INSERT INTO products
               (sku,name,cat,unit,storage,price,safety,supplier,shelf_days,weight_kg,vol_m3,fragile,lead_days)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            [
                ("SKU-001", "Mì gói tôm chua cay (thùng 30)", "Thực phẩm khô", "thùng", "dry", 115000, 200, "NCC Thực Phẩm Á Châu", 240, 4.5, 0.045, 1, 2),
                ("SKU-002", "Nước ngọt có ga 330ml (thùng 24)", "Đồ uống", "thùng", "dry", 190000, 150, "NCC Giải Khát Sài Gòn", 365, 9.2, 0.025, 0, 2),
                ("SKU-003", "Sữa chua có đường (thùng 48)", "Sữa", "thùng", "chilled", 260000, 100, "NCC Sữa Việt", 45, 6.0, 0.022, 1, 1),
                ("SKU-004", "Sữa tươi tiệt trùng 1L (thùng 12)", "Sữa", "thùng", "chilled", 380000, 200, "NCC Sữa Việt", 30, 12.6, 0.024, 0, 1),
                ("SKU-005", "Kem que socola (thùng 40)", "Đông lạnh", "thùng", "frozen", 310000, 80, "NCC Đông Lạnh Miền Nam", 120, 5.5, 0.032, 1, 2),
                ("SKU-006", "Há cảo đông lạnh 500g (thùng 20)", "Đông lạnh", "thùng", "frozen", 420000, 60, "NCC Đông Lạnh Miền Nam", 180, 10.5, 0.030, 0, 2),
                ("SKU-007", "Dầu gội 650ml (thùng 12)", "Hóa mỹ phẩm", "thùng", "cosmetics", 1450000, 50, "NCC Hóa Phẩm Xanh", 1095, 8.4, 0.026, 0, 3),
                ("SKU-008", "Sữa tắm 850ml (thùng 12)", "Hóa mỹ phẩm", "thùng", "cosmetics", 1200000, 50, "NCC Hóa Phẩm Xanh", 1095, 10.8, 0.028, 0, 3),
                ("SKU-009", "Nước mắm 750ml (thùng 12)", "Gia vị", "thùng", "dry", 560000, 80, "NCC Thực Phẩm Á Châu", 365, 11.0, 0.024, 1, 3),
                ("SKU-010", "Bánh quy bơ 400g (thùng 24)", "Bánh kẹo", "thùng", "dry", 240000, 100, "NCC Thực Phẩm Á Châu", 365, 5.2, 0.048, 1, 2),
            ],
        )
        con.executemany(
            "INSERT INTO zones (code,name,storage,cap,tmin,tmax,temp,hum,racks,bays,levels) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            [
                ("DRY", "Kho khô", "dry", 20000, 15, 30, 27.5, 60, 4, 6, 4),
                ("CHL", "Kho mát 2-8°C", "chilled", 3000, 2, 8, 9.1, 75, 2, 4, 3),      # 9.1°C: cố ý vượt ngưỡng để có cảnh báo
                ("FRZ", "Kho đông -18°C", "frozen", 2000, -25, -18, -18.6, 55, 2, 4, 3),
                ("COS", "Kho mỹ phẩm", "cosmetics", 6000, 15, 28, 24.0, 50, 3, 5, 4),
            ],
        )
        for pid, no, d, q, z, b in [
            (1, "L2401", 150, 400, "DRY", 1), (1, "L2402", 260, 500, "DRY", 2), (2, "L2403", 200, 600, "DRY", 3),
            (3, "L2404", 5, 60, "CHL", 1), (3, "L2405", 25, 120, "CHL", 2), (4, "L2406", 12, 120, "CHL", 3),
            (5, "L2407", 120, 150, "FRZ", 1), (6, "L2408", -3, 40, "FRZ", 2), (6, "L2409", 90, 100, "FRZ", 3),
            (7, "L2410", 400, 45, "COS", 1), (8, "L2411", 500, 120, "COS", 2),
            (9, "L2412", 300, 200, "DRY", 4), (10, "L2413", 20, 180, "DRY", 5),
        ]:
            con.execute(
                "INSERT INTO batches (product_id,batch_no,exp,qty,zone,bin,received_at) VALUES (?,?,?,?,?,?,?)",
                (pid, no, day(d), q, z, b, f"{day(-5)}T08:00:00"),
            )
        # PO mẫu kèm dữ liệu ASN cho quy trình Inbound CV1-CV4
        con.executemany(
            """INSERT INTO pos
               (po_no,product_id,qty,eta,status,recv,plan_status,asn_no,asn_uom,asn_exp,asn_batch,priority,need_qc,dock,slot_time,area_ready,gate_pass)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            [
                ("PO-001", 4, 300, day(0), "pending", 0, "draft", "ASN-2401", "thùng", day(28), "L2490", "urgent", 1, None, None, 0, None),
                ("PO-002", 7, 100, day(1), "pending", 0, "draft", None, "lốc", None, None, "standard", 0, None, None, 0, None),
                ("PO-003", 1, 400, day(-2), "received", 400, "received", "ASN-2400", "thùng", day(210), "L2402", "standard", 0, "N3", "08:00-09:00", 1, "GP-0003"),
            ],
        )
        # Đơn bán mẫu kèm kênh khách hàng (% HSD tối thiểu) và tuyến giao hàng
        con.executemany(
            """INSERT INTO sos
               (so_no,customer,product_id,qty,due,status,plate,on_time,channel,min_shelf_pct,route_zone,audit_status)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            [
                ("SO-001", "Siêu thị An Phú", 1, 450, day(1), "new", None, None, "sieuthi", 65, "Q1", "pending"),
                ("SO-002", "Tạp hóa Minh Tâm", 3, 100, day(1), "new", None, None, "taphoa", 40, "Q1", "pending"),
                ("SO-003", "Nhà hàng Biển Xanh", 6, 120, day(2), "new", None, None, "daily", 50, "Q1", "pending"),
                ("SO-004", "Cửa hàng Bình Minh", 5, 40, day(1), "new", None, None, "taphoa", 40, "Q3", "pending"),
                ("SO-005", "Siêu thị An Phú", 10, 60, day(0), "new", None, None, "sieuthi", 65, "Q1", "approved"),
                ("SO-006", "Đại lý Hòa Bình", 2, 100, day(-1), "delivered", "51C-123.45", 1, "daily", 50, "Q3", "approved"),
                ("SO-007", "Tạp hóa Minh Tâm", 9, 50, day(-2), "delivered", "51C-123.45", 0, "taphoa", 40, "Q1", "approved"),
                ("SO-008", "Mỹ phẩm Hoa Mai", 8, 30, day(-1), "delivered", "51C-123.45", 1, "daily", 50, "BinhThanh", "approved"),
                ("SO-009", "Siêu thị An Phú", 2, 80, day(1), "new", None, None, "sieuthi", 65, "Q1", "pending"),
                ("SO-010", "Tạp hóa Minh Tâm", 1, 90, day(1), "new", None, None, "taphoa", 40, "Q1", "pending"),
                ("SO-011", "Siêu thị Coop Q7", 10, 30, day(1), "new", None, None, "sieuthi", 65, "Q7", "pending"),
            ],
        )
        con.executemany(
            "INSERT INTO vehicles (plate,driver,kind,cap_qty,cap_kg,cap_m3,cost_trip) VALUES (?,?,?,?,?,?,?)",
            [
                ("51C-123.45", "Nguyễn Văn An", "dry", 400, 5000.0, 20.0, 1600000),
                ("51D-678.90", "Trần Minh Bảo", "cold", 260, 3500.0, 14.0, 2100000),
                ("51C-888.99", "Lê Hoàng Nam", "dry", 350, 4500.0, 18.0, 1500000),
                ("51E-246.80", "Phạm Thanh Tùng", "cold", 320, 4200.0, 16.0, 2300000),
            ],
        )
        # Lịch sử nhập/xuất 14 ngày gần nhất theo nhiều SKU để dự báo nhu cầu & FSN/ABC-XYZ có số liệu thật
        hist = [
            (1, 180, 130), (2, 140, 120), (3, 70, 55), (4, 150, 135),
            (5, 50, 42), (6, 40, 28), (10, 95, 70), (2, 160, 140),
            (1, 210, 165), (4, 170, 155), (3, 65, 60), (9, 45, 25),
            (1, 190, 145), (2, 150, 130),
        ]
        for i, (pid, a, b) in enumerate(hist):
            ts = f"{day(i - 13)}T10:00:00"
            log(con, "IN", pid, "L24xx", a, "Nhập hàng (lịch sử mẫu)", ts)
            log(con, "OUT", pid, "L24xx", -b, "Xuất hàng (lịch sử mẫu)", ts)

        # Soạn hàng và xuất hàng mẫu bằng đúng hàm nghiệp vụ lõi
        do_pick(con, 4)                 # SO-004: đã soạn (hàng đông lạnh chờ tại Staging)
        do_pick(con, 5)
        do_ship(con, 5, "51C-123.45")   # SO-005: đang giao
        do_pick(con, 9)                 # SO-009: đã soạn (đạt chuẩn Siêu thị, sẵn sàng ghép chuyến Q1)
        do_pick(con, 10)                # SO-010: đã soạn (cùng tuyến Q1 & kho khô với SO-009)
        do_pick(con, 11)                # SO-011: đã soạn (lô L2413 cận date -> ví dụ chặn HSD kênh siêu thị)

        # Gắn thời điểm chờ tại Staging cho SO-004 (16 phút trước) để demo đồng hồ chống sốc nhiệt
        con.execute("UPDATE sos SET staged_at=? WHERE id=4", (t_iso(16),))
        con.execute("UPDATE sos SET audit_status='approved' WHERE id IN (5, 9, 10)")

        # Tạo chuyến mẫu đang chạy cho SO-005 kèm chuỗi cảm biến nhiệt độ thùng xe (phân biệt mở cửa vs bất thường)
        tlog = [
            {"t": "08:00", "temp": 25.0, "event": "Xuất cổng", "anomaly": False},
            {"t": "08:20", "temp": 25.6, "event": "", "anomaly": False},
            {"t": "08:40", "temp": 28.4, "event": "Mở cửa dỡ hàng (An toàn)", "anomaly": False},
            {"t": "09:00", "temp": 26.2, "event": "Ổn định sau đóng cửa", "anomaly": False},
            {"t": "09:20", "temp": 27.9, "event": "", "anomaly": False},
            {"t": "09:40", "temp": 30.8, "event": "Bất thường nhiệt thùng tăng liên tục", "anomaly": True},
        ]
        con.execute(
            """INSERT INTO trips
               (trip_no,plate,route_zone,storage,dock,slot_start,slot_end,est_load_min,status,fill_pct,saved_vnd,eta_text,sla_risk_pct,temp_log_json,created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            ("TR-001", "51C-123.45", "Q1", "dry", "X3", "07:30", "08:10", 35, "in_transit", 42.0, 0,
             f"{day(0)} 10:25", 35, json.dumps(tlog, ensure_ascii=False), t_iso(95)),
        )
        tid = con.execute("SELECT id FROM trips WHERE trip_no='TR-001'").fetchone()[0]
        con.execute("UPDATE sos SET trip_id=? WHERE id=5", (tid,))

        # Nhật ký và tin nhắn nội bộ mẫu để các role thấy bối cảnh bàn giao ngay lần mở đầu
        con.executemany(
            "INSERT INTO audit_logs (ts,username,user_name,role,module,action,ref_no,detail) VALUES (?,?,?,?,?,?,?,?)",
            [
                (t_iso(120), "nhap01", "Lê Thị Hạnh", "inbound", "inbound", "Tiếp nhận chứng từ", "PO-001",
                 "Nhận PO-001 (300 thùng sữa tươi) kèm ASN-2401, gắn cờ đỏ ưu tiên chuỗi lạnh"),
                (t_iso(90), "luu01", "Vũ Đức Long", "storage", "inventory", "Cảnh báo môi trường", "CHL",
                 "Phát hiện Kho mát đang 9.1°C (vượt ngưỡng 2-8°C), đề xuất kiểm tra lốc lạnh"),
                (t_iso(50), "soan01", "Bùi Văn Khang", "picking", "picking", "Bàn giao khu Staging", "SO-004",
                 "Đã soạn xong 40 thùng Kem que (L2407) ra Khu 6 chờ xuất xe lạnh"),
                (t_iso(20), "xuat01", "Đặng Hữu Phước", "shipping", "shipping", "Duyệt chứng từ 3 chiều", "SO-009",
                 "SO-009 và SO-010 đạt 100% SL & chuẩn HSD kênh, sẵn sàng ghép chuyến Q1"),
            ],
        )
        con.executemany(
            "INSERT INTO team_messages (ts,sender_user,sender_name,sender_role,channel,ref_no,body) VALUES (?,?,?,?,?,?,?)",
            [
                (t_iso(110), "nhap01", "Lê Thị Hạnh", "inbound", "storage", "PO-001",
                 "PO-001 (300 thùng sữa tươi) về hôm nay, nhờ tổ Lưu trữ chuẩn bị trống khu CHL và khu QC nhé."),
                (t_iso(45), "soan01", "Bùi Văn Khang", "picking", "shipping", "SO-004",
                 "Đơn SO-004 (Kem que) đã đưa ra Staging Khu 6, nhờ tổ Xuất kho ưu tiên xe lạnh kẻo quá 20 phút."),
                (t_iso(15), "xuat01", "Đặng Hữu Phước", "shipping", "all", "SO-011",
                 "Mọi người lưu ý: SO-011 của Siêu thị Coop Q7 đang dính lô L2413 cận date dưới 65% HSD, cần kiểm tra hoán đổi lô."),
            ],
        )
    con.close()
