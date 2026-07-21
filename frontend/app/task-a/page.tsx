"use client";
import { useState, useRef, useEffect } from "react";
import toast from "react-hot-toast";
import {
  Upload, Loader2, Download, AlertTriangle, CheckCircle2,
  XCircle, Info, FileUp, RotateCcw, GitCompare, FileSpreadsheet, FileJson,
} from "lucide-react";
import api, {
  getTaskAHistory, saveTaskAHistory, downloadTaskAFile,
  sendTaskAEmail, sendTaskATelegram, type TaskAHistoryRow,
} from "@/lib/api";
import TaskHistory from "@/components/TaskHistory";

// Đọc field kiểu {value, source} hoặc scalar từ PO canonical
function fieldVal(v: unknown): string {
  if (v && typeof v === "object" && "value" in (v as Record<string, unknown>)) {
    const inner = (v as Record<string, unknown>).value;
    return inner != null ? String(inner) : "";
  }
  return v != null ? String(v) : "";
}

// ── Types ─────────────────────────────────────────────────────────────────────

interface Alert {
  level:    "ERROR" | "WARNING" | "INFO";
  category: string;
  message:  string;
  source?:  string | null;
}
interface CompareRow {
  field: string; status: "MATCH" | "MISMATCH" | "MISSING" | "EXTRA";
  po_value: string; go_value: string; difference: string; source: string; confidence: string;
}
interface Summary {
  status: "OK" | "PARTIAL" | "MISMATCH";
  errors: number; warnings: number; infos: number;
  po_total: number; go_total: number; qty_diff: number;
  po_lines: number; go_lines: number; compared: number;
}
interface ValIssue { level: "ERROR" | "WARNING" | "INFO"; code: string; message: string; }
interface GenResult {
  success: boolean; token?: string; batch_go_token?: string; po?: any; error?: string;
  validation?: { summary: { errors: number; warnings: number; infos: number }; issues: ValIssue[] };
}
interface CmpResult {
  success: boolean; go_source?: "uploaded" | "generated";
  compare?: { rows: CompareRow[]; alerts: Alert[]; summary: Summary };
  report_token?: string; alerts_token?: string; error?: string;
}

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// ── Page ─────────────────────────────────────────────────────────────────────

