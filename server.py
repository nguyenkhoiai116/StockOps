"""Chạy StockOps cho nhiều máy trong mạng LAN (thay cho `python app.py`, vốn là server thử nghiệm của Flask).
Chạy:  python server.py   (hoặc bấm đúp server.bat), các máy khác mở http://<IP máy này>:5000

Dùng waitress: chạy được trên Windows, 1 tiến trình nhiều luồng. 1 tiến trình là đủ cho 2-10 người
và không có chuyện nhiều worker tranh nhau tạo database lúc khởi động.
"""
import os
import socket
import sys

from waitress import serve

from app import app   # tạo app, đọc .env, chạy migration


def ips():
    """Các địa chỉ IPv4 của máy này, để in ra cho người dùng gõ ở máy khác."""
    try:
        return sorted({a[4][0] for a in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)} - {"127.0.0.1"})
    except OSError:
        return []


if __name__ == "__main__":
    # Chạy bằng Task Scheduler / ghi ra file thì Windows dùng bảng mã cp1252: in tiếng Việt sẽ lỗi và server chết ngay
    for s in (sys.stdout, sys.stderr):
        if s and hasattr(s, "reconfigure"):
            s.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)   # ghi ngay từng dòng vào log
    port = int(os.getenv("PORT", "5000"))
    # Mỗi câu hỏi Kvis giữ 1 luồng tới 60 giây (chờ LLM); mặc định 4 luồng thì 4 người chat là cả hệ thống đứng
    threads = int(os.getenv("THREADS", "16"))
    if os.getenv("FLASK_DEBUG") == "1":
        print("CẢNH BÁO: FLASK_DEBUG=1 trong .env -> đặt lại 0 khi cho máy khác vào")
    print(f"StockOps đang chạy ({threads} luồng). Máy này: http://localhost:{port}")
    for ip in ips():
        print(f"  Máy khác cùng mạng: http://{ip}:{port}")
    print("Tắt: Ctrl+C")
    serve(app, host=os.getenv("HOST", "0.0.0.0"), port=port, threads=threads)
