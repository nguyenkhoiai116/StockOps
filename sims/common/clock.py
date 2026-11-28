"""Đồng hồ mô phỏng thời gian: hỗ trợ chạy live (x1..x3600), tạm dừng và backfill lịch sử."""
import threading
from datetime import datetime, timedelta, timezone


def kho_tz(offset_hours=7):
    """Múi giờ kho (mặc định UTC+7)."""
    return timezone(timedelta(hours=offset_hours))


class SimClock:
    """Đồng hồ ảo thread-safe cho simulator.

    Tách riêng thời gian thực (monotonic) và thời gian mô phỏng để đổi tốc độ
    (x1, x60, x600, x3600) hoặc tạm dừng mà không làm giật mốc thời gian.
    """

    SPEEDS = (1, 60, 600, 3600)

    def __init__(self, start=None, speed=60, tz_offset=7):
        self._lock = threading.Lock()
        self.tz = kho_tz(tz_offset)
        self._sim_now = start or datetime.now(self.tz)
        self._last_real = self._mono()
        self._speed = speed if speed in self.SPEEDS else 60
        self._paused = False

    @staticmethod
    def _mono():
        import time
        return time.monotonic()

    def _advance_locked(self):
        now_real = self._mono()
        dt_real = max(0.0, now_real - self._last_real)
        self._last_real = now_real
        if not self._paused:
            self._sim_now += timedelta(seconds=dt_real * self._speed)

    def now(self):
        """Trả về thời gian mô phỏng hiện tại và số giây mô phỏng trôi qua từ lần trước."""
        with self._lock:
            self._advance_locked()
            return self._sim_now

    def step(self):
        """Cập nhật đồng hồ và trả về (sim_now, dt_sim_seconds) kể từ lần step() trước."""
        with self._lock:
            prev = self._sim_now
            self._advance_locked()
            dt_sim = max(0.0, (self._sim_now - prev).total_seconds())
            return self._sim_now, dt_sim

    def set_speed(self, speed):
        speed = int(speed)
        if speed not in self.SPEEDS:
            raise ValueError(f"Tốc độ phải thuộc {self.SPEEDS}")
        with self._lock:
            self._advance_locked()
            self._speed = speed

    def set_paused(self, paused):
        with self._lock:
            self._advance_locked()
            self._paused = bool(paused)

    def reset(self, start=None):
        with self._lock:
            self._sim_now = start or datetime.now(self.tz)
            self._last_real = self._mono()

    def state(self):
        with self._lock:
            self._advance_locked()
            return {
                "sim_time": self._sim_now.isoformat(timespec="seconds"),
                "speed": self._speed,
                "paused": self._paused,
            }
