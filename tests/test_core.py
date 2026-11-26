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


class ForeignKeyTest(Base):
    def test_db_chan_lo_tro_toi_sku_khong_co(self):
        import sqlite3
        with self.assertRaises(sqlite3.IntegrityError):
            with self.con:
                self.con.execute("INSERT INTO batches (product_id,batch_no,exp,qty,zone,bin) VALUES (99999,'X','2099-01-01',1,'DRY',90)")

    def test_du_lieu_mau_khong_vi_pham_khoa_ngoai(self):
        self.assertEqual(self.con.execute("PRAGMA foreign_key_check").fetchall(), [])

    def test_api_tao_don_sku_sai_bao_400(self):
        r = self.admin().post("/api/orders", json={"customer": "Khách", "product_id": 99999, "qty": 5})
        self.assertEqual((r.status_code, r.get_json()["error"]), (400, "Sản phẩm không tồn tại"))

    def test_api_tao_don_danh_so_tiep(self):
        pid = self.product()
        n = self.one("SELECT COUNT(*) FROM sos")[0]
        self.assertEqual(self.admin().post("/api/orders", json={"customer": "Khách", "product_id": pid, "qty": 5}).status_code, 200)
        self.assertEqual(self.one("SELECT so_no FROM sos ORDER BY id DESC LIMIT 1"), (f"SO-{n + 1:03d}",))


class CancelTest(Base):
    """Hủy đơn và soạn lại: reserved phải luôn = tổng picks còn hiệu lực của các đơn 'picked'."""

    def setup_lots(self):
        pid = self.product()
        self.batch(pid, "XB", 10, 50, bin=50)
        self.batch(pid, "XA", 60, 50, bin=51)
        return pid

    def invariant(self):
        bad = self.con.execute("""SELECT b.batch_no, b.reserved,
                 (SELECT COALESCE(SUM(k.qty),0) FROM picks k JOIN sos s ON s.id=k.so_id
                  WHERE k.batch_id=b.id AND k.released=0 AND s.status='picked') AS want
                 FROM batches b WHERE b.reserved != want""").fetchall()
        self.assertEqual([tuple(r) for r in bad], [])

    def test_huy_don_da_soan_tra_hang_giu(self):
        pid = self.setup_lots()
        sid = self.order(pid, 80)
        self.go(core.do_pick, sid)
        self.go(core.do_cancel, sid)
        self.assertEqual(self.one("SELECT SUM(reserved) FROM batches WHERE product_id=?", (pid,)), (0,))
        self.assertEqual(self.one("SELECT status FROM sos WHERE id=?", (sid,)), ("cancelled",))
        self.assertEqual(self.one("SELECT COUNT(*), SUM(released) FROM picks WHERE so_id=?", (sid,)), (2, 2))   # còn lịch sử
        self.invariant()

    def test_huy_don_moi(self):
        sid = self.order(self.setup_lots(), 10)
        self.go(core.do_cancel, sid)
        self.assertEqual(self.one("SELECT status FROM sos WHERE id=?", (sid,)), ("cancelled",))

    def test_khong_huy_don_da_xuat(self):
        sid = self.order(self.setup_lots(), 10)
        self.go(core.do_pick, sid)
        self.go(core.do_ship, sid, DRY_CAR)
        with self.assertRaises(ValueError):
            self.go(core.do_cancel, sid)

    def test_soan_lai_roi_xuat_chi_tru_lan_soan_moi(self):
        pid = self.setup_lots()
        sid = self.order(pid, 30)
        self.go(core.do_pick, sid)
        self.go(core.do_unpick, sid)
        self.assertEqual(self.one("SELECT status FROM sos WHERE id=?", (sid,)), ("new",))
        self.go(core.do_pick, sid)
        self.invariant()
        self.go(core.do_ship, sid, DRY_CAR)
        self.assertEqual(self.one("SELECT SUM(qty), SUM(reserved) FROM batches WHERE product_id=?", (pid,)), (70, 0))
        self.invariant()

    def test_soan_lai_chi_cho_don_da_soan(self):
        sid = self.order(self.setup_lots(), 10)
        with self.assertRaises(ValueError):
            self.go(core.do_unpick, sid)

    def test_kpi_bo_don_da_huy(self):
        before = core.get_kpis(self.con)
        sid = self.order(self.setup_lots(), 10)
        self.go(core.do_cancel, sid)
        after = core.get_kpis(self.con)
        self.assertEqual((after["fill"], after["so_open"]), (before["fill"], before["so_open"]))

    def test_api_huy_va_soan_lai(self):
        pid = self.setup_lots()
        sid = self.order(pid, 10)
        c = self.admin()
        self.assertEqual(c.post(f"/api/orders/{sid}/pick").status_code, 200)
        self.assertEqual(c.post(f"/api/orders/{sid}/unpick").status_code, 200)
        self.assertEqual(c.post(f"/api/orders/{sid}/cancel").status_code, 200)
        self.assertEqual(c.post(f"/api/orders/{sid}/cancel").status_code, 400)   # hủy 2 lần


