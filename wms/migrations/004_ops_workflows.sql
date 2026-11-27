-- Nâng cấp dữ liệu cho quy trình 3 nhóm: Inbound (PO/ASN/Dock), Storage & Inventory (Slotting/Kiểm kê/Điều chuyển),
-- Outbound (Kênh khách hàng, Đối chiếu 3 chiều, Ghép chuyến LIFO, Staging/QR/ETA), cộng thêm Nhật ký & Chat nội bộ.

-- 1. Thuộc tính vật lý & vòng đời chuẩn của SKU (phục vụ COI, xếp tải 2 tầng, % HSD kênh, ROP)
ALTER TABLE products ADD COLUMN shelf_days INTEGER NOT NULL DEFAULT 180;
ALTER TABLE products ADD COLUMN weight_kg REAL NOT NULL DEFAULT 10.0;
ALTER TABLE products ADD COLUMN vol_m3 REAL NOT NULL DEFAULT 0.04;
ALTER TABLE products ADD COLUMN fragile INTEGER NOT NULL DEFAULT 0;
ALTER TABLE products ADD COLUMN lead_days INTEGER NOT NULL DEFAULT 2;

UPDATE products SET shelf_days=240, weight_kg=4.5,  vol_m3=0.045, fragile=1, lead_days=2 WHERE sku='SKU-001';
UPDATE products SET shelf_days=365, weight_kg=9.2,  vol_m3=0.025, fragile=0, lead_days=2 WHERE sku='SKU-002';
UPDATE products SET shelf_days=45,  weight_kg=6.0,  vol_m3=0.022, fragile=1, lead_days=1 WHERE sku='SKU-003';
UPDATE products SET shelf_days=30,  weight_kg=12.6, vol_m3=0.024, fragile=0, lead_days=1 WHERE sku='SKU-004';
UPDATE products SET shelf_days=120, weight_kg=5.5,  vol_m3=0.032, fragile=1, lead_days=2 WHERE sku='SKU-005';
UPDATE products SET shelf_days=180, weight_kg=10.5, vol_m3=0.030, fragile=0, lead_days=2 WHERE sku='SKU-006';
UPDATE products SET shelf_days=1095,weight_kg=8.4,  vol_m3=0.026, fragile=0, lead_days=3 WHERE sku='SKU-007';
UPDATE products SET shelf_days=1095,weight_kg=10.8, vol_m3=0.028, fragile=0, lead_days=3 WHERE sku='SKU-008';
UPDATE products SET shelf_days=365, weight_kg=11.0, vol_m3=0.024, fragile=1, lead_days=3 WHERE sku='SKU-009';
UPDATE products SET shelf_days=365, weight_kg=5.2,  vol_m3=0.048, fragile=1, lead_days=2 WHERE sku='SKU-010';

-- 2. Trạng thái chất lượng, khóa vị trí kiểm kê và mốc nhận của lô hàng
ALTER TABLE batches ADD COLUMN q_status TEXT NOT NULL DEFAULT 'ok';
ALTER TABLE batches ADD COLUMN locked INTEGER NOT NULL DEFAULT 0;
ALTER TABLE batches ADD COLUMN received_at TEXT;

