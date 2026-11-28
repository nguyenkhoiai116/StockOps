"""Kiểm thử cho bộ mô phỏng nhiệt độ AIoT (sims/temp_sim)."""
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from sims.common.clock import SimClock, kho_tz
from sims.temp_sim.app import create_app
from sims.temp_sim.physics import WarehouseThermalSim


class TempSimPhysicsTest(unittest.TestCase):
    def test_on_dinh_khi_binh_thuong(self):
        sim = WarehouseThermalSim(ambient_temp=31.0, seed=1)
        now = datetime(2026, 11, 27, 12, 0, tzinfo=kho_tz(7))
        for i in range(10):
            payload = sim.step(60.0, now + timedelta(minutes=i))
        chl = next(r for r in payload["readings"] if r["zone"] == "CHL")
        self.assertEqual(chl["status"], "ok")
        self.assertTrue(2.0 <= chl["temp"] <= 8.0)

    def test_hong_may_nen_kho_mat_vuot_nguong(self):
        sim = WarehouseThermalSim(ambient_temp=33.0, seed=2)
        sim.trigger_event("compressor_fault", zone="CHL", active=True)
        now = datetime(2026, 11, 27, 13, 0, tzinfo=kho_tz(7))
        for i in range(45):
            payload = sim.step(60.0, now + timedelta(minutes=i))
        chl = next(r for r in payload["readings"] if r["zone"] == "CHL")
        self.assertGreater(chl["temp"], 8.0)
        self.assertEqual(chl["status"], "critical")
        self.assertIn("compressor_fault", chl["events"])

    def test_mo_cua_kho_tang_nhiet_roi_tu_dong(self):
        sim = WarehouseThermalSim(ambient_temp=34.0, seed=3)
        sim.trigger_event("door_open", zone="FRZ", active=True, duration_sec=120)
        now = datetime(2026, 11, 27, 14, 0, tzinfo=kho_tz(7))
        t0 = sim.zones["FRZ"].temp
        for i in range(2):
            sim.step(60.0, now + timedelta(minutes=i))
        self.assertGreater(sim.zones["FRZ"].temp, t0 + 1.0)
        # Sau 120s mô phỏng cửa tự đóng
        self.assertEqual(sim.zones["FRZ"].door_sec, 0.0)

    def test_mat_dien_anh_huong_tat_ca_khu(self):
        sim = WarehouseThermalSim(ambient_temp=32.0, seed=4)
        sim.trigger_event("power_outage", active=True)
        now = datetime(2026, 11, 27, 15, 0, tzinfo=kho_tz(7))
        payload = sim.step(60.0, now)
        for r in payload["readings"]:
            self.assertIn("power_outage", r["events"])

    def test_backfill_sinh_du_lieu_lich_su(self):
        sim = WarehouseThermalSim(seed=5)
        start = datetime(2026, 11, 20, 0, 0, tzinfo=kho_tz(7))
        rows = sim.generate_backfill(start, days=2, step_min=30)
        # 2 ngày * 48 bước/ngày * 4 khu = 384 bản ghi
        self.assertEqual(len(rows), 384)


class TempSimAppTest(unittest.TestCase):
    def setUp(self):
        self.app = create_app(start_worker=False)
        self.cli = self.app.test_client()

    def test_state_va_dieu_khien_su_co(self):
        r = self.cli.get("/api/sim/state")
        self.assertEqual(r.status_code, 200)
        d = r.get_json()
        self.assertEqual(len(d["warehouse"]["zones"]), 4)

        r2 = self.cli.post("/api/sim/clock", json={"speed": 3600, "paused": True})
        self.assertEqual(r2.status_code, 200)
        self.assertEqual(r2.get_json()["clock"]["speed"], 3600)
        self.assertTrue(r2.get_json()["clock"]["paused"])

        r3 = self.cli.post("/api/sim/event", json={"event": "compressor_fault", "zone": "CHL", "active": True})
        self.assertEqual(r3.status_code, 200)
        chl = next(z for z in r3.get_json()["warehouse"]["zones"] if z["code"] == "CHL")
        self.assertTrue(chl["compressor_fault"])

    def test_push_http_khong_phu_thuoc_wms(self):
        with patch("sims.common.client.requests.post") as mock_post:
            mock_post.return_value.status_code = 200
            mock_post.return_value.text = "ok"
            r = self.cli.post("/api/sim/target", json={
                "base_url": "http://localhost:5000",
                "ingest_key": "secret-123",
                "push_now": True,
            })
            self.assertEqual(r.status_code, 200)
            self.assertTrue(r.get_json()["push_result"]["ok"])
            _, kwargs = mock_post.call_args
            self.assertEqual(kwargs["headers"]["X-Ingest-Key"], "secret-123")
            self.assertEqual(kwargs["json"]["source"], "temp_sim")
            self.assertEqual(len(kwargs["json"]["readings"]), 4)

    def test_export_csv_va_backfill(self):
        r_csv = self.cli.get("/api/sim/export.csv")
        self.assertEqual(r_csv.status_code, 200)
        self.assertIn("SHT30-CHL-01", r_csv.get_data(as_text=True))

        r_bf = self.cli.post("/api/sim/backfill", json={"days": 1, "step_min": 60})
        self.assertEqual(r_bf.status_code, 200)
        self.assertEqual(r_bf.get_json()["count"], 96)

    def test_khong_import_wms(self):
        sims_dir = Path(__file__).resolve().parent.parent / "sims"
        for py in sims_dir.rglob("*.py"):
            txt = py.read_text(encoding="utf-8")
            self.assertNotIn("import wms", txt, f"{py} không được import wms")
            self.assertNotIn("from wms", txt, f"{py} không được import wms")


if __name__ == "__main__":
    unittest.main()
