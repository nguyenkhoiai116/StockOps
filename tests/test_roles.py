"""Chạy: python -m unittest discover tests   (dùng database tạm, không đụng wms.db)"""
import os
import sqlite3
import tempfile
import unittest

from wms import create_app
from wms import db as dbm
from wms.roles import ANY, PERMS, PUBLIC, ROLES, can


class TestRoles(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.old, cls.tmp = dbm.DB, tempfile.mkdtemp()
        dbm.DB = os.path.join(cls.tmp, "test.db")
        cls.app = create_app()

    @classmethod
    def tearDownClass(cls):
        os.remove(dbm.DB)
        os.rmdir(cls.tmp)
        dbm.DB = cls.old

    def test_moi_api_deu_co_quyen(self):
        apis = {f"{m} {r.rule}" for r in self.app.url_map.iter_rules() if r.rule.startswith("/api/")
                for m in r.methods - {"HEAD", "OPTIONS"}}
        declared = [a for _, _, s in PERMS.values() for a in s]
        self.assertEqual(len(declared), len(set(declared)), "1 API nằm ở 2 quyền")
        self.assertEqual(apis, set(declared) | PUBLIC | ANY)

    def test_role_trong_quyen_hop_le(self):
        for p, (_, who, _) in PERMS.items():
            self.assertTrue(who <= set(ROLES), p)
            self.assertIn("admin", who, p)

    def test_gioi_han_tung_role(self):
        self.assertTrue(can("inbound", "po.receive"))
        self.assertTrue(can("storage", "inv.adjust"))
        self.assertTrue(can("picking", "so.pick"))
        self.assertTrue(can("shipping", "so.ship"))
        self.assertFalse(can("inbound", "so.ship"))
        self.assertFalse(can("storage", "po.receive"))
        self.assertFalse(can("picking", "inv.adjust"))
        self.assertFalse(can("shipping", "so.pick"))
        self.assertFalse(can("khach", "dash.view"))
        self.assertFalse(can("admin", "khong.co"))

    def test_du_lieu_user(self):
        con = dbm.db()
        us = dbm.rows(con, "SELECT * FROM users")
        for u, r in (("x", "sep"), ("admin", "admin")):   # role lạ, trùng tài khoản
            with self.assertRaises(sqlite3.IntegrityError):
                con.execute("INSERT INTO users (username,name,role,created_at) VALUES (?,'x',?,'2026-01-01')", (u, r))
        con.close()
        self.assertEqual({u["role"] for u in us}, set(ROLES))
        self.assertTrue(all(u["pw_hash"] is None for u in us), "dữ liệu mẫu không được có sẵn mật khẩu")

    def test_chay_lai_khong_nhan_doi(self):
        con = dbm.db()
        q = "SELECT COUNT(*) FROM users"
        n = con.execute(q).fetchone()[0]
        create_app()
        self.assertEqual(con.execute(q).fetchone()[0], n)
        con.close()


if __name__ == "__main__":
    unittest.main()
