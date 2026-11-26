-- Số dãy kệ / ô mỗi dãy / tầng của từng khu (thay hằng BINS = 12 cũ). Số ô của khu = racks * bays * levels.
ALTER TABLE zones ADD COLUMN racks INTEGER NOT NULL DEFAULT 2 CHECK (racks > 0);
ALTER TABLE zones ADD COLUMN bays INTEGER NOT NULL DEFAULT 2 CHECK (bays > 0);
ALTER TABLE zones ADD COLUMN levels INTEGER NOT NULL DEFAULT 3 CHECK (levels > 0);

UPDATE zones SET racks=4, bays=6, levels=4 WHERE code='DRY';
UPDATE zones SET racks=3, bays=5, levels=4 WHERE code='COS';
UPDATE zones SET racks=2, bays=4, levels=3 WHERE code='CHL';
UPDATE zones SET racks=2, bays=4, levels=3 WHERE code='FRZ';

-- Sức chứa mới, chỉ đổi khi người dùng chưa tự sửa (còn đúng giá trị cũ).
UPDATE zones SET cap=20000 WHERE code='DRY' AND cap=3000;
UPDATE zones SET cap=6000 WHERE code='COS' AND cap=400;
UPDATE zones SET cap=3000 WHERE code='CHL' AND cap=800;
UPDATE zones SET cap=2000 WHERE code='FRZ' AND cap=500;
