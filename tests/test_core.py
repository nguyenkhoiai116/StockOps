"""Chạy: python -m unittest tests.test_core   (luật nghiệp vụ lõi, dùng database tạm)

Mỗi test dựng 1 SKU riêng (SKU-T) với lô có hạn dùng biết trước, nên kết quả
tính được bằng tay, không phụ thuộc dữ liệu mẫu.
"""
import os
import secrets
import shutil
import tempfile
import unittest

from wms import core, create_app
from wms import db as dbm
from wms.features import auth
from wms.users import set_password

PW = secrets.token_urlsafe(12)   # mật khẩu thử, sinh ngẫu nhiên mỗi lần chạy
DRY_CAR, COLD_CAR = "51C-123.45", "51D-678.90"   # 2 xe trong dữ liệu mẫu: xe thường, xe lạnh


class Base(unittest.TestCase):
    def setUp(self):
        self.old, self.tmp = dbm.DB, tempfile.mkdtemp()
        dbm.DB = os.path.join(self.tmp, "test.db")
        auth.fails.clear()
        self.app = create_app()
        self.con = dbm.db()
        with self.con:
            set_password(self.con, "admin", PW)

    def tearDown(self):
        self.con.close()
        dbm.DB = self.old
        shutil.rmtree(self.tmp, ignore_errors=True)

    # ---- dựng dữ liệu thử ----
    def product(self, storage="dry", safety=100):
        with self.con:
            return self.con.execute("INSERT INTO products (sku,name,cat,unit,storage,price,safety) VALUES (?,?,?,?,?,?,?)",
                                    ("SKU-T", "Hàng thử", "Thử", "thùng", storage, 1000, safety)).lastrowid

    def batch(self, pid, no, exp, qty, reserved=0, zone="DRY", bin=50):
        """exp: số ngày tới hạn tính từ hôm nay (âm = đã hết hạn)."""
        with self.con:
            return self.con.execute("INSERT INTO batches (product_id,batch_no,exp,qty,reserved,zone,bin) VALUES (?,?,?,?,?,?,?)",
                                    (pid, no, dbm.day(exp), qty, reserved, zone, bin)).lastrowid

    def order(self, pid, qty):
        with self.con:
            return self.con.execute("INSERT INTO sos (so_no,customer,product_id,qty,due) VALUES (?,?,?,?,?)",
                                    (f"SO-T{qty}", "Khách thử", pid, qty, dbm.day(1))).lastrowid

    def go(self, fn, *args):
        """Chạy 1 hàm nghiệp vụ trong 1 transaction có khóa, như core.run()."""
        with self.con:
            dbm.lock(self.con)
            fn(self.con, *args)

    def one(self, sql, args=()):
        return tuple(self.con.execute(sql, args).fetchone())

    def picks(self, sid):
        return [tuple(r) for r in self.con.execute(
            "SELECT b.batch_no, k.qty FROM picks k JOIN batches b ON b.id=k.batch_id WHERE k.so_id=? ORDER BY k.id", (sid,))]

    def admin(self):
        c = self.app.test_client()
        c.post("/api/login", json={"user": "admin", "pass": PW})
        return c


