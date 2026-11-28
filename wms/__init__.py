"""Khởi tạo ứng dụng Flask và gắn tất cả feature.

Thêm 1 feature mới: tạo file trong wms/features/ (có biến bp = Blueprint),
rồi thêm tên nó vào danh sách FEATURES bên dưới. Không cần sửa gì khác.
"""
import os
import secrets
from datetime import timedelta

from dotenv import load_dotenv
from flask import Flask

from .db import ROOT
from .features import (analytics, auth, chat, dashboard, inbound, inventory,
                       layout, picking, products, shipping)
from .seed import init_db

# Mỗi phần tử là 1 nhóm chức năng (1 Blueprint)
FEATURES = [dashboard, products, inbound, layout, inventory, picking, shipping, analytics, auth, chat]


KEY_FILE = ROOT / ".secret_key"   # khóa ký cookie, tự tạo lần chạy đầu, không đưa lên git


def secret_key():
    """Khóa ký phiên đăng nhập: lấy SECRET_KEY trong .env, không có thì dùng file tự tạo."""
    if os.getenv("SECRET_KEY"):
        return os.environ["SECRET_KEY"]
    try:
        with open(KEY_FILE, "x") as f:   # "x": chỉ 1 tiến trình tạo được, tránh ghi đè nhau
            f.write(secrets.token_hex(32))
    except FileExistsError:
        pass
    with open(KEY_FILE) as f:
        key = f.read().strip()
    if len(key) < 32:
        raise RuntimeError(f"File {KEY_FILE} bị hỏng, hãy xóa file rồi chạy lại")
    return key


def create_app():
    load_dotenv()   # nạp biến trong file .env (API key, tên model...) vào môi trường
    # static_folder="../static": thư mục giao diện nằm ngoài package wms/
    # static_url_path="": file trong static được phục vụ ngay ở gốc (vd /css/base.css)
    app = Flask(__name__, static_folder="../static", static_url_path="")
    app.secret_key = secret_key()
    app.session_interface = auth.Session()   # cookie phiên bật Secure khi vào qua Cloudflare Tunnel (https)
    app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax",
                      SESSION_COOKIE_SECURE=os.getenv("COOKIE_SECURE") == "1",   # đặt 1 khi chạy qua HTTPS
                      PERMANENT_SESSION_LIFETIME=timedelta(hours=8))
    app.config["MAX_CONTENT_LENGTH"] = 3 * 1024 * 1024   # giới hạn kích thước body mỗi request: 3MB

    for mod in FEATURES:
        app.register_blueprint(mod.bp)   # gắn từng nhóm chức năng vào app

    @app.get("/")
    def home():
        """Mở trang chủ = file static/index.html"""
        return app.send_static_file("index.html")

    init_db()   # tạo database + dữ liệu mẫu nếu chưa có
    return app
