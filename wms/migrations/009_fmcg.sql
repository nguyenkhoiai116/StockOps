-- Thuộc tính sản phẩm theo danh mục FMCG chuẩn hóa (file Excel StockOps_DanhMuc_FMCG-v2).
-- Mọi cột đều cho phép trống: SKU cũ hoặc SKU thêm trên web chưa có các thông tin này vẫn hợp lệ.
ALTER TABLE products ADD COLUMN barcode TEXT;                          -- mã vạch EAN-13
ALTER TABLE products ADD COLUMN pack INTEGER CHECK (pack > 0);         -- quy cách: số đơn vị lẻ trong 1 thùng
ALTER TABLE products ADD COLUMN dims TEXT;                             -- kích thước thùng "D x R x C" (cm)
ALTER TABLE products ADD COLUMN vol REAL CHECK (vol > 0);              -- thể tích 1 thùng (m³)
ALTER TABLE products ADD COLUMN tmin REAL;                             -- nhiệt độ bảo quản thấp nhất (°C)
ALTER TABLE products ADD COLUMN tmax REAL;                             -- nhiệt độ bảo quản cao nhất (°C)
ALTER TABLE products ADD COLUMN shelf INTEGER CHECK (shelf > 0);       -- hạn sử dụng tính từ ngày sản xuất (ngày)
ALTER TABLE products ADD COLUMN fefo INTEGER CHECK (fefo >= 0);        -- ngưỡng cảnh báo FEFO: còn <= bấy nhiêu ngày thì báo
ALTER TABLE products ADD COLUMN qc INTEGER NOT NULL DEFAULT 0 CHECK (qc IN (0, 1));   -- 1 = phải kiểm QC khi nhập
ALTER TABLE products ADD COLUMN abc TEXT CHECK (abc IN ('A', 'B', 'C'));             -- phân loại ABC theo giá trị
