# StockOps — Hệ thống quản lý kho FMCG

Web quản lý kho hàng tiêu dùng nhanh (FMCG) theo **lô và hạn dùng**: nhập hàng, lưu kho, soạn hàng theo FEFO (hết hạn trước, xuất trước), xuất kho, cảnh báo cận date, sơ đồ kho 2D/3D và trợ lý AI **Kvis**.

- **Backend:** Python + Flask, database SQLite (file `wms.db`)
- **Frontend:** HTML/CSS/JavaScript thuần, không cần build
- **Kho 3D:** Three.js (tải từ CDN khi mở chế độ 3D)
- **Trợ lý Kvis:** gọi LLM qua OpenRouter hoặc LM Studio (tùy chọn, cần API key)

---

## 1. Cần chuẩn bị

| Thứ cần có | Ghi chú |
|---|---|
| **Python 3.10 trở lên** | Tải tại python.org. Windows: khi cài nhớ tick **"Add Python to PATH"** |
| **Git** (hoặc tải ZIP) | Không có Git thì trên GitHub bấm **Code → Download ZIP** rồi giải nén |
| **Mạng Internet** | Lần đầu để cài thư viện. Font chữ và Three.js cũng tải từ mạng; mất mạng thì kho tự chuyển về sơ đồ 2D |

Kiểm tra Python: mở terminal, gõ `python --version` (macOS/Linux: `python3 --version`).

---

## 2. Cài đặt và chạy

### Cách 1 — Windows, nhanh nhất

```bat
git clone https://github.com/nguyenkhoiai116/StockOps.git
cd StockOps
chay.bat
```

Hoặc mở thư mục `StockOps` rồi **bấm đúp `chay.bat`**. Lần đầu file này tự:

1. tạo môi trường Python riêng `.venv` và cài thư viện,
2. tạo file cấu hình `.env` từ `.env.example`,
3. tạo database mẫu và **hỏi 1 mật khẩu demo** (tối thiểu 8 ký tự) dùng chung cho mọi tài khoản mẫu.

> Khi gõ mật khẩu, màn hình không hiện ký tự nào — bình thường, cứ gõ rồi Enter.

Các lần sau bấm đúp `chay.bat` là server chạy luôn.

### Cách 2 — Làm từng bước (Windows, macOS, Linux)

```bash
git clone https://github.com/nguyenkhoiai116/StockOps.git
cd StockOps

python -m venv .venv               # macOS/Linux: python3 -m venv .venv
.venv\Scripts\activate             # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt

copy .env.example .env             # macOS/Linux: cp .env.example .env
python database.py reset           # tạo dữ liệu mẫu + đặt mật khẩu demo
python app.py                      # chạy server
```

> `.venv` là "môi trường ảo": thư viện của dự án được cài vào đây, không lẫn với Python của máy.
> Mỗi lần mở terminal mới phải chạy lại lệnh `activate` trước khi `python app.py`.

**Kết quả đúng:** lệnh `reset` in ra `Đã đặt mật khẩu cho admin, nhap01, ...`, lệnh `app.py` in ra `Serving Flask app 'wms'`.

### Mở web

- Trên máy đang chạy: **http://localhost:5000**
- Điện thoại / máy khác cùng Wi-Fi: `http://<địa chỉ IP máy tính>:5000`
  (lần đầu Windows hỏi tường lửa → cho phép mạng **Private**)
- Tắt server: bấm **Ctrl+C** trong terminal.

### Chạy thật cho 2–10 máy trong mạng LAN

`chay.bat` / `python app.py` là server thử nghiệm của Flask, chỉ dùng khi phát triển. Khi cả kho dùng chung:

1. Chọn 1 máy luôn bật làm máy chủ, tắt Sleep, đặt IP cố định (DHCP reservation trên router).
2. Bấm đúp `chay.bat` 1 lần để cài đặt và đặt mật khẩu, rồi đặt mật khẩu riêng cho từng người: `python users.py passwd <tên>`.
3. Bấm đúp **`server.bat`** (chạy `python server.py` bằng waitress). Màn hình in ra địa chỉ cho máy khác, vd `http://192.168.1.137:5000`.
4. Mở tường lửa cho cổng 5000, chỉ mạng Private (PowerShell chạy quyền Admin):
   ```powershell
   New-NetFirewallRule -DisplayName "StockOps 5000" -Direction Inbound -Protocol TCP -LocalPort 5000 -Action Allow -Profile Private
   ```
5. Tự chạy khi bật máy: Task Scheduler → *Create Task* → trigger *At startup*, action chạy `server.bat`, tick *Run whether user is logged on or not*.
6. Sao lưu mỗi tối, và định kỳ chép thư mục `backups/` sang máy/USB khác:
   ```powershell
   schtasks /Create /TN "StockOps backup" /SC DAILY /ST 23:00 /TR "<thư mục dự án>\.venv\Scripts\python.exe <thư mục dự án>\database.py backup"
   ```

