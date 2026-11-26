"""Tiện ích database dùng chung cho mọi feature.

Mọi file trong wms/features/ đều import từ đây để mở kết nối, chạy truy vấn,
ghi sổ giao dịch... -> tránh lặp code, sửa 1 chỗ dùng mọi nơi.
"""
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path

from flask import jsonify, request

ROOT = Path(__file__).resolve().parent.parent   # thư mục dự án
DB = str(ROOT / "wms.db")   # file database SQLite, tự tạo ở lần chạy đầu; đường dẫn cố định nên chạy từ thư mục nào cũng ra cùng 1 file
NEAR = 30       # còn <= 30 ngày tới hạn thì coi là "cận date"


def db():
    """Mở kết nối database. row_factory giúp đọc cột theo tên (vd r['sku'])."""
    con = sqlite3.connect(DB, timeout=5)   # đợi tối đa 5 giây nếu người khác đang ghi, thay vì báo lỗi ngay
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")   # WAL: đang ghi vẫn đọc được, nhiều người dùng cùng lúc ít bị khóa
    # Bật kiểm tra khóa ngoại (REFERENCES). SQLite mặc định TẮT và phải bật lại ở MỖI kết nối;
    # không có dòng này thì PO/đơn trỏ tới SKU không tồn tại vẫn ghi được rồi "biến mất" khỏi các danh sách JOIN.
    con.execute("PRAGMA foreign_keys=ON")
    return con


def lock(con):
    """Gọi ngay đầu khối `with con:` có ghi. Giữ quyền ghi từ trước khi đọc để kiểm tra,
    nên 2 request cùng lúc (vd bấm đúp) phải xếp hàng: request sau đọc được trạng thái mới.
    Không có dòng này, Python chỉ mở transaction ở lệnh ghi đầu tiên -> 2 bên cùng đọc số cũ."""
    con.execute("BEGIN IMMEDIATE")


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


def body():
    """Body JSON của request, luôn là dict. Body hỏng, rỗng hoặc không phải {...} (mảng, chuỗi, số)
    thì trả {} -> route kiểm tra thiếu trường và báo lỗi 400, không bao giờ nổ lỗi 500."""
    d = request.get_json(silent=True)
    return d if isinstance(d, dict) else {}


def as_int(v, label):
    """Đổi giá trị từ body sang số nguyên. Sai kiểu (chữ, mảng, True/False...) thì ValueError
    kèm lời giải thích; route bắt ValueError và trả 400 qua bad()."""
    if isinstance(v, bool) or not isinstance(v, (int, str)):
        raise ValueError(f"{label} phải là số nguyên")
    try:
        return int(v)
    except ValueError:
        raise ValueError(f"{label} phải là số nguyên") from None


def text(v):
    """Giá trị chữ từ body: số / mảng / None đều thành chuỗi gọn, tránh lỗi khi gọi .strip()."""
    return v.strip() if isinstance(v, str) else ""
