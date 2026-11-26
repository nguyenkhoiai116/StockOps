-- Hủy đơn / soạn lại: dòng picks cũ được đánh dấu released=1 thay vì xóa, để còn lịch sử "đã từng giữ lô nào".
-- released=1: không còn giữ hàng (reserved đã trả về lô) và KHÔNG bị trừ khi xuất kho.
ALTER TABLE picks ADD COLUMN released INTEGER NOT NULL DEFAULT 0 CHECK (released IN (0, 1));
