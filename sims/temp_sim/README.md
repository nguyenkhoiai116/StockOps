# StockOps AIoT — Warehouse Temperature Simulator (`temp_sim`)

Bộ mô phỏng cảm biến nhiệt độ & độ ẩm (`SHT30`) cho 4 khu kho (`DRY`, `CHL`, `FRZ`, `COS`), chạy như một tiến trình độc lập ở cổng `5101`, hoàn toàn tách biệt với `wms/` và `wms.db`.

## 1. Chạy simulator

Từ thư mục gốc `StockOps`:

```bash
# Windows PowerShell
.\.venv\Scripts\python.exe -m sims.temp_sim.app
```

Mở trình duyệt tại: **http://localhost:5101**

## 2. Biến môi trường tùy chọn (`.env`)

| Biến | Mặc định | Ý nghĩa |
|---|---|---|
| `TEMP_SIM_PORT` | `5101` | Cổng chạy web simulator |
| `TEMP_SIM_HOST` | `127.0.0.1` | Chỉ máy này mở được. Đừng đổi thành `0.0.0.0`: trang simulator không có đăng nhập, người cùng Wi-Fi đổi được địa chỉ đích và lấy `INGEST_KEY` |
| `STOCKOPS_URL` | `http://localhost:5000` | Địa chỉ StockOps nhận dữ liệu |
| `INGEST_KEY` | trống | Giá trị gửi trong header `X-Ingest-Key` |
| `TEMP_SIM_PUSH` | `0` | `1` = tự động đẩy dữ liệu lên StockOps ngay khi khởi động |
| `TZ_OFFSET` | `7` | Múi giờ kho (UTC+7) |

## 3. Hợp đồng API đẩy sang StockOps (dùng khi tích hợp)

Khi bật đẩy tự động hoặc bấm **Gửi ngay 1 nhịp**, simulator gửi:

- **Method & Path:** `POST {STOCKOPS_URL}/api/ingest/sensor`
- **Headers:** `Content-Type: application/json`, `X-Ingest-Key: <INGEST_KEY>` (nếu có)
- **Body:**

```json
{
  "source": "temp_sim",
  "readings": [
    {
      "sensor_id": "SHT30-CHL-01",
      "zone": "CHL",
      "temp": 4.62,
      "hum": 74.1,
      "ts": "2026-11-27T21:20:00+07:00",
      "status": "ok",
      "rate_c_per_min": 0.002,
      "eta_breach_min": null,
      "events": []
    }
  ]
}
```
