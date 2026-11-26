-- Các bảng ban đầu (chuyển nguyên từ seed.py). IF NOT EXISTS: database cũ đã có bảng thì giữ nguyên.
-- CHECK (qty>=0) để DB tự chặn tồn kho âm.
CREATE TABLE IF NOT EXISTS products (
  id INTEGER PRIMARY KEY, sku TEXT UNIQUE NOT NULL, name TEXT NOT NULL, cat TEXT, unit TEXT,
  storage TEXT NOT NULL,            -- dry | chilled | frozen | cosmetics
  price INTEGER DEFAULT 0, safety INTEGER DEFAULT 0, supplier TEXT);
CREATE TABLE IF NOT EXISTS zones (
  code TEXT PRIMARY KEY, name TEXT, storage TEXT, cap INTEGER,
  tmin REAL, tmax REAL, temp REAL, hum REAL);
CREATE TABLE IF NOT EXISTS batches (
  id INTEGER PRIMARY KEY, product_id INTEGER REFERENCES products(id), batch_no TEXT, exp TEXT,
  qty INTEGER NOT NULL CHECK (qty >= 0),
  reserved INTEGER NOT NULL DEFAULT 0 CHECK (reserved >= 0 AND reserved <= qty),
  zone TEXT REFERENCES zones(code), bin INTEGER);
CREATE TABLE IF NOT EXISTS pos (
  id INTEGER PRIMARY KEY, po_no TEXT, product_id INTEGER REFERENCES products(id), qty INTEGER,
  eta TEXT, status TEXT DEFAULT 'pending', recv INTEGER DEFAULT 0, dmg INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS sos (
  id INTEGER PRIMARY KEY, so_no TEXT, customer TEXT, product_id INTEGER REFERENCES products(id),
  qty INTEGER, due TEXT, status TEXT DEFAULT 'new', plate TEXT, on_time INTEGER);
CREATE TABLE IF NOT EXISTS picks (
  id INTEGER PRIMARY KEY, so_id INTEGER REFERENCES sos(id), batch_id INTEGER REFERENCES batches(id), qty INTEGER);
CREATE TABLE IF NOT EXISTS vehicles (plate TEXT PRIMARY KEY, driver TEXT, kind TEXT);
CREATE TABLE IF NOT EXISTS txs (
  id INTEGER PRIMARY KEY, ts TEXT, kind TEXT, product_id INTEGER, batch_no TEXT, qty INTEGER, note TEXT);