class ShipExpiredTest(Base):
    def test_lo_het_han_sau_khi_soan_khong_xuat_duoc(self):
        pid = self.product()
        bid = self.batch(pid, "XB", 10, 50, bin=50)
        self.batch(pid, "XA", 60, 50, bin=51)
        sid = self.order(pid, 30)
        self.go(core.do_pick, sid)
        with self.con:   # giả lập thời gian trôi: lô XB hết hạn trước khi kịp xuất
            self.con.execute("UPDATE batches SET exp=? WHERE id=?", (dbm.day(-1), bid))
        with self.assertRaisesRegex(ValueError, "XB"):
            self.go(core.do_ship, sid, DRY_CAR)
        self.assertEqual(self.one("SELECT qty, reserved FROM batches WHERE id=?", (bid,)), (50, 30))   # chưa trừ gì
        self.go(core.do_unpick, sid)
        self.go(core.do_pick, sid)
        self.assertEqual(self.picks(sid)[-1], ("XA", 30))   # soạn lại lấy lô còn hạn
        self.go(core.do_ship, sid, DRY_CAR)
        self.assertEqual(self.one("SELECT status FROM sos WHERE id=?", (sid,)), ("shipping",))

    def test_lo_het_han_dung_hom_nay_van_xuat_duoc(self):
        pid = self.product()
        self.batch(pid, "XT", 0, 50, bin=50)   # hạn dùng = hôm nay: còn dùng được hết ngày
        sid = self.order(pid, 10)
        self.go(core.do_pick, sid)
        self.go(core.do_ship, sid, DRY_CAR)


