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