export default function TaskAPage() {
  const [poFile, setPoFile]   = useState<File | null>(null);
  const [goFile, setGoFile]   = useState<File | null>(null);
  const [gen, setGen]         = useState<GenResult | null>(null);
  const [cmp, setCmp]         = useState<CmpResult | null>(null);
  const [generating, setGenerating] = useState(false);
  const [comparing, setComparing]   = useState(false);
  const [tab, setTab] = useState<"summary" | "detail" | "alerts">("summary");
  const [history, setHistory]       = useState<TaskAHistoryRow[]>([]);
  const [loadingHist, setLoadingHist] = useState(true);
  const poRef = useRef<HTMLInputElement>(null);
  const goRef = useRef<HTMLInputElement>(null);

  async function loadHistory() {
    setLoadingHist(true);
    try {
      // map compared → item_count để dashboard hiển thị cột "SO SÁNH"
      const rows = await getTaskAHistory();
      setHistory(rows.map(r => ({ ...r, item_count: r.compared })));
    }
    catch { /* history is best-effort */ }
    finally { setLoadingHist(false); }
  }
  useEffect(() => { loadHistory(); }, []);

  async function generate() {
    if (!poFile) { toast.error("Chọn file PO trước"); return; }
    setGenerating(true); setGen(null); setCmp(null);
    const form = new FormData();
    form.append("po_file", poFile);
    try {
      const { data } = await api.post<GenResult>("/api/task-a/generate", form, { timeout: 600000 });
      if (!data.success) toast.error(data.error || "Tạo Batch GO thất bại");
      else {
        toast.success("Đã tạo Batch GO"); setGen(data);
        if (data.token) {
          await saveTaskAHistory({
            token:          data.token,
            status:         "partial",
            file_name:      poFile.name,
            po_number:      fieldVal(data.po?.po_number) || null,
            style_code:     fieldVal(data.po?.style) || null,
            qty:            data.po?.total_qty ?? 0,
            batch_go_token: data.batch_go_token || null,
          }).then(loadHistory).catch(() => {});
        }
      }
    } catch (e: any) {
      toast.error(e?.response?.data?.error || e?.message || "Lỗi kết nối");
    } finally { setGenerating(false); }
  }

  async function compare() {
    if (!gen?.token) return;
    setComparing(true); setCmp(null);
    const form = new FormData();
    form.append("token", gen.token);
    if (goFile) form.append("go_file", goFile);
    try {
      const { data } = await api.post<CmpResult>("/api/task-a/compare", form, { timeout: 600000 });
      if (!data.success) toast.error(data.error || "So sánh thất bại");
      else {
        toast.success("Đối chiếu hoàn tất"); setCmp(data); setTab("summary");
        const s = data.compare?.summary;
        const status = s?.status === "OK" ? "success" : s?.status === "MISMATCH" ? "error" : "partial";
        await saveTaskAHistory({
          token:          gen.token,
          status,
          file_name:      poFile?.name || null,
          po_number:      fieldVal(gen.po?.po_number) || null,
          style_code:     fieldVal(gen.po?.style) || null,
          qty:            gen.po?.total_qty ?? 0,
          compared:       s?.compared ?? 0,
          go_source:      data.go_source || null,
          batch_go_token: gen.batch_go_token || null,
          report_token:   data.report_token || null,
          alerts_token:   data.alerts_token || null,
        }).then(loadHistory).catch(() => {});
      }
    } catch (e: any) {
      toast.error(e?.response?.data?.error || e?.message || "Lỗi kết nối");
    } finally { setComparing(false); }
  }

  function reset() {
    setPoFile(null); setGoFile(null); setGen(null); setCmp(null);
    if (poRef.current) poRef.current.value = "";
    if (goRef.current) goRef.current.value = "";
  }

  function download(token?: string) {
    if (!token) return;
    window.open(`${API_BASE}/api/task-a/download/${token}`, "_blank");
  }

  const summary = cmp?.compare?.summary;

  return (
    <div className="max-w-6xl mx-auto p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center gap-3">
        <div className="w-10 h-10 rounded-lg bg-indigo-600 flex items-center justify-center">
          <GitCompare className="w-5 h-5 text-white" />
        </div>
        <div>
          <h1 className="text-xl font-bold text-gray-900">PO ↔ GO Compare</h1>
          <p className="text-sm text-gray-500">Bước 1: tạo Batch GO từ PO — Bước 2: đối chiếu GO</p>
        </div>
        <button onClick={reset}
          className="ml-auto flex items-center gap-2 border border-gray-300 text-gray-600 rounded-lg
                     px-4 py-2 text-sm hover:bg-gray-50 transition-colors">
          <RotateCcw className="w-4 h-4" /> Làm lại
        </button>
      </div>

      {/* Stepper */}
      <div className="flex items-center gap-2 text-sm">
        <StepPill n={1} label="Tạo Batch GO" active={!gen} done={!!gen} />
        <div className="h-px flex-1 bg-gray-200" />
        <StepPill n={2} label="Đối chiếu GO" active={!!gen && !cmp} done={!!cmp} disabled={!gen} />
      </div>

      {/* ── STEP 1 ── */}
      <section className="bg-white rounded-xl border border-gray-200 p-6 space-y-4">
        <h2 className="text-sm font-semibold text-gray-700">Bước 1 — Upload PO &amp; tạo Batch GO</h2>
        <Dropzone
          inputRef={poRef} file={poFile} onPick={setPoFile}
          title="PO — bắt buộc" hint="Chọn file PO (Excel, PDF, Word…)" accent="indigo"
          disabled={!!gen}
        />
        {!gen ? (
          <button onClick={generate} disabled={generating || !poFile}
            className="w-full flex items-center justify-center gap-2 bg-indigo-600 text-white rounded-lg
                       py-2.5 text-sm font-medium hover:bg-indigo-700 disabled:opacity-50
                       disabled:cursor-not-allowed transition-colors">
            {generating ? <Loader2 className="w-4 h-4 animate-spin" /> : <FileSpreadsheet className="w-4 h-4" />}
            {generating ? "Đang tạo Batch GO…" : "Tạo Batch GO"}
          </button>
        ) : (
          <div className="space-y-3">
            <div className="flex items-center gap-3 bg-green-50 border border-green-200 rounded-lg px-4 py-3">
              <CheckCircle2 className="w-5 h-5 text-green-600" />
              <span className="text-sm text-green-800">
                Đã tạo Batch GO từ PO ({gen.po?.lines?.length ?? 0} dòng, tổng {(gen.po?.total_qty ?? 0).toLocaleString()}).
              </span>
              <button onClick={() => download(gen.batch_go_token)}
                className="ml-auto flex items-center gap-2 border border-green-300 bg-white text-green-700
                           rounded-lg px-3 py-1.5 text-sm hover:bg-green-100 transition-colors">
                <Download className="w-4 h-4" /> Tải Batch GO Output
              </button>
            </div>
            {gen.validation && (gen.validation.summary.errors + gen.validation.summary.warnings) > 0 && (
              <div className="border border-gray-200 rounded-lg p-3">
                <p className="text-xs font-semibold text-gray-600 mb-2">
                  Kiểm tra PO: {gen.validation.summary.errors} lỗi · {gen.validation.summary.warnings} cảnh báo
                </p>
                <div className="space-y-1 max-h-40 overflow-y-auto">
                  {gen.validation.issues.slice(0, 30).map((iss, i) => (
                    <div key={i} className="flex items-start gap-2 text-xs">
                      <span className={iss.level === "ERROR" ? "text-red-500" : "text-yellow-600"}>
                        {iss.level === "ERROR" ? "●" : "▲"}
                      </span>
                      <span className="text-gray-600">{iss.message}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </section>

      {/* ── STEP 2 ── (only after step 1) */}
      {gen && (
        <section className="bg-white rounded-xl border border-gray-200 p-6 space-y-4">
          <h2 className="text-sm font-semibold text-gray-700">Bước 2 — Đối chiếu GO với PO</h2>
          <Dropzone
            inputRef={goRef} file={goFile} onPick={setGoFile}
            title="GO thật — tùy chọn" hint="Có file GO từ ERP thì thêm để đối chiếu thật" accent="emerald"
          />
          <p className="text-xs text-gray-400">
            Không có file GO → so sánh với chính Batch GO vừa tạo (round-trip self-check).
          </p>
          <button onClick={compare} disabled={comparing}
            className="w-full flex items-center justify-center gap-2 bg-emerald-600 text-white rounded-lg
                       py-2.5 text-sm font-medium hover:bg-emerald-700 disabled:opacity-50
                       disabled:cursor-not-allowed transition-colors">
            {comparing ? <Loader2 className="w-4 h-4 animate-spin" /> : <GitCompare className="w-4 h-4" />}
            {comparing ? "Đang đối chiếu…" : "Chạy đối chiếu"}
          </button>
        </section>
      )}

      {/* ── RESULTS ── */}
      {cmp?.success && summary && (
        <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
          <StatusBanner summary={summary} goSource={cmp.go_source} />
          <div className="flex flex-wrap gap-2 px-6 py-3 border-b border-gray-100 bg-gray-50">
            <DownloadBtn icon={<Download className="w-4 h-4" />} label="Compare Report"
              onClick={() => download(cmp.report_token)} />
            <DownloadBtn icon={<FileJson className="w-4 h-4" />} label="Alerts.json"
              onClick={() => download(cmp.alerts_token)} />
          </div>
          <div className="flex border-b border-gray-100">
            {(["summary", "detail", "alerts"] as const).map((t) => (
              <button key={t} onClick={() => setTab(t)}
                className={`px-5 py-3 text-sm font-medium transition-colors ${
                  tab === t ? "text-indigo-700 border-b-2 border-indigo-600" : "text-gray-500 hover:text-gray-700"}`}>
                {t === "summary" ? "Tổng quan" : t === "detail" ? "Chi tiết" : `Cảnh báo (${cmp.compare!.alerts.length})`}
              </button>
            ))}
          </div>
          <div className="p-6">
            {tab === "summary" && <SummaryView summary={summary} />}
            {tab === "detail"  && <DetailView rows={cmp.compare!.rows} />}
            {tab === "alerts"  && <AlertsView alerts={cmp.compare!.alerts} />}
          </div>
        </div>
      )}

      {/* ── HISTORY DASHBOARD ── */}
      <TaskHistory
        rows={history} loading={loadingHist} onRefresh={loadHistory}
        trimLabel="SO SÁNH" accent="indigo"
        canSend={(r) => !!r.batch_go_token}
        onSendEmail={(r, to) => sendTaskAEmail({
          filename: r.batch_go_token!, to_email: to,
          po_number: r.po_number, style_code: r.style_code, qty: r.qty,
        })}
        onSendTelegram={(r) => sendTaskATelegram({
          filename: r.batch_go_token!,
          po_number: r.po_number, style_code: r.style_code, qty: r.qty,
        })}
        renderDownloads={(r) => (
          <>
            {r.batch_go_token && (
              <button onClick={() => downloadTaskAFile(r.batch_go_token!)}
                className="text-xs text-indigo-600 hover:text-indigo-800 flex items-center gap-1">
                <Download className="w-3 h-3" /> GO
              </button>
            )}
            {r.report_token && (
              <button onClick={() => downloadTaskAFile(r.report_token!)}
                className="text-xs text-emerald-600 hover:text-emerald-800 flex items-center gap-1">
                <Download className="w-3 h-3" /> Report
              </button>
            )}
            {r.alerts_token && (
              <button onClick={() => downloadTaskAFile(r.alerts_token!)}
                className="text-xs text-rose-600 hover:text-rose-800 flex items-center gap-1">
                <Download className="w-3 h-3" /> Alerts
              </button>
            )}
          </>
        )}
      />
    </div>
  );
}

// ── Sub-components ─────────────────────────────────────────────────────────────

function StepPill({ n, label, active, done, disabled }:
  { n: number; label: string; active?: boolean; done?: boolean; disabled?: boolean }) {
  const cls = done ? "bg-green-100 text-green-700 border-green-300"
    : active ? "bg-indigo-100 text-indigo-700 border-indigo-300"
    : disabled ? "bg-gray-50 text-gray-300 border-gray-200"
    : "bg-gray-100 text-gray-500 border-gray-200";
  return (
    <div className={`flex items-center gap-2 border rounded-full px-3 py-1.5 ${cls}`}>
      <span className="w-5 h-5 rounded-full bg-white/70 flex items-center justify-center text-xs font-bold">
        {done ? "✓" : n}
      </span>
      {label}
    </div>
  );
}

function Dropzone({ inputRef, file, onPick, title, hint, accent, disabled }: {
  inputRef: React.RefObject<HTMLInputElement | null>; file: File | null;
  onPick: (f: File | null) => void; title: string; hint: string;
  accent: "indigo" | "emerald"; disabled?: boolean;
}) {
  const border = accent === "indigo" ? "hover:border-indigo-400 hover:bg-indigo-50/40"
                                     : "hover:border-emerald-400 hover:bg-emerald-50/40";
  const text = accent === "indigo" ? "text-indigo-700" : "text-emerald-700";
  return (
    <label
      onClick={() => !disabled && inputRef.current?.click()}
      className={`flex flex-col items-center justify-center gap-2 border-2 border-dashed border-gray-300
                  rounded-lg py-8 transition-colors ${disabled ? "opacity-60 cursor-not-allowed" : `cursor-pointer ${border}`}`}
    >
      <FileUp className="w-7 h-7 text-gray-400" />
      <span className="text-xs font-semibold text-gray-400 uppercase tracking-wide">{title}</span>
      {file ? <span className={`text-sm font-medium ${text} text-center px-2`}>{file.name}</span>
            : <span className="text-sm text-gray-500 text-center px-2">{hint}</span>}
      <input ref={inputRef} type="file" className="hidden" accept=".xlsx,.xls,.pdf,.docx,.csv"
        onChange={(e) => onPick(e.target.files?.[0] || null)} />
    </label>
  );
}

function StatusBanner({ summary, goSource }: { summary: Summary; goSource?: string }) {
  const map = {
    OK:       { bg: "bg-green-50",  text: "text-green-700",  icon: <CheckCircle2 className="w-5 h-5" />, label: "KHỚP" },
    PARTIAL:  { bg: "bg-yellow-50", text: "text-yellow-700", icon: <AlertTriangle className="w-5 h-5" />, label: "CẦN KIỂM TRA" },
    MISMATCH: { bg: "bg-red-50",    text: "text-red-700",    icon: <XCircle className="w-5 h-5" />, label: "SAI LỆCH" },
  }[summary.status];
  return (
    <div className={`flex items-center gap-3 px-6 py-4 ${map.bg} ${map.text}`}>
      {map.icon}
      <span className="font-semibold">{map.label}</span>
      <span className="text-sm opacity-80">· {summary.errors} lỗi · {summary.warnings} cảnh báo · {summary.infos} info</span>
      <span className="ml-auto text-xs font-medium px-2 py-1 rounded-full bg-white/60">
        {goSource === "uploaded" ? "GO: file thật (ERP)" : "GO: tự sinh (round-trip)"}
      </span>
    </div>
  );
}

function SummaryView({ summary }: { summary: Summary }) {
  const cells = [
    { label: "PO Total Qty", value: summary.po_total.toLocaleString() },
    { label: "GO Total Qty", value: summary.go_total.toLocaleString() },
    { label: "Chênh lệch", value: (summary.qty_diff >= 0 ? "+" : "") + summary.qty_diff.toLocaleString(), warn: summary.qty_diff !== 0 },
    { label: "PO Lines", value: summary.po_lines },
    { label: "GO Lines", value: summary.go_lines },
    { label: "Đã so sánh", value: summary.compared },
  ];
  return (
    <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
      {cells.map((c) => (
        <div key={c.label} className="border border-gray-200 rounded-lg p-4">
          <p className="text-xs text-gray-500">{c.label}</p>
          <p className={`text-2xl font-bold ${c.warn ? "text-red-600" : "text-gray-900"}`}>{c.value}</p>
        </div>
      ))}
    </div>
  );
}

function DetailView({ rows }: { rows: CompareRow[] }) {
  const statusColor: Record<string, string> = {
    MATCH: "bg-green-100 text-green-700", MISMATCH: "bg-red-100 text-red-700",
    MISSING: "bg-orange-100 text-orange-700", EXTRA: "bg-blue-100 text-blue-700",
  };
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="text-left text-gray-500 border-b border-gray-200">
            <th className="py-2 pr-4 font-medium">Field</th><th className="py-2 pr-4 font-medium">Status</th>
            <th className="py-2 pr-4 font-medium">PO Value</th><th className="py-2 pr-4 font-medium">GO Value</th>
            <th className="py-2 pr-4 font-medium">Diff</th><th className="py-2 pr-4 font-medium">Source</th>
            <th className="py-2 font-medium">Conf.</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i} className="border-b border-gray-100">
              <td className="py-2 pr-4 font-medium text-gray-800">{r.field}</td>
              <td className="py-2 pr-4"><span className={`px-2 py-0.5 rounded text-xs font-medium ${statusColor[r.status] || ""}`}>{r.status}</span></td>
              <td className="py-2 pr-4 text-gray-600">{r.po_value}</td>
              <td className="py-2 pr-4 text-gray-600">{r.go_value}</td>
              <td className={`py-2 pr-4 font-medium ${r.difference ? "text-red-600" : "text-gray-400"}`}>{r.difference || "—"}</td>
              <td className="py-2 pr-4 text-xs text-gray-400 max-w-[220px] truncate" title={r.source}>{r.source}</td>
              <td className="py-2 text-xs text-gray-500">{r.confidence}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function AlertsView({ alerts }: { alerts: Alert[] }) {
  if (!alerts.length) return <p className="text-sm text-gray-500">Không có cảnh báo.</p>;
  const cfg = {
    ERROR:   { icon: <XCircle className="w-4 h-4 text-red-500" />,          bg: "bg-red-50 border-red-200" },
    WARNING: { icon: <AlertTriangle className="w-4 h-4 text-yellow-500" />, bg: "bg-yellow-50 border-yellow-200" },
    INFO:    { icon: <Info className="w-4 h-4 text-blue-500" />,            bg: "bg-blue-50 border-blue-200" },
  };
  return (
    <div className="space-y-2">
      {alerts.map((a, i) => {
        const c = cfg[a.level] || cfg.INFO;
        return (
          <div key={i} className={`flex items-start gap-3 border rounded-lg px-4 py-3 ${c.bg}`}>
            {c.icon}
            <div className="flex-1">
              <p className="text-sm text-gray-800">{a.message}</p>
              {a.source && <p className="text-xs text-gray-400 mt-0.5">Nguồn: {a.source}</p>}
            </div>
          </div>
        );
      })}
    </div>
  );
}

function DownloadBtn({ icon, label, onClick }: { icon: React.ReactNode; label: string; onClick: () => void }) {
  return (
    <button onClick={onClick}
      className="flex items-center gap-2 border border-gray-300 bg-white text-gray-700 rounded-lg
                 px-3 py-1.5 text-sm hover:bg-indigo-50 hover:border-indigo-300 transition-colors">
      {icon} {label}
    </button>
  );
}