class LedgerTest(Base):
    """Sổ giao dịch txs phải đối soát được với tồn: SUM(txs.qty) của 1 lô = batches.qty."""

    def test_du_lieu_mau_khop_so(self):
        self.assertEqual(core.ledger_gaps(self.con), [])
        self.assertEqual(self.one("SELECT COUNT(*) FROM txs WHERE batch_id IS NULL"), (0,))

    def test_du_lieu_mau_giu_dung_ton_cuoi(self):
        got = dict(self.con.execute("SELECT batch_no, qty FROM batches WHERE batch_no LIKE 'L24%'").fetchall())
        self.assertEqual(got, {"L2401": 400, "L2402": 500, "L2403": 600, "L2404": 60, "L2405": 120, "L2406": 120,
                               "L2407": 150, "L2408": 40, "L2409": 100, "L2410": 45, "L2411": 120, "L2412": 200,
                               "L2413": 120})
        self.assertEqual(self.one("SELECT reserved FROM batches WHERE batch_no='L2407'"), (40,))   # SO-004 đã soạn

    def test_lich_su_xuat_co_ngay_qua_khu(self):
        n = self.one("SELECT COUNT(*) FROM txs WHERE kind='OUT' AND substr(ts,1,10) < ?", (dbm.day(),))[0]
        self.assertEqual(n, 3)   # 3 đơn đã giao SO-006, SO-007, SO-008

    def test_thao_tac_qua_api_van_khop_va_ghi_nguoi_lam(self):
        c = self.admin()
        pid = self.product()
        bid = self.batch(pid, "XA", 60, 50)
        with self.con:   # lô thử dựng tay -> ghi IN đầu kỳ cho khớp như lô thật
            dbm.log(self.con, "IN", pid, "XA", 50, "đầu kỳ thử", bid=bid)
        po = c.post("/api/pos", json={"product_id": pid, "qty": 30})
        self.assertEqual(po.status_code, 200)
        po_id = self.one("SELECT id FROM pos ORDER BY id DESC LIMIT 1")[0]
        self.assertEqual(c.post(f"/api/pos/{po_id}/receive", json={"batch_no": "XN", "exp": dbm.day(90), "qty": 30}).status_code, 200)
        sid = self.order(pid, 60)
        self.assertEqual(c.post(f"/api/orders/{sid}/pick").status_code, 200)
        self.assertEqual(c.post(f"/api/orders/{sid}/ship", json={"plate": DRY_CAR}).status_code, 200)
        self.assertEqual(c.post(f"/api/inventory/{bid}/adjust", json={"delta": -0}).status_code, 400)
        nb = self.one("SELECT id FROM batches WHERE batch_no='XN'")[0]
        self.assertEqual(c.post(f"/api/inventory/{nb}/adjust", json={"delta": -5, "note": "vỡ"}).status_code, 200)
        self.assertEqual(core.ledger_gaps(self.con), [])
        self.assertEqual(self.one("SELECT COUNT(*) FROM txs WHERE product_id=? AND who='admin'", (pid,)), (4,))   # IN, 2 OUT, ADJ

    def test_migration_dien_batch_id_cho_dong_cu(self):
        import sqlite3
        from wms.migrate import DIR
        con = sqlite3.connect(os.path.join(self.tmp, "old.db"))
        for f in sorted(DIR.glob("00[1-5]_*.sql")):
            con.executescript(f.read_text(encoding="utf-8"))
        con.execute("PRAGMA user_version=5")
        con.execute("INSERT INTO products (id,sku,name,storage) VALUES (1,'S1','A','dry')")
        con.execute("INSERT INTO zones (code,name,storage,cap,tmin,tmax,temp,hum) VALUES ('DRY','K','dry',100,0,40,20,50)")
        con.executemany("INSERT INTO batches (id,product_id,batch_no,exp,qty,zone,bin) VALUES (?,1,?,'2099-01-01',1,'DRY',?)",
                        [(1, "A1", 1), (2, "B1", 2), (3, "B1", 3)])   # B1 trùng số lô ở 2 lô
        con.executemany("INSERT INTO txs (ts,kind,product_id,batch_no,qty,note) VALUES ('t','IN',1,?,1,'')", [("A1",), ("B1",)])
        con.commit()
        from wms.migrate import migrate
        migrate(con)
        self.assertEqual(con.execute("SELECT batch_no, batch_id FROM txs ORDER BY id").fetchall(), [("A1", 1), ("B1", None)])
        con.close()


