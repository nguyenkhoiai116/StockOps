"""Điểm khởi động. Chạy:  python app.py  rồi mở http://localhost:5000
File này chỉ việc tạo app và chạy server.
"""
import os

from wms import create_app

app = create_app()   # đọc .env, tạo database + dữ liệu mẫu nếu chưa có

if __name__ == "__main__":
    # host="0.0.0.0": cho phép điện thoại cùng Wi-Fi mở bằng http://<IP máy tính>:5000
    # FLASK_DEBUG=1 trong .env để bật chế độ phát triển; mặc định tắt vì trang lỗi debug không nên lộ ra mạng Wi-Fi
    app.run(debug=os.getenv("FLASK_DEBUG") == "1", host="0.0.0.0", port=int(os.getenv("PORT", "5000")))
