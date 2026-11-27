"""Chạy: python -m unittest tests.test_tools   (tool đọc dữ liệu của Kvis, database tạm)

Các test kiểm giá trị cụ thể tự dựng SKU-T và lô T-..., không dựa vào dữ liệu mẫu (dữ liệu mẫu có thể đổi).
"""
import json
import os
import shutil
import tempfile
import unittest
from unittest import mock

from wms import core, create_app
from wms import db as dbm
from wms.ai import tools
from wms.roles import ROLES, can

ADMIN, PICK = {"role": "admin"}, {"role": "picking"}


class ToolsTest(unittest.TestCase):
    def setUp(self):
        self.old, self.tmp = dbm.DB, tempfile.mkdtemp()
        dbm.DB = os.path.join(self.tmp, "test.db")
        create_app()
        self.con = dbm.db()
        with self.con:
            dbm.lock(self.con)
            pid = self.con.execute("INSERT INTO products (sku,name,cat,unit,storage,price,safety) VALUES (?,?,?,?,?,?,?)",
                                   ("SKU-T", "Sữa chua thử Đà Lạt", "Thử", "thùng", "dry", 1000, 100)).lastrowid
            for no, exp, b in [("T-5", 5, 90), ("T-EXP", -3, 91), ("T-25", 25, 92)]:   # hạn sau 5 ngày / đã hết 3 ngày / sau 25 ngày
                self.con.execute("INSERT INTO batches (product_id,batch_no,exp,qty,zone,bin) VALUES (?,?,?,?,?,?)",
                                 (pid, no, dbm.day(exp), 10, "DRY", b))

    def tearDown(self):
        self.con.close()
        dbm.DB = self.old
        shutil.rmtree(self.tmp, ignore_errors=True)

    def call(self, name, args="{}", user=ADMIN):
        return tools.call(self.con, user, name, args)

    def test_moi_tool_chay_duoc(self):
        for name in tools.TOOLS:
            r = self.call(name)
            self.assertNotIn("error", r, name)
            json.dumps(r, ensure_ascii=False)

    def test_specs_theo_role(self):
        for role in ROLES:
            names = {s["function"]["name"] for s in tools.specs(role)}
            self.assertEqual(names, {n for n, t in tools.TOOLS.items() if can(role, t["perm"])}, role)
        self.assertNotIn("get_pos", {s["function"]["name"] for s in tools.specs("picking")})
        self.assertNotIn("get_lots", {s["function"]["name"] for s in tools.specs("shipping")})

    def test_ngoai_quyen_bi_chan(self):
        self.assertEqual(self.call("get_pos", user=PICK), {"error": "Không có quyền: Xem đơn mua (PO)"})

    def test_tham_so_hong(self):
        for args in ['{sku:', '[]', '{"near_days": "abc"}', '{"near_days": true}', '{"near_days": 999}']:
            self.assertIn("error", self.call("get_lots", args), args)
        self.assertIn("error", self.call("get_alerts", '{"kind": "xyz"}'))

    def test_args_rong_la_khong_tham_so(self):
        for args in ["", None, "null"]:
            self.assertNotIn("error", self.call("get_kpis", args), repr(args))

    def test_tool_bia(self):
        self.assertEqual(self.call("get_inventory"), {"error": "Không có tool get_inventory"})

    def test_sku_viet_thuong(self):
        r = self.call("get_stock", '{"sku": "sku-t"}')
        self.assertEqual([x["sku"] for x in r["rows"]], ["SKU-T"])

    def test_tim_khong_dau(self):
        for q in ["sua chua thu", "da lat", "ĐÀ LẠT"]:
            r = self.call("get_stock", json.dumps({"q": q}))
            self.assertEqual([x["sku"] for x in r["rows"]], ["SKU-T"], q)

    def test_lo_can_date(self):
        r = self.call("get_lots", '{"sku": "SKU-T", "near_days": 7}')
        lots = {x["batch_no"]: x for x in r["rows"]}
        self.assertEqual(set(lots), {"T-5", "T-EXP"})
        self.assertTrue(lots["T-EXP"]["expired"])
        self.assertFalse(lots["T-5"]["expired"])
        self.assertEqual((lots["T-5"]["days_left"], lots["T-5"]["bin"], lots["T-5"]["av"]), (5, "DRY-90", 10))

    def test_reorder_khop_core(self):
        self.assertEqual(self.call("get_reorder")["rows"], core.reorder(self.con))

    def test_loc_don_va_po(self):
        self.assertTrue(all(x["status"] == "new" for x in self.call("get_orders", '{"status": "new"}')["rows"]))
        self.assertTrue(all(x["status"] == "pending" for x in self.call("get_pos", '{"status": "PENDING"}')["rows"]))

    def test_don_va_po_xep_theo_han(self):
        # Danh sách bị cắt khi dài -> phải xếp theo hạn (sắp tới hạn nằm đầu), không theo thứ tự nhập
        pid = self.con.execute("SELECT id FROM products WHERE sku='SKU-T'").fetchone()[0]
        with self.con:
            dbm.lock(self.con)
            for no, d in [("SO-TB", 5), ("SO-TA", 1)]:
                self.con.execute("INSERT INTO sos (so_no,customer,product_id,qty,due) VALUES (?,?,?,?,?)",
                                 (no, "Khách thử", pid, 1, dbm.day(d)))
            for no, d in [("PO-TB", 5), ("PO-TA", 1)]:
                self.con.execute("INSERT INTO pos (po_no,product_id,qty,eta) VALUES (?,?,?,?)", (no, pid, 1, dbm.day(d)))
        self.assertEqual([x["so_no"] for x in self.call("get_orders", '{"sku": "SKU-T"}')["rows"]], ["SO-TA", "SO-TB"])
        self.assertEqual([x["po_no"] for x in self.call("get_pos", '{"sku": "SKU-T"}')["rows"]], ["PO-TA", "PO-TB"])

    def test_cat_theo_so_dong(self):
        n = self.con.execute("SELECT COUNT(*) FROM batches WHERE qty>0").fetchone()[0]
        with mock.patch.object(tools, "MAX_ROWS", 3):
            r = self.call("get_lots")
        self.assertEqual((len(r["rows"]), r["truncated"], r["count"]), (3, True, n))

    def test_cat_theo_so_ky_tu(self):
        with mock.patch.object(tools, "MAX_CHARS", 300):
            r = self.call("get_lots")
        self.assertLessEqual(len(json.dumps(r, ensure_ascii=False)), 300)
        self.assertTrue(r["truncated"])


if __name__ == "__main__":
    unittest.main()
