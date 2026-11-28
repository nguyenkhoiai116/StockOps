"""Chạy: python -m unittest discover tests   (dùng database tạm, không đụng wms.db)"""
import csv
import os
import shutil
import sqlite3
import tempfile
import unittest
from pathlib import Path

import database
from wms import csvdb
from wms import db as dbm


class DatabaseTest(unittest.TestCase):
    def setUp(self):
        self.old, self.bak, self.tmp = dbm.DB, database.BAK, tempfile.mkdtemp()
        dbm.DB = os.path.join(self.tmp, "test.db")
        database.BAK = Path(self.tmp) / "backups"

    def tearDown(self):
        dbm.DB, database.BAK = self.old, self.bak
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_reset_tao_du_lieu_mau(self):
        """Reset từ chỗ chưa có gì: đủ bảng, đủ migration, có dữ liệu mẫu, bật WAL."""
        self.assertEqual(database.reset(yes=True), 0)
        con = dbm.db()
        self.assertEqual(con.execute("PRAGMA user_version").fetchone()[0], database.latest())
        self.assertEqual(con.execute("PRAGMA journal_mode").fetchone()[0], "wal")
        for t in ("products", "users", "vehicles", "batches", "sos"):   # đủ mọi dòng trong data/*.csv
            with open(csvdb.DATA / f"{t}.csv", encoding="utf-8-sig") as f:
                n = sum(1 for r in csv.reader(f) if any(r)) - 1
            self.assertEqual(con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0], n, t)
        self.assertEqual(con.execute("SELECT COUNT(*) FROM users WHERE pw_hash IS NOT NULL").fetchone()[0], 0)
        con.close()

    def test_export_ra_csv(self):
        database.reset(yes=True)
        self.assertEqual(database.export(Path(self.tmp) / "out"), 0)
        self.assertEqual({f.name for f in (Path(self.tmp) / "out").iterdir()},
                         {f"{t}.csv" for t in csvdb.TABLES} | {csvdb.BASE})

    def test_reset_sao_luu_va_xoa_du_lieu_cu(self):
        """Reset lần 2: dữ liệu thêm tay mất đi, nhưng còn trong bản sao lưu."""
        database.reset(yes=True)
        con = dbm.db()
        with con:
            con.execute("UPDATE products SET name='Đã sửa' WHERE sku='SKU-001'")
        con.close()
        database.reset(yes=True)
        con = dbm.db()
        self.assertNotEqual(con.execute("SELECT name FROM products WHERE sku='SKU-001'").fetchone()[0], "Đã sửa")
        con.close()
        baks = list(database.BAK.glob("*.db"))
        self.assertEqual(len(baks), 1)
        old = sqlite3.connect(baks[0])
        self.assertEqual(old.execute("SELECT name FROM products WHERE sku='SKU-001'").fetchone()[0], "Đã sửa")
        old.close()

    def test_backup_khi_chua_co_database(self):
        self.assertIsNone(database.backup())


if __name__ == "__main__":
    unittest.main()
