import axios from "axios";

const api = axios.create({
  baseURL: process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000",
  timeout: 120000, // 2 phút cho LLM processing
});

export default api;

// ── Types ───────────────────────────────────────────────────────────────────

export interface POItem {
  style_code: string;
  style_name: string;
  color_name: string;
  size: string;
  total_quantity: number;
  unit_price: number;
  total_price: number;
}

export interface POResult {
  status: string;
  po_id: number | null;
  timestamp: string;
  po_number: string;
  style_code: string;
  style_name: string;
  buyer: string;
  factory: string;
  total_qty: number;
  total_amount: number;
  item_count: number;
  items: POItem[];
  excel_path: string;
}

export interface TrimItem {
  trim_item: string;
  spec: string | null;
  supplier: string | null;
  supplier_code: string | null;
  placement: string | null;
  qty_per_garment: number;
  unit: string;
  total_qty: number | null;
}

export interface TrimlistResult {
  status: string;
  timestamp: string;
  item_count: number;
  trim_items: TrimItem[];
  excel_path: string;
}

export interface POHistory {
  id: number;
  po_number: string;
  buyer: string;
  seller: string;
  order_date: string;
  delivery_date: string;
  total_quantity: number;
  total_amount: number;
  created_at: string;
}

export interface TrimlistHistory {
  filename: string;
  timestamp: string;
  created_at: string;
  size_kb: number;
}

// ── API calls ────────────────────────────────────────────────────────────────

export interface AgentResult {
  status: "success" | "partial";
  timestamp: string;
  warning?: string;
  techpack_found: string[];
  po: POResult;
  trimlist: TrimlistResult | null;
}

export async function runAgent(file: File): Promise<AgentResult> {
  const form = new FormData();
  form.append("file", file);
  const res = await api.post("/api/agent/run", form);
  return res.data;
}

export function downloadAgentPO(timestamp: string) {
  window.open(`${process.env.NEXT_PUBLIC_API_URL}/api/agent/download/po/${timestamp}`, "_blank");
}

export function downloadAgentTrimlist(timestamp: string) {
  window.open(`${process.env.NEXT_PUBLIC_API_URL}/api/agent/download/trimlist/${timestamp}`, "_blank");
}

export function downloadAgentTrimlistPDF(timestamp: string) {
  window.open(`${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}/api/agent/trimlist-pdf/${timestamp}`, "_blank");
}

export async function processPO(file: File): Promise<POResult> {
  const form = new FormData();
  form.append("file", file);
  const res = await api.post("/api/po/process", form);
  return res.data;
}

export async function processTrimlist(
  file: File,
  meta: {
    po_number?: string;
    style_code?: string;
    style_name?: string;
    buyer?: string;
    factory?: string;
    order_qty?: number;
    season?: string;
  }
): Promise<TrimlistResult> {
  const form = new FormData();
  form.append("file", file);
  form.append("po_number",  meta.po_number  || "");
  form.append("style_code", meta.style_code || "");
  form.append("style_name", meta.style_name || "");
  form.append("buyer",      meta.buyer      || "");
  form.append("factory",    meta.factory    || "");
  form.append("order_qty",  String(meta.order_qty || 0));
  form.append("season",     meta.season     || "");
  const res = await api.post("/api/trimlist/process", form);
  return res.data;
}

export async function getPOHistory(): Promise<POHistory[]> {
  const res = await api.get("/api/history/po");
  return res.data.data || [];
}

export async function getTrimlistHistory(): Promise<TrimlistHistory[]> {
  const res = await api.get("/api/history/trimlist");
  return res.data.data || [];
}

export function downloadPO(timestamp: string) {
  window.open(
    `${process.env.NEXT_PUBLIC_API_URL}/api/po/download/${timestamp}`,
    "_blank"
  );
}

export function downloadTrimlist(timestamp: string) {
  window.open(
    `${process.env.NEXT_PUBLIC_API_URL}/api/trimlist/download/${timestamp}`,
    "_blank"
  );
}

// ── Task History — 2 bảng riêng (Task A PO↔GO & Task B Trimlist) ─────────────

/** Trường hiển thị chung mà dashboard dùng. */
export interface TaskHistoryBase {
  id?:         number | string;
  token:       string;
  status:      "success" | "partial" | "error";
  file_name?:  string;
  po_number?:  string;
  style_code?: string;
  qty?:        number;
  item_count?: number;   // Task A: số dòng so sánh (compared) · Task B: số trim item
  warning?:    string;
  error_msg?:  string;
  created_at?: string;
}

export interface TaskAHistoryRow extends TaskHistoryBase {
  compared?:       number;
  go_source?:      string;
  batch_go_token?: string;
  report_token?:   string;
  alerts_token?:   string;
}

export type TaskBHistoryRow = TaskHistoryBase;

export interface TaskAHistorySave {
  token:           string;
  status:          "success" | "partial" | "error";
  file_name?:      string | null;
  po_number?:      string | null;
  style_code?:     string | null;
  qty?:            number;
  compared?:       number;
  go_source?:      string | null;
  batch_go_token?: string | null;
  report_token?:   string | null;
  alerts_token?:   string | null;
  warning?:        string | null;
  error?:          string | null;
}

export interface TaskBHistorySave {
  token:       string;
  status:      "success" | "partial" | "error";
  file_name?:  string | null;
  po_number?:  string | null;
  style_code?: string | null;
  qty?:        number;
  item_count?: number;
  warning?:    string | null;
  error?:      string | null;
}

export async function getTaskAHistory(): Promise<TaskAHistoryRow[]> {
  const res = await api.get("/api/task-a/history");
  return res.data.data || [];
}

export async function getTaskBHistory(): Promise<TaskBHistoryRow[]> {
  const res = await api.get("/api/task-b/history");
  return res.data.data || [];
}

export async function saveTaskAHistory(entry: TaskAHistorySave): Promise<void> {
  await api.post("/api/task-a/history", entry);
}

export async function saveTaskBHistory(entry: TaskBHistorySave): Promise<void> {
  await api.post("/api/task-b/history", entry);
}

export function downloadTaskAFile(filename: string) {
  window.open(`${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}/api/task-a/download/${filename}`, "_blank");
}

export function downloadTaskBExcel(token: string) {
  window.open(`${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}/api/task-b/download/${token}`, "_blank");
}

export function downloadTaskBPdf(token: string) {
  window.open(`${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}/api/task-b/pdf/${token}`, "_blank");
}

// Gửi Batch GO (Task A) qua Gmail / Telegram
export async function sendTaskAEmail(body: {
  filename: string; to_email: string; po_number?: string; style_code?: string; qty?: number;
}): Promise<string> {
  const res = await api.post("/api/task-a/send-email", body);
  return res.data?.message || "Đã gửi email";
}

export async function sendTaskATelegram(body: {
  filename: string; po_number?: string; style_code?: string; qty?: number;
}): Promise<string> {
  const res = await api.post("/api/task-a/send-telegram", body);
  return res.data?.message || "Đã gửi Telegram";
}

// Gửi Trimlist (Task B) qua Gmail / Telegram
export async function sendTaskBEmail(body: {
  token: string; to_email: string; po_number?: string; style_code?: string; qty?: number; item_count?: number;
}): Promise<string> {
  const res = await api.post("/api/task-b/send-email", body);
  return res.data?.message || "Đã gửi email";
}

export async function sendTaskBTelegram(body: {
  token: string; po_number?: string; style_code?: string; qty?: number; item_count?: number;
}): Promise<string> {
  const res = await api.post("/api/task-b/send-telegram", body);
  return res.data?.message || "Đã gửi Telegram";
}
