"use client";
import { useState, useEffect } from "react";
import toast from "react-hot-toast";
import axios from "axios";
import {
  Download, Loader2, CheckCircle2, ClipboardList,
  RefreshCw, Package, Send,
} from "lucide-react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface TrimSession {
  id: number;
  po_number: string;
  style_code: string;
  item_count: number;
  order_qty: number;
  techpack_file: string;
  created_at: string;
}

interface AggregatedItem {
  trim_item: string;
  spec: string;
  supplier: string;
  unit: string;
  total_qty: number;
  po_sources: string;
}

interface AggregateResult {
  timestamp: string;
  meta: { po_count: number; po_numbers: string; date: string };
  total_items: number;
  total_qty: number;
  items: AggregatedItem[];
}

interface HistoryEntry {
  timestamp: string;
  saved_at: string;
  po_count: number;
  po_numbers: string;
  total_items: number;
  total_qty: number;
  session_ids: number[];
}

export default function RecapPage() {
  const [sessions,  setSessions]  = useState<TrimSession[]>([]);
  const [selected,  setSelected]  = useState<Set<number>>(new Set());
  const [loading,   setLoading]   = useState(false);
  const [fetching,  setFetching]  = useState(true);
  const [result,    setResult]    = useState<AggregateResult | null>(null);
  const [history,   setHistory]   = useState<HistoryEntry[]>([]);
  const [emailModal, setEmailModal] = useState<HistoryEntry | null>(null);
  const [toEmail,    setToEmail]    = useState("");
  const [sending,    setSending]    = useState(false);

  useEffect(() => { loadSessions(); loadHistory(); }, []);

  async function loadHistory() {
    try {
      const res = await axios.get(`${API}/api/recap/history`);
      setHistory(res.data.history || []);
    } catch { /* ignore */ }
  }

  async function loadSessions() {
    setFetching(true);
    try {
      const res = await axios.get(`${API}/api/recap/sessions`);
      setSessions(res.data.sessions || []);
    } catch {
      toast.error("Không tải được danh sách Trimlist");
    } finally {
      setFetching(false);
    }
  }

  function toggleSession(id: number) {
    setSelected(prev => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  }

  function toggleAll() {
    if (selected.size === sessions.length) setSelected(new Set());
    else setSelected(new Set(sessions.map(s => s.id)));
  }

  async function sendRecapTelegram(h: HistoryEntry) {
    const tid = toast.loading("Đang gửi Telegram...");
    try {
      await axios.post(`${API}/api/recap/send-telegram`, {
        timestamp:   h.timestamp,
        po_numbers:  h.po_numbers,
        total_items: h.total_items,
        total_qty:   h.total_qty,
      });
      toast.success("Đã gửi Recap qua Telegram!", { id: tid });
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } }; message?: string };
      toast.error(err?.response?.data?.detail || "Gửi Telegram thất bại", { id: tid });
    }
  }

  async function handleSendEmail() {
    if (!emailModal || !toEmail) return;
    setSending(true);
    try {
      await axios.post(`${API}/api/recap/send-email`, {
        to_email:    toEmail,
        timestamp:   emailModal.timestamp,
        po_numbers:  emailModal.po_numbers,
        total_items: emailModal.total_items,
        total_qty:   emailModal.total_qty,
      });
      toast.success(`Đã gửi email đến ${toEmail}`);
      setEmailModal(null);
      setToEmail("");
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } }; message?: string };
      toast.error(err?.response?.data?.detail || err?.message || "Gửi email thất bại");
    } finally {
      setSending(false);
    }
  }

  async function handleAggregate() {
    if (selected.size === 0) { toast.error("Chọn ít nhất 1 Trimlist"); return; }
    setLoading(true); setResult(null);
    try {
      const res = await axios.post(`${API}/api/recap/aggregate`, {
        session_ids: Array.from(selected),
      });
      setResult(res.data);
      toast.success(`Tổng hợp xong: ${res.data.total_items} loại trim`);
      loadHistory();
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } }; message?: string };
      toast.error(err?.response?.data?.detail || err?.message || "Lỗi tổng hợp");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="p-8 max-w-6xl mx-auto">
      <h1 className="text-xl font-bold text-gray-900 mb-1">Recap Trim List</h1>
      <p className="text-sm text-gray-500 mb-6">
        Chọn các Trimlist đã tạo → hệ thống gom nhóm và tính tổng qty từng loại phụ liệu để đặt hàng nhà cung cấp.
      </p>

      {/* Danh sách sessions */}
      <div className="bg-white rounded-xl border border-gray-200 mb-4">
        <div className="flex items-center justify-between px-5 py-3 border-b border-gray-200">
          <h2 className="text-sm font-semibold text-gray-900">
            Danh sách Trimlist đã tạo
            {sessions.length > 0 && (
              <span className="ml-2 text-xs font-normal text-gray-400">({sessions.length} file)</span>
            )}
          </h2>
          <button
            onClick={loadSessions}
            className="flex items-center gap-1.5 text-xs text-gray-500 hover:text-gray-700"
          >
            <RefreshCw className="w-3.5 h-3.5" /> Làm mới
          </button>
        </div>

        {fetching ? (
          <div className="flex items-center justify-center py-12 text-gray-400">
            <Loader2 className="w-5 h-5 animate-spin mr-2" /> Đang tải...
          </div>
        ) : sessions.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-12 text-gray-400">
            <Package className="w-8 h-8 mb-2" />
            <p className="text-sm">Chưa có Trimlist nào. Hãy tạo Trimlist trước.</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-4 py-2.5 w-10">
                    <input
                      type="checkbox"
                      checked={selected.size === sessions.length && sessions.length > 0}
                      onChange={toggleAll}
                      className="rounded border-gray-300 text-indigo-600"
                    />
                  </th>
                  {["PO Number", "Style Code", "Số loại trim", "Order Qty", "Ngày tạo"].map(h => (
                    <th key={h} className="text-left px-3 py-2.5 text-xs font-medium text-gray-500 uppercase tracking-wide">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {sessions.map(s => (
                  <tr
                    key={s.id}
                    onClick={() => toggleSession(s.id)}
                    className={`cursor-pointer transition-colors ${
                      selected.has(s.id) ? "bg-indigo-50" : "hover:bg-gray-50"
                    }`}
                  >
                    <td className="px-4 py-2.5">
                      <input
                        type="checkbox"
                        checked={selected.has(s.id)}
                        onChange={() => toggleSession(s.id)}
                        onClick={e => e.stopPropagation()}
                        className="rounded border-gray-300 text-indigo-600"
                      />
                    </td>
                    <td className="px-3 py-2.5 font-medium text-gray-900">{s.po_number || "—"}</td>
                    <td className="px-3 py-2.5 text-gray-600">{s.style_code || "—"}</td>
                    <td className="px-3 py-2.5 text-gray-600">{s.item_count ?? "—"}</td>
                    <td className="px-3 py-2.5 text-gray-600">
                      {s.order_qty ? s.order_qty.toLocaleString() + " pcs" : "—"}
                    </td>
                    <td className="px-3 py-2.5 text-gray-400 text-xs">
                      {s.created_at ? new Date(s.created_at).toLocaleString("vi-VN") : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* Footer */}
        {sessions.length > 0 && (
          <div className="px-5 py-3 border-t border-gray-200 flex items-center justify-between">
            <p className="text-xs text-gray-500">
              Đã chọn <span className="font-semibold text-indigo-600">{selected.size}</span> / {sessions.length} trimlist
            </p>
            <button
              onClick={handleAggregate}
              disabled={selected.size === 0 || loading}
              className="flex items-center gap-2 px-5 py-2 bg-indigo-600 text-white text-sm font-medium
                rounded-lg hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {loading
                ? <><Loader2 className="w-4 h-4 animate-spin" /> Đang tổng hợp...</>
                : <><ClipboardList className="w-4 h-4" /> Tổng hợp Trim</>}
            </button>
          </div>
        )}
      </div>

      {/* Lịch sử tổng hợp */}
      {history.length > 0 && (
        <div className="bg-white rounded-xl border border-gray-200 mb-4">
          <div className="px-5 py-3 border-b border-gray-200">
            <h2 className="text-sm font-semibold text-gray-900">Lịch sử tổng hợp</h2>
          </div>
          <div className="divide-y divide-gray-100">
            {history.map((h, i) => (
              <div key={i} className="flex items-center justify-between px-5 py-3 hover:bg-gray-50">
                <div className="flex items-center gap-4">
                  <div className="w-8 h-8 rounded-full bg-indigo-100 flex items-center justify-center flex-shrink-0">
                    <ClipboardList className="w-4 h-4 text-indigo-600" />
                  </div>
                  <div>
                    <p className="text-sm font-medium text-gray-900">
                      {h.po_count} PO · {h.total_items} loại trim · {h.total_qty.toLocaleString()} qty
                    </p>
                    <p className="text-xs text-gray-400 mt-0.5">{h.po_numbers}</p>
                  </div>
                </div>
                <div className="flex items-center gap-3 flex-shrink-0">
                  <span className="text-xs text-gray-400">{h.saved_at}</span>
                  <button
                    onClick={() => window.open(`${API}/api/recap/download/${h.timestamp}`, "_blank")}
                    className="flex items-center gap-1 text-xs text-indigo-600 hover:text-indigo-800 font-medium"
                  >
                    <Download className="w-3.5 h-3.5" /> Excel
                  </button>
                  <button
                    onClick={() => { setEmailModal(h); setToEmail(""); }}
                    className="flex items-center gap-1 text-xs text-emerald-600 hover:text-emerald-800 font-medium"
                  >
                    <Send className="w-3.5 h-3.5" /> Email
                  </button>
                  <button
                    onClick={() => sendRecapTelegram(h)}
                    className="flex items-center gap-1 text-xs text-sky-600 hover:text-sky-800 font-medium"
                    title="Gửi Telegram"
                  >
                    ✈ Telegram
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Kết quả */}
      {result && (
        <div className="space-y-4">
          {/* Summary banner */}
          <div className="bg-green-50 border border-green-200 rounded-xl p-4 flex items-center justify-between">
            <div className="flex items-center gap-3">
              <CheckCircle2 className="w-6 h-6 text-green-600" />
              <div>
                <p className="font-semibold text-green-800">
                  Tổng hợp thành công — {result.total_items} loại phụ liệu
                </p>
                <p className="text-xs text-gray-500 mt-0.5">
                  {result.meta.po_count} PO · Tổng qty: {result.total_qty.toLocaleString()} · {result.meta.po_numbers}
                </p>
              </div>
            </div>
            <button
              onClick={() => window.open(`${API}/api/recap/download/${result.timestamp}`, "_blank")}
              className="flex items-center gap-1.5 text-sm text-indigo-600 hover:text-indigo-800 font-medium whitespace-nowrap"
            >
              <Download className="w-4 h-4" /> Download Excel
            </button>
          </div>

          {/* Bảng kết quả */}
          <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
            <div className="px-5 py-3 border-b border-gray-200">
              <h3 className="text-sm font-semibold text-gray-900">Bảng tổng hợp phụ liệu cần đặt</h3>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="bg-gray-50">
                  <tr>
                    {["#", "Trim Item", "Spec / Mô tả", "Nhà cung cấp", "Unit", "Tổng Qty", "PO nguồn"].map(h => (
                      <th key={h} className="text-left px-3 py-2.5 text-xs font-medium text-gray-500 uppercase tracking-wide whitespace-nowrap">
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {result.items.map((item, i) => (
                    <tr key={i} className={i % 2 === 1 ? "bg-blue-50/30" : "hover:bg-gray-50"}>
                      <td className="px-3 py-2 text-gray-400 text-xs">{i + 1}</td>
                      <td className="px-3 py-2 font-medium text-gray-900">{item.trim_item}</td>
                      <td className="px-3 py-2 text-gray-600 text-xs">{item.spec || "—"}</td>
                      <td className="px-3 py-2 text-gray-700">{item.supplier || "—"}</td>
                      <td className="px-3 py-2 text-gray-500">{item.unit || "—"}</td>
                      <td className="px-3 py-2 text-right font-semibold text-indigo-700">
                        {item.total_qty.toLocaleString()}
                      </td>
                      <td className="px-3 py-2 text-xs text-gray-400">{item.po_sources || "—"}</td>
                    </tr>
                  ))}
                </tbody>
                <tfoot>
                  <tr className="bg-yellow-50 border-t-2 border-yellow-200">
                    <td colSpan={5} className="px-3 py-2.5 text-right font-bold text-gray-700 text-sm">
                      TỔNG CỘNG
                    </td>
                    <td className="px-3 py-2.5 text-right font-bold text-indigo-700 text-sm">
                      {result.total_qty.toLocaleString()}
                    </td>
                    <td />
                  </tr>
                </tfoot>
              </table>
            </div>
          </div>
        </div>
      )}
      {/* Modal gửi email */}
      {emailModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-white rounded-2xl shadow-xl w-full max-w-md p-6">
            <h3 className="text-base font-semibold text-gray-900 mb-1">Gửi Recap Trim qua Email</h3>
            <p className="text-xs text-gray-500 mb-4">
              {emailModal.po_count} PO · {emailModal.total_items} loại trim · {emailModal.total_qty.toLocaleString()} qty
            </p>

            <label className="block text-sm font-medium text-gray-700 mb-1.5">
              Địa chỉ email nhận
            </label>
            <input
              type="email"
              value={toEmail}
              onChange={e => setToEmail(e.target.value)}
              onKeyDown={e => e.key === "Enter" && handleSendEmail()}
              placeholder="example@gmail.com"
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 mb-4"
              autoFocus
            />

            <div className="flex gap-2 justify-end">
              <button
                onClick={() => setEmailModal(null)}
                className="px-4 py-2 text-sm text-gray-600 hover:text-gray-900 rounded-lg hover:bg-gray-100"
              >
                Huỷ
              </button>
              <button
                onClick={handleSendEmail}
                disabled={!toEmail || sending}
                className="flex items-center gap-2 px-5 py-2 bg-emerald-600 text-white text-sm font-medium
                  rounded-lg hover:bg-emerald-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                {sending
                  ? <><Loader2 className="w-4 h-4 animate-spin" /> Đang gửi...</>
                  : <><Send className="w-4 h-4" /> Gửi ngay</>}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