Lưu ý:
- **Không** port-forward ra Internet: app chạy HTTP, mật khẩu đi trên mạng không mã hóa. Khách dùng chung Wi-Fi thì tách sang mạng khách.
- **Không** mở `wms.db` qua thư mục chia sẻ mạng (SQLite WAL hỏng khi nhiều máy mở file qua mạng). Mọi máy vào qua web.
- Cập nhật code: tắt server → `python database.py backup` → `git pull` → bấm `server.bat` (tự cài thư viện mới, tự chạy migration).
- Máy chủ Linux: `gunicorn -w 1 --threads 16 -b 0.0.0.0:5000 app:app`, chạy bằng systemd, `ufw` chỉ cho dải LAN.


---

## 3. Đăng nhập

Mọi tài khoản mẫu dùng chung **mật khẩu demo** bạn vừa đặt.

| Tài khoản | Vai trò | Làm được gì |
|---|---|---|
| `admin` | Quản trị | Tất cả chức năng |
| `nhap01`, `nhap02` | Nhập kho | Xem đơn mua (PO), nhận hàng theo lô |
| `luu01`, `luu02` | Lưu kho | Xem tồn kho, điều chỉnh tồn, xuất CSV |
| `soan01`, `soan02` | Soạn hàng | Soạn hàng theo FEFO |
| `xuat01`, `xuat02` | Xuất kho | Chọn xe, xuất kho, xác nhận đã giao |

Bảng quyền chi tiết: [docs/roles.md](docs/roles.md).

```bash
python users.py                    # xem danh sách tài khoản
python users.py passwd admin       # đổi mật khẩu 1 tài khoản
python users.py passwd --moi       # đặt chung 1 mật khẩu cho các tài khoản chưa có
```

---

## 4. Bật trợ lý Kvis (tùy chọn)

Không có API key thì mọi chức năng khác vẫn chạy bình thường, chỉ khung chat báo *"Chưa cấu hình LLM_API_KEY"*.

1. Tạo key miễn phí tại https://openrouter.ai/settings/keys
2. Mở file `.env`, điền: `LLM_API_KEY=sk-or-...`
3. Tắt server (Ctrl+C) rồi chạy lại `python app.py` — `.env` chỉ được đọc lúc khởi động.

Muốn chạy model trên máy bằng **LM Studio**: xem phần mẫu trong `.env.example`.

> File `.env` chứa bí mật, đã nằm trong `.gitignore`. **Không bao giờ** đưa nó lên GitHub.

---

## 5. Cấu hình (`.env`)

| Biến | Mặc định | Ý nghĩa |
|---|---|---|
| `PORT` | `5000` | Cổng chạy web. Cổng bị chiếm thì đổi sang `5001`... |
| `FLASK_DEBUG` | `0` | `1` = tự nạp lại khi sửa code + trang lỗi chi tiết. Để `0` khi cho người khác vào qua Wi-Fi |
| `THREADS` | `16` | Số luồng của `server.py`. Mỗi câu hỏi Kvis giữ 1 luồng tới 60 giây |
| `HOST` | `0.0.0.0` | Địa chỉ `server.py` lắng nghe. `127.0.0.1` = chỉ máy này vào được |
| `LLM_BASE_URL` | OpenRouter | Địa chỉ dịch vụ LLM (chuẩn OpenAI) |
| `LLM_API_KEY` | trống | Key của dịch vụ LLM |
| `LLM_MODEL` | `google/gemma-4-31b-it:free` | Tên model, phải hỗ trợ gọi tool |

---

## 6. Quản lý database

File `wms.db` nằm trong thư mục dự án (không đưa lên GitHub). Chạy từ đâu cũng dùng đúng file này.

```bash
python database.py                 # xem tình trạng: số bảng, số dòng, phiên bản migration
python database.py backup          # sao lưu vào backups/ (server đang chạy vẫn được)
python database.py reset           # sao lưu rồi làm lại dữ liệu mẫu (TẮT server trước)
```

Cấu trúc bảng được tạo bằng các file **migration** trong `wms/migrations/` (`001_base.sql`, `002_users.sql`, ...). Server tự chạy các file mới khi khởi động. Muốn đổi cấu trúc bảng: **thêm file số tiếp theo**, không sửa file cũ, không sửa bảng trong `seed.py`.

---

## 7. Lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách sửa |
|---|---|---|
| `python` không được nhận diện | Chưa cài Python hoặc chưa tick "Add to PATH" | Cài lại Python, tick ô đó; hoặc dùng lệnh `py` |
| Đăng nhập luôn báo sai | Chạy thẳng `python app.py`, bỏ qua bước `reset` → tài khoản chưa có mật khẩu | `python users.py passwd --moi` |
| `Không xóa được wms.db...` | Reset khi server đang chạy (Windows khóa file) | Ctrl+C tắt server rồi reset lại |
| `ModuleNotFoundError: flask` | Chưa `activate` môi trường `.venv` | Chạy lệnh `activate` ở bước 2 |
| Cổng 5000 đã bị dùng | App khác chiếm cổng | Đặt `PORT=5001` trong `.env` |
| Điện thoại không vào được | Tường lửa chặn hoặc khác mạng Wi-Fi | Cho phép mạng Private; kiểm tra cùng Wi-Fi |
| Kho 3D không hiện | Không có mạng để tải Three.js | Kết nối mạng, hoặc dùng chế độ 2D |

