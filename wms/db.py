"""Tiện ích database dùng chung cho mọi feature.

Mọi file trong wms/features/ đều import từ đây để mở kết nối, chạy truy vấn,
ghi sổ giao dịch... -> tránh lặp code, sửa 1 chỗ dùng mọi nơi.
"""
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path

from flask import jsonify

ROOT = Path(__file__).resolve().parent.parent   # thư mục dự án
DB = str(ROOT / "wms.db")   # file database SQLite, tự tạo ở lần chạy đầu; đường dẫn cố định nên chạy từ thư mục nào cũng ra cùng 1 file
BINS = 12       # số ô chứa (bin) trong mỗi khu kho
NEAR = 30       # còn <= 30 ngày tới hạn thì coi là "cận date"


def db():
    """Mở kết nối database. row_factory giúp đọc cột theo tên (vd r['sku'])."""
    con = sqlite3.connect(DB, timeout=5)   # đợi tối đa 5 giây nếu người khác đang ghi, thay vì báo lỗi ngay
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")   # WAL: đang ghi vẫn đọc được, nhiều người dùng cùng lúc ít bị khóa
    return con


def rows(con, sql, args=()):
    """Chạy câu SELECT và trả về danh sách dict (dễ đổi sang JSON)."""
    return [dict(r) for r in con.execute(sql, args)]


def day(n=0):
    """Ngày hôm nay cộng n ngày, dạng chữ 'YYYY-MM-DD'."""
    return (date.today() + timedelta(days=n)).isoformat()


def log(con, kind, pid, batch, qty, note, ts=None):
    """Ghi 1 dòng vào sổ giao dịch kho. kind: IN (nhập) | OUT (xuất) | ADJ (điều chỉnh)."""
    ts = ts or datetime.now().isoformat(timespec="seconds")
    con.execute("INSERT INTO txs (ts, kind, product_id, batch_no, qty, note) VALUES (?,?,?,?,?,?)",
                (ts, kind, pid, batch, qty, note))


def bad(msg, code=400):
    """Trả lỗi về cho giao diện kèm lời giải thích để người dùng đọc được."""
    return jsonify(error=msg), code
