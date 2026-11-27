"""Kiểm thử toàn diện quy trình 3 nhóm: Inbound (CV1–CV4), Storage & Inventory (CV1–CV5),
Outbound (CV1–CV5), Phối hợp (Chat nội bộ & Audit Trail) và Kvis lọc theo vai trò.
"""
import os
import secrets
import shutil
import tempfile
import unittest

from wms import create_app
from wms import db as dbm
from wms.ai.prompts import snapshot
from wms.db import day
from wms.features import auth
from wms.users import set_password

PW = secrets.token_urlsafe(12)


class TestWorkflows(unittest.TestCase):
    def setUp(self):
        self.old, self.tmp = dbm.DB, tempfile.mkdtemp()
        dbm.DB = os.path.join(self.tmp, "test.db")
        auth.fails.clear()
        self.app = create_app()
        con = dbm.db()
        with con:
            for u in ("admin", "nhap01", "luu01", "soan01", "xuat01"):
                set_password(con, u, PW)
        con.close()

    def tearDown(self):
        dbm.DB = self.old
        shutil.rmtree(self.tmp)

    def login(self, user):
        c = self.app.test_client()
        r = c.post("/api/login", json={"user": user, "pass": PW})
        self.assertEqual(r.status_code, 200)
        return c

    def test_inbound_cv1_den_cv4_va_synergy(self):
        c = self.login("nhap01")
        pos = c.get("/api/pos").get_json()
        po1 = next(x for x in pos if x["po_no"] == "PO-001")
        po2 = next(x for x in pos if x["po_no"] == "PO-002")
        self.assertEqual(po1["priority"], "urgent")
        self.assertTrue(len(po2["ai_issues"]) >= 2)   # PO-002 cố ý thiếu ASN + sai UOM

        # Chưa chuẩn hóa PO-002 -> không cho validate
        self.assertEqual(c.post(f"/api/pos/{po2['id']}/validate").status_code, 400)
        self.assertEqual(c.post(f"/api/pos/{po2['id']}/asn", json={
            "asn_no": "ASN-9999", "asn_uom": "thùng", "asn_exp": day(300), "need_qc": 0,
        }).status_code, 200)
        self.assertEqual(c.post(f"/api/pos/{po2['id']}/validate").status_code, 200)

        # PO-001 đi đủ 4 bước: validate -> schedule -> area-ready -> arrive -> receive (lô cận date -> Synergy)
        self.assertEqual(c.post(f"/api/pos/{po1['id']}/validate").status_code, 200)
        self.assertEqual(c.post(f"/api/pos/{po1['id']}/schedule", json={
            "dock": "N1", "slot_time": "08:30-09:30", "workers": 3, "est_min": 45,
        }).status_code, 200)
        self.assertEqual(c.post(f"/api/pos/{po1['id']}/area-ready").status_code, 200)
        r_arr = c.post(f"/api/pos/{po1['id']}/arrive", json={"plate": "51D-999.01", "driver": "Anh Ba"})
        self.assertEqual(r_arr.status_code, 200)
        self.assertTrue(r_arr.get_json()["gate_pass"].startswith("GP-"))
        self.assertEqual(c.post(f"/api/pos/{po1['id']}/receive", json={
            "batch_no": "L-SYN-01", "exp": day(12), "qty": 100, "dmg": 0,
        }).status_code, 200)

        # Kiểm tra Cross-Functional Synergy: đã có thông báo cận date trong Team Chat & Audit Trail
        msgs = c.get("/api/collab/messages?channel=picking").get_json()["messages"]
        self.assertTrue(any("L-SYN-01" in m["body"] for m in msgs))

    def test_inbound_tu_choi_tai_dock_toan_bo_va_mot_phan(self):
        c = self.login("nhap01")
        pos = c.get("/api/pos").get_json()
        po1 = next(x for x in pos if x["po_no"] == "PO-001")   # Sữa tươi (chilled)
        po2 = next(x for x in pos if x["po_no"] == "PO-002")   # Dầu gội (cosmetics)

        # 1. Đo nhiệt độ hàng mát 14°C khi nhận -> bị chặn, yêu cầu Từ chối tại Dock
        r_bad_temp = c.post(f"/api/pos/{po1['id']}/receive", json={
            "batch_no": "L-FAIL", "exp": day(20), "qty": 100, "dmg": 0, "measured_temp": 14,
        })
        self.assertEqual(r_bad_temp.status_code, 400)
        self.assertIn("Từ chối tại Dock", r_bad_temp.get_json()["error"])

        # 2. Từ chối toàn bộ PO-001 tại Dock -> KHÔNG cộng tồn kho, tạo biên bản RTV-001
        con = dbm.db()
        n_batch_before = con.execute("SELECT COUNT(*) FROM batches").fetchone()[0]
        con.close()
        r_rej = c.post(f"/api/pos/{po1['id']}/reject", json={
            "reason": "Nhiệt độ thùng xe vượt ngưỡng bảo quản", "measured_temp": 14,
            "plate": "51D-778.90", "driver": "Anh Tư",
        })
        self.assertEqual(r_rej.status_code, 200)
        self.assertEqual(r_rej.get_json()["rej_no"], "RTV-001")
        con = dbm.db()
        self.assertEqual(con.execute("SELECT COUNT(*) FROM batches").fetchone()[0], n_batch_before)
        self.assertEqual(con.execute("SELECT status FROM pos WHERE id=?", (po1["id"],)).fetchone()[0], "rejected")
        con.close()

        # 3. Từ chối 1 phần PO-002 (nhận 92 thùng đạt, trả 8 thùng móp tại Dock) -> tự sinh RTV-002
        r_part = c.post(f"/api/pos/{po2['id']}/receive", json={
            "batch_no": "L-PART-01", "exp": day(300), "qty": 92, "dmg": 8,
            "dmg_reason": "8 thùng bị móp rách lúc dỡ xe",
        })
        self.assertEqual(r_part.status_code, 200)
        self.assertEqual(r_part.get_json()["rej_no"], "RTV-002")

        rejs = c.get("/api/pos/rejections").get_json()
        self.assertEqual(len(rejs), 2)
        self.assertEqual({r["kind"] for r in rejs}, {"full", "partial"})

    def test_storage_slotting_rop_transfer_va_cycle_count_rca(self):
        c = self.login("luu01")
        # CV1: Slotting Top 3
        sl = c.post("/api/storage/slot-suggest", json={"product_id": 1, "qty": 50, "exp": day(20)}).get_json()
        self.assertTrue(sl["ok"])
        self.assertEqual(len(sl["suggestions"]), 3)
        self.assertEqual(sl["zone"]["code"], "DRY")

        # CV2 & CV3 & CV5 intel
        intel = c.get("/api/storage/intel").get_json()
        self.assertEqual(len(intel["demand"]), 10)
        self.assertTrue(len(intel["risks"]) >= 1)
        self.assertTrue(len(intel["slob"]["skus"]) == 10)

        # CV4: Điều chuyển 2 đầu (chặn sai vùng nhiệt độ, cho phép đúng vùng)
        inv = c.get("/api/inventory").get_json()
        b_dry = next(b for b in inv["batches"] if b["zone"] == "DRY")
        self.assertEqual(c.post("/api/storage/transfers", json={
            "batch_id": b_dry["id"], "to_zone": "FRZ", "to_bin": 10,
        }).status_code, 400)   # sai vùng nhiệt -> chặn cứng
        self.assertEqual(c.post("/api/storage/transfers", json={
            "batch_id": b_dry["id"], "to_zone": "DRY", "to_bin": 20,
        }).status_code, 200)
        tid = c.get("/api/inventory").get_json()["transfers"][0]["id"]
        self.assertEqual(c.post(f"/api/storage/transfers/{tid}/confirm", json={"action": "complete"}).status_code, 200)
        b_after = next(b for b in c.get("/api/inventory").get_json()["batches"] if b["id"] == b_dry["id"])
        self.assertEqual(b_after["bin"], 20)

        # CV3: Kiểm kê Cut-off -> Recount -> RCA -> Duyệt
        b2 = next(b for b in inv["batches"] if b["zone"] == "COS")
        self.assertEqual(c.post("/api/storage/counts", json={"batch_id": b2["id"]}).status_code, 200)
        cid = c.get("/api/inventory").get_json()["counts"][0]["id"]
        # Đang khóa vị trí -> chặn điều chỉnh trực tiếp
        self.assertEqual(c.post(f"/api/inventory/{b2['id']}/adjust", json={"delta": -1}).status_code, 400)
        # Nhập số lệch lớn lần 1 -> hệ thống chuyển trạng thái 'recount'
        self.assertEqual(c.post(f"/api/storage/counts/{cid}/submit", json={"q_physical": b2["qty"] - 5}).status_code, 200)
        cnt = next(x for x in c.get("/api/inventory").get_json()["counts"] if x["id"] == cid)
        self.assertEqual(cnt["status"], "recount")
        self.assertTrue(bool(cnt["rca_hint"]))
        # Đếm lại lần 2 -> pending_approve -> duyệt điều chỉnh
        self.assertEqual(c.post(f"/api/storage/counts/{cid}/submit", json={"q_physical": b2["qty"] - 5}).status_code, 200)
        self.assertEqual(c.post(f"/api/storage/counts/{cid}/approve", json={"action": "approve"}).status_code, 200)
        b2_after = next(b for b in c.get("/api/inventory").get_json()["batches"] if b["id"] == b2["id"])
        self.assertEqual(b2_after["qty"], b2["qty"] - 5)
        self.assertEqual(b2_after["locked"], 0)

    def test_outbound_audit_lifo_qr_va_nhiet_do(self):
        c = self.login("xuat01")
        # CV1A: AI bóc tách file đơn hàng & chặn thiếu tồn 100%
        parsed = c.post("/api/outbound/parse", json={
            "text": f"Siêu thị An Phú, Nước ngọt có ga, 30, {day(1)}\nTạp hóa Minh Tâm, Há cảo đông lạnh, 999, {day(1)}",
        }).get_json()["items"]
        self.assertTrue(parsed[0]["ok"])
        self.assertFalse(parsed[1]["ok"])

        board = c.get("/api/outbound/board").get_json()
        # CV1B: SO-011 (Siêu thị Coop Q7 >= 65% HSD, lô L2413 cận date) phải bị chặn duyệt và có gợi ý Batch Swap
        q11 = next(q for q in board["ready_queue"] if q["so"]["so_no"] == "SO-011")
        self.assertFalse(q11["checks"]["hsd_ok"])
        self.assertFalse(q11["can_approve"])
        self.assertTrue(bool(q11["swap_hint"]))
        self.assertEqual(c.post(f"/api/outbound/orders/{q11['so']['id']}/audit", json={"action": "approve"}).status_code, 400)
        self.assertEqual(c.post(f"/api/outbound/orders/{q11['so']['id']}/audit", json={"action": "return"}).status_code, 200)

        # CV2 & CV3: AI Ghép chuyến SO-009 + SO-010 (cùng tuyến Q1 & kho khô) -> kiểm tra tiết kiệm & LIFO 2D
        r_con = c.post("/api/outbound/consolidate")
        self.assertEqual(r_con.status_code, 200)
        self.assertTrue(len(r_con.get_json()["trips"]) >= 1)
        self.assertEqual(c.post("/api/outbound/schedule-docks").status_code, 200)

        board2 = c.get("/api/outbound/board").get_json()
        tr = next(t for t in board2["trips"] if t["status"] == "scheduled")
        self.assertTrue(tr["saved_vnd"] > 0)   # ghép 2 đơn tiết kiệm 1 chuyến
        # Safety Guard thử xếp kèm hóa mỹ phẩm -> bật cảnh báo nhiễm chéo
        sf = c.post(f"/api/outbound/trips/{tr['id']}/safety-check", json={"simulate_cosmetics": True}).get_json()["plan"]
        self.assertTrue(any("NHIỄM CHÉO" in w["msg"] for w in sf["warnings"]))

        # CV5: Chốt lệnh -> Quét nhầm bị chặn -> Chưa đủ 100% bị khóa xuất cổng -> Quét đủ thì xuất thành công
        self.assertEqual(c.post(f"/api/outbound/trips/{tr['id']}/start-load").status_code, 200)
        self.assertEqual(c.post(f"/api/outbound/trips/{tr['id']}/scan", json={"code": "SO-NHAM"}).status_code, 400)
        self.assertEqual(c.post(f"/api/outbound/trips/{tr['id']}/dispatch").status_code, 400)
        for o in tr["orders"]:
            self.assertEqual(c.post(f"/api/outbound/trips/{tr['id']}/scan", json={"code": o["so_no"]}).status_code, 200)
        self.assertEqual(c.post(f"/api/outbound/trips/{tr['id']}/dispatch").status_code, 200)

        # CV4: Mô phỏng sự cố nhiệt độ thùng xe & gửi lệnh khẩn + hoàn tất e-POD
        self.assertEqual(c.post(f"/api/outbound/trips/{tr['id']}/alert", json={"mode": "sim_fault"}).status_code, 200)
        self.assertEqual(c.post(f"/api/outbound/trips/{tr['id']}/alert", json={"mode": "notify"}).status_code, 200)
        for o in tr["orders"]:
            self.assertEqual(c.post(f"/api/orders/{o['id']}/deliver", json={"epod_note": "Đã ký nhận đủ"}).status_code, 200)

    def test_collab_va_kvis_ca_nhan_hoa_theo_role(self):
        c = self.login("xuat01")
        self.assertEqual(c.post("/api/collab/messages", json={"channel": "picking", "ref_no": "SO-004", "body": "Kiểm tra giúp đơn lạnh"}).status_code, 200)
        msgs = c.get("/api/collab/messages?channel=picking").get_json()["messages"]
        self.assertTrue(any("Kiểm tra giúp đơn lạnh" in m["body"] for m in msgs))
        aud = c.get("/api/collab/audit").get_json()["items"]
        self.assertTrue(len(aud) >= 4)

        # Kvis lọc số liệu theo vai trò: nhân viên shipping KHÔNG thấy "Giá trị tồn:" tài chính như admin
        con = dbm.db()
        s_adm = snapshot(con, {"name": "Admin", "role": "admin"})
        s_shp = snapshot(con, {"name": "Phước", "role": "shipping"})
        con.close()
        self.assertIn("Giá trị tồn:", s_adm)
        self.assertNotIn("Giá trị tồn:", s_shp)
        self.assertIn("ĐƠN XUẤT ĐANG MỞ", s_shp)

    def test_upload_excel_xlsx_cho_po_va_so(self):
        import io
        import zipfile

        def make_xlsx(rows_data):
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w") as zf:
                trs = []
                for ri, row in enumerate(rows_data, 1):
                    cs = []
                    for ci, val in enumerate(row):
                        col = chr(65 + ci)
                        cs.append(f'<c r="{col}{ri}" t="inlineStr"><is><t>{val}</t></is></c>')
                    trs.append(f'<row r="{ri}">{"".join(cs)}</row>')
                sheet = (
                    '<?xml version="1.0" encoding="UTF-8"?>'
                    '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                    f'<sheetData>{"".join(trs)}</sheetData></worksheet>'
                )
                zf.writestr("xl/worksheets/sheet1.xml", sheet)
            buf.seek(0)
            return buf

        # 1. Nhân viên Nhập kho (nhap01) upload file Excel .xlsx tạo PO
        c_inb = self.login("nhap01")
        po_xlsx = make_xlsx([
            ["Sản phẩm", "Số lượng", "Ngày đến", "Mã ASN", "Đơn vị tính", "HSD", "Cần QC"],
            ["Sữa tươi tiệt trùng 1L", "120", day(2), "ASN-XL01", "thùng", day(28), "Có"],
            ["Mì gói tôm chua cay", "150", day(2), "", "lốc", "", "Không"],
        ])
        r = c_inb.post("/api/pos/parse", data={"file": (po_xlsx, "don-po.xlsx")}, content_type="multipart/form-data")
        self.assertEqual(r.status_code, 200)
        items = r.get_json()["items"]
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0]["sku"], "SKU-004")
        self.assertEqual(items[0]["priority"], "urgent")
        self.assertTrue(items[0]["need_qc"])
        self.assertTrue(items[0]["ok"])
        self.assertEqual(items[1]["sku"], "SKU-001")
        self.assertEqual(items[1]["confidence"], "low")   # thiếu ASN + sai UOM lốc

        # 2. Nhân viên Xuất kho (xuat01) upload file Excel .xlsx tạo SO
        c_shp = self.login("xuat01")
        so_xlsx = make_xlsx([
            ["Khách hàng", "Sản phẩm", "Số lượng", "Hạn giao"],
            ["Siêu thị An Phú", "Nước ngọt có ga 330ml", "35", day(2)],
        ])
        r2 = c_shp.post("/api/outbound/parse", data={"file": (so_xlsx, "don-so.xlsx")}, content_type="multipart/form-data")
        self.assertEqual(r2.status_code, 200)
        so_items = r2.get_json()["items"]
        self.assertEqual(len(so_items), 1)
        self.assertEqual(so_items[0]["sku"], "SKU-002")
        self.assertTrue(so_items[0]["ok"])


if __name__ == "__main__":
    unittest.main()
