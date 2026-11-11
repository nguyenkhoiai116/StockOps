"""Khởi tạo ứng dụng Flask và gắn tất cả feature.

Thêm 1 feature mới: tạo file trong wms/features/ (có biến bp = Blueprint),
rồi thêm tên nó vào danh sách FEATURES bên dưới. Không cần sửa gì khác.
"""
from flask import Flask

from .features import (analytics, auth, dashboard, inbound, inventory,
                       layout, picking, products, shipping)
from .seed import init_db

# Mỗi phần tử là 1 nhóm chức năng (1 Blueprint)
FEATURES = [dashboard, products, inbound, layout, inventory, picking, shipping, analytics, auth]


def create_app():
    # static_folder="../static": thư mục giao diện nằm ngoài package wms/
    # static_url_path="": file trong static được phục vụ ngay ở gốc (vd /css/base.css)
    app = Flask(__name__, static_folder="../static", static_url_path="")
    app.config["MAX_CONTENT_LENGTH"] = 3 * 1024 * 1024   # giới hạn ảnh tải lên: 3MB

    for mod in FEATURES:
        app.register_blueprint(mod.bp)   # gắn từng nhóm chức năng vào app

    @app.get("/")
    def home():
        """Mở trang chủ = file static/index.html"""
        return app.send_static_file("index.html")

    init_db()   # tạo database + dữ liệu mẫu nếu chưa có
    return app
