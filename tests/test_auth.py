"""Chạy: python -m unittest discover tests   (dùng database tạm, không đụng wms.db)"""
import os
import re
import secrets
import shutil
import tempfile
import unittest

from wms import create_app
from wms import db as dbm
from wms.features import auth
from wms.roles import ANY, PERMS, PUBLIC
from wms.users import set_password

PW = secrets.token_urlsafe(12)   # mật khẩu thử, sinh ngẫu nhiên mỗi lần chạy
WHO = {"admin": "admin", "inbound": "nhap01", "storage": "luu01", "picking": "soan01", "shipping": "xuat01"}


class TestAuth(unittest.TestCase):
    def setUp(self):
        self.old, self.tmp = dbm.DB, tempfile.mkdtemp()
        dbm.DB = os.path.join(self.tmp, "test.db")
        auth.fails.clear()
        self.app = create_app()
        for u in WHO.values():
            self.sql(lambda con, u=u: set_password(con, u, PW))

    def tearDown(self):
        dbm.DB = self.old
        shutil.rmtree(self.tmp)

    def sql(self, fn):
        con = dbm.db()
        with con:
            fn(con)
        con.close()

    def login(self, user, pw=PW):
        c = self.app.test_client()
        r = c.post("/api/login", json={"user": user, "pass": pw})
        return c, r

    def call(self, c, key, **kw):
        m, rule = key.split(" ", 1)
        return c.open(re.sub(r"<[^>]+>", "999999", rule), method=m, **({} if m == "GET" else {"json": {}}), **kw)

    def test_chua_dang_nhap_bi_chan_het(self):
        for key in [a for _, _, s in PERMS.values() for a in s] + list(ANY):
            self.assertEqual(self.call(self.app.test_client(), key).status_code, 401, key)

    def test_moi_api_voi_moi_role(self):
        self.app.config["PROPAGATE_EXCEPTIONS"] = False   # dữ liệu rỗng có thể gây lỗi 500; ở đây chỉ xét quyền
        for role, user in WHO.items():
            c, _ = self.login(user)
            for p, (_, who, apis) in PERMS.items():
                for key in apis - {"POST /api/chat"}:   # chat gọi ra ngoài, xét riêng
                    st = self.call(c, key).status_code
                    self.assertEqual(st == 403, role not in who, f"{role} {key} -> {st}")
                    self.assertNotEqual(st, 401, f"{role} {key}")

    def test_chat_can_dang_nhap(self):
        c, _ = self.login("xuat01")
        self.assertEqual(c.post("/api/chat", json={"text": ""}).status_code, 400)   # qua được chốt, dừng ở câu hỏi trống

    def test_api_la_bi_chan(self):
        self.app.add_url_rule("/api/moi", "moi", lambda: "x")
        c, _ = self.login("admin")
        self.assertEqual(c.get("/api/moi").status_code, 403)

    def test_dang_nhap_sai(self):
        for u, p in (("admin", "sai"), ("khongco", PW), ("", ""), ("nhap02", ""), ("admin' OR 1=1--", PW)):
            c, r = self.login(u, p)
            self.assertEqual((r.status_code, r.get_json()["error"]), (401, "Sai tài khoản hoặc mật khẩu"), u)
            self.assertIsNone(c.get("/api/me").get_json()["user"])
        c = self.app.test_client()
        self.assertEqual(c.post("/api/login", json=[1]).status_code, 401)
        self.assertEqual(c.post("/api/login", data="x").status_code, 401)

    def test_thong_tin_khong_lo_mat_khau(self):
        c, r = self.login("NHAP01 ")   # không phân biệt hoa thường, bỏ khoảng trắng
        self.assertEqual(r.status_code, 200)
        u = c.get("/api/me").get_json()["user"]
        self.assertEqual(set(u), {"username", "name", "role", "role_name", "perms"})
        self.assertIn("po.receive", u["perms"])
        self.assertNotIn("so.ship", u["perms"])

    def test_khoa_tam_khi_sai_nhieu(self):
        for _ in range(auth.MAX_USER):
            self.login("admin", "sai")
        self.assertEqual(self.login("admin")[1].status_code, 429)
        self.assertEqual(self.login("nhap01")[1].status_code, 200)   # tài khoản khác không bị ảnh hưởng
        for k in auth.fails:
            auth.fails[k] = [t - auth.WAIT for t in auth.fails[k]]
        self.assertEqual(self.login("admin")[1].status_code, 200)

    def test_dang_xuat(self):
        c, _ = self.login("admin")
        self.assertEqual(c.post("/api/logout").status_code, 200)
        self.assertEqual(c.get("/api/dashboard").status_code, 401)

    def test_khoa_tai_khoan_va_doi_role_co_hieu_luc_ngay(self):
        c, _ = self.login("nhap01")
        self.sql(lambda con: con.execute("UPDATE users SET role='shipping' WHERE username='nhap01'"))
        self.assertEqual(c.get("/api/pos").status_code, 403)
        self.sql(lambda con: con.execute("UPDATE users SET active=0 WHERE username='nhap01'"))
        self.assertEqual(c.get("/api/dashboard").status_code, 401)
        self.assertEqual(self.login("nhap01")[1].status_code, 401)

    def test_doi_mat_khau(self):
        a, _ = self.login("luu01")
        b, _ = self.login("luu01")
        new = secrets.token_urlsafe(12)
        self.assertEqual(a.post("/api/password", json={"old": "sai", "new": new}).status_code, 400)
        self.assertEqual(a.post("/api/password", json={"old": PW, "new": "ngan"}).status_code, 400)
        self.assertEqual(a.post("/api/password", json={"old": PW, "new": new}).status_code, 200)
        self.assertEqual(a.get("/api/dashboard").status_code, 200)   # phiên vừa đổi vẫn dùng được
        self.assertEqual(b.get("/api/dashboard").status_code, 401)   # phiên khác bị đăng xuất
        self.assertEqual(self.login("luu01")[1].status_code, 401)
        self.assertEqual(self.login("luu01", new)[1].status_code, 200)

    def test_trang_khac_gui_lenh_bi_chan(self):
        c, _ = self.login("soan01")
        self.assertEqual(c.post("/api/orders/1/pick", headers={"Origin": "http://xau.example"}).status_code, 403)
        self.assertNotEqual(c.post("/api/orders/1/pick", headers={"Origin": "http://localhost"}).status_code, 403)

    def test_cookie_gia_bi_tu_choi(self):
        c = self.app.test_client()
        c.set_cookie("session", "eyJ1aWQiOjF9.aaaa.bbbb")
        self.assertEqual(c.get("/api/dashboard").status_code, 401)

    def test_cookie_an_toan(self):
        _, r = self.login("admin")
        ck = r.headers["Set-Cookie"]
        self.assertIn("HttpOnly", ck)
        self.assertIn("SameSite=Lax", ck)

    def test_trang_va_file_tinh_mo_duoc(self):
        c = self.app.test_client()
        r = c.get("/")
        self.assertEqual(r.status_code, 200)
        r.close()
        self.assertEqual(c.get("/api/khong-co").status_code, 401)   # đường dẫn lạ cũng bị chặn
        self.assertEqual(c.get("/api/me").status_code, 200)
        self.assertTrue(PUBLIC >= {"GET /api/me", "POST /api/login"})


if __name__ == "__main__":
    unittest.main()
