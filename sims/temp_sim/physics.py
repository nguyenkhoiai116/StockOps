"""Mô hình vật lý nhiệt độ / độ ẩm và phân tích AIoT tại biên cho 4 khu kho.

Mô phỏng 4 khu chuẩn của kho StockOps:
  - DRY: Kho khô (15..30°C)
  - CHL: Kho mát (2..8°C)
  - FRZ: Kho đông (-25..-18°C)
  - COS: Kho mỹ phẩm (15..28°C)

Áp dụng mô hình làm lạnh Newton + dao động môi trường ngày/đêm + quán tính nhiệt
khi mở cửa, xả đá, hỏng máy nén hoặc mất điện; kèm ước lượng tốc độ biến thiên
và thời gian dự kiến vượt ngưỡng (Edge AIoT) trên cửa sổ trượt.
"""
import math
import random
import threading
from collections import deque
from datetime import timedelta

# Cấu hình vật lý mặc định cho từng khu (khớp ngưỡng tmin/tmax trong data/zones.csv)
ZONE_SPECS = {
    "DRY": {
        "name": "Kho khô",
        "sensor_id": "SHT30-DRY-01",
        "tmin": 15.0,
        "tmax": 30.0,
        "setpoint": 25.0,
        "hum_set": 58.0,
        "k_cool": 0.0022,   # thông gió / điều hòa nhẹ
        "k_env": 0.0010,
        "door_heat": 0.015,
        "noise": 0.06,
    },
    "CHL": {
        "name": "Kho mát 2-8°C",
        "sensor_id": "SHT30-CHL-01",
        "tmin": 2.0,
        "tmax": 8.0,
        "setpoint": 4.5,
        "hum_set": 74.0,
        "k_cool": 0.0055,   # máy lạnh kho mát hồi nhiệt nhanh
        "k_env": 0.00018,   # vách cách nhiệt kho mát
        "door_heat": 0.045, # mở cửa kho mát khiến nhiệt tăng nhanh
        "noise": 0.04,
    },
    "FRZ": {
        "name": "Kho đông -18°C",
        "sensor_id": "SHT30-FRZ-01",
        "tmin": -25.0,
        "tmax": -18.0,
        "setpoint": -21.0,
        "hum_set": 54.0,
        "k_cool": 0.0065,
        "k_env": 0.00015,   # vách cách nhiệt kho đông
        "door_heat": 0.060,
        "noise": 0.05,
    },
    "COS": {
        "name": "Kho mỹ phẩm",
        "sensor_id": "SHT30-COS-01",
        "tmin": 15.0,
        "tmax": 28.0,
        "setpoint": 22.5,
        "hum_set": 50.0,
        "k_cool": 0.0038,
        "k_env": 0.0011,
        "door_heat": 0.022,
        "noise": 0.05,
    },
}


def diurnal_ambient(ts, base_temp=31.0, base_hum=72.0):
    """Nhiệt độ & độ ẩm môi trường ngoài trời theo chu kỳ ngày/đêm.

    Đỉnh nóng ~14:00 (+3.5°C), thấp nhất ~04:00 (-3.5°C).
    """
    hour = ts.hour + ts.minute / 60.0 + ts.second / 3600.0
    wave = math.sin((hour - 8.5) / 24.0 * 2.0 * math.pi)
    t_env = base_temp + 3.5 * wave
    h_env = max(35.0, min(95.0, base_hum - 8.0 * wave))
    return t_env, h_env


def _linear_slope_per_min(points):
    """Hồi quy tuyến tính đơn giản: trả về tốc độ thay đổi (°C/phút) trên danh sách (t_sec, temp)."""
    n = len(points)
    if n < 3:
        return 0.0
    t0 = points[0][0]
    xs = [(p[0] - t0) / 60.0 for p in points]
    ys = [p[1] for p in points]
    span = xs[-1] - xs[0]
    if span < 0.25:
        return 0.0
    mx = sum(xs) / n
    my = sum(ys) / n
    denom = sum((x - mx) ** 2 for x in xs)
    if denom <= 1e-9:
        return 0.0
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / denom


