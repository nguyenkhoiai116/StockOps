"""HTTP client gửi dữ liệu từ simulator lên StockOps (/api/ingest/*).

Thiết kế để hoạt động độc lập: khi chưa nối với StockOps hoặc server đích chưa bật
endpoint ingest, client không làm sập simulator mà lưu trạng thái + payload mẫu gần nhất.
"""
import threading
from collections import deque

import requests


class IngestClient:
    """Gửi payload cảm biến qua HTTP POST kèm header X-Ingest-Key."""

    def __init__(self, base_url="http://localhost:5000", ingest_key="",
                 endpoint="/api/ingest/sensor", enabled=False, timeout=2.5):
        self._lock = threading.Lock()
        self.base_url = base_url.rstrip("/")
        self.ingest_key = ingest_key
        self.endpoint = endpoint
        self.enabled = bool(enabled)
        self.timeout = timeout

        self.sent_batches = 0
        self.sent_records = 0
        self.failed_batches = 0
        self.last_status = None
        self.last_error = ""
        self.last_sent_at = ""
        self.last_payload = None
        self.history = deque(maxlen=20)

    def configure(self, base_url=None, ingest_key=None, enabled=None):
        with self._lock:
            if base_url is not None:
                self.base_url = str(base_url).strip().rstrip("/")
            if ingest_key is not None:
                self.ingest_key = str(ingest_key).strip()
            if enabled is not None:
                self.enabled = bool(enabled)

    def target_url(self):
        return f"{self.base_url}{self.endpoint}"

    def send(self, payload, force=False):
        """Gửi 1 payload JSON lên endpoint ingest. Trả về dict kết quả."""
        with self._lock:
            self.last_payload = payload
            if not self.enabled and not force:
                return {"ok": False, "skipped": True, "reason": "Chế độ đẩy API đang tắt"}
            url = self.target_url()
            headers = {"Content-Type": "application/json"}
            if self.ingest_key:
                headers["X-Ingest-Key"] = self.ingest_key
            timeout = self.timeout

        count = len(payload.get("readings", [])) if isinstance(payload, dict) else 1
        try:
            res = requests.post(url, json=payload, headers=headers, timeout=timeout)
            ok = 200 <= res.status_code < 300
            err = "" if ok else f"HTTP {res.status_code}: {res.text[:160]}"
            status = res.status_code
        except requests.RequestException as exc:
            ok = False
            status = None
            err = str(exc)[:180]

        ts = ""
        if isinstance(payload, dict):
            rs = payload.get("readings") or []
            if rs:
                ts = rs[-1].get("ts", "")

        with self._lock:
            self.last_status = status
            self.last_error = err
            if ok:
                self.sent_batches += 1
                self.sent_records += count
                self.last_sent_at = ts
            else:
                self.failed_batches += 1
            entry = {
                "ts": ts,
                "ok": ok,
                "status": status,
                "count": count,
                "error": err,
            }
            self.history.appendleft(entry)
            return entry

    def status(self):
        with self._lock:
            return {
                "enabled": self.enabled,
                "target_url": self.target_url(),
                "has_key": bool(self.ingest_key),
                "sent_batches": self.sent_batches,
                "sent_records": self.sent_records,
                "failed_batches": self.failed_batches,
                "last_status": self.last_status,
                "last_error": self.last_error,
                "last_sent_at": self.last_sent_at,
                "last_payload": self.last_payload,
                "recent_logs": list(self.history),
            }
