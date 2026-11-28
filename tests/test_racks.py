"""Chạy: python -m unittest tests.test_racks   (số ô/kệ theo từng khu, dùng database tạm)"""
import csv
import os
import shutil
import sqlite3
import tempfile
import unittest

from wms import csvdb, db as dbm, seed
from wms.core import free_bin, zone_bins
from wms.migrate import DIR, migrate


class RacksTest(unittest.TestCase):
    def setUp(self):
        self.old, self.tmp = dbm.DB, tempfile.mkdtemp()
        dbm.DB = os.path.join(self.tmp, "test.db")

    def tearDown(self):
        dbm.DB = self.old
        shutil.rmtree(self.tmp, ignore_errors=True)

    def new(self):
        seed.init_db()
        return dbm.db()

    def test_db_moi_co_so_o_theo_khu(self):
        con = self.new()
        zs = con.execute("SELECT * FROM zones").fetchall()
        with open(csvdb.DATA / "zones.csv", encoding="utf-8-sig") as f:   # số dãy, ô, tầng, sức chứa lấy từ data/zones.csv
            want = {r["code"]: (int(r["racks"]) * int(r["bays"]) * int(r["levels"]), int(r["cap"])) for r in csv.DictReader(f)}
        self.assertEqual({z["code"]: (zone_bins(z), z["cap"]) for z in zs}, want)
        con.close()

    def test_db_cu_duoc_nang_cap(self):
        con = sqlite3.connect(os.path.join(self.tmp, "old.db"))
        con.row_factory = sqlite3.Row
        for n in ("001", "002"):
            f = next(DIR.glob(f"{n}_*.sql"))
            con.executescript(f.read_text(encoding="utf-8"))
        con.execute("PRAGMA user_version=2")
        con.executemany("INSERT INTO zones VALUES (?,?,?,?,?,?,?,?)", [
            ("DRY", "Kho khô", "dry", 3000, 15, 30, 27.5, 60),
            ("CHL", "Kho mát", "chilled", 800, 2, 8, 5, 75),
            ("FRZ", "Kho đông", "frozen", 500, -25, -18, -19, 55),
            ("COS", "Kho mỹ phẩm", "cosmetics", 999, 15, 28, 24, 50),   # người dùng đã sửa cap
            ("TMP", "Khu lạ", "dry", 100, 0, 30, 20, 50),
        ])
        con.commit()
        migrate(con)
        z = {r["code"]: r for r in con.execute("SELECT * FROM zones")}
        self.assertEqual((z["DRY"]["racks"], z["DRY"]["bays"], z["DRY"]["levels"]), (4, 6, 4))
        self.assertEqual(z["DRY"]["cap"], 20000)
        self.assertEqual(z["COS"]["cap"], 999)
        self.assertEqual(z["CHL"]["cap"], 3000)
        self.assertEqual(z["FRZ"]["cap"], 2000)
        self.assertEqual((z["TMP"]["racks"], z["TMP"]["bays"], z["TMP"]["levels"]), (2, 2, 3))
        con.close()

    def test_lo_mau_nam_trong_so_do(self):
        con = self.new()
        zs = {z["code"]: zone_bins(z) for z in con.execute("SELECT * FROM zones")}
        for b in con.execute("SELECT zone, bin FROM batches WHERE qty>0"):
            self.assertTrue(1 <= b["bin"] <= zs[b["zone"]], (b["zone"], b["bin"]))
        con.close()

    def _fill(self, con, zone, ns):
        with con:
            for n in ns:
                con.execute("INSERT INTO batches (product_id,batch_no,exp,qty,zone,bin) VALUES (1,?,?,1,?,?)",
                            (f"T{zone}{n}", "2099-01-01", zone, n))

    def test_free_bin_qua_12(self):
        # lấp mọi ô trống từ 1 tới 12 (giới hạn BINS = 12 cũ) -> ô cấp tiếp phải > 12
        con = self.new()
        used = {r[0] for r in con.execute("SELECT bin FROM batches WHERE zone='DRY' AND qty>0")}
        self._fill(con, "DRY", [i for i in range(1, 13) if i not in used])
        self.assertEqual(free_bin(con, "DRY"), next(i for i in range(13, 97) if i not in used))
        con.close()

    def test_free_bin_het_o(self):
        con = self.new()
        used = {r[0] for r in con.execute("SELECT bin FROM batches WHERE zone='CHL' AND qty>0")}
        self._fill(con, "CHL", [i for i in range(1, 25) if i not in used])
        self.assertIsNone(free_bin(con, "CHL"))
        con.close()


if __name__ == "__main__":
    unittest.main()
