"use client";
import { useState, useRef, useEffect, Fragment } from "react";
import toast from "react-hot-toast";
import {
  FileUp, Loader2, Download, CheckCircle2, XCircle,
  AlertTriangle, Info, Scissors, BookOpen, Mail, ChevronDown, ChevronUp, Users,
} from "lucide-react";
import api, {
  getTaskBHistory, saveTaskBHistory, downloadTaskBExcel, downloadTaskBPdf,
  sendTaskBEmail, sendTaskBTelegram, type TaskBHistoryRow,
} from "@/lib/api";
import TaskHistory from "@/components/TaskHistory";

// ── Types ─────────────────────────────────────────────────────────────────────

interface TrimItem {
  // New pipeline fields
  material_name?:  string;
  material_code?:  string;
  category?:       string;
  spec?:           string;
  supplier?:       string;
  supplier_code?:  string;
  placement?:      string;
  color?:          string;
  consumption?:    string;
  unit?:           string;
  remark?:         string;
  source?:         string;
  source_detail?:  {
    techpack_ref?: string; master_ref?: string; buyer_rule?: string; email_ref?: string;
    master_loc?:   { file?: string; sheet?: string; cell?: string; row?: number } | null;
  };
  alerts?:         string[];
  // Legacy fields (backward compat)
  trim_item?:      string;
  pending?:        string[];
  notes?:          string;
}

interface AlertItem {
  severity:  "ERROR" | "WARNING" | "INFO";
  item_name: string;
  code:      string;
  message:   string;
}

interface PendingSummary {
  missing_code?:      number;
  missing_supplier?:  number;
  missing_spec?:      number;
  missing_placement?: number;
}

interface CompletionField {
  label:         string;
  filled:        number;
  missing:       number;
  missing_items: string[];
}

interface Completion {
  total_items:      number;
  complete_items:   number;
  incomplete_items: number;
  fields:           Record<string, CompletionField>;
  pending_summary:  PendingSummary;
}

interface RunResult {
  success:          boolean;
  items?:           TrimItem[];
  item_count?:      number;
  pending_summary?: PendingSummary;
  completion?:      Completion;
  alert_summary?:   { errors: number; warnings: number; infos: number; total: number };
  alerts?:          AlertItem[];
  email_changes?:   string[];
  excel_token?:     string;
  sources?:         { techpack?: string; master?: string | null };
  steps?:           Record<string, { status: string; [k: string]: unknown }>;
  error?:           string;
}

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// ── Page ─────────────────────────────────────────────────────────────────────

