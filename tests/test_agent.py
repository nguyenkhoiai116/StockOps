"""Chạy: python -m unittest tests.test_agent   (vòng lặp agent Kvis với LLM giả, không gọi mạng)

LLM giả (Fake) trả lời theo kịch bản soạn sẵn và ghi lại mọi lần được gọi.
Tài khoản thử tự tạo, không dựa vào tài khoản mẫu.
"""
import copy
import json
import os
import secrets
import shutil
import sqlite3
import tempfile
import unittest
from unittest import mock

from wms import create_app
from wms import db as dbm
from wms.ai import agent
from wms.ai.llm import LLMError, NoTools
from wms.users import set_password

USAGE = {"prompt_tokens": 10, "completion_tokens": 5}
PW = secrets.token_urlsafe(12)   # mật khẩu thử, sinh ngẫu nhiên mỗi lần chạy


def reply(text):
    return {"text": text, "calls": [], "model": "m-thu", "usage": USAGE}


def calls(*names, args="{}"):
    """1 bước LLM gọi 1 hay nhiều tool cùng lúc."""
    cs = [{"id": f"c{i}", "type": "function", "function": {"name": n, "arguments": args}} for i, n in enumerate(names)]
    return {"text": "", "calls": cs, "model": "m-thu", "usage": USAGE}


class Fake:
    """LLM giả: mỗi lần gọi lấy 1 phần tử của kịch bản (dict trả lời, hoặc exception thì raise)."""

    def __init__(self, *script, hook=None):
        self.script, self.seen, self.hook = list(script), [], hook

    def __call__(self, msgs, tools=None, **kw):
        self.seen.append((copy.deepcopy(msgs), tools))
        if self.hook:
            self.hook()
        x = self.script.pop(0)
        if isinstance(x, Exception):
            raise x
        return x


