"""Chạy các file wms/migrations/NNN_*.sql chưa chạy, theo thứ tự số (xem ADR-007).

Số của file chạy cuối cùng được lưu trong PRAGMA user_version của database.
"""
from pathlib import Path

DIR = Path(__file__).parent / "migrations"


def migrate(con):
    """Mỗi file 1 transaction: lỗi giữa chừng thì hoàn tác cả file đó."""
    now = con.execute("PRAGMA user_version").fetchone()[0]
    for f in sorted(DIR.glob("[0-9][0-9][0-9]_*.sql")):
        n = int(f.name[:3])
        if n <= now:
            continue
        try:
            con.executescript(f"BEGIN IMMEDIATE;\n{f.read_text(encoding='utf-8')}\nPRAGMA user_version={n};\nCOMMIT;")
        except Exception:
            con.rollback()
            raise
