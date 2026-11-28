"""Chạy: python -m unittest tests.test_tunnel   (truy cập từ xa qua Cloudflare Tunnel, dùng database tạm)

cloudflared chạy trên chính máy chủ, nên mọi request qua tunnel đến từ 127.0.0.1;
IP thật của người dùng nằm trong header CF-Connecting-IP.
"""
import os
import secrets
import shutil
import tempfile
import unittest

from wms import create_app
from wms import db as dbm
from wms.features import auth
from wms.users import set_password

PW = secrets.token_urlsafe(12)
LAN = {"REMOTE_ADDR": "192.168.1.50"}


class TunnelTest(unittest.TestCase):
    def setUp(self):
        self.old, self.tmp = dbm.DB, tempfile.mkdtemp()
        self.url = os.environ.pop("APP_URL", None)
        dbm.DB = os.path.join(self.tmp, "test.db")
        self.app = create_app()
        con = dbm.db()
        with con:
            set_password(con, "admin", PW)
        con.close()

    def tearDown(self):
        dbm.DB = self.old
        if self.url is not None:
            os.environ["APP_URL"] = self.url
        else:
            os.environ.pop("APP_URL", None)
        shutil.rmtree(self.tmp)

    def login(self, pw, ip=None, env=None, **kw):
        h = {"CF-Connecting-IP": ip} if ip else {}
        return self.app.test_client().post("/api/login", json={"user": "admin", "pass": pw},
                                           headers={**h, **kw.pop("headers", {})}, environ_base=env or {}, **kw)

    def test_sai_nhieu_lan_chi_khoa_dung_nguoi(self):
        for i in range(auth.MAX_IP):
            self.login("sai", ip="1.1.1.1")
        self.assertEqual(self.login("sai", ip="1.1.1.1").status_code, 429)
        self.assertEqual(self.login(PW, ip="2.2.2.2").status_code, 200)   # người khác qua tunnel vẫn vào được

    def test_may_lan_khong_gia_duoc_ip(self):
        # Header CF-Connecting-IP chỉ tin khi request đến từ cloudflared trên chính máy chủ
        for i in range(auth.MAX_IP):
            self.login("sai", ip=f"9.9.9.{i}", env=LAN)
        self.assertEqual(self.login(PW, ip="8.8.8.8", env=LAN).status_code, 429)

    def test_cookie_https_khi_qua_tunnel(self):
        r = self.login(PW, ip="2.2.2.2")
        self.assertIn("Secure", r.headers["Set-Cookie"])
        r = self.login(PW, env=LAN)   # máy trong LAN vào bằng http vẫn đăng nhập được
        self.assertNotIn("Secure", r.headers["Set-Cookie"])

    def test_origin_ten_mien_cong_khai(self):
        os.environ["APP_URL"] = "https://kho.example.vn"
        r = self.login(PW, ip="2.2.2.2", headers={"Origin": "https://kho.example.vn"})
        self.assertEqual(r.status_code, 200)
        r = self.login(PW, ip="2.2.2.2", headers={"Origin": "https://evil.example.com"})
        self.assertEqual(r.status_code, 403)


if __name__ == "__main__":
    unittest.main()
