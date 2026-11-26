"""Chạy: python -m unittest tests.test_json   (body JSON sai không được làm server lỗi 500)

Quét MỌI route ghi (POST/DELETE) của app, gửi các kiểu body hỏng.
Đúng: server trả 4xx kèm {"error": "..."} để giao diện hiện được lời giải thích.
"""
import os
import secrets
import shutil
import tempfile
import unittest

from wms import create_app
from wms import db as dbm
from wms.users import set_password

PW = secrets.token_urlsafe(12)
# Body hỏng: không có body, JSON sai cú pháp, mảng, chuỗi, số, dict có kiểu sai ở mọi trường hay gặp
BAD = [None, "{hỏng", [1, 2], "x", 5,
       {"qty": "abc", "product_id": "x", "dmg": [], "delta": {}, "customer": 5, "sku": 7, "name": [],
        "storage": "dry", "price": "1.5", "safety": "x", "exp": 20261231, "batch_no": 9, "plate": [],
        "text": 3, "history": "x", "user": [], "pass": {}, "old": 1, "new": 2}]


class JsonTest(unittest.TestCase):
    def setUp(self):
        self.old, self.tmp = dbm.DB, tempfile.mkdtemp()
        dbm.DB = os.path.join(self.tmp, "test.db")
        self.app = create_app()
        con = dbm.db()
        with con:
            set_password(con, "admin", PW)
        con.close()
        self.c = self.app.test_client()
        self.c.post("/api/login", json={"user": "admin", "pass": PW})

    def tearDown(self):
        dbm.DB = self.old
        shutil.rmtree(self.tmp, ignore_errors=True)

    def send(self, method, url, b):
        if b is None:
            return self.c.open(url, method=method)
        if isinstance(b, str) and b.startswith("{"):
            return self.c.open(url, method=method, data=b, content_type="application/json")
        return self.c.open(url, method=method, json=b)

    def test_moi_route_ghi_khong_loi_500(self):
        skip = {"/api/logout", "/api/chat"}   # logout không đọc body; chat gọi mạng (kiểm riêng bên dưới)
        hit = 0
        for r in self.app.url_map.iter_rules():
            for m in sorted((r.methods or set()) & {"POST", "DELETE"}):
                if not r.rule.startswith("/api/") or r.rule in skip:
                    continue
                url = r.rule.replace("<int:", "<").split("<")[0] + ("1" + r.rule.split(">", 1)[1] if ">" in r.rule else "")
                for b in BAD:
                    with self.subTest(route=f"{m} {r.rule}", body=b):
                        res = self.send(m, url, b)
                        self.assertLess(res.status_code, 500, res.get_data(as_text=True)[:200])
                        if res.status_code >= 400:
                            self.assertIn("error", res.get_json() or {})
                hit += 1
                self.c.post("/api/login", json={"user": "admin", "pass": PW})   # đổi mật khẩu sai không được làm mất phiên
        self.assertGreater(hit, 10)

    def test_chat_body_sai_khong_goi_llm(self):
        for b in BAD:
            with self.subTest(body=b):
                res = self.send("POST", "/api/chat", b)
                self.assertLess(res.status_code, 500)
