"""Chạy: python -m unittest tests.test_eval   (kiểm bộ chấm điểm Kvis, không gọi LLM)"""
import importlib.util
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

from wms import create_app
from wms import db as dbm
from wms.ai import tools
from wms.roles import ROLES

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("eval_agent", ROOT / "scripts" / "eval_agent.py")
ev = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ev)


class EvalTest(unittest.TestCase):
    def test_hit_so(self):
        self.assertTrue(ev.hit("Giá trị 1.234.000 đ", [1234000]))
        self.assertTrue(ev.hit("1234000", [1234000]))
        self.assertTrue(ev.hit("1,234,000", [1234000]))
        self.assertFalse(ev.hit("123400", [1234000]))
        self.assertFalse(ev.hit("11234000", [1234000]))
        self.assertTrue(ev.hit("Lấp đầy 85,3%", [85.3]))
        self.assertFalse(ev.hit("Lấp đầy 85,35%", [85.3]))
        self.assertTrue(ev.hit("OTIF 50%", [50.0]))
        self.assertTrue(ev.hit("po-001 đang chờ", ["PO-001"]))
        self.assertFalse(ev.hit("SKU-001 còn 120 thùng", ["SKU-001", 130]))   # phải có đủ mọi đáp án

    def test_denied(self):
        self.assertTrue(ev.denied("Bạn không có quyền xem PO", ["PO-001"]))
        self.assertFalse(ev.denied("PO-001 đang chờ, bạn không có quyền", ["PO-001"]))
        self.assertFalse(ev.denied("Không tra được", ["PO-001"]))   # phải nói tới quyền

    def test_score(self):
        A, D = {"ans": "x"}, {"deny": "x"}
        ok, err = {"mode": "agent", "reply": "SKU-001; Bạn không có quyền"}, {"mode": "error", "reply": ""}
        self.assertIs(ev.score(A, ok, ["SKU-001"]), True)
        self.assertIs(ev.score(A, err, []), False)        # lỗi gọi model không bao giờ tính là đạt
        self.assertIsNone(ev.score(A, ok, []))            # đáp án rỗng (dữ liệu không có) -> không chấm
        self.assertIs(ev.score(D, err, ["PO-001"]), False)
        self.assertIs(ev.score(D, ok, ["PO-001"]), True)

    def test_cau_tu_choi_khong_lo_qua_tool_duoc_phep(self):
        """Câu "deny" chỉ có nghĩa khi mọi tool role đó được dùng đều KHÔNG trả về chuỗi bị cấm.
        Nếu tool được phép (vd Cảnh báo, ai cũng xem) đã chứa chuỗi đó thì trả lời đúng lại bị chấm trượt."""
        qs = [q for q in json.loads((ROOT / "tests" / "ai_eval" / "questions.json").read_text(encoding="utf-8")) if "deny" in q]
        old, tmp = dbm.DB, tempfile.mkdtemp()
        dbm.DB = os.path.join(tmp, "test.db")
        try:
            create_app()
            con = dbm.db()
            for q in qs:
                banned = ev.DENY[q["deny"]](con)
                self.assertTrue(banned, q["id"])
                for s in tools.specs(q["role"]):
                    out = json.dumps(tools.call(con, {"role": q["role"]}, s["function"]["name"], "{}"), ensure_ascii=False)
                    self.assertEqual([b for b in banned if b in out], [], f"{q['id']} lộ qua {s['function']['name']}")
            con.close()
        finally:
            dbm.DB = old
            shutil.rmtree(tmp, ignore_errors=True)

    def test_moi_cau_co_ham(self):
        qs = json.loads((ROOT / "tests" / "ai_eval" / "questions.json").read_text(encoding="utf-8"))
        self.assertEqual(len(qs), 20)
        self.assertEqual(len({q["id"] for q in qs}), 20)
        self.assertGreaterEqual(sum("deny" in q for q in qs), 3)
        old, tmp = dbm.DB, tempfile.mkdtemp()
        dbm.DB = os.path.join(tmp, "test.db")
        try:
            create_app()
            con = dbm.db()
            for q in qs:
                self.assertIn(q["role"], ROLES, q["id"])
                self.assertTrue(q["q"].strip(), q["id"])
                fn = ev.ANS[q["ans"]] if "ans" in q else ev.DENY[q["deny"]]
                self.assertIsInstance(fn(con), list, q["id"])
            con.close()
        finally:
            dbm.DB = old
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
