"""Chạy: python -m unittest tests.test_race   (2 request ghi cùng lúc, dùng database tạm)

Mô phỏng người dùng bấm đúp: 2 request cùng đọc dữ liệu rồi mới ghi.
Đúng: chỉ 1 request được ghi, request kia nhận lỗi 400 có lời giải thích.
"""
import os
import secrets
import shutil
import sqlite3
import tempfile
import threading
import unittest

from wms import core, create_app
from wms import db as dbm
from wms.users import set_password

PW = secrets.token_urlsafe(12)   # mật khẩu thử, sinh ngẫu nhiên mỗi lần chạy


def gate():
    """Cửa chờ: request đến trước đợi request sau tối đa 1 giây rồi mới đi tiếp.
    Có khóa ghi từ đầu thì request sau không tới được đây -> hết giờ, đi tiếp bình thường."""
    bar = threading.Barrier(2)

    def wait():
        try:
            bar.wait(timeout=1)
        except threading.BrokenBarrierError:
            pass
    return wait


class RaceTest(unittest.TestCase):
    def setUp(self):
        self.old, self.tmp = dbm.DB, tempfile.mkdtemp()
        dbm.DB = os.path.join(self.tmp, "test.db")
        self.app = create_app()
        con = dbm.db()
        with con:
            set_password(con, "admin", PW)
        con.close()
        self.rows, self.free = core.rows, core.free_bin

    def tearDown(self):
        core.rows, core.free_bin = self.rows, self.free
        dbm.DB = self.old
        shutil.rmtree(self.tmp, ignore_errors=True)

    def q(self, sql, args=()):
        con = dbm.db()
        try:
            return con.execute(sql, args).fetchone()
        finally:
            con.close()

    def twice(self, path, body=None):
        """Gửi cùng 1 request ghi từ 2 luồng song song; trả về 2 mã HTTP."""
        out = []

        def one():
            c = self.app.test_client()
            c.post("/api/login", json={"user": "admin", "pass": PW})
            out.append(c.post(path, json=body or {}).status_code)
        ts = [threading.Thread(target=one) for _ in range(2)]
        for t in ts:
            t.start()
        for t in ts:
            t.join()
        return sorted(out)

    def test_soan_2_lan_cung_luc_chi_giu_hang_1_lan(self):
        con = dbm.db()
        with con:
            sid = con.execute("INSERT INTO sos (so_no,customer,product_id,qty,due) VALUES ('SO-T','Thử',2,10,'2099-01-01')").lastrowid
        con.close()
        wait = gate()

        def slow(con, sql, args=()):
            out = self.rows(con, sql, args)
            if "FROM batches" in sql:   # đã đọc lô khả dụng, sắp ghi
                wait()
            return out
        core.rows = slow
        self.assertEqual(self.twice(f"/api/orders/{sid}/pick"), [200, 400])
        self.assertEqual(tuple(self.q("SELECT COUNT(*), SUM(qty) FROM picks WHERE so_id=?", (sid,))), (1, 10))
        self.assertEqual(self.q("SELECT SUM(reserved) FROM batches WHERE product_id=2")[0], 10)

    def test_nhan_po_2_lan_cung_luc_chi_tao_1_lo(self):
        wait = gate()

        def slow(con, code):
            wait()   # đã kiểm PO còn chờ nhận, sắp tạo lô
            return self.free(con, code)
        core.free_bin = slow
        po = self.q("SELECT id FROM pos WHERE status='pending' ORDER BY id LIMIT 1")[0]   # 1 PO đang chờ nhận trong dữ liệu mẫu
        body = {"qty": 10, "dmg": 0, "batch_no": "L-T1", "exp": "2099-01-01"}
        self.assertEqual(self.twice(f"/api/pos/{po}/receive", body), [200, 400])
        self.assertEqual(self.q("SELECT COUNT(*) FROM batches WHERE batch_no='L-T1'")[0], 1)
        self.assertEqual(self.q("SELECT COUNT(*) FROM txs WHERE batch_no='L-T1'")[0], 1)

    def test_so_don_khong_trung(self):
        con = dbm.db()
        for sql in ("INSERT INTO pos (po_no,product_id,qty) VALUES ('PO-001',1,1)",
                    "INSERT INTO sos (so_no,customer,product_id,qty) VALUES ('SO-001','Thử',1,1)"):
            with self.assertRaises(sqlite3.IntegrityError):
                with con:
                    con.execute(sql)
        con.close()

    def test_tao_don_lien_tiep_danh_so_tang_dan(self):
        c = self.app.test_client()
        c.post("/api/login", json={"user": "admin", "pass": PW})
        n = self.q("SELECT COUNT(*) FROM sos")[0]
        for _ in range(2):
            self.assertEqual(c.post("/api/orders", json={"customer": "Thử", "product_id": 1, "qty": 5}).status_code, 200)
        self.assertEqual(tuple(self.q("SELECT COUNT(DISTINCT so_no), COUNT(*) FROM sos")), (n + 2, n + 2))


if __name__ == "__main__":
    unittest.main()
