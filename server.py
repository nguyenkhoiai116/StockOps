"""Chạy StockOps cho nhiều máy (thay cho `python app.py`, vốn là server thử nghiệm của Flask).
Chạy:  python server.py   (hoặc bấm đúp server.bat), các máy khác mở http://<IP máy này>:5000

Dùng waitress: chạy được trên Windows, 1 tiến trình nhiều luồng. 1 tiến trình là đủ cho 2-10 người
và không có chuyện nhiều worker tranh nhau tạo database lúc khởi động.
Bản chạy thật (E:\\StockOps-live) do Task Scheduler bật với tham số --log, cập nhật bằng capnhat.ps1.
"""
import os
import socket
import sys
from pathlib import Path


def setup_output():
    """--log: ghi mọi thứ (kể cả lỗi lúc khởi động) vào logs/server.log, vì chạy nền thì không có cửa sổ.
    Không có --log: in ra màn hình bằng UTF-8 (Windows mặc định cp1252, in tiếng Việt sẽ lỗi và server chết ngay)."""
    if "--log" in sys.argv:
        d = Path(__file__).resolve().parent / "logs"
        d.mkdir(exist_ok=True)
        f = open(d / "server.log", "a", encoding="utf-8", errors="replace", buffering=1)
        sys.stdout = sys.stderr = f
        return
    for s in (sys.stdout, sys.stderr):
        if s and hasattr(s, "reconfigure"):
            s.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)   # ghi ngay từng dòng


def ips():
    """Các địa chỉ IPv4 của máy này, để in ra cho người dùng gõ ở máy khác."""
    try:
        return sorted({a[4][0] for a in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)} - {"127.0.0.1"})
    except OSError:
        return []


if __name__ == "__main__":
    setup_output()   # phải chạy trước khi tạo app: lỗi migration lúc khởi động cũng phải vào log
    from datetime import datetime

    from waitress import serve

    from app import app   # tạo app, đọc .env, chạy migration

    port = int(os.getenv("PORT", "5000"))
    # Mỗi câu hỏi Kvis giữ 1 luồng tới 60 giây (chờ LLM); mặc định 4 luồng thì 4 người chat là cả hệ thống đứng
    threads = int(os.getenv("THREADS", "16"))
    if os.getenv("FLASK_DEBUG") == "1":
        print("CẢNH BÁO: FLASK_DEBUG=1 trong .env -> đặt lại 0 khi cho máy khác vào")
    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] StockOps đang chạy ({threads} luồng). Máy này: http://localhost:{port}")
    for ip in ips():
        print(f"  Máy khác cùng mạng: http://{ip}:{port}")
    print("Tắt: Ctrl+C")
    serve(app, host=os.getenv("HOST", "0.0.0.0"), port=port, threads=threads)
