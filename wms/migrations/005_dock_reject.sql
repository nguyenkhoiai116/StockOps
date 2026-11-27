-- Biên bản từ chối và trả hàng cho nhà cung cấp ngay tại cửa nhập (Dock Rejection / RTV).
-- Gồm 2 loại: từ chối toàn bộ chuyến xe (full) hoặc từ chối 1 phần hàng móp/hỏng lúc dỡ xe (partial).
ALTER TABLE pos ADD COLUMN reject_reason TEXT;

CREATE TABLE IF NOT EXISTS dock_rejections (
  id INTEGER PRIMARY KEY,
  rej_no TEXT UNIQUE NOT NULL,
  po_id INTEGER NOT NULL REFERENCES pos(id),
  po_no TEXT NOT NULL,
  sku TEXT NOT NULL,
  product_name TEXT NOT NULL,
  supplier TEXT,
  kind TEXT NOT NULL CHECK (kind IN ('full', 'partial')),
  qty_rejected INTEGER NOT NULL CHECK (qty_rejected > 0),
  qty_accepted INTEGER NOT NULL DEFAULT 0,
  reason TEXT NOT NULL,
  measured_temp REAL,
  plate TEXT,
  driver TEXT,
  dock TEXT,
  created_by TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_dock_rej_po ON dock_rejections(po_id);