class FefoTest(Base):
    def test_lay_lo_het_han_som_nhat_truoc(self):
        pid = self.product()
        self.batch(pid, "XA", 60, 50, bin=50)
        self.batch(pid, "XB", 10, 50, bin=51)
        sid = self.order(pid, 30)
        self.go(core.do_pick, sid)
        self.assertEqual(self.picks(sid), [("XB", 30)])
        self.assertEqual(self.one("SELECT reserved FROM batches WHERE batch_no='XB'"), (30,))
        self.assertEqual(self.one("SELECT status FROM sos WHERE id=?", (sid,)), ("picked",))

    def test_chia_nhieu_lo_theo_han(self):
        pid = self.product()
        self.batch(pid, "XA", 60, 50, bin=50)
        self.batch(pid, "XB", 10, 50, bin=51)
        sid = self.order(pid, 80)
        self.go(core.do_pick, sid)
        self.assertEqual(self.picks(sid), [("XB", 50), ("XA", 30)])

    def test_bo_qua_lo_het_han(self):
        pid = self.product()
        self.batch(pid, "XC", -1, 100, bin=50)   # đã hết hạn: không được soạn dù còn nhiều
        self.batch(pid, "XA", 60, 50, bin=51)
        sid = self.order(pid, 40)
        self.go(core.do_pick, sid)
        self.assertEqual(self.picks(sid), [("XA", 40)])

    def test_chi_lay_phan_chua_giu(self):
        pid = self.product()
        self.batch(pid, "XB", 10, 50, reserved=45, bin=50)   # còn 5 khả dụng
        self.batch(pid, "XA", 60, 50, bin=51)
        sid = self.order(pid, 20)
        self.go(core.do_pick, sid)
        self.assertEqual(self.picks(sid), [("XB", 5), ("XA", 15)])

    def test_thieu_hang_tu_choi_ca_don(self):
        pid = self.product()
        self.batch(pid, "XC", -1, 100, bin=50)
        self.batch(pid, "XA", 60, 50, bin=51)
        sid = self.order(pid, 60)   # còn hạn chỉ có 50
        with self.assertRaises(ValueError):
            self.go(core.do_pick, sid)
        self.assertEqual(self.picks(sid), [])
        self.assertEqual(self.one("SELECT SUM(reserved) FROM batches WHERE product_id=?", (pid,)), (0,))
        self.assertEqual(self.one("SELECT status FROM sos WHERE id=?", (sid,)), ("new",))

    def test_don_da_soan_khong_soan_lai(self):
        pid = self.product()
        self.batch(pid, "XA", 60, 50)
        sid = self.order(pid, 10)
        self.go(core.do_pick, sid)
        with self.assertRaises(ValueError):
            self.go(core.do_pick, sid)
        self.assertEqual(self.one("SELECT reserved FROM batches WHERE batch_no='XA'"), (10,))


class ShipTest(Base):
    def picked(self, storage="dry", zone="DRY"):
        pid = self.product(storage)
        self.batch(pid, "XA", 60, 50, zone=zone, bin=20)
        sid = self.order(pid, 30)
        self.go(core.do_pick, sid)
        return pid, sid

    def test_xuat_tru_ton_va_ghi_so(self):
        pid, sid = self.picked()
        self.go(core.do_ship, sid, DRY_CAR)
        self.assertEqual(self.one("SELECT qty, reserved FROM batches WHERE batch_no='XA'"), (20, 0))
        self.assertEqual(self.one("SELECT kind, qty FROM txs WHERE batch_no='XA'"), ("OUT", -30))
        self.assertEqual(self.one("SELECT status, plate FROM sos WHERE id=?", (sid,)), ("shipping", DRY_CAR))

    def test_hang_mat_phai_di_xe_lanh(self):
        pid, sid = self.picked("chilled", "CHL")
        with self.assertRaises(ValueError):
            self.go(core.do_ship, sid, DRY_CAR)
        self.assertEqual(self.one("SELECT qty FROM batches WHERE batch_no='XA'"), (50,))
        self.go(core.do_ship, sid, COLD_CAR)
        self.assertEqual(self.one("SELECT status FROM sos WHERE id=?", (sid,)), ("shipping",))

    def test_hang_dong_phai_di_xe_lanh(self):
        pid, sid = self.picked("frozen", "FRZ")
        with self.assertRaises(ValueError):
            self.go(core.do_ship, sid, DRY_CAR)

    def test_chua_soan_khong_xuat_duoc(self):
        pid = self.product()
        self.batch(pid, "XA", 60, 50)
        sid = self.order(pid, 10)
        with self.assertRaises(ValueError):
            self.go(core.do_ship, sid, DRY_CAR)
        self.assertEqual(self.one("SELECT qty FROM batches WHERE batch_no='XA'"), (50,))


