-- Số PO / số đơn bán không được trùng. DB tự chặn, kể cả khi code đánh số sai.
-- (SQLite không thêm UNIQUE vào bảng có sẵn được, nên dùng UNIQUE INDEX.)
CREATE UNIQUE INDEX IF NOT EXISTS ux_pos_po_no ON pos(po_no);
CREATE UNIQUE INDEX IF NOT EXISTS ux_sos_so_no ON sos(so_no);
