"use client";
import { useState, useRef, useEffect } from "react";
import toast from "react-hot-toast";
import {
  Upload, Loader2, CheckCircle2, XCircle, AlertTriangle,
  Clock, Scissors, Download, X, Plus, FileUp, RefreshCw, RotateCcw,
} from "lucide-react";
import api, { downloadAgentPO, downloadAgentTrimlist, downloadAgentTrimlistPDF } from "@/lib/api";

// ── Types ─────────────────────────────────────────────────────────────────────

interface UpdateFile {
  id:    string;
  file:  File;
  label: string;
}


interface FileEntry {
  id:           string;
  poFile:       File;
  techpackFile: File | null;
  updateFiles:  UpdateFile[];
  status:       "waiting" | "processing" | "success" | "partial" | "error";
  error?:       string;
  warning?:     string;
  timestamp?:   string;
  po?:          { po_number?: string; style_code?: string; total_qty?: number };
  trimlist?:    { item_count: number } | null;
}

interface HistoryEntry {
  processed_at:      string;
  filename:          string;
  status:            "success" | "partial" | "error";
  timestamp?:        string;
  po_number?:        string;
  style_code?:       string;
  total_qty?:        number;
  trim_count?:       number;
  warning?:          string;
  updateFiles:       UpdateFile[];
  // Trạng thái cập nhật từ file HZSH / buyer update
  is_rescanning?:    boolean;
  updated?:          boolean;
  update_label?:     string;
  prev_style_code?:  string;
  prev_total_qty?:   number;
  needs_manual_input?: boolean;
}

let _idCounter = 0;
const uid = () => String(++_idCounter);

function detectUpdateLabel(filename: string): string {
  const n = filename.toLowerCase();
  if (n.startsWith("hzsh"))                                    return "HZSH — Size/Qty Update";
  if (n.includes("go information") || n.includes("go info"))  return "GO Information";
  if (n.includes("trim master") || n.includes("packing trim")) return "Master Trim";
  if (n.includes("batch go"))                                  return "Batch GO Template";
  return "File cập nhật";
}

// ── Page ─────────────────────────────────────────────────────────────────────

