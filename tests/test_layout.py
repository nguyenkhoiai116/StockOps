"""Chạy: python -m unittest tests.test_layout   (database tạm, không đụng wms.db)"""
import os
import secrets
import shutil
import tempfile
import unittest

from wms import create_app
from wms import db as dbm
from wms.core import free_bin
from wms.users import set_password

PW = secrets.token_urlsafe(12)   # mật khẩu thử, sinh ngẫu nhiên mỗi lần chạy


class TestLayout(unittest.TestCase):
    def setUp(self):
        self.old, self.tmp = dbm.DB, tempfile.mkdtemp()
        dbm.DB = os.path.join(self.tmp, "test.db")
        self.app = create_app()
        con = dbm.db()
        with con:
            for u in ("admin", "luu01", "soan01"):
                set_password(con, u, PW)
        con.close()

    def tearDown(self):
        dbm.DB = self.old
        shutil.rmtree(self.tmp)

    def get(self, user):
        c = self.app.test_client()
        c.post("/api/login", json={"user": user, "pass": PW})
        r = c.get("/api/layout")
        self.assertEqual(r.status_code, 200)
        return r.get_json()

    def sql(self, *stmts):
        """Dựng dữ liệu thử riêng (không dựa vào số đơn, số lô trong data/*.csv)."""
        con = dbm.db()
        with con:
            for s, a in stmts:
                con.execute(s, a)
        con.close()

    def test_admin_thay_du(self):
        # 1 PO về hôm nay, 1 PO về mai, 1 đơn đã soạn, 1 đơn đang giao trên xe T-BAN; xe T-RANH không chở gì
        self.sql(("INSERT INTO products (sku,name,storage) VALUES ('SKU-T','Hàng thử','dry')", ()),
                 ("INSERT INTO vehicles VALUES ('T-BAN','A','dry'), ('T-RANH','B','cold')", ()),
                 ("INSERT INTO pos (po_no,product_id,qty,eta) SELECT 'PO-TH',id,5,? FROM products WHERE sku='SKU-T'", (dbm.day(),)),
                 ("INSERT INTO pos (po_no,product_id,qty,eta) SELECT 'PO-TM',id,5,? FROM products WHERE sku='SKU-T'", (dbm.day(1),)),
                 ("INSERT INTO sos (so_no,customer,product_id,qty,due,status) SELECT 'SO-TP','K',id,5,?,'picked' FROM products WHERE sku='SKU-T'", (dbm.day(),)),
                 ("INSERT INTO sos (so_no,customer,product_id,qty,due,status,plate) SELECT 'SO-TS','K',id,5,?,'shipping','T-BAN' FROM products WHERE sku='SKU-T'", (dbm.day(),)))
        d = self.get("admin")
        self.assertNotIn("bins", d)   # số ô nằm trong từng khu, không ở cấp ngoài cùng
        con = dbm.db()
        self.assertEqual({z["code"]: z["bins"] for z in d["zones"]},
                         {r["code"]: r["racks"] * r["bays"] * r["levels"] for r in con.execute("SELECT * FROM zones")})
        con.close()
        f = d["flow"]
        self.assertEqual(set(f), {"inbound", "topick", "staged", "shipping", "fleet", "quarantine"})
        self.assertIn("dmg", f["quarantine"])
        self.assertIn("PO-TH", [x["po_no"] for x in f["inbound"]])
        self.assertNotIn("PO-TM", [x["po_no"] for x in f["inbound"]])   # chưa tới ngày về
        self.assertIn("SO-TP", [x["so_no"] for x in f["staged"]])
        self.assertIn(("SO-TS", "T-BAN"), [(x["so_no"], x["plate"]) for x in f["shipping"]])
        bz = {x["plate"]: x["busy"] for x in f["fleet"]}
        self.assertIs(bz["T-BAN"], True)
        self.assertIs(bz["T-RANH"], False)

    def test_storage_khong_thay_don_ban(self):
        f = self.get("luu01")["flow"]
        for k in ("topick", "staged", "shipping", "fleet"):
            self.assertNotIn(k, f)
        self.assertIn("inbound", f)
        self.assertIn("dmg", f["quarantine"])

    def test_picking_khong_thay_po(self):
        con = dbm.db()
        free = free_bin(con, "DRY")
        con.close()
        self.sql(("INSERT INTO batches (product_id,batch_no,exp,qty,zone,bin) VALUES ((SELECT MIN(id) FROM products),'XHH',?,3,'DRY',?)",
                  (dbm.day(-1), free)),)
        f = self.get("soan01")["flow"]
        self.assertNotIn("inbound", f)
        self.assertNotIn("dmg", f["quarantine"])
        self.assertIn("XHH", [x["batch_no"] for x in f["quarantine"]["expired"]])   # lô hết hạn hôm qua -> cách ly

    def test_inbound_xep_theo_id(self):
        # cùng eta: PO-999 (id nhỏ) phải đứng trước PO-1000 dù theo chuỗi "PO-1000" < "PO-999"
        con = dbm.db()
        with con:
            pid = con.execute("SELECT MIN(id) FROM products").fetchone()[0]
            for no in ("PO-999", "PO-1000"):
                con.execute("INSERT INTO pos(po_no, product_id, qty, eta, status) VALUES(?,?,?,?,'pending')", (no, pid, 1, dbm.day()))
        con.close()
        d = [x["po_no"] for x in self.get("admin")["flow"]["inbound"] if x["eta"] == dbm.day()]
        self.assertEqual(d[-2:], ["PO-999", "PO-1000"])   # PO có sẵn về hôm nay (id nhỏ hơn) đứng trước


if __name__ == "__main__":
    unittest.main()
