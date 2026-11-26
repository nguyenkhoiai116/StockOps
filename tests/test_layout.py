"""Chạy: python -m unittest tests.test_layout   (database tạm, không đụng wms.db)"""
import os
import secrets
import shutil
import tempfile
import unittest

from wms import create_app
from wms import db as dbm
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

    def test_admin_thay_du(self):
        d = self.get("admin")
        self.assertNotIn("bins", d)   # số ô nằm trong từng khu, không ở cấp ngoài cùng
        self.assertEqual({z["code"]: z["bins"] for z in d["zones"]}["DRY"], 96)
        f = d["flow"]
        self.assertEqual(set(f), {"inbound", "topick", "staged", "shipping", "fleet", "quarantine"})
        self.assertIn("dmg", f["quarantine"])
        self.assertEqual([x["po_no"] for x in f["inbound"]], ["PO-001"])
        self.assertIn("SO-004", [x["so_no"] for x in f["staged"]])
        self.assertEqual(f["shipping"][0]["plate"], "51C-123.45")
        bz = {x["plate"]: x["busy"] for x in f["fleet"]}
        self.assertIs(bz["51C-123.45"], True)
        self.assertIs(bz["51D-678.90"], False)

    def test_storage_khong_thay_don_ban(self):
        f = self.get("luu01")["flow"]
        for k in ("topick", "staged", "shipping", "fleet"):
            self.assertNotIn(k, f)
        self.assertIn("inbound", f)
        self.assertIn("dmg", f["quarantine"])

    def test_picking_khong_thay_po(self):
        f = self.get("soan01")["flow"]
        self.assertNotIn("inbound", f)
        self.assertNotIn("dmg", f["quarantine"])
        self.assertIn("L2408", [x["batch_no"] for x in f["quarantine"]["expired"]])

    def test_inbound_xep_theo_id(self):
        # cùng eta: PO-999 (id nhỏ) phải đứng trước PO-1000 dù theo chuỗi "PO-1000" < "PO-999"
        con = dbm.db()
        with con:
            pid = con.execute("SELECT product_id FROM pos LIMIT 1").fetchone()[0]
            eta = con.execute("SELECT eta FROM pos WHERE po_no='PO-001'").fetchone()[0]
            for no in ("PO-999", "PO-1000"):
                con.execute("INSERT INTO pos(po_no, product_id, qty, eta, status) VALUES(?,?,?,?,'pending')", (no, pid, 1, eta))
        con.close()
        d = [x["po_no"] for x in self.get("admin")["flow"]["inbound"] if x["eta"] == eta]
        self.assertEqual(d, ["PO-001", "PO-999", "PO-1000"])


if __name__ == "__main__":
    unittest.main()
