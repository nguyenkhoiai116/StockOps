"""Chạy: python -m unittest tests.test_migrate   (nhiều worker khởi động cùng lúc, dùng database tạm)"""
import os
import shutil
import sqlite3
import tempfile
import threading
import unittest

from wms.migrate import DIR, migrate, run


def connect(path):
    return sqlite3.connect(path, timeout=10)


class MigrateTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.path = os.path.join(self.tmp, "test.db")
        self.last = sorted(DIR.glob("[0-9][0-9][0-9]_*.sql"))[-1]
        self.top = int(self.last.name[:3])

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_file_da_chay_thi_bo_qua(self):
        # Worker B đọc user_version cũ, chờ khóa; worker A chạy xong file rồi -> B phải bỏ qua, không chạy lại
        con = connect(self.path)
        migrate(con)
        self.assertFalse(run(con, self.last, self.top))
        self.assertEqual(con.execute("PRAGMA user_version").fetchone()[0], self.top)
        con.close()

    def test_nhieu_worker_cung_luc(self):
        errs = []

        def go():
            con = connect(self.path)
            try:
                migrate(con)
            except Exception as e:   # gom lỗi lại để thread chính kiểm
                errs.append(e)
            finally:
                con.close()

        ts = [threading.Thread(target=go) for _ in range(4)]
        for t in ts:
            t.start()
        for t in ts:
            t.join()
        self.assertEqual(errs, [])
        con = connect(self.path)
        self.assertEqual(con.execute("PRAGMA user_version").fetchone()[0], self.top)
        con.close()


if __name__ == "__main__":
    unittest.main()
