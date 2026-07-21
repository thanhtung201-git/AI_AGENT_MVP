"use client";
import { useMemo, useState, type ReactNode } from "react";
import toast from "react-hot-toast";
import { Clock, Search, RefreshCw, CheckCircle2, AlertTriangle, XCircle, Send, Plane, Loader2, X } from "lucide-react";

// ── Types ─────────────────────────────────────────────────────────────────────

/** Trường hiển thị chung cho dashboard của cả 2 task. */
export interface TaskHistoryBase {
  id?:         number | string;
  token:       string;
  status:      "success" | "partial" | "error";
  file_name?:  string;
  po_number?:  string;
  style_code?: string;
  qty?:        number;
  item_count?: number;
  warning?:    string;
  error_msg?:  string;
  created_at?: string;
}

// ── Component ─────────────────────────────────────────────────────────────────

export default function TaskHistory<T extends TaskHistoryBase>({
  rows, loading, onRefresh, renderDownloads, trimLabel = "TRIM", accent = "indigo",
  onSendEmail, onSendTelegram, canSend,
}: {
  rows:            T[];
  loading:         boolean;
  onRefresh:       () => void;
  renderDownloads: (row: T) => ReactNode;
  trimLabel?:      string;
  accent?:         "indigo" | "emerald";
  onSendEmail?:    (row: T, toEmail: string) => Promise<string>;
  onSendTelegram?: (row: T) => Promise<string>;
  canSend?:        (row: T) => boolean;   // chỉ hiện nút gửi khi có file để gửi
}) {
  const [query, setQuery] = useState("");
  const [date,  setDate]  = useState("");   // yyyy-mm-dd
  const [emailRow, setEmailRow] = useState<T | null>(null);
  const [toEmail,  setToEmail]  = useState("");
  const [sending,  setSending]  = useState(false);
  const [tgSending, setTgSending] = useState<string | null>(null);  // token đang gửi TG

  async function submitEmail() {
    if (!emailRow || !onSendEmail || !toEmail.trim()) return;
    setSending(true);
    const tid = toast.loading("Đang gửi email...");
    try {
      const msg = await onSendEmail(emailRow, toEmail.trim());
      toast.success(msg, { id: tid });
      setEmailRow(null); setToEmail("");
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } }; message?: string };
      toast.error(err?.response?.data?.detail || err?.message || "Gửi email thất bại", { id: tid });
    } finally { setSending(false); }
  }

  async function sendTelegram(row: T) {
    if (!onSendTelegram) return;
    setTgSending(row.token);
    const tid = toast.loading("Đang gửi Telegram...");
    try {
      const msg = await onSendTelegram(row);
      toast.success(msg, { id: tid });
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } }; message?: string };
      toast.error(err?.response?.data?.detail || err?.message || "Gửi Telegram thất bại", { id: tid });
    } finally { setTgSending(null); }
  }

  const showSend = (row: T) => (canSend ? canSend(row) : true);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return rows.filter(r => {
      if (q) {
        const hay = `${r.file_name ?? ""} ${r.po_number ?? ""} ${r.style_code ?? ""}`.toLowerCase();
        if (!hay.includes(q)) return false;
      }
      if (date && r.created_at) {
        if (!r.created_at.startsWith(date)) return false;
      }
      return true;
    });
  }, [rows, query, date]);

  const done   = rows.filter(r => r.status === "success").length;
  const errors = rows.filter(r => r.status === "error").length;

  const activeCard = accent === "emerald"
    ? "bg-emerald-50 border-emerald-300"
    : "bg-indigo-50 border-indigo-300";
  const activeNum  = accent === "emerald" ? "text-emerald-600" : "text-indigo-600";

  return (
    <section className="mt-10">
      {/* Stat cards */}
      <div className="grid grid-cols-3 gap-4 mb-6">
        <StatCard label="Tổng file"  value={rows.length} />
        <StatCard label="Đã xử lý"   value={done} highlight className={activeCard} numClass={activeNum} />
        <StatCard label="Có lỗi"     value={errors} numClass={errors > 0 ? "text-red-500" : undefined} />
      </div>

      {/* Header + filters */}
      <div className="flex flex-wrap items-center gap-3 mb-4">
        <h2 className="text-sm font-semibold text-gray-700 flex items-center gap-2 mr-auto">
          <Clock className="w-4 h-4 text-gray-400" />
          Lịch sử đã xử lý ({filtered.length} file)
        </h2>
        <div className="relative">
          <Search className="w-4 h-4 text-gray-400 absolute left-3 top-1/2 -translate-y-1/2" />
          <input
            value={query} onChange={e => setQuery(e.target.value)}
            placeholder="Tìm file, PO, style..."
            className="pl-9 pr-3 py-2 border border-gray-300 rounded-lg text-sm w-56
              focus:outline-none focus:ring-2 focus:ring-indigo-300"
          />
        </div>
        <input
          type="date" value={date} onChange={e => setDate(e.target.value)}
          className="px-3 py-2 border border-gray-300 rounded-lg text-sm text-gray-600
            focus:outline-none focus:ring-2 focus:ring-indigo-300"
        />
        <button onClick={onRefresh}
          className="flex items-center gap-2 text-sm text-gray-600 hover:text-gray-900 border border-gray-300 rounded-lg px-3 py-2 hover:bg-gray-50">
          <RefreshCw className={`w-4 h-4 ${loading ? "animate-spin" : ""}`} /> Refresh
        </button>
      </div>

      {/* Table */}
      <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
        {loading ? (
          <div className="p-10 text-center text-sm text-gray-400">Đang tải...</div>
        ) : filtered.length === 0 ? (
          <div className="p-10 text-center text-sm text-gray-400">
            {rows.length === 0 ? "Chưa có lần xử lý nào" : "Không có kết quả khớp bộ lọc"}
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-gray-50">
                <tr>
                  {["FILE", "PO NUMBER", "STYLE", "QTY", trimLabel, "XỬ LÝ LÚC", "TT", ""].map(h => (
                    <th key={h} className="text-left px-4 py-2.5 text-xs font-medium text-gray-500 uppercase tracking-wide whitespace-nowrap">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {filtered.map((r, i) => (
                  <tr key={r.id ?? r.token ?? i} className="hover:bg-gray-50">
                    <td className="px-4 py-3 font-mono text-xs text-gray-700 max-w-56 truncate" title={r.file_name}>
                      {r.file_name || "—"}
                    </td>
                    <td className="px-4 py-3 text-xs">{r.po_number || "—"}</td>
                    <td className="px-4 py-3 font-mono text-xs">{r.style_code || "—"}</td>
                    <td className="px-4 py-3 text-xs text-right">{r.qty ? r.qty.toLocaleString() : "—"}</td>
                    <td className="px-4 py-3 text-xs text-right">{r.item_count ? r.item_count.toLocaleString() : "—"}</td>
                    <td className="px-4 py-3 text-xs text-gray-400 whitespace-nowrap">
                      {r.created_at ? new Date(r.created_at).toLocaleString("vi-VN") : "—"}
                    </td>
                    <td className="px-4 py-3"><StatusBadge status={r.status} /></td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-3 flex-wrap">
                        {renderDownloads(r)}
                        {onSendEmail && showSend(r) && (
                          <button onClick={() => { setEmailRow(r); setToEmail(""); }}
                            title="Gửi Gmail"
                            className="text-sky-600 hover:text-sky-800">
                            <Send className="w-4 h-4" />
                          </button>
                        )}
                        {onSendTelegram && showSend(r) && (
                          <button onClick={() => sendTelegram(r)} disabled={tgSending === r.token}
                            title="Gửi Telegram"
                            className="text-blue-500 hover:text-blue-700 disabled:opacity-40">
                            {tgSending === r.token
                              ? <Loader2 className="w-4 h-4 animate-spin" />
                              : <Plane className="w-4 h-4" />}
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Email modal */}
      {emailRow && (
        <div className="fixed inset-0 bg-black/30 flex items-center justify-center z-50 p-4"
          onClick={() => !sending && setEmailRow(null)}>
          <div className="bg-white rounded-xl shadow-xl w-full max-w-md p-5" onClick={e => e.stopPropagation()}>
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-sm font-semibold text-gray-800 flex items-center gap-2">
                <Send className="w-4 h-4 text-sky-600" /> Gửi qua Gmail
              </h3>
              <button onClick={() => setEmailRow(null)} disabled={sending}
                className="text-gray-300 hover:text-gray-500 disabled:opacity-40"><X className="w-4 h-4" /></button>
            </div>
            <p className="text-xs text-gray-500 mb-3">
              File: <span className="font-mono">{emailRow.file_name || emailRow.token}</span>
              {emailRow.po_number ? ` · PO ${emailRow.po_number}` : ""}
            </p>
            <input
              type="email" value={toEmail} onChange={e => setToEmail(e.target.value)}
              onKeyDown={e => e.key === "Enter" && submitEmail()}
              placeholder="example@gmail.com" autoFocus
              className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm mb-4
                focus:outline-none focus:ring-2 focus:ring-sky-300"
            />
            <div className="flex justify-end gap-2">
              <button onClick={() => setEmailRow(null)} disabled={sending}
                className="px-3 py-2 text-sm text-gray-500 hover:text-gray-700 disabled:opacity-40">Huỷ</button>
              <button onClick={submitEmail} disabled={!toEmail.trim() || sending}
                className="flex items-center gap-2 px-4 py-2 bg-sky-600 text-white rounded-lg text-sm font-medium
                  hover:bg-sky-700 disabled:opacity-40 disabled:cursor-not-allowed">
                {sending ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
                Gửi ngay
              </button>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}

// ── Sub-components ─────────────────────────────────────────────────────────────

function StatCard({ label, value, highlight, className, numClass }: {
  label: string; value: number; highlight?: boolean; className?: string; numClass?: string;
}) {
  return (
    <div className={`rounded-xl border p-5 text-center ${highlight ? className : "bg-white border-gray-200"}`}>
      <p className={`text-3xl font-bold ${numClass || "text-gray-900"}`}>{value}</p>
      <p className="text-xs text-gray-500 mt-1">{label}</p>
    </div>
  );
}

function StatusBadge({ status }: { status: string }) {
  if (status === "success")
    return <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs bg-green-100 text-green-700 whitespace-nowrap"><CheckCircle2 className="w-3 h-3" /> Xong</span>;
  if (status === "partial")
    return <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs bg-amber-100 text-amber-700 whitespace-nowrap"><AlertTriangle className="w-3 h-3" /> 1 phần</span>;
  return <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs bg-red-100 text-red-700 whitespace-nowrap"><XCircle className="w-3 h-3" /> Lỗi</span>;
}