export default function UploadFilePage() {
  const [queue,     setQueue]     = useState<FileEntry[]>([]);
  const [isRunning, setIsRunning] = useState(false);
  const [history,   setHistory]   = useState<HistoryEntry[]>([]);
  const [pendingPO, setPendingPO] = useState<File | null>(null);

  const poRef       = useRef<HTMLInputElement>(null);
  const techpackRef = useRef<HTMLInputElement>(null);

  // Load lịch sử từ DB khi vào trang
  useEffect(() => {
    api.get("/api/upload-history")
      .then(r => {
        const rows = (r.data?.data ?? []).map((row: Record<string, unknown>) => ({
          processed_at: row.created_at
            ? new Date(row.created_at as string).toLocaleString("vi-VN")
            : "—",
          filename:    row.filename   as string,
          status:      (row.status   as "success" | "partial" | "error") || "error",
          timestamp:   row.timestamp  as string | undefined,
          po_number:   row.po_number  as string | undefined,
          style_code:  row.style_code as string | undefined,
          total_qty:   row.total_qty  as number | undefined,
          trim_count:  row.trim_count as number | undefined,
          warning:     row.warning    as string | undefined,
          updateFiles: [],
        }));
        setHistory(rows);
      })
      .catch(() => {});
  }, []);

  const addPOFile  = (file: File) => setPendingPO(file);
  const confirmAdd = (techpack: File | null = null) => {
    if (!pendingPO) return;
    setQueue(prev => [...prev, {
      id: uid(), poFile: pendingPO, techpackFile: techpack,
      updateFiles: [], status: "waiting",
    }]);
    setPendingPO(null);
  };

  const removeEntry = (id: string) =>
    setQueue(prev => prev.filter(e => e.id !== id));

  // ── Queue: update files ───────────────────────────────────────────────────
  const addUpdateToEntry = (entryId: string, files: FileList) => {
    const newFiles: UpdateFile[] = Array.from(files).map(f => ({
      id: uid(), file: f, label: detectUpdateLabel(f.name),
    }));
    setQueue(prev => prev.map(e =>
      e.id === entryId ? { ...e, updateFiles: [...e.updateFiles, ...newFiles] } : e
    ));
  };

  const removeUpdateFromEntry = (entryId: string, updateId: string) =>
    setQueue(prev => prev.map(e =>
      e.id === entryId ? { ...e, updateFiles: e.updateFiles.filter(u => u.id !== updateId) } : e
    ));

  // ── History: update files ─────────────────────────────────────────────────
  const addUpdateToHistory = (idx: number, files: FileList) => {
    const newFiles: UpdateFile[] = Array.from(files).map(f => ({
      id: uid(), file: f, label: detectUpdateLabel(f.name),
    }));
    setHistory(prev => prev.map((h, i) =>
      i === idx ? { ...h, updateFiles: [...h.updateFiles, ...newFiles] } : h
    ));
  };

  const removeUpdateFromHistory = (idx: number, updateId: string) =>
    setHistory(prev => prev.map((h, i) =>
      i === idx ? { ...h, updateFiles: h.updateFiles.filter(u => u.id !== updateId) } : h
    ));

  // ── History: lưu qty nhập tay ────────────────────────────────────────────
  const saveManualQty = (histIdx: number, qty: number) => {
    setHistory(prev => prev.map((h, i) =>
      i === histIdx ? {
        ...h,
        needs_manual_input: false,
        updated:            true,
        update_label:       "Nhập tay",
        prev_total_qty:     h.total_qty,
        total_qty:          qty,
        updateFiles:        [],
      } : h
    ));
    toast.success(`Đã cập nhật: ${qty.toLocaleString()} pcs`);
  };

  // ── History: rescan ───────────────────────────────────────────────────────
  const rescanHistory = async (idx: number) => {
    const entry = history[idx];
    if (!entry.updateFiles.length) return;

    setHistory(prev => prev.map((h, i) =>
      i === idx ? { ...h, is_rescanning: true } : h
    ));

    try {
      const form = new FormData();
      form.append("file", entry.updateFiles[0].file);
      const { data } = await api.post("/api/agent/rescan-update", form, { timeout: 60000 });

      if (data.needs_manual_input) {
        setHistory(prev => prev.map((h, i) =>
          i === idx ? { ...h, is_rescanning: false, needs_manual_input: true } : h
        ));
        return;
      }

      // Cập nhật trực tiếp cột trong dòng gốc
      setHistory(prev => prev.map((h, i) =>
        i === idx ? {
          ...h,
          is_rescanning:   false,
          needs_manual_input: false,
          updated:         true,
          update_label:    data.label || entry.updateFiles[0].label,
          prev_style_code: h.style_code,
          prev_total_qty:  h.total_qty,
          style_code:      data.style_code ?? h.style_code,
          total_qty:       data.total_qty  ?? h.total_qty,
          updateFiles:     [],
        } : h
      ));

      toast.success("Đã cập nhật thông tin từ file buyer");
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } }; message?: string };
      const msg = err?.response?.data?.detail || err?.message || "Lỗi không xác định";
      setHistory(prev => prev.map((h, i) =>
        i === idx ? { ...h, is_rescanning: false } : h
      ));
      toast.error(`Quét lại thất bại: ${msg}`);
    }
  };

  // ── Main queue run ────────────────────────────────────────────────────────
  const canRun = queue.some(e => e.status === "waiting") && !isRunning;

  const runAll = async () => {
    const waiting = queue.filter(e => e.status === "waiting");
    if (!waiting.length) return;
    setIsRunning(true);

    for (const entry of waiting) {
      setQueue(prev => prev.map(e => e.id === entry.id ? { ...e, status: "processing" } : e));
      try {
        const form = new FormData();
        form.append("file", entry.poFile);
        if (entry.techpackFile) form.append("techpack", entry.techpackFile);

        const { data } = await api.post("/api/agent/run", form, { timeout: 300000 });

        const updated: Partial<FileEntry> = {
          status:    data.status === "success" ? "success" : "partial",
          timestamp: data.timestamp,
          warning:   data.warning,
          po:        data.po,
          trimlist:  data.trimlist,
        };

        setQueue(prev => prev.map(e => e.id === entry.id ? { ...e, ...updated } : e));

        const histEntry: HistoryEntry = {
          processed_at: new Date().toLocaleString("vi-VN"),
          filename:     entry.poFile.name,
          status:       updated.status as "success" | "partial",
          timestamp:    data.timestamp,
          po_number:    data.po?.po_number,
          style_code:   data.po?.style_code,
          total_qty:    data.po?.total_qty,
          trim_count:   data.trimlist?.item_count,
          warning:      data.warning,
          updateFiles:  entry.updateFiles,
        };
        setHistory(prev => [histEntry, ...prev]);

        api.post("/api/upload-history", {
          filename:     histEntry.filename,
          status:       histEntry.status,
          po_number:    histEntry.po_number  ?? null,
          style_code:   histEntry.style_code ?? null,
          total_qty:    histEntry.total_qty  ?? 0,
          trim_count:   histEntry.trim_count ?? 0,
          timestamp:    histEntry.timestamp  ?? "",
          warning:      histEntry.warning    ?? "",
          has_techpack: !!entry.techpackFile,
        }).catch(() => {});

      } catch (e: unknown) {
        const err = e as { response?: { data?: { detail?: string } }; message?: string };
        const msg = err?.response?.data?.detail || err?.message || "Lỗi không xác định";
        setQueue(prev => prev.map(e => e.id === entry.id ? { ...e, status: "error", error: msg } : e));
        const errEntry: HistoryEntry = {
          processed_at: new Date().toLocaleString("vi-VN"),
          filename: entry.poFile.name, status: "error", updateFiles: [],
        };
        setHistory(prev => [errEntry, ...prev]);
        api.post("/api/upload-history", { filename: errEntry.filename, status: "error", error: msg }).catch(() => {});
      }
    }

    setIsRunning(false);
    toast.success("Đã xử lý xong tất cả file");
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    const f = e.dataTransfer.files[0];
    if (f) addPOFile(f);
  };

  return (
    <div className="p-8 max-w-5xl mx-auto">

      {/* Header */}
      <div className="flex items-start justify-between mb-6">
        <div>
          <h1 className="text-xl font-bold text-gray-900 mb-1">Upload & Xử lý File</h1>
          <p className="text-sm text-gray-500">
            Thêm nhiều file PO · AI tự động đọc và tạo Trim List từng file
          </p>
        </div>
        <button
          onClick={runAll} disabled={!canRun}
          className="flex items-center gap-2 px-4 py-2 bg-indigo-600 text-white rounded-lg text-sm font-medium
            disabled:opacity-40 disabled:cursor-not-allowed hover:bg-indigo-700 transition-colors"
        >
          {isRunning
            ? <><Loader2 className="w-4 h-4 animate-spin" />Đang xử lý...</>
            : <><Scissors className="w-4 h-4" />Xử lý tất cả</>}
        </button>
      </div>

      {/* Upload card */}
      <div className="bg-white rounded-xl border border-gray-200 p-5 mb-5">
        {pendingPO ? (
          <div className="space-y-3">
            <div className="flex items-center gap-3 p-3 bg-indigo-50 border border-indigo-200 rounded-xl">
              <FileUp className="w-5 h-5 text-indigo-500 flex-shrink-0" />
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium text-gray-900 truncate">{pendingPO.name}</p>
                <p className="text-xs text-indigo-600">Đã chọn — muốn thêm Techpack không?</p>
              </div>
            </div>
            <div className="flex gap-2">
              <button onClick={() => techpackRef.current?.click()}
                className="flex items-center gap-2 px-4 py-2 border border-gray-300 rounded-lg text-sm text-gray-700 hover:bg-gray-50 transition-colors">
                <Upload className="w-4 h-4" />Thêm Techpack
              </button>
              <button onClick={() => confirmAdd(null)}
                className="flex items-center gap-2 px-4 py-2 bg-indigo-600 text-white rounded-lg text-sm font-medium hover:bg-indigo-700 transition-colors">
                <Plus className="w-4 h-4" />Thêm vào hàng chờ
              </button>
              <button onClick={() => setPendingPO(null)}
                className="px-3 py-2 text-sm text-gray-400 hover:text-red-500 rounded-lg hover:bg-gray-50">
                Huỷ
              </button>
            </div>
            <input ref={techpackRef} type="file" accept=".pdf,.xlsx,.xls,.docx" className="hidden"
              onChange={e => { const f = e.target.files?.[0]; if (f) confirmAdd(f); }} />
          </div>
        ) : (
          <div
            onDragOver={e => e.preventDefault()} onDrop={handleDrop}
            onClick={() => poRef.current?.click()}
            className="border-2 border-dashed border-gray-300 rounded-xl p-8 text-center
              cursor-pointer hover:border-indigo-400 hover:bg-indigo-50/30 transition-colors"
          >
            <Upload className="w-7 h-7 text-gray-300 mx-auto mb-2" />
            <p className="text-sm font-medium text-gray-500">
              Kéo &amp; thả hoặc <span className="text-indigo-600">click để chọn file PO</span>
            </p>
            <p className="text-xs text-gray-400 mt-1">Excel (.xlsx) hoặc PDF · Thêm từng file một</p>
            <input ref={poRef} type="file" accept=".xlsx,.xls,.pdf" className="hidden"
              onChange={e => { const f = e.target.files?.[0]; if (f) addPOFile(f); }} />
          </div>
        )}

        {queue.length > 0 && (
          <div className="mt-4 space-y-2">
            <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">
              Hàng chờ ({queue.length} file)
            </p>
            {queue.map(entry => (
              <QueueCard
                key={entry.id}
                entry={entry}
                onRemove={() => removeEntry(entry.id)}
                onAddUpdate={files => addUpdateToEntry(entry.id, files)}
                onRemoveUpdate={uid => removeUpdateFromEntry(entry.id, uid)}
              />
            ))}
          </div>
        )}
      </div>

      {/* Empty state */}
      {queue.length === 0 && history.length === 0 && (
        <div className="bg-white rounded-xl border border-dashed border-gray-300 p-12 text-center">
          <Upload className="w-10 h-10 text-gray-300 mx-auto mb-3" />
          <p className="text-gray-500 font-medium">Chưa có file nào</p>
          <p className="text-sm text-gray-400 mt-1">Kéo thả hoặc click vào ô trên để thêm file PO</p>
        </div>
      )}

      {/* History table */}
      {history.length > 0 && (
        <div>
          <h2 className="text-sm font-semibold text-gray-700 mb-3 flex items-center gap-2">
            <Clock className="w-4 h-4 text-gray-400" />
            Lịch sử đã xử lý ({history.length} file)
          </h2>
          <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-gray-50">
                <tr>
                  {["File", "PO Number", "Style", "Qty", "Trim", "Xử lý lúc", "TT", ""].map(h => (
                    <th key={h} className="text-left px-4 py-2.5 text-xs font-medium text-gray-500 uppercase tracking-wide whitespace-nowrap">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {history.map((entry, i) => (
                  <HistoryRow
                    key={i}
                    entry={entry}
                    onAddUpdate={files => addUpdateToHistory(i, files)}
                    onRemoveUpdate={uid => removeUpdateFromHistory(i, uid)}
                    onRescan={() => rescanHistory(i)}
                    onSaveManual={qty => saveManualQty(i, qty)}
                  />
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}

// ── QueueCard ─────────────────────────────────────────────────────────────────

function QueueCard({
  entry, onRemove, onAddUpdate, onRemoveUpdate,
}: {
  entry: FileEntry;
  onRemove: () => void;
  onAddUpdate: (files: FileList) => void;
  onRemoveUpdate: (id: string) => void;
}) {
  const updateRef    = useRef<HTMLInputElement>(null);
  const isWaiting    = entry.status === "waiting";
  const isProcessing = entry.status === "processing";
  const isDone       = !isWaiting && !isProcessing;

  return (
    <div className={`rounded-xl border transition-all ${
      isProcessing             ? "bg-indigo-50 border-indigo-200" :
      isWaiting                ? "bg-gray-50   border-gray-200"   :
      entry.status === "error" ? "bg-red-50    border-red-200"    :
      entry.status === "partial" ? "bg-amber-50 border-amber-200" :
                                   "bg-green-50 border-green-200"
    }`}>
      <div className="flex items-start gap-3 p-3.5">
        <div className="flex-shrink-0 mt-0.5">
          {isProcessing ? <Loader2       className="w-4 h-4 text-indigo-500 animate-spin" />
          : isWaiting   ? <Clock         className="w-4 h-4 text-gray-400" />
          : entry.status === "error"   ? <XCircle       className="w-4 h-4 text-red-500" />
          : entry.status === "partial" ? <AlertTriangle className="w-4 h-4 text-amber-500" />
          :                              <CheckCircle2  className="w-4 h-4 text-green-600" />}
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-sm font-mono font-medium text-gray-900 truncate">{entry.poFile.name}</p>
          {entry.techpackFile && (
            <p className="text-xs text-gray-500 mt-0.5">+ Techpack: {entry.techpackFile.name}</p>
          )}
          {isProcessing && <p className="text-xs text-indigo-600 mt-1">Đang gọi AI xử lý... (1–2 phút)</p>}
          {isWaiting    && <p className="text-xs text-gray-400 mt-1">Chờ đến lượt...</p>}
          {entry.error   && <p className="text-xs text-red-700 mt-1">{entry.error}</p>}
          {entry.warning && <p className="text-xs text-amber-700 mt-1">⚠ {entry.warning}</p>}
          {entry.po && isDone && (
            <div className="flex flex-wrap gap-3 mt-2">
              <span className="text-xs text-gray-600">PO: <strong>{entry.po.po_number || "—"}</strong></span>
              <span className="text-xs text-gray-600">Style: <strong>{entry.po.style_code || "—"}</strong></span>
              <span className="text-xs text-gray-600">Qty: <strong>{entry.po.total_qty?.toLocaleString() || "—"} pcs</strong></span>
              {entry.trimlist && <span className="text-xs text-green-700">Trim: <strong>{entry.trimlist.item_count} items</strong></span>}
            </div>
          )}
        </div>
        <div className="flex items-center gap-2 flex-shrink-0">
          {entry.timestamp && isDone && (
            <>
              <button onClick={() => downloadAgentPO(entry.timestamp!)}
                className="text-xs text-indigo-600 hover:text-indigo-800 flex items-center gap-1">
                <Download className="w-3 h-3" />PO
              </button>
              {entry.trimlist && (
                <button onClick={() => downloadAgentTrimlist(entry.timestamp!)}
                  className="text-xs text-green-600 hover:text-green-800 flex items-center gap-1">
                  <Download className="w-3 h-3" />TL
                </button>
              )}
            </>
          )}
          {isWaiting && (
            <button onClick={onRemove} className="text-gray-300 hover:text-red-400">
              <X className="w-3.5 h-3.5" />
            </button>
          )}
        </div>
      </div>

      {/* Update files inline */}
      <div className="border-t border-dashed border-gray-200 mx-3.5 pt-2.5 pb-3 space-y-1.5">
        {entry.updateFiles.map(u => (
          <div key={u.id} className="flex items-center gap-2 px-2 py-1.5 bg-white/70 rounded-lg border border-gray-200">
            <RefreshCw className="w-3 h-3 text-indigo-400 flex-shrink-0" />
            <span className="text-xs text-gray-700 truncate flex-1">{u.file.name}</span>
            <span className="text-xs text-indigo-500 whitespace-nowrap">{u.label}</span>
            <button onClick={() => onRemoveUpdate(u.id)} className="text-gray-300 hover:text-red-400 flex-shrink-0">
              <X className="w-3 h-3" />
            </button>
          </div>
        ))}
        <button
          onClick={() => updateRef.current?.click()}
          className="flex items-center gap-1.5 text-xs text-gray-400 hover:text-indigo-600 transition-colors py-0.5"
        >
          <Plus className="w-3 h-3" />
          Thêm file cập nhật từ khách hàng (HZSH, GO Info...)
        </button>
        <input ref={updateRef} type="file" multiple accept=".xlsx,.xls,.pdf,.csv" className="hidden"
          onChange={e => { if (e.target.files?.length) onAddUpdate(e.target.files); }} />
      </div>
    </div>
  );
}

// ── HistoryRow ────────────────────────────────────────────────────────────────

function HistoryRow({
  entry, onAddUpdate, onRemoveUpdate, onRescan, onSaveManual,
}: {
  entry: HistoryEntry;
  onAddUpdate: (files: FileList) => void;
  onRemoveUpdate: (id: string) => void;
  onRescan: () => void;
  onSaveManual: (qty: number) => void;
}) {
  const updateRef  = useRef<HTMLInputElement>(null);
  const [manualQty, setManualQty] = useState("");
  const hasUpdates  = entry.updateFiles.length > 0;
  const qtyChanged  = entry.updated && entry.prev_total_qty !== undefined && entry.prev_total_qty !== entry.total_qty;
  const styleChanged = entry.updated && entry.prev_style_code && entry.prev_style_code !== entry.style_code;

  return (
    <>
      {/* ── Dòng gốc ── */}
      <tr className={`hover:bg-gray-50 ${entry.updated ? "bg-blue-50/30" : ""}`}>
        <td className="px-4 py-2.5 font-mono text-xs text-gray-700 max-w-48 truncate" title={entry.filename}>
          {entry.filename}
        </td>
        <td className="px-4 py-2.5 text-xs">{entry.po_number || "—"}</td>

        {/* Style — inline diff nếu đã thay đổi */}
        <td className="px-4 py-2.5 text-xs font-mono">
          {styleChanged
            ? <span className="flex flex-col leading-tight">
                <span className="text-blue-700 font-medium">{entry.style_code}</span>
                <span className="text-gray-400 line-through text-[10px]">{entry.prev_style_code}</span>
              </span>
            : (entry.style_code || "—")}
        </td>

        {/* Qty — inline diff nếu đã thay đổi */}
        <td className="px-4 py-2.5 text-xs text-right">
          {qtyChanged
            ? <span className="flex flex-col items-end leading-tight">
                <span className="text-blue-700 font-medium">{entry.total_qty?.toLocaleString()}</span>
                <span className="text-gray-400 line-through text-[10px]">{entry.prev_total_qty?.toLocaleString()}</span>
              </span>
            : (entry.total_qty?.toLocaleString() || "—")}
        </td>

        <td className="px-4 py-2.5 text-xs text-right">{entry.trim_count || "—"}</td>
        <td className="px-4 py-2.5 text-xs text-gray-400 whitespace-nowrap">{entry.processed_at}</td>

        {/* Status — kèm badge "↺ Cập nhật" nếu đã rescan */}
        <td className="px-4 py-2.5">
          <div className="flex flex-col gap-0.5">
            <StatusBadge status={entry.status} />
            {entry.updated && (
              <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-full text-[10px] bg-blue-100 text-blue-700 whitespace-nowrap w-fit">
                <RotateCcw className="w-2.5 h-2.5" />{entry.update_label || "Đã cập nhật"}
              </span>
            )}
            {entry.is_rescanning && (
              <span className="inline-flex items-center gap-1 text-[10px] text-indigo-500">
                <Loader2 className="w-2.5 h-2.5 animate-spin" />Đang quét...
              </span>
            )}
          </div>
        </td>

        <td className="px-4 py-2.5">
          <div className="flex items-center gap-2 flex-wrap">
            {entry.timestamp && (
              <>
                <button onClick={() => downloadAgentPO(entry.timestamp!)}
                  className="text-xs text-indigo-600 hover:text-indigo-800 flex items-center gap-1">
                  <Download className="w-3 h-3" />PO
                </button>
                {!!entry.trim_count && (
                  <>
                    <button onClick={() => downloadAgentTrimlist(entry.timestamp!)}
                      className="text-xs text-green-600 hover:text-green-800 flex items-center gap-1">
                      <Download className="w-3 h-3" />TL
                    </button>
                    <button onClick={() => downloadAgentTrimlistPDF(entry.timestamp!)}
                      className="text-xs text-rose-600 hover:text-rose-800 flex items-center gap-1">
                      <Download className="w-3 h-3" />PDF
                    </button>
                  </>
                )}
              </>
            )}
            <button
              onClick={() => updateRef.current?.click()}
              title="Thêm file cập nhật"
              className="text-gray-300 hover:text-indigo-500 transition-colors"
            >
              <RefreshCw className="w-3.5 h-3.5" />
            </button>
            {hasUpdates && (
              <button
                onClick={onRescan}
                disabled={entry.is_rescanning}
                title="Quét lại với file cập nhật"
                className="flex items-center gap-1 text-xs font-medium text-amber-600 hover:text-amber-800
                  disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
              >
                {entry.is_rescanning
                  ? <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  : <RotateCcw className="w-3.5 h-3.5" />}
                Quét lại
              </button>
            )}
            <input ref={updateRef} type="file" multiple accept=".xlsx,.xls,.pdf,.csv" className="hidden"
              onChange={e => { if (e.target.files?.length) onAddUpdate(e.target.files); }} />
          </div>
        </td>
      </tr>

      {/* ── File update đang chờ quét ── */}
      {hasUpdates && (
        <tr className="bg-amber-50/60">
          <td colSpan={8} className="px-6 py-2 border-b border-amber-100">
            <div className="flex items-center gap-2 flex-wrap">
              <span className="text-xs text-amber-600 font-medium whitespace-nowrap">Chờ quét lại:</span>
              {entry.updateFiles.map(u => (
                <span key={u.id}
                  className="inline-flex items-center gap-1.5 px-2 py-0.5 bg-white border border-amber-200 rounded-full text-xs text-amber-700">
                  <RefreshCw className="w-2.5 h-2.5" />
                  {u.file.name}
                  <span className="text-amber-400">· {u.label}</span>
                  <button onClick={() => onRemoveUpdate(u.id)} className="text-amber-300 hover:text-red-400 ml-0.5">
                    <X className="w-2.5 h-2.5" />
                  </button>
                </span>
              ))}
            </div>
          </td>
        </tr>
      )}

      {/* ── Form nhập tay (hiện tạm khi AI không đọc được, xóa sau khi lưu) ── */}
      {entry.needs_manual_input && (
        <tr className="bg-orange-50">
          <td colSpan={8} className="px-8 py-3">
            <div className="flex items-center gap-3">
              <AlertTriangle className="w-4 h-4 text-orange-400 flex-shrink-0" />
              <span className="text-xs text-orange-700 flex-1">
                Không tự động đọc được file này. Nhập tổng số lượng mới (pcs):
              </span>
              <input
                type="number"
                placeholder="VD: 1538"
                value={manualQty}
                onChange={e => setManualQty(e.target.value)}
                className="w-32 px-3 py-1.5 border border-orange-300 rounded-lg text-sm text-center
                  focus:outline-none focus:ring-2 focus:ring-orange-400 bg-white"
              />
              <button
                onClick={() => {
                  const qty = parseInt(manualQty || "0");
                  if (qty > 0) { onSaveManual(qty); setManualQty(""); }
                }}
                disabled={!manualQty || parseInt(manualQty) <= 0}
                className="px-3 py-1.5 bg-orange-500 text-white rounded-lg text-xs font-medium
                  hover:bg-orange-600 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
              >
                Lưu
              </button>
            </div>
          </td>
        </tr>
      )}
    </>
  );
}

// ── Badges ────────────────────────────────────────────────────────────────────

function StatusBadge({ status }: { status: string }) {
  if (status === "success")
    return <span className="inline-flex px-2 py-0.5 rounded-full text-xs bg-green-100 text-green-700 whitespace-nowrap">✓ Xong</span>;
  if (status === "partial")
    return <span className="inline-flex px-2 py-0.5 rounded-full text-xs bg-amber-100 text-amber-700 whitespace-nowrap">⚠ 1 phần</span>;
  return <span className="inline-flex px-2 py-0.5 rounded-full text-xs bg-red-100 text-red-700 whitespace-nowrap">✗ Lỗi</span>;
}