class ZoneThermalState:
    """Trạng thái nhiệt - ẩm và các sự cố đang hoạt động của 1 khu kho."""

    def __init__(self, code, spec, history_len=240):
        self.code = code
        self.spec = spec
        self.temp = spec["setpoint"]
        self.hum = spec["hum_set"]
        self.compressor_fault = False
        self.door_sec = 0.0      # số giây mô phỏng cửa còn đang mở
        self.defrost_sec = 0.0   # số giây mô phỏng đang xả đá
        self.history = deque(maxlen=history_len)

    def reset(self):
        self.temp = self.spec["setpoint"]
        self.hum = self.spec["hum_set"]
        self.compressor_fault = False
        self.door_sec = 0.0
        self.defrost_sec = 0.0
        self.history.clear()

    def active_events(self, power_outage=False):
        ev = []
        if power_outage:
            ev.append("power_outage")
        if self.compressor_fault:
            ev.append("compressor_fault")
        if self.door_sec > 0:
            ev.append("door_open")
        if self.defrost_sec > 0:
            ev.append("defrost")
        return ev

    def step(self, dt_sec, sim_now, ambient_temp, ambient_hum, power_outage=False, rng=None):
        """Tiến hóa trạng thái nhiệt - ẩm trong dt_sec giây mô phỏng (chia bước nhỏ để ổn định)."""
        if dt_sec <= 0:
            return
        rng = rng or random
        t_env, h_env = diurnal_ambient(sim_now, ambient_temp, ambient_hum)

        # Chia nhỏ bước tối đa 30s để phương trình vi phân luôn ổn định ngay cả ở tốc độ x3600
        steps = max(1, int(math.ceil(dt_sec / 30.0)))
        sub_dt = dt_sec / steps
        sp = self.spec

        for _ in range(steps):
            cooling_on = (not power_outage) and (not self.compressor_fault) and (self.defrost_sec <= 0)
            k_cool = sp["k_cool"] if cooling_on else 0.0
            k_env = sp["k_env"] * (1.8 if self.door_sec > 0 else 1.0)

            q_door = sp["door_heat"] if self.door_sec > 0 else 0.0
            q_defrost = 0.018 if self.defrost_sec > 0 else 0.0

            d_temp = (
                -k_cool * (self.temp - sp["setpoint"])
                + k_env * (t_env - self.temp)
                + q_door
                + q_defrost
            ) * sub_dt
            noise_t = rng.gauss(0.0, sp["noise"] * math.sqrt(min(sub_dt, 30.0) / 30.0))
            self.temp += d_temp + noise_t

            # Độ ẩm: tiến về hum_set khi máy lạnh chạy, kéo về h_env khi mở cửa hoặc mất lạnh
            h_target = h_env if (self.door_sec > 0 or not cooling_on) else sp["hum_set"]
            k_hum = 0.008 if self.door_sec > 0 else 0.003
            d_hum = k_hum * (h_target - self.hum) * sub_dt
            noise_h = rng.gauss(0.0, 0.15 * math.sqrt(min(sub_dt, 30.0) / 30.0))
            self.hum = max(20.0, min(98.0, self.hum + d_hum + noise_h))

            if self.door_sec > 0:
                self.door_sec = max(0.0, self.door_sec - sub_dt)
            if self.defrost_sec > 0:
                self.defrost_sec = max(0.0, self.defrost_sec - sub_dt)

        epoch = sim_now.timestamp()
        self.history.append({
            "epoch": epoch,
            "ts": sim_now.isoformat(timespec="seconds"),
            "temp": round(self.temp, 2),
            "hum": round(self.hum, 1),
        })

    def edge_analysis(self):
        """Phân tích AIoT tại biên: tốc độ (°C/phút), dự báo vượt ngưỡng (ETA), mức cảnh báo."""
        sp = self.spec
        t = round(self.temp, 2)
        h = round(self.hum, 1)

        # Lấy tối đa 30 điểm gần nhất (hoặc cửa sổ 15 phút mô phỏng)
        recent = list(self.history)[-30:]
        pts = [(p["epoch"], p["temp"]) for p in recent]
        rate = _linear_slope_per_min(pts)

        eta_min = None
        breach_dir = None
        if t > sp["tmax"] or t < sp["tmin"]:
            status = "critical"
            breach_dir = "high" if t > sp["tmax"] else "low"
            eta_min = 0.0
        else:
            if rate > 0.02 and t < sp["tmax"]:
                eta_min = round((sp["tmax"] - t) / rate, 1)
                breach_dir = "high"
            elif rate < -0.02 and t > sp["tmin"]:
                eta_min = round((t - sp["tmin"]) / abs(rate), 1)
                breach_dir = "low"

            near_edge = (sp["tmax"] - t) <= 1.0 or (t - sp["tmin"]) <= 1.0
            fast_drift = eta_min is not None and eta_min <= 20.0
            status = "warn" if (near_edge or fast_drift) else "ok"

        return {
            "temp": t,
            "hum": h,
            "rate_c_per_min": round(rate, 3),
            "eta_breach_min": eta_min,
            "breach_dir": breach_dir,
            "status": status,
        }


