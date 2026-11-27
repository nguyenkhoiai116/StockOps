"""Chạy: python -m unittest tests.test_llm   (giả lập máy chủ LLM, không gọi mạng)"""
import os
import unittest
from unittest import mock

from wms.ai import llm

MSGS = [{"role": "user", "content": "Chào"}]
TOOLS = [{"type": "function", "function": {"name": "get_kpis", "description": "KPI", "parameters": {"type": "object", "properties": {}}}}]
USAGE = {"prompt_tokens": 12, "completion_tokens": 3}


def resp(status=200, msg=None, err=None):
    """Response giả của requests.post: status + body JSON kiểu /chat/completions."""
    r = mock.Mock(status_code=status)
    r.json.return_value = {"error": {"message": err}} if err else {
        "model": "m-thu", "usage": USAGE, "choices": [{"message": msg or {}}]}
    r.text = ""
    return r


class LlmTest(unittest.TestCase):
    def setUp(self):
        self.env = mock.patch.dict(os.environ, {"LLM_API_KEY": "khoa-gia", "LLM_MODEL": "m-thu"})
        self.env.start()

    def tearDown(self):
        self.env.stop()

    def run_with(self, r, **kw):
        with mock.patch("wms.ai.llm.requests.post", return_value=r) as post:
            return llm.chat(MSGS, **kw), post

    def test_tra_ve_dict(self):
        r, _ = self.run_with(resp(msg={"content": "Chào"}))
        self.assertEqual(r["text"], "Chào")
        self.assertEqual(r["calls"], [])
        self.assertEqual(r["model"], "m-thu")
        self.assertEqual(r["usage"], USAGE)

    def test_tool_calls_cho_phep_chu_rong(self):
        call = {"id": "c1", "type": "function", "function": {"name": "get_kpis", "arguments": "{}"}}
        r, _ = self.run_with(resp(msg={"content": None, "tool_calls": [call]}), tools=TOOLS)
        self.assertEqual(r["text"], "")
        self.assertEqual(r["calls"][0]["function"]["name"], "get_kpis")
        self.assertEqual(r["calls"][0]["id"], "c1")

    def test_rong_ca_hai_thi_bao_loi(self):
        # Model reasoning hay hết max_tokens cho phần suy nghĩ: content rỗng, không tool call
        with self.assertRaises(llm.LLMError) as e:
            self.run_with(resp(msg={"content": "", "reasoning": "..."}), tools=TOOLS)
        self.assertIn("rỗng", str(e.exception))

    def test_gui_tools_khi_co(self):
        _, post = self.run_with(resp(msg={"content": "ok"}), tools=TOOLS)
        self.assertEqual(post.call_args.kwargs["json"]["tools"], TOOLS)
        _, post = self.run_with(resp(msg={"content": "ok"}))
        self.assertNotIn("tools", post.call_args.kwargs["json"])

    def test_notools(self):
        r = resp(404, err="No endpoints found that support tool use")
        with self.assertRaises(llm.NoTools):
            self.run_with(r, tools=TOOLS)
        # Không gửi tools thì cùng lỗi đó chỉ là LLMError thường (vd sai tên model)
        with self.assertRaises(llm.LLMError) as e:
            self.run_with(r)
        self.assertNotIsInstance(e.exception, llm.NoTools)

    def test_loi_tool_call_id_khong_phai_notools(self):
        # Lỗi do chính request của mình (vd tool_call_id sai) có chữ "tool" nhưng không phải model thiếu tool
        r = resp(400, err="Invalid parameter: messages[3].tool_call_id does not match any tool call")
        with self.assertRaises(llm.LLMError) as e:
            self.run_with(r, tools=TOOLS)
        self.assertNotIsInstance(e.exception, llm.NoTools)


if __name__ == "__main__":
    unittest.main()