-- 3. Kế hoạch nhập kho (Inbound CV1-CV4): ASN, cờ ưu tiên, Dock/Time-slot, mặt bằng, thẻ cổng
ALTER TABLE pos ADD COLUMN plan_status TEXT NOT NULL DEFAULT 'draft';
ALTER TABLE pos ADD COLUMN asn_no TEXT;
ALTER TABLE pos ADD COLUMN asn_uom TEXT DEFAULT 'thùng';
ALTER TABLE pos ADD COLUMN asn_exp TEXT;
ALTER TABLE pos ADD COLUMN asn_batch TEXT;
ALTER TABLE pos ADD COLUMN priority TEXT NOT NULL DEFAULT 'standard';
ALTER TABLE pos ADD COLUMN need_qc INTEGER NOT NULL DEFAULT 0;
ALTER TABLE pos ADD COLUMN dock TEXT;
ALTER TABLE pos ADD COLUMN slot_time TEXT;
ALTER TABLE pos ADD COLUMN est_min INTEGER NOT NULL DEFAULT 45;
ALTER TABLE pos ADD COLUMN workers INTEGER NOT NULL DEFAULT 2;
ALTER TABLE pos ADD COLUMN forklift TEXT;
ALTER TABLE pos ADD COLUMN area_ready INTEGER NOT NULL DEFAULT 0;
ALTER TABLE pos ADD COLUMN gate_pass TEXT;
ALTER TABLE pos ADD COLUMN plate TEXT;
ALTER TABLE pos ADD COLUMN driver TEXT;
ALTER TABLE pos ADD COLUMN pre_batch TEXT;

UPDATE pos SET plan_status='received' WHERE status='received';

-- 4. Xuất hàng nâng cao (Outbound CV1-CV5): kênh khách, % HSD, tuyến giao, đối chiếu 3 chiều, chuyến xe, staging, QR
ALTER TABLE sos ADD COLUMN channel TEXT NOT NULL DEFAULT 'taphoa';
ALTER TABLE sos ADD COLUMN min_shelf_pct INTEGER NOT NULL DEFAULT 40;
ALTER TABLE sos ADD COLUMN route_zone TEXT NOT NULL DEFAULT 'Q1';
ALTER TABLE sos ADD COLUMN audit_status TEXT NOT NULL DEFAULT 'pending';
ALTER TABLE sos ADD COLUMN audit_note TEXT;
ALTER TABLE sos ADD COLUMN trip_id INTEGER;
ALTER TABLE sos ADD COLUMN staged_at TEXT;
ALTER TABLE sos ADD COLUMN scanned_qty INTEGER NOT NULL DEFAULT 0;
ALTER TABLE sos ADD COLUMN epod_note TEXT;

-- 5. Thông số tải trọng, thể tích và chi phí chuyến của đội xe
ALTER TABLE vehicles ADD COLUMN cap_qty INTEGER NOT NULL DEFAULT 300;
ALTER TABLE vehicles ADD COLUMN cap_kg REAL NOT NULL DEFAULT 3500.0;
ALTER TABLE vehicles ADD COLUMN cap_m3 REAL NOT NULL DEFAULT 15.0;
ALTER TABLE vehicles ADD COLUMN cost_trip INTEGER NOT NULL DEFAULT 1800000;

UPDATE vehicles SET cap_qty=400, cap_kg=5000.0, cap_m3=20.0, cost_trip=1600000 WHERE plate='51C-123.45';
UPDATE vehicles SET cap_qty=260, cap_kg=3500.0, cap_m3=14.0, cost_trip=2100000 WHERE plate='51D-678.90';

-- 6. Danh mục phân loại khách hàng & chuẩn HSD tối thiểu theo kênh
CREATE TABLE IF NOT EXISTS customers (
  id INTEGER PRIMARY KEY,
  name TEXT UNIQUE NOT NULL,
  channel TEXT NOT NULL CHECK (channel IN ('sieuthi', 'daily', 'taphoa')),
  min_shelf_pct INTEGER NOT NULL,
  route_zone TEXT NOT NULL,
  unload_min INTEGER NOT NULL DEFAULT 15
);

INSERT OR IGNORE INTO customers (name, channel, min_shelf_pct, route_zone, unload_min) VALUES
  ('Siêu thị An Phú',    'sieuthi', 65, 'Q1',        40),
  ('Siêu thị Coop Q7',   'sieuthi', 65, 'Q7',        35),
  ('Đại lý Hòa Bình',    'daily',   50, 'Q3',        25),
  ('Nhà hàng Biển Xanh', 'daily',   50, 'Q1',        20),
  ('Tạp hóa Minh Tâm',   'taphoa',  40, 'Q1',        10),
  ('Cửa hàng Bình Minh', 'taphoa',  40, 'Q3',        10),
  ('Mỹ phẩm Hoa Mai',    'daily',   50, 'BinhThanh', 15);

