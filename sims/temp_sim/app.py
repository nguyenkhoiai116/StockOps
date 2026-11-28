"""Ứng dụng Flask độc lập cho bộ mô phỏng cảm biến nhiệt độ AIoT (cổng 5101).

Chạy độc lập:
    python -m sims.temp_sim.app

Không import từ wms/ và không mở wms.db. Chỉ giao tiếp với StockOps qua HTTP API
(/api/ingest/sensor) khi được bật.
"""
import csv
import io
import os
import threading
import time
from datetime import timedelta
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, Response, jsonify, request

from sims.common.client import IngestClient
from sims.common.clock import SimClock
from sims.temp_sim.physics import WarehouseThermalSim

STATIC_DIR = Path(__file__).resolve().parent / "static"


def create_app(start_worker=True, tick_sec=1.0):
    load_dotenv()

    tz_offset = int(os.getenv("TZ_OFFSET", "7"))
    stockops_url = os.getenv("STOCKOPS_URL", "http://localhost:5000")
    ingest_key = os.getenv("INGEST_KEY", "")
    push_on = os.getenv("TEMP_SIM_PUSH", "0") == "1"

    clock = SimClock(speed=60, tz_offset=tz_offset)
    sim = WarehouseThermalSim()
    client = IngestClient(
        base_url=stockops_url,
        ingest_key=ingest_key,
        endpoint="/api/ingest/sensor",
        enabled=push_on,
    )

    # Khởi tạo vài điểm dữ liệu ban đầu để biểu đồ có sẵn đường nền khi mở trang
    now = clock.now()
    for i in range(12, 0, -1):
        sim.step(60.0, now - timedelta(minutes=i))

    app = Flask(__name__, static_folder=str(STATIC_DIR), static_url_path="")
    app.extensions["temp_sim"] = {"clock": clock, "sim": sim, "client": client}

    def tick_once(force_push=False):
        sim_now, dt_sim = clock.step()
        if dt_sim <= 0:
            # Khi đang pause nhưng người dùng bấm "Gửi ngay", vẫn lấy trạng thái hiện tại để đẩy
            payload = sim.step(0.0, sim_now)
        else:
            payload = sim.step(dt_sim, sim_now)
        if client.enabled or force_push:
            return payload, client.send(payload, force=force_push)
        client.last_payload = payload
        return payload, {"ok": False, "skipped": True}

    if start_worker:
        stop_ev = threading.Event()

        def worker():
            while not stop_ev.is_set():
                try:
                    tick_once(force_push=False)
                except Exception:
                    pass
                stop_ev.wait(tick_sec)

        th = threading.Thread(target=worker, name="temp-sim-loop", daemon=True)
        th.start()
        app.extensions["temp_sim"]["stop_event"] = stop_ev

    @app.get("/")
    def index():
        return app.send_static_file("index.html")

    @app.get("/api/sim/state")
    def api_state():
        sim_now = clock.now()
        return jsonify({
            "clock": clock.state(),
            "warehouse": sim.snapshot(sim_now),
            "ingest": client.status(),
        })

    @app.post("/api/sim/clock")
    def api_clock():
        d = request.get_json(silent=True) or {}
        try:
            if d.get("reset"):
                clock.reset()
                sim.reset()
                now_t = clock.now()
                sim.step(60.0, now_t)
            if "speed" in d:
                clock.set_speed(d["speed"])
            if "paused" in d:
                clock.set_paused(bool(d["paused"]))
        except ValueError as e:
            return jsonify({"error": str(e)}), 400
        return jsonify({"ok": True, "clock": clock.state()})

    @app.post("/api/sim/ambient")
    def api_ambient():
        d = request.get_json(silent=True) or {}
        try:
            sim.set_ambient(temp=d.get("temp"), hum=d.get("hum"))
        except (TypeError, ValueError):
            return jsonify({"error": "Giá trị nhiệt độ/độ ẩm không hợp lệ"}), 400
        return jsonify({"ok": True, "warehouse": sim.snapshot(clock.now())})

    @app.post("/api/sim/event")
    def api_event():
        d = request.get_json(silent=True) or {}
        event = d.get("event")
        if not event:
            return jsonify({"error": "Thiếu tên sự cố (event)"}), 400
        try:
            res = sim.trigger_event(
                event=event,
                zone=d.get("zone"),
                active=bool(d.get("active", True)),
                duration_sec=float(d.get("duration_sec", 180)),
            )
        except (TypeError, ValueError) as e:
            return jsonify({"error": str(e)}), 400
        return jsonify({"ok": True, "event": res, "warehouse": sim.snapshot(clock.now())})

    @app.post("/api/sim/target")
    def api_target():
        d = request.get_json(silent=True) or {}
        client.configure(
            base_url=d.get("base_url"),
            ingest_key=d.get("ingest_key"),
            enabled=d.get("enabled"),
        )
        push_res = None
        if d.get("push_now"):
            _, push_res = tick_once(force_push=True)
        return jsonify({"ok": True, "ingest": client.status(), "push_result": push_res})

    @app.post("/api/sim/backfill")
    def api_backfill():
        """Sinh dữ liệu lịch sử (mặc định 7 ngày, bước 15 phút). Có thể đẩy luôn lên StockOps nếu push=true."""
        d = request.get_json(silent=True) or {}
        try:
            days = max(1, min(365, int(d.get("days", 7))))
            step_min = max(5, min(60, int(d.get("step_min", 15))))
        except (TypeError, ValueError):
            return jsonify({"error": "days hoặc step_min không hợp lệ"}), 400

        start_dt = clock.now() - timedelta(days=days)
        rows_out = sim.generate_backfill(start_dt, days=days, step_min=step_min)

        pushed = None
        if d.get("push"):
            # Chia lô 500 bản ghi/request để không vượt giới hạn body 3MB của StockOps
            ok_batches, fail_batches = 0, 0
            for i in range(0, len(rows_out), 500):
                res = client.send({"source": "temp_sim_backfill", "readings": rows_out[i:i + 500]}, force=True)
                if res.get("ok"):
                    ok_batches += 1
                else:
                    fail_batches += 1
            pushed = {"ok_batches": ok_batches, "fail_batches": fail_batches}

        return jsonify({
            "ok": True,
            "days": days,
            "step_min": step_min,
            "count": len(rows_out),
            "sample": rows_out[:4],
            "pushed": pushed,
        })

    @app.get("/api/sim/export.csv")
    def api_export_csv():
        snap = sim.snapshot(clock.now())
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["zone", "sensor_id", "ts", "temp_c", "hum_pct"])
        for z in snap["zones"]:
            for pt in z["history"]:
                w.writerow([z["code"], z["sensor_id"], pt["ts"], pt["temp"], pt["hum"]])
        return Response(
            buf.getvalue(),
            mimetype="text/csv; charset=utf-8",
            headers={"Content-Disposition": "attachment; filename=temp_sim_history.csv"},
        )

    return app


if __name__ == "__main__":
    port = int(os.getenv("TEMP_SIM_PORT", "5101"))
    # Mặc định chỉ mở trên máy này: /api/sim/target không cần đăng nhập mà đổi được địa chỉ đích,
    # mở ra Wi-Fi thì người khác đổi đích sang máy họ là lấy được INGEST_KEY.
    host = os.getenv("TEMP_SIM_HOST", "127.0.0.1")
    debug = os.getenv("FLASK_DEBUG", "0") == "1"
    app = create_app(start_worker=True, tick_sec=1.0)
    print(f"StockOps AIoT Temp Simulator đang chạy tại http://localhost:{port}")
    app.run(host=host, port=port, debug=debug, use_reloader=False)
