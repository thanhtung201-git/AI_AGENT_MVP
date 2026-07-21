"use client";
import { useState, useRef } from "react";
import toast from "react-hot-toast";
import {
  FileUp, Loader2, CheckCircle2, XCircle, AlertTriangle,
  ClipboardCheck, BookOpen, ShieldCheck,
} from "lucide-react";
import api from "@/lib/api";

// ── Types ─────────────────────────────────────────────────────────────────────

interface VerifiedLine {
  row:        number;
  item_no?:   string;
  description: string;
  status:     "ok" | "mismatch" | "missing" | "unverified";
  issue?:     string;
  source_ref?: string;
  severity?:  "ok" | "warning" | "critical";
}

interface Stats {
  ok_count:         number;
  mismatch_count:   number;
  missing_count:    number;
  unverified_count: number;
  total:            number;
}

interface RunResult {
  success:        boolean;
  verified_lines?: VerifiedLine[];
  missing_items?:  string[];
  summary?:        string;
  stats?:          Stats;
  error?:          string;
}

// ── Page ─────────────────────────────────────────────────────────────────────

export default function TaskCPage() {
  const [trimlistFile,  setTrimlistFile]  = useState<File | null>(null);
  const [techpackFile,  setTechpackFile]  = useState<File | null>(null);
  const [masterFile,    setMasterFile]    = useState<File | null>(null);
  const [garmentType,   setGarmentType]  = useState("Men Woven");
  const [running,       setRunning]       = useState(false);
  const [result,        setResult]        = useState<RunResult | null>(null);
  const [filterStatus,  setFilterStatus]  = useState<string>("all");

  const trimlistRef = useRef<HTMLInputElement>(null);
  const techpackRef = useRef<HTMLInputElement>(null);
  const masterRef   = useRef<HTMLInputElement>(null);

  const handleRun = async () => {
    if (!trimlistFile) { toast.error("Chọn file Trimlist trước"); return; }
    setRunning(true);
    setResult(null);

    const form = new FormData();
    form.append("trimlist_file", trimlistFile);
    if (techpackFile) form.append("techpack_file", techpackFile);
    if (masterFile)   form.append("master_trim_file", masterFile);
    form.append("garment_type", garmentType);

    try {
      const { data } = await api.post("/api/task-c/run", form, { timeout: 300000 });
      setResult(data);
      if (data.success) {
        const s = data.stats as Stats;
        const issues = s.mismatch_count + s.missing_count;
        toast[issues > 0 ? "error" : "success"](
          issues > 0 ? `Phát hiện ${issues} vấn đề` : "Trimlist hợp lệ — không có bất thường"
        );
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

  const lines = (result?.verified_lines || []).filter(l => {
    if (filterStatus === "all") return true;
    return l.status === filterStatus;
  });

  const stats = result?.stats;

  const garmentTypes = ["Men Woven", "Men Knit", "Ladies Knit", "Ladies Woven", "KIDS Woven"];

  return (
    <div className="p-8 max-w-6xl mx-auto">
      {/* Header */}
      <div className="mb-6">
        <h1 className="text-xl font-bold text-gray-900 mb-1 flex items-center gap-2">
          <ShieldCheck className="w-5 h-5 text-violet-600" />
          Task C — Verify Trimlist
        </h1>
        <p className="text-sm text-gray-500">
          Upload Trimlist đã tạo · AI kiểm tra từng dòng đối chiếu Tech Pack + Trim Master · Báo cáo sai sót / thiếu
        </p>
      </div>

      {/* Upload section */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-5">
        {/* Trimlist */}
        <UploadBox
          label="Trimlist cần verify"
          required
          hint="Excel hoặc PDF trimlist đã tạo"
          icon={<ClipboardCheck className="w-5 h-5" />}
          color="violet"
          file={trimlistFile}
          accept=".xlsx,.xls,.pdf"
          inputRef={trimlistRef}
          onClear={() => setTrimlistFile(null)}
          onFile={setTrimlistFile}
        />
        {/* Tech Pack */}
        <UploadBox
          label="Tech Pack"
          hint="Nguồn gốc trim — dùng để đối chiếu"
          icon={<BookOpen className="w-5 h-5" />}
          color="blue"
          file={techpackFile}
          accept=".pdf,.xlsx,.xls,.docx"
          inputRef={techpackRef}
          onClear={() => setTechpackFile(null)}
          onFile={setTechpackFile}
        />
        {/* Trim Master */}
        <UploadBox
          label="Trim Master"
          hint="Rules chuẩn supplier / spec"
          icon={<FileUp className="w-5 h-5" />}
          color="indigo"
          file={masterFile}
          accept=".xlsx,.xls"
          inputRef={masterRef}
          onClear={() => setMasterFile(null)}
          onFile={setMasterFile}
        />
      </div>

      {/* Garment type */}
      <div className="mb-5">
        <label className="block text-xs font-medium text-gray-500 mb-1">Garment Type</label>
        <select value={garmentType} onChange={e => setGarmentType(e.target.value)}
          className="w-48 px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-violet-400">
          {garmentTypes.map(g => <option key={g} value={g}>{g}</option>)}
        </select>
      </div>

      {/* Run button */}
      <div className="flex items-center gap-4 mb-8">
        <button
          onClick={handleRun}
          disabled={!trimlistFile || running}
          className="flex items-center gap-2 px-6 py-2.5 bg-violet-600 text-white rounded-lg font-medium text-sm
            hover:bg-violet-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
        >
          {running
            ? <><Loader2 className="w-4 h-4 animate-spin" />Đang kiểm tra...</>
            : <><ShieldCheck className="w-4 h-4" />Verify Trimlist</>}
        </button>

        {result?.success && stats && (
          <div className={`flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium ${
            (stats.mismatch_count + stats.missing_count) > 0
              ? "bg-red-100 text-red-700"
              : "bg-green-100 text-green-700"
          }`}>
            {(stats.mismatch_count + stats.missing_count) > 0
              ? <XCircle className="w-4 h-4" />
              : <CheckCircle2 className="w-4 h-4" />}
            {result.summary}
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
      {result?.success && stats && (
        <div>
          {/* Stats */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-5">
            {[
              { label: "OK",          count: stats.ok_count,         color: "green",  status: "ok" },
              { label: "Sai khác",    count: stats.mismatch_count,   color: "red",    status: "mismatch" },
              { label: "Thiếu",       count: stats.missing_count,    color: "amber",  status: "missing" },
              { label: "Chưa xác nhận", count: stats.unverified_count, color: "gray", status: "unverified" },
            ].map(({ label, count, color, status }) => (
              <button
                key={status}
                onClick={() => setFilterStatus(prev => prev === status ? "all" : status)}
                className={`p-4 rounded-xl border-2 text-center transition-all ${
                  filterStatus === status
                    ? `border-${color}-400 bg-${color}-50`
                    : `border-${color}-200 bg-${color}-50/40 hover:border-${color}-300`
                }`}
              >
                <p className={`text-2xl font-bold text-${color}-600`}>{count}</p>
                <p className={`text-xs text-${color}-500 mt-0.5`}>{label}</p>
              </button>
            ))}
          </div>

          {/* Missing items */}
          {(result.missing_items || []).length > 0 && (
            <div className="mb-4 p-4 bg-amber-50 border border-amber-200 rounded-xl">
              <p className="text-sm font-semibold text-amber-800 mb-2 flex items-center gap-2">
                <AlertTriangle className="w-4 h-4" />
                Items trong nguồn nhưng KHÔNG có trong Trimlist
              </p>
              <ul className="space-y-1">
                {(result.missing_items || []).map((item, i) => (
                  <li key={i} className="text-xs text-amber-700 flex items-start gap-2">
                    <span className="text-amber-400 mt-0.5">•</span>
                    {item}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Filter info */}
          {filterStatus !== "all" && (
            <div className="mb-3 flex items-center gap-2">
              <span className="text-xs text-gray-500">Đang lọc: <strong>{filterStatus}</strong></span>
              <button onClick={() => setFilterStatus("all")}
                className="text-xs text-indigo-500 underline">Xem tất cả</button>
            </div>
          )}

          {/* Verified lines table */}
          <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="bg-violet-900 text-white">
                  <tr>
                    <th className="px-3 py-2.5 text-left text-xs font-medium w-10">#</th>
                    <th className="px-4 py-2.5 text-left text-xs font-medium">DESCRIPTION</th>
                    <th className="px-3 py-2.5 text-center text-xs font-medium w-24">STATUS</th>
                    <th className="px-4 py-2.5 text-left text-xs font-medium">ISSUE / NOTE</th>
                    <th className="px-4 py-2.5 text-left text-xs font-medium">SOURCE REF</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {lines.length === 0 && (
                    <tr>
                      <td colSpan={5} className="px-4 py-8 text-center text-sm text-gray-400">
                        Không có dòng nào phù hợp
                      </td>
                    </tr>
                  )}
                  {lines.map((line, i) => (
                    <tr key={i} className={`${i % 2 === 0 ? "bg-white" : "bg-gray-50/40"}`}>
                      <td className="px-3 py-2.5 text-xs text-gray-400">{line.row || i + 1}</td>
                      <td className="px-4 py-2.5 text-xs font-medium text-gray-800">{line.description || "—"}</td>
                      <td className="px-3 py-2.5 text-center">
                        <StatusBadge status={line.status} />
                      </td>
                      <td className="px-4 py-2.5 text-xs text-gray-600">
                        {line.issue || <span className="text-gray-300">—</span>}
                      </td>
                      <td className="px-4 py-2.5 text-xs text-gray-400 italic">{line.source_ref || "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ── UploadBox ─────────────────────────────────────────────────────────────────

function UploadBox({
  label, required, hint, icon, color, file, accept, inputRef, onClear, onFile,
}: {
  label: string; required?: boolean; hint: string; icon: React.ReactNode; color: string;
  file: File | null; accept: string; inputRef: React.RefObject<HTMLInputElement | null>;
  onClear: () => void; onFile: (f: File) => void;
}) {
  return (
    <div
      onClick={() => inputRef.current?.click()}
      className={`relative border-2 border-dashed rounded-xl p-5 cursor-pointer transition-all
        ${file
          ? `border-${color}-400 bg-${color}-50`
          : `border-gray-300 hover:border-${color}-300 hover:bg-${color}-50/20`}`}
    >
      <div className="flex items-start gap-3">
        <span className={`mt-0.5 flex-shrink-0 ${file ? `text-${color}-600` : "text-gray-400"}`}>{icon}</span>
        <div className="flex-1 min-w-0">
          <p className="text-sm font-semibold text-gray-700">
            {label} {required && <span className="text-red-500">*</span>}
          </p>
          {file
            ? <p className={`text-xs text-${color}-700 font-medium truncate mt-0.5`}>{file.name}</p>
            : <p className="text-xs text-gray-400 mt-0.5">{hint}</p>}
        </div>
        {file && (
          <button onClick={e => { e.stopPropagation(); onClear(); }}
            className="text-gray-300 hover:text-red-400 flex-shrink-0">
            <XCircle className="w-4 h-4" />
          </button>
        )}
      </div>
      <input ref={inputRef} type="file" accept={accept} className="hidden"
        onChange={e => { const f = e.target.files?.[0]; if (f) onFile(f); }} />
    </div>
  );
}

// ── StatusBadge ───────────────────────────────────────────────────────────────

function StatusBadge({ status }: { status: string }) {
  const map: Record<string, [React.ReactNode, string]> = {
    ok:         [<CheckCircle2 key="ok"   className="w-3 h-3" />, "bg-green-100 text-green-700"],
    mismatch:   [<XCircle      key="mm"   className="w-3 h-3" />, "bg-red-100 text-red-700"],
    missing:    [<AlertTriangle key="ms"  className="w-3 h-3" />, "bg-amber-100 text-amber-700"],
    unverified: [<span         key="uv">?</span>,                 "bg-gray-100 text-gray-500"],
  };
  const [icon, cls] = map[status] || [null, "bg-gray-100 text-gray-400"];
  return (
    <span className={`inline-flex items-center gap-1 text-[10px] px-2 py-0.5 rounded-full font-semibold ${cls}`}>
      {icon}
      {status.toUpperCase()}
    </span>
  );
}