class ReceiveZoneTest(Base):
    """Nhận hàng khi có nhiều khu cùng loại kho (DRY và DRY2)."""

    def setUp(self):
        super().setUp()
        with self.con:
            self.con.execute("""INSERT INTO zones (code,name,storage,cap,tmin,tmax,temp,hum,racks,bays,levels)
                                VALUES ('DRY2','Kho khô 2','dry',1000,15,30,25,60,1,2,2)""")
        self.pid = self.product()

    def po(self):
        with self.con:
            return self.con.execute("INSERT INTO pos (po_no,product_id,qty,eta) VALUES (?,?,?,?)",
                                    (f"PO-T{secrets.token_hex(3)}", self.pid, 100, dbm.day())).lastrowid

    def recv(self, qty, zone=None):
        self.go(core.do_receive, self.po(), "XN", dbm.day(90), qty, 0, zone)
        return self.one("SELECT zone, bin FROM batches ORDER BY id DESC LIMIT 1")

    def test_chon_khu_con_trong_nhieu_nhat(self):
        # DRY còn ~16.000 trống, DRY2 1.000 -> vào DRY
        self.assertEqual(self.recv(10)[0], "DRY")
        with self.con:   # làm DRY gần đầy -> lần sau phải vào DRY2
            self.con.execute("UPDATE zones SET cap=(SELECT SUM(qty) FROM batches WHERE zone='DRY')+5 WHERE code='DRY'")
        self.assertEqual(self.recv(50), ("DRY2", 1))

    def test_chi_dinh_khu(self):
        self.assertEqual(self.recv(10, "DRY2")[0], "DRY2")

    def test_chi_dinh_khu_sai_loai_kho(self):
        with self.assertRaisesRegex(ValueError, "CHL"):
            self.recv(10, "CHL")

    def test_moi_khu_day_bao_ly_do_tung_khu(self):
        with self.assertRaises(ValueError) as e:
            self.recv(50_000)
        self.assertIn("Kho khô 2", str(e.exception))
        self.assertIn("Kho khô ", str(e.exception))

    def test_khu_het_o_thi_sang_khu_khac(self):
        with self.con:   # DRY2 chỉ có 4 ô, lấp kín cả 4
            for i in range(1, 5):
                self.con.execute("INSERT INTO batches (product_id,batch_no,exp,qty,zone,bin) VALUES (?,?,?,1,'DRY2',?)",
                                 (self.pid, f"F{i}", dbm.day(90), i))
        self.assertEqual(self.recv(10, None)[0], "DRY")
        with self.assertRaisesRegex(ValueError, "hết ô"):
            self.recv(10, "DRY2")

    def test_api_nhan_hang_vao_khu_chi_dinh(self):
        r = self.admin().post(f"/api/pos/{self.po()}/receive", json={"batch_no": "XN", "exp": dbm.day(90), "qty": 10, "zone": "DRY2"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.one("SELECT zone FROM batches WHERE batch_no='XN'"), ("DRY2",))


class BinTest(Base):
    def setup_two(self):
        pid = self.product()
        old = self.batch(pid, "XO", 60, 10, bin=50)
        self.go(core.do_adjust, old, -10, "hủy lô")   # ô 50 thành trống
        new = self.batch(pid, "XN", 60, 20, bin=50)   # ô 50 cấp cho lô mới
        return old, new

    def test_khong_tang_lai_lo_da_ve_0_khi_o_da_co_lo_khac(self):
        old, _ = self.setup_two()
        with self.assertRaisesRegex(ValueError, "DRY-50"):
            self.go(core.do_adjust, old, 5, "kiểm kê")

    def test_db_chan_2_lo_con_hang_cung_o(self):
        import sqlite3
        old, _ = self.setup_two()
        with self.assertRaises(sqlite3.IntegrityError):
            with self.con:
                self.con.execute("UPDATE batches SET qty=5 WHERE id=?", (old,))

    def test_tang_lai_lo_da_ve_0_khi_o_con_trong(self):
        pid = self.product()
        bid = self.batch(pid, "XO", 60, 10, bin=50)
        self.go(core.do_adjust, bid, -10, "nhầm")
        self.go(core.do_adjust, bid, 10, "sửa lại")
        self.assertEqual(self.one("SELECT qty FROM batches WHERE id=?", (bid,)), (10,))


class DateTest(Base):
    BAD = ["abc", "", "2026-13-01", "2026-02-30", "20991231", "2099-1-5", "2099/01/05", " ", "9999-99-99"]

    def test_as_day(self):
        self.assertEqual(dbm.as_day(" 2099-01-05 ", "Hạn"), "2099-01-05")
        for s in self.BAD + [None, 20991231]:
            with self.subTest(s=s), self.assertRaisesRegex(ValueError, "YYYY-MM-DD"):
                dbm.as_day(s, "Hạn")

    def test_nhan_hang_han_dung_sai_bao_400_va_khong_tao_lo(self):
        c, pid = self.admin(), self.product()
        with self.con:
            po = self.con.execute("INSERT INTO pos (po_no,product_id,qty,eta) VALUES ('PO-TD',?,10,?)", (pid, dbm.day())).lastrowid
        for s in self.BAD:
            with self.subTest(exp=s):
                r = c.post(f"/api/pos/{po}/receive", json={"batch_no": "XD", "exp": s, "qty": 10})
                self.assertEqual(r.status_code, 400)
        self.assertEqual(self.one("SELECT COUNT(*) FROM batches WHERE batch_no='XD'"), (0,))
        self.assertEqual(c.post(f"/api/pos/{po}/receive", json={"batch_no": "XD", "exp": dbm.day(30), "qty": 10}).status_code, 200)

    def test_ngay_po_va_han_giao_sai_bao_400(self):
        c, pid = self.admin(), self.product()
        self.assertEqual(c.post("/api/pos", json={"product_id": pid, "qty": 5, "eta": "mai"}).status_code, 400)
        self.assertEqual(c.post("/api/orders", json={"customer": "K", "product_id": pid, "qty": 5, "due": "2099-1-5"}).status_code, 400)
        self.assertEqual(c.post("/api/orders", json={"customer": "K", "product_id": pid, "qty": 5}).status_code, 200)   # bỏ trống = ngày mai


class TimeTest(unittest.TestCase):
    def tearDown(self):
        os.environ.pop("TZ_OFFSET", None)

    def test_mac_dinh_gio_viet_nam(self):
        from datetime import datetime, timedelta, timezone
        os.environ.pop("TZ_OFFSET", None)
        want = (datetime.now(timezone.utc) + timedelta(hours=7)).date().isoformat()
        self.assertEqual(dbm.day(), want)

    def test_khong_phu_thuoc_gio_may_chu(self):
        os.environ["TZ_OFFSET"] = "-12"
        west = dbm.day()
        os.environ["TZ_OFFSET"] = "14"
        self.assertGreater(dbm.day(), west)   # 2 nơi cách nhau 26 giờ luôn khác ngày

    def test_gio_ghi_so_khong_kem_mui_gio(self):
        self.assertEqual(len(dbm.now().isoformat(timespec="seconds")), 19)   # 'YYYY-MM-DDTHH:MM:SS'


class KvisScopeTest(Base):
    """Kvis chỉ nhận số liệu mà role của người hỏi được xem ở nơi khác trong web."""

    def test_moi_role_thay_dung_phan_dashboard(self):
        from wms.ai.prompts import snapshot
        for role in ("admin", "inbound", "storage", "picking", "shipping"):
            s = snapshot(self.con, role)
            self.assertIn("TỒN KHẢ DỤNG THEO SKU", s, role)
            self.assertIn("CẢNH BÁO", s, role)

    def test_role_khong_co_quyen_khong_thay_so_lieu(self):
        from wms.ai import prompts
        old = prompts.PARTS
        try:
            prompts.PARTS = [("inv.view", prompts.stock_part)]   # giả sử phần này cần quyền xem tồn theo lô
            self.assertIn("TỒN KHẢ DỤNG", prompts.snapshot(self.con, "storage"))
            s = prompts.snapshot(self.con, "shipping")   # role xuất kho không có inv.view
            self.assertNotIn("SKU-001", s)
            self.assertIn("không có quyền", s)
        finally:
            prompts.PARTS = old

    def test_moi_phan_deu_khai_quyen_co_that(self):
        from wms.ai.prompts import PARTS
        from wms.roles import PERMS
        for perm, fn in PARTS:
            self.assertIn(perm, PERMS, fn.__name__)