export default function TaskBPage() {
  const [techpackFile,    setTechpackFile]    = useState<File | null>(null);
  const [masterFile,      setMasterFile]      = useState<File | null>(null);
  const [emailNote,       setEmailNote]       = useState("");
  const [poNumber,        setPoNumber]        = useState("");
  const [styleCode,       setStyleCode]       = useState("");
  const [buyer,           setBuyer]           = useState("");
  const [orderQty,        setOrderQty]        = useState("");
  const [running,         setRunning]         = useState(false);
  const [result,          setResult]          = useState<RunResult | null>(null);
  const [showEmail,       setShowEmail]       = useState(false);
  const [expandedRows,    setExpandedRows]    = useState<Set<number>>(new Set());
  const [branch,          setBranch]          = useState("");
  // True only when the USER picked the branch. The pre-filled value is the
  // detector's own guess — the backend must be free to overrule it with the
  // Trim Master code match, and it can only tell the two apart via this flag.
  const [branchConfirmed, setBranchConfirmed] = useState(false);
  const [branchInfo,      setBranchInfo]      = useState<{ confidence?: string; branch_key?: string | null; evidence?: Record<string, string> } | null>(null);
  const [branchOptions,   setBranchOptions]   = useState<string[]>([]);
  const [detectingBranch, setDetectingBranch] = useState(false);

  const [history,     setHistory]     = useState<TaskBHistoryRow[]>([]);
  const [loadingHist, setLoadingHist] = useState(true);

  const techpackRef = useRef<HTMLInputElement>(null);
  const masterRef   = useRef<HTMLInputElement>(null);

  async function loadHistory() {
    setLoadingHist(true);
    try { setHistory(await getTaskBHistory()); }
    catch { /* history is best-effort */ }
    finally { setLoadingHist(false); }
  }
  useEffect(() => { loadHistory(); }, []);

  const onPickTechpack = async (f: File) => {
    setTechpackFile(f);
    setBranch(""); setBranchInfo(null); setBranchConfirmed(false);
    setDetectingBranch(true);
    try {
      const form = new FormData();
      form.append("techpack_file", f);
      const { data } = await api.post("/api/task-b/detect-branch", form, { timeout: 120000 });
      if (data.success) {
        setBranchInfo(data.branch);
        setBranchOptions(data.options || []);
        if (data.branch?.branch_key) setBranch(data.branch.branch_key);
      }
    } catch {
      // detection is best-effort — user can still pick the branch manually
    } finally {
      setDetectingBranch(false);
    }
  };

  const handleRun = async () => {
    if (!techpackFile) { toast.error("Chọn file Tech Pack trước"); return; }
    setRunning(true);
    setResult(null);

    const form = new FormData();
    form.append("techpack_file", techpackFile);
    if (masterFile) form.append("master_trim_file", masterFile);
    form.append("email_note",   emailNote);
    form.append("garment_type", "");
    form.append("buyer_code",   "");
    form.append("po_number",    poNumber);
    form.append("style_code",   styleCode);
    form.append("buyer",        buyer);
    form.append("branch",       branch);
    form.append("branch_confirmed", branchConfirmed ? "true" : "");
    form.append("order_qty",    orderQty || "0");

    try {
      const { data } = await api.post("/api/task-b/run", form, { timeout: 300000 });
      setResult(data);
      if (data.success) {
        toast.success(`Hoàn thành — ${data.item_count} trim items`);
        const pend = data.completion?.pending_summary || data.pending_summary || {};
        const pendingTotal = (pend.missing_code || 0) + (pend.missing_supplier || 0)
          + (pend.missing_spec || 0) + (pend.missing_placement || 0);
        if (data.excel_token) {
          await saveTaskBHistory({
            token:      data.excel_token,
            status:     pendingTotal > 0 ? "partial" : "success",
            file_name:  techpackFile.name,
            po_number:  poNumber || null,
            style_code: styleCode || null,
            qty:        parseInt(orderQty || "0") || 0,
            item_count: data.item_count ?? 0,
          }).then(loadHistory).catch(() => {});
        }
      } else {
        toast.error(data.error || "Có lỗi xảy ra");
      }
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } }; message?: string };
      toast.error(err?.response?.data?.detail || err?.message || "Lỗi kết nối");
    } finally {
      setRunning(false);
    }
  };

  const downloadExcel = () => {
    if (!result?.excel_token) return;
    const base = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
    window.open(`${base}/api/task-b/download/${result.excel_token}`, "_blank");
  };

  const toggleRow = (i: number) => {
    setExpandedRows(prev => {
      const next = new Set(prev);
      next.has(i) ? next.delete(i) : next.add(i);
      return next;
    });
  };

  const ps = result?.completion?.pending_summary || result?.pending_summary || {};
  const totalPending = (ps.missing_code || 0) + (ps.missing_supplier || 0) + (ps.missing_spec || 0) + (ps.missing_placement || 0);

  return (
    <div className="p-8 max-w-6xl mx-auto">
      {/* Header */}
      <div className="mb-6">
        <h1 className="text-xl font-bold text-gray-900 mb-1 flex items-center gap-2">
          <Scissors className="w-5 h-5 text-emerald-600" />
          Task B — Generate Trimlist
        </h1>
        <p className="text-sm text-gray-500">
          Tech Pack + Trim Master + Email → Trimlist hoàn chỉnh · AI trích xuất, áp dụng rules, gắn pending flags
        </p>
      </div>

      {/* Upload section */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
        {/* Tech Pack */}
        <div
          onClick={() => techpackRef.current?.click()}
          className={`relative border-2 border-dashed rounded-xl p-5 cursor-pointer transition-all
            ${techpackFile ? "border-emerald-400 bg-emerald-50" : "border-gray-300 hover:border-emerald-300 hover:bg-emerald-50/30"}`}
        >
          <div className="flex items-start gap-3">
            <BookOpen className={`w-5 h-5 mt-0.5 flex-shrink-0 ${techpackFile ? "text-emerald-600" : "text-gray-400"}`} />
            <div className="flex-1 min-w-0">
              <p className="text-sm font-semibold text-gray-700">
                Tech Pack <span className="text-red-500">*</span>
              </p>
              {techpackFile
                ? <p className="text-xs text-emerald-700 font-medium truncate mt-0.5">{techpackFile.name}</p>
                : <p className="text-xs text-gray-400 mt-0.5">PDF, Excel, Word · Chứa BOM/Trim Specification</p>}
            </div>
            {techpackFile && (
              <button onClick={e => { e.stopPropagation(); setTechpackFile(null); setBranch(""); setBranchInfo(null); setBranchConfirmed(false); }}
                className="text-gray-300 hover:text-red-400 flex-shrink-0">
                <XCircle className="w-4 h-4" />
              </button>
            )}
          </div>
          <input ref={techpackRef} type="file" accept=".pdf,.xlsx,.xls,.docx" className="hidden"
            onChange={e => { const f = e.target.files?.[0]; if (f) onPickTechpack(f); }} />
        </div>

        {/* Trim Master */}
        <div
          onClick={() => masterRef.current?.click()}
          className={`relative border-2 border-dashed rounded-xl p-5 cursor-pointer transition-all
            ${masterFile ? "border-blue-400 bg-blue-50" : "border-gray-300 hover:border-blue-300 hover:bg-blue-50/30"}`}
        >
          <div className="flex items-start gap-3">
            <FileUp className={`w-5 h-5 mt-0.5 flex-shrink-0 ${masterFile ? "text-blue-600" : "text-gray-400"}`} />
            <div className="flex-1 min-w-0">
              <p className="text-sm font-semibold text-gray-700">
                Trim Master <span className="text-xs font-normal text-gray-400">— không bắt buộc</span>
              </p>
              {masterFile
                ? <p className="text-xs text-blue-700 font-medium truncate mt-0.5">{masterFile.name}</p>
                : <p className="text-xs text-gray-400 mt-0.5">Excel Packing Trim · Áp dụng rules chuẩn</p>}
            </div>
            {masterFile && (
              <button onClick={e => { e.stopPropagation(); setMasterFile(null); }}
                className="text-gray-300 hover:text-red-400 flex-shrink-0">
                <XCircle className="w-4 h-4" />
              </button>
            )}
          </div>
          <input ref={masterRef} type="file" accept=".xlsx,.xls" className="hidden"
            onChange={e => { const f = e.target.files?.[0]; if (f) setMasterFile(f); }} />
        </div>
      </div>

      {/* Branch (Men/Ladies × Woven/Knit) — auto-detected, 1-click confirm */}
      {techpackFile && (
        <div className="mb-4 bg-white border border-gray-200 rounded-xl p-3 flex flex-wrap items-center gap-3">
          <span className="text-sm font-medium text-gray-700 flex items-center gap-1.5">
            <Users className="w-4 h-4 text-emerald-600" /> Nhánh
          </span>
          {detectingBranch ? (
            <span className="text-xs text-gray-400 flex items-center gap-1">
              <Loader2 className="w-3.5 h-3.5 animate-spin" /> Đang đọc Tech Pack để suy nhánh…
            </span>
          ) : (
            <>
              <select
                value={branch}
                onChange={e => { setBranch(e.target.value); setBranchConfirmed(true); }}
                className="px-3 py-1.5 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-emerald-400"
              >
                <option value="">— chọn nhánh —</option>
                {branchOptions.map(o => <option key={o} value={o}>{o}</option>)}
              </select>
              {branchInfo && (
                <BranchConfidence confidence={branchInfo.confidence} confirmed={branchConfirmed} detected={branchInfo.branch_key} />
              )}
              <span className="text-[11px] text-gray-400">
                File Master lấy đúng sheet của nhánh này. Sai thì đổi ở trên.
              </span>
            </>
          )}
        </div>
      )}

      {/* Email note toggle */}
      <div className="mb-4">
        <button
          onClick={() => setShowEmail(v => !v)}
          className="flex items-center gap-2 text-sm text-gray-500 hover:text-gray-700 transition-colors"
        >
          <Mail className="w-4 h-4" />
          Email / Note bổ sung
          {showEmail ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
        </button>
        {showEmail && (
          <textarea
            value={emailNote}
            onChange={e => setEmailNote(e.target.value)}
            placeholder="Paste nội dung email hoặc ghi chú yêu cầu bổ sung từ buyer..."
            rows={5}
            className="mt-2 w-full px-3 py-2.5 border border-gray-300 rounded-lg text-sm
              focus:outline-none focus:ring-2 focus:ring-emerald-400 resize-y"
          />
        )}
      </div>

      {/* Meta fields */}
      <div className="grid grid-cols-2 md:grid-cols-3 gap-3 mb-5">
        {[
          { label: "PO Number",  value: poNumber,  set: setPoNumber,  placeholder: "VD: PO88291"   },
          { label: "Style Code", value: styleCode, set: setStyleCode, placeholder: "VD: HZSH6F201" },
          { label: "Order Qty",  value: orderQty,  set: setOrderQty,  placeholder: "VD: 2104"      },
        ].map(({ label, value, set, placeholder }) => (
          <div key={label}>
            <label className="block text-xs font-medium text-gray-500 mb-1">{label}</label>
            <input type="text" value={value} onChange={e => set(e.target.value)}
              placeholder={placeholder}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-emerald-400" />
          </div>
        ))}
      </div>

      {/* Run button */}
      <div className="flex items-center gap-4 mb-8">
        <button
          onClick={handleRun}
          disabled={!techpackFile || running}
          className="flex items-center gap-2 px-6 py-2.5 bg-emerald-600 text-white rounded-lg font-medium text-sm
            hover:bg-emerald-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
        >
          {running
            ? <><Loader2 className="w-4 h-4 animate-spin" />Đang xử lý...</>
            : <><Scissors className="w-4 h-4" />Generate Trimlist</>}
        </button>

        {result?.success && (
          <button onClick={downloadExcel}
            className="flex items-center gap-2 px-4 py-2.5 bg-green-600 text-white rounded-lg font-medium text-sm
              hover:bg-green-700 transition-colors">
            <Download className="w-4 h-4" />Download Excel
          </button>
        )}

        {result?.success && (
          <div className={`flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium ${
            totalPending > 0 ? "bg-amber-100 text-amber-700" : "bg-green-100 text-green-700"
          }`}>
            {totalPending > 0
              ? <AlertTriangle className="w-4 h-4" />
              : <CheckCircle2 className="w-4 h-4" />}
            {totalPending > 0 ? `${totalPending} mục cần bổ sung` : "Trimlist hoàn chỉnh"}
          </div>
        )}
      </div>

      {/* Error */}
      {result && !result.success && (
        <div className="mb-6 p-4 bg-red-50 border border-red-200 rounded-xl flex gap-3">
          <XCircle className="w-5 h-5 text-red-500 flex-shrink-0 mt-0.5" />
          <p className="text-sm text-red-700">{result.error}</p>
        </div>
      )}

      {/* Results */}
      {result?.success && result.items && (
        <div>
          {/* Completion report (requirement 7) */}
          {result.completion && (
            <CompletionReport completion={result.completion} />
          )}

          {/* Alert summary (new pipeline) */}
          {result.alert_summary && result.alert_summary.total > 0 && (
            <div className="grid grid-cols-3 gap-3 mb-4">
              {[
                { label: "Lỗi",      count: result.alert_summary.errors,   color: "red"   },
                { label: "Cảnh báo", count: result.alert_summary.warnings, color: "amber" },
                { label: "Thông tin",count: result.alert_summary.infos,    color: "blue"  },
              ].map(({ label, count, color }) => count > 0 ? (
                <div key={label} className={`bg-${color}-50 border border-${color}-200 rounded-xl p-3 text-center`}>
                  <p className={`text-2xl font-bold text-${color}-600`}>{count}</p>
                  <p className={`text-xs text-${color}-500 mt-0.5`}>{label}</p>
                </div>
              ) : null)}
            </div>
          )}

          {/* Email changes */}
          {(result.email_changes || []).length > 0 && (
            <div className="mb-4 p-3 bg-amber-50 border border-amber-200 rounded-lg">
              <p className="text-xs font-semibold text-amber-700 mb-1 flex items-center gap-1">
                <Mail className="w-3.5 h-3.5" />Email changes applied ({result.email_changes!.length})
              </p>
              {result.email_changes!.map((c, i) => (
                <p key={i} className="text-xs text-amber-600 ml-4">• {c}</p>
              ))}
            </div>
          )}

          {/* Trimlist table */}
          <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
            <div className="px-5 py-3 border-b border-gray-100 bg-gray-50 flex items-center justify-between">
              <p className="text-sm font-semibold text-gray-700">
                Trimlist — {result.item_count} items
              </p>
              <p className="text-xs text-gray-400">Click dòng để xem chi tiết · Mã đỏ = thiếu thông tin</p>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="bg-emerald-900 text-white">
                  <tr>
                    <th className="px-3 py-2.5 text-left text-xs font-medium w-8">#</th>
                    <th className="px-4 py-2.5 text-left text-xs font-medium">MATERIAL NAME</th>
                    <th className="px-3 py-2.5 text-center text-xs font-medium w-24">CODE</th>
                    <th className="px-4 py-2.5 text-left text-xs font-medium">SUPPLIER</th>
                    <th className="px-3 py-2.5 text-center text-xs font-medium w-16">COLOR</th>
                    <th className="px-3 py-2.5 text-center text-xs font-medium">SOURCE</th>
                    <th className="px-3 py-2.5 text-center text-xs font-medium w-16">ALERT</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {result.items.map((item, i) => {
                    const name     = item.material_name || item.trim_item || "—";
                    const hasAlert = (item.alerts || []).some(a => a.startsWith("ERROR") || a.startsWith("WARNING"));
                    const hasError = (item.alerts || []).some(a => a.startsWith("ERROR"));
                    const expanded = expandedRows.has(i);
                    return (
                      <Fragment key={i}>
                        <tr
                          onClick={() => toggleRow(i)}
                          className={`cursor-pointer hover:bg-gray-50 transition-colors ${
                            i % 2 === 0 ? "bg-white" : "bg-emerald-50/20"
                          } ${hasError ? "border-l-2 border-l-red-400" : hasAlert ? "border-l-2 border-l-amber-400" : ""}`}
                        >
                          <td className="px-3 py-2 text-xs text-gray-400">{i + 1}</td>
                          <td className="px-4 py-2">
                            <p className="text-xs font-semibold text-gray-800">{name}</p>
                            <p className="text-[10px] text-gray-400 mt-0.5">{item.category || ""}</p>
                          </td>
                          <td className="px-3 py-2 text-center">
                            {item.material_code
                              ? <span className="text-xs font-mono font-bold text-indigo-700 bg-indigo-50 px-1.5 py-0.5 rounded">{item.material_code}</span>
                              : <span className="text-[10px] text-red-400 italic">TBD</span>}
                          </td>
                          <td className="px-4 py-2 text-xs text-gray-600">
                            {item.supplier || <span className="text-red-400 italic text-[10px]">TBD</span>}
                          </td>
                          <td className="px-3 py-2 text-center text-xs text-gray-600">{item.color || "—"}</td>
                          <td className="px-3 py-2 text-center">
                            <SourceBadge source={item.source || ""} detail={item.source_detail} />
                          </td>
                          <td className="px-3 py-2 text-center">
                            {hasError
                              ? <XCircle className="w-3.5 h-3.5 text-red-500 mx-auto" />
                              : hasAlert
                              ? <AlertTriangle className="w-3.5 h-3.5 text-amber-500 mx-auto" />
                              : <CheckCircle2 className="w-3.5 h-3.5 text-green-500 mx-auto" />}
                          </td>
                        </tr>

                        {/* Expanded detail */}
                        {expanded && (
                          <tr key={`${i}-detail`} className="bg-gray-50">
                            <td />
                            <td colSpan={6} className="px-4 py-3">
                              <div className="grid grid-cols-2 md:grid-cols-3 gap-x-6 gap-y-1.5 text-xs">
                                {[
                                  ["Spec",          item.spec],
                                  ["Placement",     item.placement],
                                  ["Consumption",   item.consumption],
                                  ["Supplier Code", item.supplier_code],
                                  ["Remark",        item.remark],
                                ].map(([label, val]) => val ? (
                                  <div key={label as string}>
                                    <span className="text-gray-400">{label}: </span>
                                    <span className="text-gray-700 font-medium">{val as string}</span>
                                  </div>
                                ) : null)}
                              </div>
                              {/* Traceability */}
                              {item.source_detail && (
                                <div className="mt-2 pt-2 border-t border-gray-200 text-[10px] text-gray-500 space-y-0.5">
                                  {item.source_detail.techpack_ref && <p>📄 TechPack: {item.source_detail.techpack_ref}</p>}
                                  {item.source_detail.master_loc?.sheet ? (
                                    <p className="flex items-center gap-1.5">
                                      📋 TrimMaster:
                                      <span className="font-mono font-medium text-gray-700">
                                        {item.source_detail.master_loc.sheet}!{item.source_detail.master_loc.cell}
                                      </span>
                                      {result.sources?.master && (
                                        <a href={`${API_BASE}/api/task-b/source/${result.sources.master}`}
                                           target="_blank" rel="noopener noreferrer"
                                           className="text-indigo-600 hover:text-indigo-800 underline">mở file</a>
                                      )}
                                    </p>
                                  ) : item.source_detail.master_ref ? (
                                    <p>📋 TrimMaster: {item.source_detail.master_ref}</p>
                                  ) : null}
                                  {item.source_detail.buyer_rule   && <p>📌 BuyerRule: {item.source_detail.buyer_rule}</p>}
                                  {item.source_detail.email_ref    && <p>✉️ Email: {item.source_detail.email_ref}</p>}
                                </div>
                              )}
                              {/* Alerts */}
                              {(item.alerts || []).length > 0 && (
                                <div className="mt-2 space-y-0.5">
                                  {(item.alerts || []).map((a, ai) => (
                                    <p key={ai} className={`text-[10px] ${a.startsWith("ERROR") ? "text-red-600" : "text-amber-600"}`}>⚠ {a}</p>
                                  ))}
                                </div>
                              )}
                            </td>
                          </tr>
                        )}
                      </Fragment>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {/* ── HISTORY DASHBOARD ── */}
      <TaskHistory
        rows={history} loading={loadingHist} onRefresh={loadHistory}
        trimLabel="TRIM" accent="emerald"
        onSendEmail={(r, to) => sendTaskBEmail({
          token: r.token, to_email: to,
          po_number: r.po_number, style_code: r.style_code, qty: r.qty, item_count: r.item_count,
        })}
        onSendTelegram={(r) => sendTaskBTelegram({
          token: r.token,
          po_number: r.po_number, style_code: r.style_code, qty: r.qty, item_count: r.item_count,
        })}
        renderDownloads={(r) => (
          r.token ? (
            <>
              <button onClick={() => downloadTaskBExcel(r.token)}
                className="text-xs text-emerald-600 hover:text-emerald-800 flex items-center gap-1">
                <Download className="w-3 h-3" /> TL
              </button>
              <button onClick={() => downloadTaskBPdf(r.token)}
                className="text-xs text-rose-600 hover:text-rose-800 flex items-center gap-1">
                <Download className="w-3 h-3" /> PDF
              </button>
            </>
          ) : null
        )}
      />
    </div>
  );
}

// ── BranchConfidence ──────────────────────────────────────────────────────────

function BranchConfidence({ confidence, confirmed, detected }: { confidence?: string; confirmed: boolean; detected?: string | null }) {
  if (confirmed)
    return <span className="text-[11px] text-gray-500 flex items-center gap-1"><Info className="w-3.5 h-3.5" /> đã chọn tay</span>;
  // Tech Pack never states the branch. Not a problem: the backend matches the
  // Tech Pack's material codes against each Trim Master sheet and picks the winner.
  if (!detected)
    return <span className="text-[11px] text-blue-700 bg-blue-50 border border-blue-200 rounded-full px-2 py-0.5 flex items-center gap-1"><Info className="w-3.5 h-3.5" /> Tech Pack không ghi nhánh — sẽ tự đối chiếu mã với file Master</span>;
  if (confidence === "high")
    return <span className="text-[11px] text-green-700 bg-green-50 border border-green-200 rounded-full px-2 py-0.5 flex items-center gap-1"><CheckCircle2 className="w-3.5 h-3.5" /> Tự nhận · chắc chắn</span>;
  if (confidence === "medium")
    return <span className="text-[11px] text-amber-700 bg-amber-50 border border-amber-200 rounded-full px-2 py-0.5 flex items-center gap-1"><AlertTriangle className="w-3.5 h-3.5" /> Tự nhận · nên kiểm tra</span>;
  return <span className="text-[11px] text-red-600 bg-red-50 border border-red-200 rounded-full px-2 py-0.5 flex items-center gap-1"><AlertTriangle className="w-3.5 h-3.5" /> Không chắc — hãy chọn nhánh</span>;
}

// ── CompletionReport (requirement 7: đã lấy / còn thiếu) ──────────────────────

function CompletionReport({ completion }: { completion: Completion }) {
  const { total_items, complete_items, incomplete_items, fields } = completion;
  const pct = total_items > 0 ? Math.round((complete_items / total_items) * 100) : 0;
  const fieldList = Object.entries(fields);
  return (
    <div className="mb-4 bg-white rounded-xl border border-gray-200 overflow-hidden">
      <div className="px-5 py-3 border-b border-gray-100 bg-gray-50 flex items-center justify-between">
        <p className="text-sm font-semibold text-gray-700 flex items-center gap-2">
          <CheckCircle2 className="w-4 h-4 text-emerald-600" />
          Báo cáo hoàn thành
        </p>
        <p className="text-xs text-gray-500">
          <span className="font-semibold text-emerald-700">{complete_items}</span> hoàn chỉnh
          {incomplete_items > 0 && <> · <span className="font-semibold text-amber-600">{incomplete_items}</span> còn thiếu</>}
          {" "}/ {total_items} items
        </p>
      </div>
      <div className="px-5 pt-3">
        <div className="h-2 bg-gray-100 rounded-full overflow-hidden">
          <div className="h-full bg-emerald-500 rounded-full transition-all" style={{ width: `${pct}%` }} />
        </div>
        <p className="text-[11px] text-gray-400 mt-1">{pct}% dòng đã đủ các trường chính</p>
      </div>
      <div className="p-5 grid grid-cols-2 md:grid-cols-5 gap-3">
        {fieldList.map(([key, f]) => (
          <div key={key} className={`rounded-lg border p-3 ${f.missing > 0 ? "border-amber-200 bg-amber-50/40" : "border-gray-200"}`}>
            <p className="text-xs font-medium text-gray-600">{f.label}</p>
            <p className="text-lg font-bold text-gray-900">
              {f.filled}<span className="text-xs font-normal text-gray-400">/{total_items}</span>
            </p>
            {f.missing > 0
              ? <p className="text-[10px] text-amber-600 mt-0.5" title={f.missing_items.join(", ")}>
                  thiếu {f.missing} — cần nhập tay
                </p>
              : <p className="text-[10px] text-emerald-600 mt-0.5">đủ</p>}
          </div>
        ))}
      </div>
    </div>
  );
}

// ── SourceBadge ───────────────────────────────────────────────────────────────

function SourceBadge({ source, detail }: {
  source: string;
  detail?: { techpack_ref?: string; master_ref?: string; buyer_rule?: string; email_ref?: string };
}) {
  // Determine primary source from detail if available
  let primary = source;
  if (detail) {
    if (detail.email_ref)    primary = "EMAIL";
    else if (detail.buyer_rule)   primary = "BUYER_RULE";
    else if (detail.master_ref)   primary = "TRIM_MASTER";
    else if (detail.techpack_ref) primary = "TECH_PACK";
  }

  const map: Record<string, [string, string]> = {
    "EMAIL":        ["Email",  "bg-amber-100 text-amber-700"],
    "BUYER_RULE":   ["Rule",   "bg-green-100 text-green-700"],
    "TRIM_MASTER":  ["MT",     "bg-purple-100 text-purple-700"],
    "TECH_PACK":    ["TP",     "bg-blue-100 text-blue-700"],
    // legacy
    "techpack":          ["TP",      "bg-blue-100 text-blue-700"],
    "master_trim":       ["MT",      "bg-purple-100 text-purple-700"],
    "email":             ["Email",   "bg-amber-100 text-amber-700"],
    "techpack+master":   ["TP+MT",   "bg-indigo-100 text-indigo-700"],
    "techpack+email":    ["TP+Eml",  "bg-teal-100 text-teal-700"],
    "merged":            ["Merged",  "bg-gray-100 text-gray-600"],
  };
  const [label, cls] = map[primary] || ["—", "bg-gray-100 text-gray-400"];
  return (
    <span className={`inline-block text-[10px] px-1.5 py-0.5 rounded font-medium ${cls}`}>
      {label}
    </span>
  );
}
