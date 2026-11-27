"""Chạy: python -m unittest tests.test_rules   (kiểm luật viết code trong CLAUDE.md, không cần database)

Luật: khối `with con:` có ghi phải gọi lock(con) ở dòng đầu, trước mọi câu đọc để kiểm tra.
Thiếu dòng này thì 2 request cùng lúc cùng đọc số cũ rồi cùng ghi (xem ADR-015, tests/test_race.py).
"""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FILES = [*sorted((ROOT / "wms").rglob("*.py")), ROOT / "database.py", ROOT / "users.py", ROOT / "app.py"]


def missing_lock():
    """Các chỗ `with con:` mà dòng code kế tiếp không phải lock(con), dạng 'file:dòng'."""
    bad = []
    for f in FILES:
        if not f.exists():
            continue
        lines = f.read_text(encoding="utf-8").splitlines()
        for i, s in enumerate(lines):
            if s.split("#")[0].strip() != "with con:":
                continue
            nxt = next((t.strip() for t in lines[i + 1:] if t.strip() and not t.strip().startswith("#")), "")
            if not nxt.startswith("lock(con)"):
                bad.append(f"{f.relative_to(ROOT).as_posix()}:{i + 1}")
    return bad


class RulesTest(unittest.TestCase):
    def test_moi_with_con_deu_goi_lock(self):
        bad = missing_lock()
        self.assertEqual(bad, [], "Khối `with con:` thiếu lock(con) ở dòng đầu: " + ", ".join(bad))


if __name__ == "__main__":
    unittest.main()
