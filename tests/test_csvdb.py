"""Chạy: python -m unittest tests.test_csvdb   (nạp / xuất database bằng CSV, dùng database và thư mục tạm)"""
import csv
import os
import shutil
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

import database
from wms import core, csvdb
from wms import db as dbm
from wms.migrate import migrate
from wms.users import set_password


def lines(f):
    """Số dòng dữ liệu (không tính tiêu đề, bỏ dòng trống) của 1 file CSV."""
    with open(f, encoding="utf-8-sig", newline="") as h:
        return sum(1 for r in list(csv.reader(h))[1:] if any(c.strip() for c in r))


class CsvTest(unittest.TestCase):
    def setUp(self):
        self.old, self.data, self.tmp = dbm.DB, csvdb.DATA, Path(tempfile.mkdtemp())
        self.src = self.tmp / "data"
        shutil.copytree(csvdb.DATA, self.src)   # sửa trên bản sao, không đụng data/ thật
        self.n = 0

    def tearDown(self):
        dbm.DB, csvdb.DATA = self.old, self.data
        shutil.rmtree(self.tmp, ignore_errors=True)

    def fresh(self, folder=None):
        """Database mới tinh, nạp folder (mặc định bản sao data/) trong 1 transaction có khóa."""
        self.n += 1
        dbm.DB = str(self.tmp / f"t{self.n}.db")
        con = dbm.db()
        migrate(con)
        with con:
            dbm.lock(con)
            csvdb.load(con, folder or self.src)
        self.addCleanup(con.close)
        return con

    def edit(self, name, fn):
        """Sửa 1 file CSV trong bản sao: fn nhận danh sách dòng (dòng 0 là tiêu đề)."""
        f = self.src / name
        with open(f, encoding="utf-8-sig", newline="") as h:
            rs = list(csv.reader(h))
        fn(rs)
        with open(f, "w", encoding="utf-8-sig", newline="") as h:
            csv.writer(h).writerows(rs)

    def write(self, folder, name, text, enc="utf-8"):
        folder.mkdir(exist_ok=True)
        (folder / name).write_text(text, encoding=enc)


class LoadTest(CsvTest):
    def test_nap_du_moi_dong_va_so_khop(self):
        con = self.fresh()
        for t in csvdb.TABLES:
            self.assertEqual(con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0], lines(self.src / f"{t}.csv"), t)
        self.assertEqual(core.ledger_gaps(con), [])
        self.assertEqual(con.execute("PRAGMA foreign_key_check").fetchall(), [])
        # bộ mẫu đã khớp sổ sẵn: không phải ghi thêm dòng cân sổ nào
        self.assertEqual(con.execute("SELECT COUNT(*) FROM txs WHERE note LIKE 'Cân sổ%'").fetchone()[0], 0)

    def test_san_pham_co_du_thuoc_tinh_fmcg(self):
        con = self.fresh()
        p = con.execute("SELECT * FROM products WHERE sku='SKU-001'").fetchone()
        self.assertEqual((p["barcode"], p["pack"], p["vol"], p["tmin"], p["tmax"], p["shelf"], p["fefo"], p["qc"], p["abc"]),
                         ("8935217401012", 12, 0.016, 2, 6, 30, 10, 1, "A"))
        self.assertEqual(con.execute("SELECT COUNT(*) FROM products WHERE barcode IS NULL").fetchone()[0], 0)

    def test_xuat_roi_nap_lai_giong_het(self):
        con = self.fresh()
        set_password(con, "admin", "mat-khau-thu-123")
        con.commit()
        a, b = self.tmp / "a", self.tmp / "b"
        csvdb.dump(con, a)
        csvdb.dump(self.fresh(a), b)
        for t in csvdb.TABLES:
            self.assertEqual((a / f"{t}.csv").read_text(encoding="utf-8-sig"), (b / f"{t}.csv").read_text(encoding="utf-8-sig"), t)
        users = (a / "users.csv").read_text(encoding="utf-8-sig")
        self.assertNotIn("pw_hash", users)   # không bao giờ xuất mật khẩu
        self.assertNotIn("scrypt", users)

    def test_ngay_doi_theo_ngay_goc(self):
        (self.src / csvdb.BASE).write_text((date.today() - timedelta(days=10)).isoformat(), encoding="utf-8")
        with open(self.src / "batches.csv", encoding="utf-8-sig") as h:
            r = next(csv.DictReader(h))
        with open(self.src / "txs.csv", encoding="utf-8-sig") as h:
            t = next(csv.DictReader(h))
        con = self.fresh()
        n = (dbm.today() - (date.today() - timedelta(days=10))).days   # 10, lệch 1 nếu giờ kho đã sang ngày khác giờ máy
        self.assertEqual(con.execute("SELECT exp FROM batches WHERE id=?", (r["id"],)).fetchone()[0],
                         (date.fromisoformat(r["exp"]) + timedelta(days=n)).isoformat())
        self.assertEqual(con.execute("SELECT ts FROM txs ORDER BY id LIMIT 1").fetchone()[0][:10],
                         (date.fromisoformat(t["ts"][:10]) + timedelta(days=n)).isoformat())

    def test_khong_nap_de_bang_da_co_du_lieu(self):
        con = self.fresh()
        n = con.execute("SELECT COUNT(*) FROM products").fetchone()[0]
        with con:
            dbm.lock(con)
            csvdb.load(con, self.src)
        self.assertEqual(con.execute("SELECT COUNT(*) FROM products").fetchone()[0], n)

    def test_file_excel_may_tieng_viet(self):
        # Excel cài tiếng Việt: dấu ; giữa các ô, số thập phân dùng dấu phẩy, ngày DD/MM/YYYY, không có BOM
        x = self.tmp / "x"
        self.write(x, "zones.csv", "code;name;storage;cap;tmin;tmax;temp;hum;racks;bays;levels\n"
                                   "DRY;Kho khô;dry;100;15;30;27,5;60;1;2;3\n;;;;;;;;;;\n")
        self.write(x, "products.csv", "﻿sku,name,storage,safety\nSKU-X,Hàng thử,dry,10\n")
        self.write(x, "batches.csv", "id;sku;batch_no;exp;qty;zone;bin\n1;SKU-X;LX;31/12/2030;7;DRY;2\n")
        con = self.fresh(x)
        self.assertEqual(con.execute("SELECT temp FROM zones").fetchone()[0], 27.5)
        self.assertEqual(tuple(con.execute("SELECT exp, reserved FROM batches").fetchone()), ("2030-12-31", 0))   # ô bỏ trống = mặc định
        self.assertEqual(con.execute("SELECT qc FROM products").fetchone()[0], 0)
        # lô chưa có dòng sổ nào -> tự ghi 1 dòng IN cho khớp tồn
        self.assertEqual(tuple(con.execute("SELECT kind, qty, batch_id FROM txs").fetchone()), ("IN", 7, 1))


