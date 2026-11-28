@echo off
rem Chạy StockOps cho nhiều máy trong mạng LAN: bấm đúp file này (hoặc đặt trong Task Scheduler "At startup").
rem Khác chay.bat: dùng waitress thay cho server thử nghiệm của Flask. Lần đầu hãy chạy chay.bat để tạo database và mật khẩu.
chcp 65001 >nul
cd /d "%~dp0"

if not exist .venv (
  echo Chua co .venv: bam dup chay.bat truoc de cai dat.
  pause & exit /b 1
)
if not exist wms.db (
  echo Chua co wms.db: bam dup chay.bat truoc de tao database.
  pause & exit /b 1
)
rem Cài thêm thư viện còn thiếu (vd waitress khi vừa cập nhật code); đủ rồi thì lệnh này chạy rất nhanh
.venv\Scripts\python -m pip install -q -r requirements.txt || (pause & exit /b 1)
.venv\Scripts\python server.py
pause