class AdjustTest(Base):
    """Điều chỉnh tồn qua API: không âm, không thấp hơn phần đã giữ, không vượt sức chứa khu."""

    def adj(self, bid, delta):
        return self.admin().post(f"/api/inventory/{bid}/adjust", json={"delta": delta, "note": "Kiểm kê thử"}).status_code

    def test_dieu_chinh_cap_nhat_va_ghi_so(self):
        bid = self.batch(self.product(), "XA", 60, 50)
        self.assertEqual(self.adj(bid, -5), 200)
        self.assertEqual(self.one("SELECT qty FROM batches WHERE id=?", (bid,)), (45,))
        self.assertEqual(self.one("SELECT kind, qty, note FROM txs WHERE batch_no='XA'"), ("ADJ", -5, "Kiểm kê thử"))

    def test_khong_cho_ton_am(self):
        bid = self.batch(self.product(), "XA", 60, 50)
        self.assertEqual(self.adj(bid, -51), 400)
        self.assertEqual(self.one("SELECT qty FROM batches WHERE id=?", (bid,)), (50,))

    def test_khong_giam_duoi_phan_da_giu(self):
        bid = self.batch(self.product(), "XA", 60, 50, reserved=30)
        self.assertEqual(self.adj(bid, -25), 400)   # còn 25 < 30 đã giữ
        self.assertEqual(self.adj(bid, -20), 200)   # còn 30 = đã giữ: được
        self.assertEqual(self.one("SELECT qty FROM batches WHERE id=?", (bid,)), (30,))

    def test_khong_vuot_suc_chua_khu(self):
        bid = self.batch(self.product(), "XA", 60, 50)
        cap, used = self.one("SELECT cap, (SELECT SUM(qty) FROM batches WHERE zone='DRY') FROM zones WHERE code='DRY'")
        self.assertEqual(self.adj(bid, cap - used + 1), 400)
        self.assertEqual(self.adj(bid, cap - used), 200)

    def test_so_khong_hop_le(self):
        bid = self.batch(self.product(), "XA", 60, 50)
        self.assertEqual(self.adj(bid, "abc"), 400)
        self.assertEqual(self.adj(bid, 0), 400)
        self.assertEqual(self.one("SELECT COUNT(*) FROM txs WHERE batch_no='XA'"), (0,))

    def test_body_sai_bao_loi_400(self):
        bid = self.batch(self.product(), "XA", 60, 50)
        self.assertEqual(self.admin().post(f"/api/inventory/{bid}/adjust", json=[1, 2]).status_code, 400)

    def test_do_adjust_goi_duoc_tu_core(self):
        """Tool đề xuất của Kvis sẽ gọi thẳng hàm này, không qua route."""
        bid = self.batch(self.product(), "XA", 60, 50, reserved=30)
        self.go(core.do_adjust, bid, -5, "Theo đề xuất thử")
        self.assertEqual(self.one("SELECT qty FROM batches WHERE id=?", (bid,)), (45,))
        self.assertEqual(self.one("SELECT qty, note FROM txs WHERE batch_no='XA'"), (-5, "Theo đề xuất thử"))
        with self.assertRaises(ValueError):
            self.go(core.do_adjust, bid, -20, "")   # còn 25 < 30 đã giữ


class ZoneStatusTest(Base):
    """Khu thử TST: 2 dãy x 2 ô x 3 tầng = 12 ô, sức chứa 400."""

    def zone(self):
        with self.con:
            self.con.execute("INSERT INTO zones (code,name,storage,cap,tmin,tmax,temp,hum,racks,bays,levels) "
                             "VALUES ('TST','Khu thử','test',400,2,8,5,60,2,2,3)")

    def status(self):
        return {z["code"]: z for z in core.zone_status(self.con)}

    def test_muc_day_va_so_o(self):
        self.zone()
        pid = self.product()
        self.batch(pid, "XA", 60, 100, zone="TST", bin=1)
        self.batch(pid, "XB", 60, 50, zone="TST", bin=2)
        z = self.status()["TST"]
        self.assertEqual((z["used"], z["pct"], z["bins"], z["cap"]), (150, 37.5, 12, 400))
        self.assertEqual((z["name"], z["storage"], z["temp"], z["tmin"], z["tmax"]), ("Khu thử", "test", 5, 2, 8))
        self.assertEqual((z["racks"], z["bays"], z["levels"]), (2, 2, 3))   # kho 3D cần 3 số này

    def test_khu_trong(self):
        self.zone()
        z = self.status()["TST"]
        self.assertEqual((z["used"], z["pct"]), (0, 0))

    def test_canh_bao_khi_khu_day_85(self):
        self.zone()
        bid = self.batch(self.product(), "XA", 60, 339, zone="TST", bin=1)
        cap = lambda: [a for a in core.get_alerts(self.con) if a["kind"] == "cap" and "Khu thử" in a["msg"]]
        self.assertEqual(cap(), [])   # 84,75%
        with self.con:
            self.con.execute("UPDATE batches SET qty=340 WHERE id=?", (bid,))
        self.assertEqual(len(cap()), 1)   # 85%


