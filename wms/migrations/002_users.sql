-- Tài khoản người dùng. Mỗi người 1 role; quyền của từng role nằm ở wms/roles.py.
-- pw_hash NULL = chưa đặt mật khẩu, không đăng nhập được.
CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY,
  username TEXT UNIQUE NOT NULL,
  name TEXT NOT NULL,
  role TEXT NOT NULL CHECK (role IN ('admin', 'inbound', 'storage', 'picking', 'shipping')),
  pw_hash TEXT,
  active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
  created_at TEXT NOT NULL);