class AgentTest(unittest.TestCase):
    def setUp(self):
        self.old, self.tmp = dbm.DB, tempfile.mkdtemp()
        dbm.DB = os.path.join(self.tmp, "test.db")
        self.env = mock.patch.dict(os.environ)
        self.env.start()
        os.environ.pop("LLM_TOOLS", None)
        self.app = create_app()
        self.con = dbm.db()
        with self.con:
            dbm.lock(self.con)
            for u, name, role in [("t_admin", "Quản Trị Thử", "admin"), ("t_soan", "Người Soạn Thử", "picking")]:
                self.con.execute("INSERT INTO users (username,name,role,created_at) VALUES (?,?,?,?)", (u, name, role, dbm.day()))
            set_password(self.con, "t_admin", PW)

    def tearDown(self):
        self.con.close()
        self.env.stop()
        dbm.DB = self.old
        shutil.rmtree(self.tmp, ignore_errors=True)

    def user(self, name="t_admin"):
        return dict(self.con.execute("SELECT * FROM users WHERE username=?", (name,)).fetchone())

    def ask(self, fake, user=None, text="Hỏi thử", hist=()):
        with mock.patch("wms.ai.llm.chat", fake):
            return agent.ask(user or self.user(), text, list(hist))

    def log(self):
        return dict(self.con.execute("SELECT * FROM chat_logs ORDER BY id DESC LIMIT 1").fetchone())

    @staticmethod
    def tool_msgs(msgs):
        return [m for m in msgs if m["role"] == "tool"]

    def test_mot_tool_roi_tra_loi(self):
        f = Fake(calls("get_kpis"), reply("Giá trị tồn là ..."))
        r = self.ask(f)
        self.assertEqual((r["mode"], r["tools"], r["steps"], r["reply"]), ("agent", ["Chỉ số KPI"], 2, "Giá trị tồn là ..."))
        self.assertEqual((r["actions"], r["sources"]), ([], []))
        msgs = f.seen[1][0]
        self.assertEqual(msgs[-1]["role"], "tool")
        self.assertIn("value", json.loads(msgs[-1]["content"]))
        self.assertEqual(msgs[-2]["tool_calls"][0]["function"]["name"], "get_kpis")
        lg = self.log()
        self.assertEqual((lg["steps"], lg["tok_in"], lg["tok_out"], lg["error"], lg["mode"]), (2, 20, 10, None, "agent"))
        self.assertEqual(json.loads(lg["tools"]), [{"name": "get_kpis", "args": {}, "ok": True}])
        self.assertEqual((lg["question"], lg["reply"], lg["user_id"]), ("Hỏi thử", "Giá trị tồn là ...", self.user()["id"]))

    def test_hai_tool_mot_buoc(self):
        f = Fake(calls("get_kpis", "get_alerts"), reply("X"))
        r = self.ask(f)
        tm = self.tool_msgs(f.seen[1][0])
        self.assertEqual([m["tool_call_id"] for m in tm], ["c0", "c1"])
        self.assertEqual(r["tools"], ["Chỉ số KPI", "Cảnh báo"])

    def test_call_thieu_id_duoc_dat_id(self):
        step = calls("get_kpis")
        del step["calls"][0]["id"]
        f = Fake(step, reply("X"))
        self.ask(f)
        msgs = f.seen[1][0]
        self.assertEqual(msgs[-2]["tool_calls"][0]["id"], msgs[-1]["tool_call_id"])
        self.assertTrue(msgs[-1]["tool_call_id"])

    def test_cham_gioi_han_5_buoc(self):
        f = Fake(*[calls("get_kpis")] * agent.MAX_STEPS, reply("Hết bước"))
        r = self.ask(f)
        self.assertEqual(len(f.seen), agent.MAX_STEPS + 1)
        self.assertTrue(all(t for _, t in f.seen[:agent.MAX_STEPS]))
        self.assertIsNone(f.seen[-1][1])
        self.assertEqual((r["reply"], r["steps"], r["tools"]), ("Hết bước", 6, ["Chỉ số KPI"]))
        self.assertEqual(self.log()["steps"], 6)

    def test_tool_ngoai_quyen(self):
        f = Fake(calls("get_pos"), reply("Bạn không có quyền xem PO"))
        r = self.ask(f, user=self.user("t_soan"))
        self.assertNotIn("get_pos", {s["function"]["name"] for s in f.seen[0][1]})
        content = self.tool_msgs(f.seen[1][0])[0]["content"]
        self.assertIn("error", json.loads(content))
        self.assertNotIn("PO-", content)
        self.assertEqual(r["tools"], [])
        self.assertEqual(json.loads(self.log()["tools"])[0]["ok"], False)

    def test_tham_so_hong(self):
        f = Fake(calls("get_lots", args="{sku:"), reply("ok"))
        r = self.ask(f)
        self.assertIn("error", json.loads(self.tool_msgs(f.seen[1][0])[0]["content"]))
        self.assertEqual(r["reply"], "ok")

    def test_notools_lui_ve_snapshot(self):
        f = Fake(NoTools("Model hiện tại không hỗ trợ gọi tool."), reply("Theo ảnh chụp"))
        r = self.ask(f)
        self.assertIsNone(f.seen[1][1])
        self.assertIn("SỐ LIỆU KHO HIỆN TẠI", f.seen[1][0][0]["content"])
        self.assertEqual(r["mode"], "snapshot")
        self.assertTrue(r["reply"].startswith("Theo ảnh chụp") and r["reply"].endswith(agent.NOTE))
        self.assertEqual((self.log()["mode"], self.log()["error"]), ("snapshot", None))

    def test_llm_tools_0(self):
        os.environ["LLM_TOOLS"] = "0"
        f = Fake(reply("Theo ảnh chụp"))
        r = self.ask(f)
        self.assertIsNone(f.seen[0][1])
        self.assertEqual((r["mode"], len(f.seen)), ("snapshot", 1))

    def test_loi_llm_van_ghi_log(self):
        with self.assertRaises(LLMError):
            self.ask(Fake(LLMError("Hết lượt")))
        lg = self.log()
        self.assertEqual((lg["error"], lg["reply"], lg["steps"]), ("Hết lượt", None, 1))

    def test_khong_giu_khoa_khi_cho_llm(self):
        bad = []

        def write_elsewhere():
            c2 = sqlite3.connect(dbm.DB, timeout=0.1)
            try:
                c2.execute("BEGIN IMMEDIATE")
                c2.rollback()
            except sqlite3.OperationalError as e:
                bad.append(str(e))
            finally:
                c2.close()

        self.ask(Fake(calls("get_kpis"), reply("X"), hook=write_elsewhere))
        self.assertEqual(bad, [])

    def test_loi_dan_theo_role(self):
        f = Fake(reply("X"))
        self.ask(f, user=self.user("t_soan"))
        sys = f.seen[0][0][0]["content"]
        for s in [dbm.day(), "Người Soạn Thử", "KHÔNG được xem", "Xem đơn mua (PO)"]:
            self.assertIn(s, sys)
        f = Fake(reply("X"))
        self.ask(f)
        self.assertNotIn("KHÔNG được xem", f.seen[0][0][0]["content"])

    def test_lich_su_duoc_gui_kem(self):
        f = Fake(reply("X"))
        hist = [{"role": "user", "content": "câu trước"}, {"role": "assistant", "content": "đáp trước"}]
        self.ask(f, hist=hist, text="câu này")
        self.assertEqual([m["content"] for m in f.seen[0][0][1:]], ["câu trước", "đáp trước", "câu này"])


if __name__ == "__main__":
    unittest.main()
