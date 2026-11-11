"""Điểm khởi động. Chạy:  python app.py  rồi mở http://localhost:5000
File này chỉ việc tạo app và chạy server.
"""
from wms import create_app

app = create_app()

if __name__ == "__main__":
    # host="0.0.0.0": cho phép điện thoại cùng Wi-Fi mở bằng http://<IP máy tính>:5000
    app.run(debug=True, host="0.0.0.0", port=5000)
