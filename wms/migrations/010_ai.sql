-- Bảng cho trợ lý Kvis (spec: docs/superpowers/specs/2026-11-26-kvis-agent-design.md). Số 010 vì 009 đã dùng cho danh mục FMCG.
-- chat_logs: mỗi câu hỏi 1 dòng, để chấm điểm và theo dõi chi phí token. Giao diện chat không đọc bảng này.
CREATE TABLE IF NOT EXISTS chat_logs (
  id INTEGER PRIMARY KEY,
  ts TEXT NOT NULL,
  user_id INTEGER REFERENCES users(id),
  question TEXT NOT NULL,
  reply TEXT,
  model TEXT,
  mode TEXT NOT NULL DEFAULT 'agent' CHECK (mode IN ('agent', 'snapshot')),   -- snapshot = lui về cách dán ảnh chụp số liệu
  steps INTEGER NOT NULL DEFAULT 0,          -- số lần gọi LLM
  tools TEXT,                                -- JSON [{name, args, ok}]
  tok_in INTEGER NOT NULL DEFAULT 0,
  tok_out INTEGER NOT NULL DEFAULT 0,
  ms INTEGER,                                -- tổng thời gian trả lời (mili giây)
  error TEXT);

-- agent_actions: đề xuất của Kvis (phần A3). Chỉ thành nghiệp vụ thật khi người có quyền bấm Xác nhận.
CREATE TABLE IF NOT EXISTS agent_actions (
  id INTEGER PRIMARY KEY,
  ts TEXT NOT NULL,
  user_id INTEGER REFERENCES users(id),
  chat_id INTEGER REFERENCES chat_logs(id),
  kind TEXT NOT NULL CHECK (kind IN ('po', 'adjust')),
  payload TEXT NOT NULL,                     -- JSON: po {product_id, sku, qty, eta}; adjust {batch_id, batch_no, delta, qty}
  summary TEXT NOT NULL,                     -- câu tiếng Việt hiện trên thẻ
  reason TEXT,                               -- lý do Kvis đưa ra
  status TEXT NOT NULL DEFAULT 'proposed' CHECK (status IN ('proposed', 'confirmed', 'rejected')),
  decided_by INTEGER REFERENCES users(id),
  decided_at TEXT,
  result TEXT);                              -- vd "PO-012", hoặc lý do lần xác nhận cuối bị từ chối
CREATE INDEX IF NOT EXISTS ix_agent_actions ON agent_actions(user_id, status);

-- doc_chunks: đoạn tài liệu trong knowledge/ kèm vector embedding (phần A2, do scripts/build_index.py ghi).
CREATE TABLE IF NOT EXISTS doc_chunks (
  id INTEGER PRIMARY KEY,
  doc TEXT NOT NULL,                         -- tên file trong knowledge/
  title TEXT,
  heading TEXT,
  text TEXT NOT NULL,
  emb BLOB,                                  -- float32, đã chuẩn hóa (tích vô hướng = cosine)
  model TEXT,                                -- tên model embedding
  built_at TEXT);
