@echo off
rem Chạy StockOps trên laptop Windows: bấm đúp file này.
rem Lần đầu: tạo môi trường .venv, cài thư viện, tạo .env, tạo database mẫu và hỏi mật khẩu demo.
chcp 65001 >nul
cd /d "%~dp0"

if not exist .venv (
  echo [1/3] Tao moi truong Python .venv ...
  python -m venv .venv || (echo Khong tim thay Python. Cai tu python.org, tick "Add Python to PATH". & pause & exit /b 1)
  .venv\Scripts\python -m pip install -r requirements.txt || (pause & exit /b 1)
)
if not exist .env copy .env.example .env >nul
if not exist wms.db (
  echo [2/3] Tao database du lieu mau ...
  .venv\Scripts\python database.py reset -y || (pause & exit /b 1)
)
echo [3/3] Server dang chay: http://localhost:5000   (tat: Ctrl+C)
.venv\Scripts\python app.py
pause
