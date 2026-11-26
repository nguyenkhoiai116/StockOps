-- Sổ giao dịch trỏ thẳng vào lô (batch_id) và ghi ai làm (who), để đối soát được:
--   với mọi lô: SUM(txs.qty WHERE batch_id = lô) = batches.qty
-- Trước đây txs chỉ có batch_no (chữ, không duy nhất) nên không biết dòng nào thuộc lô nào.
ALTER TABLE txs ADD COLUMN batch_id INTEGER REFERENCES batches(id);
ALTER TABLE txs ADD COLUMN who TEXT;   -- tài khoản thực hiện; NULL = hệ thống (dữ liệu mẫu, script)
-- Dòng cũ: điền batch_id khi số lô + sản phẩm khớp đúng 1 lô (khớp nhiều lô thì để NULL, không đoán)
UPDATE txs SET batch_id = (SELECT b.id FROM batches b WHERE b.batch_no = txs.batch_no AND b.product_id = txs.product_id)
 WHERE batch_id IS NULL
   AND (SELECT COUNT(*) FROM batches b WHERE b.batch_no = txs.batch_no AND b.product_id = txs.product_id) = 1;
CREATE INDEX IF NOT EXISTS ix_txs_batch ON txs(batch_id);
