"""Nạp dữ liệu mẫu từ các file CSV trong thư mục data/ (cấu trúc bảng nằm ở wms/migrations/).

Dữ liệu mẫu KHÔNG viết trong code nữa. Muốn đổi: mở file trong data/ bằng Excel, sửa, lưu kiểu CSV UTF-8,
rồi chạy  python database.py reset  (xem data/README.md).
"""
from . import csvdb
from .db import db, lock
from .migrate import migrate


def init_db():
    """Tạo bảng; database chưa có sản phẩm hoặc chưa có tài khoản thì nạp các bảng còn trống từ data/*.csv."""
    con = db()
    try:
        migrate(con)
        with con:   # 1 transaction: file CSV nào lỗi thì hoàn tác hết, không nạp dở dang
            lock(con)   # nhiều worker khởi động cùng lúc: chỉ 1 worker nạp dữ liệu mẫu
            if not all(con.execute(f"SELECT 1 FROM {t} LIMIT 1").fetchone() for t in ("products", "users")):
                csvdb.load(con)
    finally:
        con.close()
