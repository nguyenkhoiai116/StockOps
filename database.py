"""Quản lý database demo bằng dòng lệnh (chạy trong thư mục dự án):

  python database.py               xem tình trạng database
  python database.py backup        sao lưu wms.db vào thư mục backups/
  python database.py check         đối soát: sổ giao dịch có khớp tồn từng lô không, khóa ngoại có hỏng không
  python database.py reset         sao lưu rồi làm lại dữ liệu mẫu từ đầu, hỏi mật khẩu demo
  python database.py reset -y      như trên nhưng không hỏi xác nhận

Reset cần TẮT server trước (Ctrl+C), vì Windows không cho xóa file đang mở.
"""
import os
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

from wms import db as dbm
from wms.core import ledger_gaps
from wms.migrate import DIR
from wms.seed import init_db

BAK = dbm.ROOT / "backups"   # nơi chứa bản sao lưu, không đưa lên git
TABLES = ["products", "zones", "batches", "pos", "sos", "picks", "vehicles", "txs", "users"]


def latest():
    """Số migration mới nhất có trong wms/migrations/."""
    return max((int(f.name[:3]) for f in DIR.glob("[0-9][0-9][0-9]_*.sql")), default=0)


def status():
    path = Path(dbm.DB)
    if not path.exists():
        print(f"Chưa có database ({path}). Chạy: python database.py reset")
        return 0
    con = dbm.db()
    ver = con.execute("PRAGMA user_version").fetchone()[0]
    print(f"File:      {path}  ({path.stat().st_size // 1024} KB)")
    print(f"Migration: {ver}/{latest()}" + ("" if ver == latest() else "  -> chạy server 1 lần để cập nhật"))
    have = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    for t in TABLES:
        n = con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] if t in have else "-"
        print(f"  {t:<10} {n}")
    if "users" in have:
        no = con.execute("SELECT COUNT(*) FROM users WHERE pw_hash IS NULL").fetchone()[0]
        if no:
            print(f"{no} tài khoản chưa có mật khẩu -> python users.py passwd --moi")
    if ver == latest() and ledger_gaps(con):
        print("Sổ giao dịch lệch tồn kho -> xem: python database.py check")
    con.close()
    return 0


def check():
    """Đối soát: mỗi lô phải có SUM(txs.qty) = batches.qty; không có dòng nào vi phạm khóa ngoại."""
    if not Path(dbm.DB).exists():
        print("Chưa có database. Chạy: python database.py reset")
        return 1
    con = dbm.db()
    if con.execute("PRAGMA user_version").fetchone()[0] != latest():
        print("Database chưa cập nhật migration. Chạy server 1 lần rồi kiểm lại")
        con.close()
        return 1
    gaps, fk = ledger_gaps(con), con.execute("PRAGMA foreign_key_check").fetchall()
    for g in gaps:
        print(f"  Lô {g['batch_no']} (id {g['id']}): tồn {g['qty']}, sổ cộng ra {g['ledger']}")
    for r in fk:
        print(f"  Bảng {r[0]} dòng {r[1]} trỏ tới {r[2]} không tồn tại")
    loose = con.execute("SELECT COUNT(*) FROM txs WHERE batch_id IS NULL").fetchone()[0]
    con.close()
    if loose:
        print(f"  {loose} dòng sổ cũ không gắn được vào lô nào (dữ liệu trước migration 006)")
    if gaps or fk:
        print("Có chỗ lệch. Dữ liệu mẫu thì làm lại bằng: python database.py reset")
        return 1
    print("Sổ giao dịch khớp tồn từng lô, khóa ngoại không hỏng")
    return 0


def backup():
    """Sao lưu bằng backup API của SQLite: an toàn cả khi server đang chạy (WAL)."""
    if not Path(dbm.DB).exists():
        print("Chưa có database để sao lưu")
        return None
    BAK.mkdir(exist_ok=True)
    out = BAK / f"wms-{datetime.now():%Y%m%d-%H%M%S}.db"
    src, dst = sqlite3.connect(dbm.DB), sqlite3.connect(out)
    with dst:
        src.backup(dst)
    src.close()
    dst.close()
    print("Đã sao lưu:", out)
    return out


def reset(yes=False):
    if not yes and input("Xóa toàn bộ dữ liệu hiện tại và nạp lại dữ liệu mẫu? (y/N) ").strip().lower() != "y":
        print("Đã hủy")
        return 1
    backup()
    try:
        for suf in ("", "-wal", "-shm"):   # WAL tạo thêm 2 file phụ cạnh wms.db
            p = Path(dbm.DB + suf)
            if p.exists():
                os.remove(p)
    except PermissionError:
        print("Không xóa được wms.db vì server đang chạy. Tắt server (Ctrl+C) rồi chạy lại lệnh này.")
        return 1
    init_db()
    print("Đã tạo lại database với dữ liệu mẫu")
    return 0


def main(args):
    if not args:
        return status()
    if args[0] == "backup" and len(args) == 1:
        return 0 if backup() else 1
    if args[0] == "check" and len(args) == 1:
        return check()
    if args[0] == "reset" and args[1:] in ([], ["-y"]):
        if reset(yes=args[1:] == ["-y"]):
            return 1
        import users   # đặt chung 1 mật khẩu demo cho mọi tài khoản mẫu
        return users.main(["passwd", "--moi"])
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    sys.exit(main(sys.argv[1:]))