class WarehouseThermalSim:
    """Bộ mô phỏng nhiệt độ toàn kho (4 khu + môi trường + sự cố + backfill)."""

    def __init__(self, ambient_temp=31.0, ambient_hum=72.0, seed=None):
        self._lock = threading.Lock()
        self._rng = random.Random(seed)
        self.ambient_temp = float(ambient_temp)
        self.ambient_hum = float(ambient_hum)
        self.power_outage = False
        self.zones = {code: ZoneThermalState(code, spec) for code, spec in ZONE_SPECS.items()}

    def set_ambient(self, temp=None, hum=None):
        with self._lock:
            if temp is not None:
                self.ambient_temp = max(10.0, min(48.0, float(temp)))
            if hum is not None:
                self.ambient_hum = max(20.0, min(98.0, float(hum)))

    def trigger_event(self, event, zone=None, active=True, duration_sec=180.0):
        """Kích hoạt hoặc tắt sự cố AIoT: door_open, compressor_fault, defrost, power_outage."""
        with self._lock:
            if event == "power_outage":
                self.power_outage = bool(active)
                return {"event": event, "active": self.power_outage}

            if zone not in self.zones:
                raise ValueError(f"Khu không hợp lệ: {zone}")
            z = self.zones[zone]
            if event == "compressor_fault":
                z.compressor_fault = bool(active)
                return {"event": event, "zone": zone, "active": z.compressor_fault}
            if event == "door_open":
                z.door_sec = float(duration_sec) if active else 0.0
                return {"event": event, "zone": zone, "active": z.door_sec > 0, "duration_sec": z.door_sec}
            if event == "defrost":
                z.defrost_sec = float(duration_sec) if active else 0.0
                return {"event": event, "zone": zone, "active": z.defrost_sec > 0, "duration_sec": z.defrost_sec}
            raise ValueError(f"Sự cố không hỗ trợ: {event}")

    def reset(self):
        with self._lock:
            self.power_outage = False
            for z in self.zones.values():
                z.reset()

    def step(self, dt_sec, sim_now):
        """Chạy 1 bước mô phỏng cho cả 4 khu và trả về payload chuẩn Ingest API."""
        with self._lock:
            readings = []
            for code, z in self.zones.items():
                z.step(dt_sec, sim_now, self.ambient_temp, self.ambient_hum, self.power_outage, self._rng)
                edge = z.edge_analysis()
                readings.append({
                    "sensor_id": z.spec["sensor_id"],
                    "zone": code,
                    "temp": edge["temp"],
                    "hum": edge["hum"],
                    "ts": sim_now.isoformat(timespec="seconds"),
                    "status": edge["status"],
                    "rate_c_per_min": edge["rate_c_per_min"],
                    "eta_breach_min": edge["eta_breach_min"],
                    "events": z.active_events(self.power_outage),
                })
            return {
                "source": "temp_sim",
                "readings": readings,
            }

    def snapshot(self, sim_now):
        """Trạng thái chi tiết cho giao diện AIoT và API /api/sim/state."""
        with self._lock:
            t_env, h_env = diurnal_ambient(sim_now, self.ambient_temp, self.ambient_hum)
            zones_out = []
            for code, z in self.zones.items():
                edge = z.edge_analysis()
                sp = z.spec
                zones_out.append({
                    "code": code,
                    "name": sp["name"],
                    "sensor_id": sp["sensor_id"],
                    "tmin": sp["tmin"],
                    "tmax": sp["tmax"],
                    "setpoint": sp["setpoint"],
                    "temp": edge["temp"],
                    "hum": edge["hum"],
                    "rate_c_per_min": edge["rate_c_per_min"],
                    "eta_breach_min": edge["eta_breach_min"],
                    "breach_dir": edge["breach_dir"],
                    "status": edge["status"],
                    "compressor_fault": z.compressor_fault,
                    "door_open_sec": round(z.door_sec, 0),
                    "defrost_sec": round(z.defrost_sec, 0),
                    "events": z.active_events(self.power_outage),
                    "history": list(z.history)[-90:],
                })
            return {
                "ambient": {
                    "base_temp": round(self.ambient_temp, 1),
                    "base_hum": round(self.ambient_hum, 1),
                    "diurnal_temp": round(t_env, 2),
                    "diurnal_hum": round(h_env, 1),
                },
                "power_outage": self.power_outage,
                "zones": zones_out,
            }

    def generate_backfill(self, start_dt, days=7, step_min=15, seed=42):
        """Sinh dữ liệu lịch sử không làm ảnh hưởng tới trạng thái live hiện tại.

        Dùng chung mô hình vật lý + thi thoảng chèn sự cố mở cửa ngẫu nhiên để tạo
        dữ liệu có quy luật ẩn + nhiễu cho bài toán ML sau này.
        """
        rng = random.Random(seed)
        sim = WarehouseThermalSim(self.ambient_temp, self.ambient_hum, seed=seed)
        total_steps = int(days * 24 * 60 / step_min)
        dt_sec = step_min * 60
        out = []

        for i in range(total_steps):
            ts = start_dt + timedelta(minutes=i * step_min)
            # Giờ làm việc (8h-17h): thỉnh thoảng mở cửa kho nhập/xuất hàng
            if 8 <= ts.hour <= 17:
                for code in ("DRY", "CHL", "FRZ", "COS"):
                    if rng.random() < 0.04:
                        sim.zones[code].door_sec = rng.uniform(90, 240)
            payload = sim.step(dt_sec, ts)
            out.extend(payload["readings"])
        return out