---

## 8. Cấu trúc thư mục

```
StockOps/
├── app.py              Khởi động server (chạy file này)
├── chay.bat            Chạy nhanh trên Windows (bấm đúp)
├── server.py           Chạy thật cho nhiều máy trong LAN (waitress)
├── server.bat          Bấm đúp để chạy server.py
├── database.py         Xem / sao lưu / làm lại database
├── users.py            Xem tài khoản, đặt mật khẩu
├── .env.example        Mẫu cấu hình -> copy thành .env
├── requirements.txt    Thư viện Python (flask, gunicorn, requests, python-dotenv)
├── wms/                BACKEND
│   ├── __init__.py     Tạo app, gắn các chức năng (danh sách FEATURES)
│   ├── db.py           Kết nối database, khóa ghi (lock)
│   ├── core.py         Nghiệp vụ lõi: FEFO, xuất kho, tạo PO, điều chỉnh tồn, gợi ý đặt hàng, cảnh báo, KPI
│   ├── migrate.py      Chạy các file trong migrations/
│   ├── migrations/     Cấu trúc bảng theo từng bước 001, 002, ...
│   ├── roles.py        Vai trò và quyền (PERMS)
│   ├── users.py        Mật khẩu (băm, không lưu chữ thật)
│   ├── seed.py         Dữ liệu mẫu
│   ├── ai/             Kết nối LLM (llm.py) và lời nhắc cho Kvis (prompts.py)
│   └── features/       MỖI CHỨC NĂNG 1 FILE: dashboard, products, inbound, layout,
│                       inventory, picking, shipping, analytics, auth, chat
├── static/             FRONTEND
│   ├── index.html      Khung trang
│   ├── css/            theme.css (màu) · base.css (khung) · components.css · chat.css
│   ├── js/
│   │   ├── core.js     Công cụ dùng chung: gọi API, hộp thoại, điều hướng
│   │   ├── app.js      Khởi động + danh sách trang
│   │   ├── chart.js    Biểu đồ nhập / xuất
│   │   ├── wh3d.js     Kho 3D (Three.js)
│   │   ├── chat.js     Khung chat Kvis
│   │   └── features/   MỖI CHỨC NĂNG 1 FILE (trùng tên với backend)
│   └── icons/          Bộ icon SVG tự vẽ
├── tests/              Kiểm thử tự động
└── docs/               Kiến trúc (architecture.md), quyền (roles.md), review, thiết kế
```

---

## 9. Dành cho người phát triển

### Muốn sửa gì thì vào đâu

| Muốn sửa | File |
|---|---|
| Màu sắc, hiệu ứng | `static/css/theme.css` |
| Giao diện 1 chức năng | `static/js/features/<tên>.js` |
| API của 1 chức năng | `wms/features/<tên>.py` |
| Luật nghiệp vụ tồn kho (FEFO, không âm, sức chứa...) | `wms/core.py` |
| Quyền của từng vai trò | `wms/roles.py` (rồi chạy `python -m wms.roles` để in lại bảng cho `docs/roles.md`) |
| Dữ liệu mẫu | `wms/seed.py` (rồi `python database.py reset`) |
| Icon | thay file trong `static/icons/` |

### Thêm 1 chức năng mới

1. Tạo `wms/features/ten_moi.py` có biến `bp = Blueprint(...)` → thêm vào `FEATURES` trong `wms/__init__.py`.
2. Khai báo mọi route `/api/...` mới vào `PERMS` trong `wms/roles.py` (thiếu là test báo lỗi, và server chặn route đó).
3. Tạo `static/js/features/ten_moi.js` có `export const page = { perm: [...], id, name, render, ... }` (`perm` là quyền được mở trang) → import và thêm vào mảng `ALL` trong `static/js/app.js`.
4. Nút thao tác trên giao diện dùng `can()` để ẩn với người không có quyền (chỉ để ẩn — việc chặn thật nằm ở backend).

### Chạy test

```bash
# Windows (cmd):  set PYTHONUTF8=1
# macOS/Linux:    export PYTHONUTF8=1
python -m unittest discover tests
```

Kết quả đúng: dòng cuối là `OK`. `PYTHONUTF8=1` để console Windows in được tiếng Việt.

### Quy ước của dự án

Kiến trúc và các quyết định nằm trong [docs/architecture.md](docs/architecture.md); quy tắc ngắn gọn trong [CLAUDE.md](CLAUDE.md). Mọi thao tác ghi tồn kho phải chạy ở backend trong transaction, comment viết bằng tiếng Việt, tên biến ngắn.
