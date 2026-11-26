-- Mỗi ô kệ chỉ chứa 1 lô còn hàng. Lô về 0 thì ô được coi là trống và cấp cho lô khác (core.free_bin),
-- nên chặn ở DB trường hợp tăng lại lô cũ khiến 2 lô cùng nằm 1 ô.
-- Partial index (chỉ tính dòng qty > 0): lô đã về 0 không chiếm chỗ trong index.
CREATE UNIQUE INDEX IF NOT EXISTS ux_batches_bin ON batches(zone, bin) WHERE qty > 0;
