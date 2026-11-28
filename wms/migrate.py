"""Chạy các file wms/migrations/NNN_*.sql chưa chạy, theo thứ tự số (xem ADR-007).

Số của file chạy cuối cùng được lưu trong PRAGMA user_version của database.
"""
import sqlite3
from pathlib import Path

DIR = Path(__file__).parent / "migrations"

# Chạy ngay sau BEGIN IMMEDIATE (đã giữ khóa ghi): nếu user_version đã >= n thì INSERT vi phạm CHECK -> lỗi,
# cả transaction bị hoàn tác. Cần vì nhiều worker (gunicorn -w 2...) khởi động cùng lúc: worker sau đọc
# user_version cũ, chờ khóa, rồi chạy lại file mà worker trước vừa chạy xong (ALTER TABLE trùng cột -> chết).
GUARD = """CREATE TEMP TABLE _guard (ok INTEGER CHECK (ok = 1));
INSERT INTO _guard SELECT user_version < {n} FROM pragma_user_version;
DROP TABLE _guard;"""


def ver(con):
    return con.execute("PRAGMA user_version").fetchone()[0]


def run(con, f, n):
    """Chạy 1 file trong 1 transaction. Trả False nếu worker khác đã chạy file này rồi."""
    try:
        con.executescript(f"BEGIN IMMEDIATE;\n{GUARD.format(n=n)}\n{f.read_text(encoding='utf-8')}\n"
                          f"PRAGMA user_version={n};\nCOMMIT;")
        return True
    except sqlite3.IntegrityError:
        con.rollback()
        if ver(con) >= n:   # lỗi do GUARD: file đã chạy
            return False
        raise
    except Exception:
        con.rollback()
        raise


def migrate(con):
    """Mỗi file 1 transaction: lỗi giữa chừng thì hoàn tác cả file đó."""
    now = ver(con)
    for f in sorted(DIR.glob("[0-9][0-9][0-9]_*.sql")):
        n = int(f.name[:3])
        if n > now:
            run(con, f, n)
