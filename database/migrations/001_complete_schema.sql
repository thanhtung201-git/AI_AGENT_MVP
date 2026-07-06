-- ============================================================
-- AI Agent MVP — Complete Database Schema
-- Chạy file này trong Supabase SQL Editor
-- ============================================================

-- ── 1. trimlist_sessions ─────────────────────────────────────
-- Mỗi lần AI tạo trimlist từ 1 techpack
CREATE TABLE IF NOT EXISTS trimlist_sessions (
  id            bigserial PRIMARY KEY,
  po_id         bigint REFERENCES purchase_orders(id) ON DELETE SET NULL,
  po_number     text,
  style_code    text,
  style_name    text,
  buyer         text,
  factory       text,
  order_qty     int4,
  techpack_file text,          -- tên file techpack đã dùng
  item_count    int4 DEFAULT 0,
  excel_path    text,          -- đường dẫn file Excel output
  created_at    timestamptz DEFAULT now()
);

-- ── 2. trim_items ─────────────────────────────────────────────
-- Từng dòng trim item trong 1 trimlist session
CREATE TABLE IF NOT EXISTS trim_items (
  id              bigserial PRIMARY KEY,
  session_id      bigint REFERENCES trimlist_sessions(id) ON DELETE CASCADE,
  po_number       text,
  supplier_code   text,
  trim_item       text NOT NULL,
  spec            text,
  supplier        text,
  qty_per_garment numeric,
  unit            text,
  total_qty       numeric,
  placement       text,
  source_file     text,
  created_at      timestamptz DEFAULT now()
);

-- ── 3. recap_sessions ────────────────────────────────────────
-- Mỗi lần PIC upload đơn đặt hàng để đối chiếu
CREATE TABLE IF NOT EXISTS recap_sessions (
  id              bigserial PRIMARY KEY,
  po_number       text,
  order_filename  text,            -- tên file đơn đặt hàng
  trimlist_ref    text,            -- tên file trimlist tham chiếu
  total_items     int4 DEFAULT 0,
  ok_count        int4 DEFAULT 0,
  warning_count   int4 DEFAULT 0,
  error_count     int4 DEFAULT 0,
  verdict         text,            -- 'DAT' hoặc 'KHONG_DAT'
  excel_path      text,
  created_at      timestamptz DEFAULT now()
);

-- ── 4. recap_items ───────────────────────────────────────────
-- Chi tiết từng dòng kết quả đối chiếu
CREATE TABLE IF NOT EXISTS recap_items (
  id              bigserial PRIMARY KEY,
  session_id      bigint REFERENCES recap_sessions(id) ON DELETE CASCADE,
  item_no         int4,
  supplier_code   text,
  trim_item       text,
  spec_order      text,            -- spec trong đơn đặt hàng
  spec_ref        text,            -- spec trong trimlist tham chiếu
  supplier_order  text,
  supplier_ref    text,
  qty_ordered     numeric,
  qty_required    numeric,
  unit_order      text,
  unit_ref        text,
  status          text,            -- 'OK', 'ERROR', 'WARNING'
  error_detail    text,
  created_at      timestamptz DEFAULT now()
);

-- ── 5. scan_log ──────────────────────────────────────────────
-- Thay thế file .processed_log.json — theo dõi file PO đã xử lý
CREATE TABLE IF NOT EXISTS scan_log (
  id           bigserial PRIMARY KEY,
  filename     text UNIQUE NOT NULL,
  file_path    text,
  status       text,                -- 'success', 'partial', 'error'
  po_number    text,
  style_code   text,
  total_qty    int4,
  trim_count   int4 DEFAULT 0,
  po_id        bigint REFERENCES purchase_orders(id) ON DELETE SET NULL,
  session_id   bigint REFERENCES trimlist_sessions(id) ON DELETE SET NULL,
  timestamp    text,                -- dùng để tạo link download
  warning      text,
  error_msg    text,
  processed_at timestamptz DEFAULT now()
);

-- ── Indexes ──────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_trim_items_session    ON trim_items(session_id);
CREATE INDEX IF NOT EXISTS idx_trim_items_po         ON trim_items(po_number);
CREATE INDEX IF NOT EXISTS idx_recap_items_session   ON recap_items(session_id);
CREATE INDEX IF NOT EXISTS idx_trimlist_sessions_po  ON trimlist_sessions(po_id);
CREATE INDEX IF NOT EXISTS idx_scan_log_status       ON scan_log(status);
CREATE INDEX IF NOT EXISTS idx_scan_log_processed_at ON scan_log(processed_at DESC);
CREATE INDEX IF NOT EXISTS idx_po_items_size         ON po_items USING gin(size_breakdown);

-- ── Thêm cột size vào po_items (nếu chưa có) ─────────────────
ALTER TABLE po_items ADD COLUMN IF NOT EXISTS size text;

-- ── Tắt RLS cho các bảng do backend ghi (service role) ───────
ALTER TABLE scan_log          DISABLE ROW LEVEL SECURITY;
ALTER TABLE trimlist_sessions DISABLE ROW LEVEL SECURITY;
ALTER TABLE trim_items        DISABLE ROW LEVEL SECURITY;
ALTER TABLE recap_sessions    DISABLE ROW LEVEL SECURITY;
ALTER TABLE recap_items       DISABLE ROW LEVEL SECURITY;

-- ============================================================
-- Xong! Tổng cộng 9 bảng:
--   purchase_orders, po_items, execution_logs, conversation_history
--   trimlist_sessions, trim_items
--   recap_sessions, recap_items
--   scan_log
-- ============================================================
