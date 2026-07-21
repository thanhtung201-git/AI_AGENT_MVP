-- ============================================================
-- Lịch sử xử lý — tách riêng 2 bảng cho dễ làm dashboard
--   task_a_history : Task A (PO ↔ GO Compare)
--   task_b_history : Task B (Generate Trimlist)
-- Chạy file này trong Supabase SQL Editor
-- ============================================================

-- Bỏ bảng gộp cũ nếu đã tạo trước đó (chưa có dữ liệu thật vì bị RLS chặn)
DROP TABLE IF EXISTS task_history;

-- ── Task A — PO ↔ GO Compare ─────────────────────────────────
CREATE TABLE IF NOT EXISTS task_a_history (
  id              bigserial PRIMARY KEY,
  token           text NOT NULL UNIQUE,             -- session token (gộp generate + compare)
  status          text NOT NULL DEFAULT 'partial',  -- success | partial | error
  file_name       text,                             -- tên file PO
  po_number       text,
  style_code      text,
  qty             int8 DEFAULT 0,                   -- tổng số lượng PO
  compared        int8 DEFAULT 0,                   -- số dòng đã so sánh
  go_source       text,                             -- 'uploaded' | 'generated'
  batch_go_token  text,                             -- file Batch GO để tải
  report_token    text,                             -- file Compare Report để tải
  alerts_token    text,                             -- file Alerts.json để tải
  warning         text,
  error_msg       text,
  created_at      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS task_a_history_created_idx ON task_a_history (created_at DESC);

-- ── Task B — Generate Trimlist ───────────────────────────────
CREATE TABLE IF NOT EXISTS task_b_history (
  id          bigserial PRIMARY KEY,
  token       text NOT NULL UNIQUE,             -- = excel_token (dùng để tải Excel)
  status      text NOT NULL DEFAULT 'success',  -- success | partial | error
  file_name   text,                             -- tên file Tech Pack
  po_number   text,
  style_code  text,
  qty         int8 DEFAULT 0,                   -- order qty
  item_count  int8 DEFAULT 0,                   -- số trim item
  warning     text,
  error_msg   text,
  created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS task_b_history_created_idx ON task_b_history (created_at DESC);

-- ── RLS ──────────────────────────────────────────────────────
-- Nhiều project Supabase bật cưỡng bức RLS trên mọi bảng public nên DISABLE bị
-- vô hiệu → PostgREST chặn INSERT: 42501. Cách chắc chắn: thêm policy cho phép
-- (backend là bên ghi bằng key server-side, không phải người dùng cuối).
ALTER TABLE task_a_history ENABLE ROW LEVEL SECURITY;
ALTER TABLE task_b_history ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS task_a_history_all ON task_a_history;
CREATE POLICY task_a_history_all ON task_a_history
  FOR ALL USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS task_b_history_all ON task_b_history;
CREATE POLICY task_b_history_all ON task_b_history
  FOR ALL USING (true) WITH CHECK (true);