class ReorderTest(Base):
    def test_cong_thuc(self):
        # gợi ý = tồn an toàn x 2 - khả dụng - PO đang chờ, không âm
        for av, safety, pending, want in [(120, 200, 0, 280), (45, 50, 0, 55), (120, 200, 100, 180),
                                          (120, 200, 300, 0), (500, 200, 0, 0)]:
            self.assertEqual(core.reorder_qty(av, safety, pending), want, (av, safety, pending))

    def po(self, pid, qty, status="pending"):
        with self.con:
            self.con.execute("INSERT INTO pos (po_no,product_id,qty,eta,status) VALUES (?,?,?,?,?)",
                             (f"PO-T{qty}{status}", pid, qty, dbm.day(1), status))

    def test_tru_po_dang_cho_khong_tru_po_da_nhan(self):
        pid = self.product(safety=100)
        self.batch(pid, "XA", 60, 30)
        self.po(pid, 50)
        self.po(pid, 70, "received")   # đã nhận thì nằm trong tồn rồi, không được trừ lần nữa
        r = {x["sku"]: x for x in core.reorder(self.con)}["SKU-T"]
        self.assertEqual((r["av"], r["safety"], r["pending"], r["qty"]), (30, 100, 50, 120))

    def test_chi_liet_ke_sku_duoi_ton_an_toan(self):
        pid = self.product(safety=100)
        self.batch(pid, "XA", 60, 100)   # bằng tồn an toàn: không thiếu
        self.assertNotIn("SKU-T", [x["sku"] for x in core.reorder(self.con)])

    def test_dashboard_dung_goi_y_da_tru_po(self):
        pid = self.product(safety=100)
        self.batch(pid, "XA", 60, 30)
        self.po(pid, 50)
        tips = self.admin().get("/api/dashboard").get_json()["tips"]
        mine = [t for t in tips if "SKU-T" in t["title"]]
        self.assertEqual(len(mine), 1)
        self.assertIn("120", mine[0]["detail"])
        self.assertNotIn("170", mine[0]["detail"])   # 170 = công thức cũ, quên trừ PO


class CreatePoTest(Base):
    def test_tao_po_danh_so_tiep(self):
        pid = self.product()
        with self.con:
            dbm.lock(self.con)
            no = core.create_po(self.con, pid, 40, dbm.day(3))
        self.assertEqual(no, "PO-004")   # dữ liệu mẫu có PO-001..003
        self.assertEqual(self.one("SELECT product_id, qty, eta, status FROM pos WHERE po_no='PO-004'"),
                         (pid, 40, dbm.day(3), "pending"))

    def test_sku_khong_ton_tai(self):
        with self.assertRaises(ValueError):
            self.go(core.create_po, 99999, 40, dbm.day(3))
        self.assertEqual(self.one("SELECT COUNT(*) FROM pos"), (3,))

    def test_so_luong_phai_duong(self):
        pid = self.product()
        for qty in (0, -5):
            with self.assertRaises(ValueError):
                self.go(core.create_po, pid, qty, dbm.day(3))

    def test_api_tao_po(self):
        pid, c = self.product(), self.admin()
        self.assertEqual(c.post("/api/pos", json={"product_id": pid, "qty": 40}).status_code, 200)
        self.assertEqual(self.one("SELECT qty, eta FROM pos WHERE product_id=?", (pid,)), (40, dbm.day(1)))

    def test_api_body_sai_bao_loi_400(self):
        c = self.admin()
        for body in ([1, 2], {"qty": 40}, {"product_id": 99999, "qty": 40}, {"product_id": "x", "qty": 40}):
            self.assertEqual(c.post("/api/pos", json=body).status_code, 400, body)
        self.assertEqual(self.one("SELECT COUNT(*) FROM pos"), (3,))


if __name__ == "__main__":
    unittest.main()