-- 7. Chuyến xe ghép đơn, sơ đồ LIFO 2D, lịch cửa xuất và giám sát nhiệt độ thùng xe
CREATE TABLE IF NOT EXISTS trips (
  id INTEGER PRIMARY KEY,
  trip_no TEXT UNIQUE NOT NULL,
  plate TEXT REFERENCES vehicles(plate),
  route_zone TEXT NOT NULL,
  storage TEXT NOT NULL,
  dock TEXT,
  slot_start TEXT,
  slot_end TEXT,
  est_load_min INTEGER NOT NULL DEFAULT 40,
  status TEXT NOT NULL DEFAULT 'planned',
  load_plan_json TEXT,
  fill_pct REAL NOT NULL DEFAULT 0,
  saved_vnd INTEGER NOT NULL DEFAULT 0,
  eta_text TEXT,
  sla_risk_pct INTEGER NOT NULL DEFAULT 0,
  temp_log_json TEXT,
  proof_note TEXT,
  created_at TEXT NOT NULL
);

-- 8. Đợt kiểm kê theo rủi ro (Storage CV3)
CREATE TABLE IF NOT EXISTS cycle_counts (
  id INTEGER PRIMARY KEY,
  batch_id INTEGER REFERENCES batches(id),
  zone TEXT NOT NULL,
  bin INTEGER NOT NULL,
  sku TEXT NOT NULL,
  batch_no TEXT NOT NULL,
  q_system INTEGER NOT NULL,
  q_physical INTEGER,
  variance INTEGER DEFAULT 0,
  val_diff INTEGER DEFAULT 0,
  status TEXT NOT NULL DEFAULT 'open',
  rca_hint TEXT,
  approval_level TEXT,
  note TEXT,
  created_by TEXT,
  approved_by TEXT,
  created_at TEXT NOT NULL
);

-- 9. Điều chuyển hàng giữa các vị trí/khu xác nhận 2 đầu (Storage CV4)
CREATE TABLE IF NOT EXISTS transfers (
  id INTEGER PRIMARY KEY,
  batch_id INTEGER REFERENCES batches(id),
  sku TEXT NOT NULL,
  batch_no TEXT NOT NULL,
  from_zone TEXT NOT NULL,
  from_bin INTEGER NOT NULL,
  to_zone TEXT NOT NULL,
  to_bin INTEGER NOT NULL,
  qty INTEGER NOT NULL CHECK (qty > 0),
  status TEXT NOT NULL DEFAULT 'in_transit',
  note TEXT,
  created_by TEXT,
  confirmed_by TEXT,
  created_at TEXT NOT NULL,
  completed_at TEXT
);

-- 10. Lịch sử thao tác liên phòng ban (Audit Trail của mọi role)
CREATE TABLE IF NOT EXISTS audit_logs (
  id INTEGER PRIMARY KEY,
  ts TEXT NOT NULL,
  username TEXT NOT NULL,
  user_name TEXT NOT NULL,
  role TEXT NOT NULL,
  module TEXT NOT NULL,
  action TEXT NOT NULL,
  ref_no TEXT,
  detail TEXT
);
CREATE INDEX IF NOT EXISTS idx_audit_ts ON audit_logs(ts DESC);

-- 11. Hệ thống chat nội bộ trao đổi giữa các user/role
CREATE TABLE IF NOT EXISTS team_messages (
  id INTEGER PRIMARY KEY,
  ts TEXT NOT NULL,
  sender_user TEXT NOT NULL,
  sender_name TEXT NOT NULL,
  sender_role TEXT NOT NULL,
  channel TEXT NOT NULL DEFAULT 'all',
  ref_no TEXT,
  body TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_team_msg_ch ON team_messages(channel, id DESC);
