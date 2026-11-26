-- Lần đăng nhập sai, để khóa tạm khi sai nhiều (xem auth.api_login).
-- Lưu trong DB thay vì biến trong RAM: chạy nhiều tiến trình (gunicorn nhiều worker) vẫn đếm chung,
-- và khởi động lại server không xóa mất bộ đếm.
CREATE TABLE IF NOT EXISTS login_fails (
  id INTEGER PRIMARY KEY,
  ip TEXT NOT NULL,
  username TEXT NOT NULL,   -- tên đã gõ (có thể không tồn tại)
  ts REAL NOT NULL);        -- giây kể từ 1970 (time.time())
CREATE INDEX IF NOT EXISTS ix_login_fails ON login_fails(ip, username, ts);