class FixTest(CsvTest):
    def test_sua_ton_trong_csv_thi_tu_can_so(self):
        def more(rs):
            i = rs[0].index("qty")
            rs[1][i] = str(int(rs[1][i]) + 5)
        self.edit("batches.csv", more)
        con = self.fresh()
        self.assertEqual(core.ledger_gaps(con), [])
        self.assertEqual([tuple(r) for r in con.execute("SELECT kind, qty FROM txs WHERE note LIKE 'Cân sổ%'")], [("ADJ", 5)])


class ErrorTest(CsvTest):
    def bad(self, pattern):
        with self.assertRaisesRegex(ValueError, pattern):
            self.fresh()

    def test_sku_khong_co(self):
        self.edit("batches.csv", lambda rs: rs[1].__setitem__(rs[0].index("sku"), "SKU-ZZZ"))
        self.bad(r"batches\.csv dòng 2: SKU 'SKU-ZZZ' chưa có")

    def test_cot_la_hoac_cot_mat_khau(self):
        def pw(rs):
            for r in rs:
                r.append("x")
            rs[0][-1] = "pw_hash"
        self.edit("users.csv", pw)
        self.bad(r"users\.csv: .*pw_hash")

    def test_ma_vach_bi_excel_doi_so_mu(self):
        self.edit("products.csv", lambda rs: rs[3].__setitem__(rs[0].index("barcode"), "8.93467E+12"))
        self.bad(r"products\.csv dòng 4: mã vạch")

    def test_trung_sku(self):
        self.edit("products.csv", lambda rs: rs.append(list(rs[1])))
        self.bad(r"products\.csv dòng 37: trùng")

    def test_o_ke_ngoai_khu(self):
        self.edit("batches.csv", lambda rs: rs[1].__setitem__(rs[0].index("bin"), "999"))
        self.bad(r"chỉ có ô 1\.\.")

    def test_so_sai_kieu(self):
        self.edit("products.csv", lambda rs: rs[2].__setitem__(rs[0].index("price"), "420.000đ"))
        self.bad(r"products\.csv dòng 3, cột price: phải là số nguyên")

    def test_file_khong_phai_utf8(self):
        self.write(self.src, "vehicles.csv", "plate,driver,kind\n51C-999.99,Lê Tâm,dry\n", enc="latin-1")   # Excel lưu kiểu "CSV" thường
        self.bad(r"vehicles\.csv: không đọc được tiếng Việt")

    def test_reset_loi_thi_khong_nap_do_dang(self):
        csvdb.DATA = self.src
        dbm.DB, bak = str(self.tmp / "reset.db"), database.BAK
        database.BAK = self.tmp / "backups"
        try:
            self.edit("users.csv", lambda rs: rs[2].__setitem__(rs[0].index("role"), "lạ"))
            self.assertEqual(database.reset(yes=True), 1)
            self.assertFalse(os.path.exists(dbm.DB))   # xóa database rỗng để lần sau reset lại từ đầu
        finally:
            database.BAK = bak


if __name__ == "__main__":
    unittest.main()
