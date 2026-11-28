@echo off
rem Cập nhật bản chạy thật lên code mới nhất của nhánh main: bấm đúp file này trong E:\StockOps-live.
rem Thêm tham số: capnhat.bat -Restart (chỉ khởi động lại), capnhat.bat -NoTest (bỏ chạy test)
chcp 65001 >nul
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0capnhat.ps1" %*
pause
