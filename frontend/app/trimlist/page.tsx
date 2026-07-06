"use client";
import { useState, useEffect, useCallback } from "react";
import toast from "react-hot-toast";
import {
  RefreshCw, Download, Loader2, CheckCircle2, XCircle,
  Scissors, FolderSearch, AlertTriangle, Clock, FolderOpen, Send,
} from "lucide-react";
import api, { downloadAgentPO, downloadAgentTrimlist, downloadAgentTrimlistPDF } from "@/lib/api";

interface ScanStatus {
  scan_folder:   string;
  total_files:   number;
  processed:     number;
  new_files:     number;
  new_filenames: string[];
  log:           Record<string, ProcessedEntry>;
}

interface ProcessedEntry {
  processed_at: string;
  file_path:    string;
  status:       "success" | "partial" | "error";
  timestamp?:   string;
  po_number?:   string;
  style_code?:  string;
  total_qty?:   number;
  trim_count?:  number;
  warning?:     string;
  error?:       string;
}

interface EmailTarget {
  timestamp:  string;
  po_number:  string;
  style_code: string;
  total_qty:  number;
  trim_count: number;
}

interface PreviewItem {
  trim_item: string;
  spec:      string;
  supplier:  string;
  unit:      string;
  total_qty: number | string;
}

interface FileResult {
  filename:        string;
  status:          "success" | "partial" | "error" | "processing" | "waiting";
  timestamp?:      string;
  warning?:        string;
  error?:          string;
  po?:             { po_number?: string; style_code?: string; total_qty?: number };
  trimlist?:       { item_count: number } | null;
}

export default function TrimlistPage() {
  const [scanStatus,  setScanStatus]  = useState<ScanStatus | null>(null);
  const [isScanning,  setIsScanning]  = useState(false);
  const [fileQueue,   setFileQueue]   = useState<FileResult[]>([]);
  const [loadingInit, setLoadingInit] = useState(true);
  const [emailTarget,    setEmailTarget]    = useState<EmailTarget | null>(null);
  const [toEmail,        setToEmail]        = useState("");
  const [sending,        setSending]        = useState(false);
  const [previewItems,   setPreviewItems]   = useState<PreviewItem[]>([]);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [telegramTarget, setTelegramTarget] = useState<EmailTarget | null>(null);

  const loadStatus = useCallback(async () => {
    try {
      const { data } = await api.get<ScanStatus>("/api/agent/scan/status");
      setScanStatus(data);
    } catch {
      toast.error("Khong ket noi duoc Backend");
    } finally {
      setLoadingInit(false);
    }
  }, []);

  const [newBadge,    setNewBadge]    = useState(0);
  const [searchText,  setSearchText]  = useState("");
  const [filterDate,  setFilterDate]  = useState("");

  useEffect(() => {
    loadStatus();
    const interval = setInterval(async () => {
      if (isScanning) return;
      try {
        const { data } = await api.get<ScanStatus>("/api/agent/scan/status");
        setScanStatus(data);
        if (data.new_files > 0) {
          setNewBadge(data.new_files);
          toast(`Có ${data.new_files} file mới chưa xử lý`, {
            id: "new-files-badge",
            duration: 5000,
            icon: "🔔",
          });
        } else {
          setNewBadge(0);
        }
      } catch { /* silent poll */ }
    }, 30000);
    return () => clearInterval(interval);
  }, [isScanning, loadStatus]);

  const runScan = async () => {
    if (isScanning) return;

    // Reload status truoc de lay danh sach file moi nhat
    let newFilenames: string[] = [];
    try {
      const { data } = await api.get<ScanStatus>("/api/agent/scan/status");
      setScanStatus(data);
      newFilenames = data.new_filenames;
    } catch {
      toast.error("Khong ket noi duoc Backend");
      return;
    }

    if (newFilenames.length === 0) {
      toast("Khong co file moi", { icon: "✅" });
      return;
    }

    // Khoi tao queue hien thi
    setFileQueue(newFilenames.map(f => ({ filename: f, status: "waiting" })));
    setIsScanning(true);

    let okCount  = 0;
    let errCount = 0;

    for (let i = 0; i < newFilenames.length; i++) {
      const filename = newFilenames[i];

      // Cap nhat trang thai dang xu ly
      setFileQueue(prev => prev.map(f =>
        f.filename === filename ? { ...f, status: "processing" } : f
      ));

      try {
        const { data } = await api.post<FileResult>(
          "/api/agent/scan/run-one",
          { filename },
          { timeout: 300000 }  // 5 phut cho moi file
        );

        setFileQueue(prev => prev.map(f =>
          f.filename === filename ? { ...data, filename } : f
        ));

        if (data.status === "error") errCount++;
        else okCount++;

      } catch (e: unknown) {
        const err = e as { response?: { data?: { detail?: string } }; message?: string };
        const msg = err?.response?.data?.detail || err?.message || "Timeout hoac loi mang";
        setFileQueue(prev => prev.map(f =>
          f.filename === filename ? { ...f, status: "error", error: msg } : f
        ));
        errCount++;
      }
    }

    setIsScanning(false);

    // Reload log sau khi xong
    const { data: finalStatus } = await api.get<ScanStatus>("/api/agent/scan/status");
    setScanStatus(finalStatus);

    if (errCount > 0) toast.error(`${errCount} file loi · ${okCount} file thanh cong`);
    else toast.success(`Xu ly xong ${okCount} file`);
  };

  const fetchPreview = async (timestamp: string) => {
    setPreviewItems([]);
    if (!timestamp) return;
    setPreviewLoading(true);
    try {
      const { data } = await api.get<{ items: PreviewItem[] }>(`/api/agent/trimlist-preview/${timestamp}`);
      setPreviewItems(data.items || []);
    } catch {
      setPreviewItems([]);
    } finally {
      setPreviewLoading(false);
    }
  };

  const openEmailModal = (entry: ProcessedEntry) => {
    const target = {
      timestamp:  entry.timestamp || "",
      po_number:  entry.po_number  || "",
      style_code: entry.style_code || "",
      total_qty:  entry.total_qty  || 0,
      trim_count: entry.trim_count || 0,
    };
    setEmailTarget(target);
    setToEmail("");
    fetchPreview(target.timestamp);
  };

  const openTelegramModal = (entry: ProcessedEntry) => {
    const target = {
      timestamp:  entry.timestamp || "",
      po_number:  entry.po_number  || "",
      style_code: entry.style_code || "",
      total_qty:  entry.total_qty  || 0,
      trim_count: entry.trim_count || 0,
    };
    setTelegramTarget(target);
    fetchPreview(target.timestamp);
  };

  const handleSendEmail = async () => {
    if (!emailTarget || !toEmail) return;
    setSending(true);
    try {
      await api.post("/api/agent/send-trimlist-email", { to_email: toEmail, ...emailTarget });
      toast.success(`Đã gửi Trim List đến ${toEmail}`);
      setEmailTarget(null);
      setToEmail("");
      setPreviewItems([]);
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } }; message?: string };
      toast.error(err?.response?.data?.detail || err?.message || "Gửi email thất bại");
    } finally {
      setSending(false);
    }
  };

  const confirmSendTelegram = async () => {
    if (!telegramTarget) return;
    setSending(true);
    const tid = toast.loading("Đang gửi Telegram...");
    try {
      await api.post("/api/agent/send-trimlist-telegram", {
        timestamp:  telegramTarget.timestamp,
        po_number:  telegramTarget.po_number  || "",
        style_code: telegramTarget.style_code || "",
        total_qty:  telegramTarget.total_qty  || 0,
        trim_count: telegramTarget.trim_count || 0,
      });
      toast.success("Đã gửi qua Telegram!", { id: tid });
      setTelegramTarget(null);
      setPreviewItems([]);
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } }; message?: string };
      toast.error(err?.response?.data?.detail || "Gửi Telegram thất bại", { id: tid });
    } finally {
      setSending(false);
    }
  };

  const resetFile = async (filename: string) => {
    try {
      await api.post(`/api/agent/scan/reset/${encodeURIComponent(filename)}`);
      toast.success("Da reset file");
      await loadStatus();
    } catch {
      toast.error("Reset that bai");
    }
  };

  return (
    <div className="p-8 max-w-5xl mx-auto">
      {/* Header */}
      <div className="flex items-start justify-between mb-6">
        <div>
          <h1 className="text-xl font-bold text-gray-900 mb-1">Trim List — Auto Scan</h1>
          <p className="text-sm text-gray-500">
            He thong tu quet folder khi mo trang · File PO moi duoc xu ly tu dong
          </p>
        </div>
        <div className="relative">
          <button
            onClick={() => { setNewBadge(0); runScan(); }}
            disabled={isScanning}
            className="flex items-center gap-2 px-4 py-2 bg-indigo-600 text-white rounded-lg text-sm font-medium
              disabled:opacity-50 disabled:cursor-not-allowed hover:bg-indigo-700 transition-colors"
          >
            {isScanning
              ? <><Loader2 className="w-4 h-4 animate-spin" />Đang xử lý...</>
              : <><RefreshCw className="w-4 h-4" />Quét lại</>}
          </button>
          {newBadge > 0 && (
            <span className="absolute -top-2 -right-2 w-5 h-5 bg-red-500 text-white text-xs
              rounded-full flex items-center justify-center font-bold animate-pulse">
              {newBadge}
            </span>
          )}
        </div>
      </div>

      {/* Folder status */}
      {scanStatus && (
        <div className="bg-white rounded-xl border border-gray-200 p-5 mb-5">
          <div className="flex items-center gap-2 mb-3">
            <FolderOpen className="w-4 h-4 text-indigo-500" />
            <span className="text-sm font-semibold text-gray-900">Folder dang theo doi</span>
          </div>
          <p className="text-xs font-mono text-gray-500 mb-4 bg-gray-50 rounded px-3 py-2 break-all">
            {scanStatus.scan_folder}
          </p>
          <div className="grid grid-cols-3 gap-4">
            <div className="bg-gray-50 rounded-lg p-3 text-center">
              <p className="text-2xl font-bold text-gray-900">{scanStatus.total_files}</p>
              <p className="text-xs text-gray-500 mt-0.5">Tong file</p>
            </div>
            <div className="bg-green-50 rounded-lg p-3 text-center">
              <p className="text-2xl font-bold text-green-700">{scanStatus.processed}</p>
              <p className="text-xs text-green-600 mt-0.5">Da xu ly</p>
            </div>
            <div className={`rounded-lg p-3 text-center ${scanStatus.new_files > 0 ? "bg-amber-50" : "bg-gray-50"}`}>
              <p className={`text-2xl font-bold ${scanStatus.new_files > 0 ? "text-amber-700" : "text-gray-400"}`}>
                {scanStatus.new_files}
              </p>
              <p className={`text-xs mt-0.5 ${scanStatus.new_files > 0 ? "text-amber-600" : "text-gray-400"}`}>
                File moi
              </p>
            </div>
          </div>

          {scanStatus.new_filenames.length > 0 && !isScanning && fileQueue.length === 0 && (
            <div className="mt-4 p-3 bg-amber-50 border border-amber-200 rounded-lg">
              <p className="text-xs font-medium text-amber-800 mb-1.5">
                Cho xu ly ({scanStatus.new_filenames.length} file) — nhan Quet lai de bat dau:
              </p>
              <ul className="space-y-1">
                {scanStatus.new_filenames.map(f => (
                  <li key={f} className="text-xs text-amber-700 font-mono">• {f}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}

      {/* Loading init */}
      {loadingInit && (
        <div className="bg-white rounded-xl border border-gray-200 p-8 text-center">
          <Loader2 className="w-6 h-6 animate-spin text-indigo-500 mx-auto mb-2" />
          <p className="text-sm text-gray-500">Dang ket noi...</p>
        </div>
      )}

      {/* Progress: file queue dang xu ly */}
      {fileQueue.length > 0 && (
        <div className="mb-5">
          <h2 className="text-sm font-semibold text-gray-700 mb-3 flex items-center gap-2">
            <Scissors className="w-4 h-4 text-indigo-500" />
            {isScanning ? "Dang xu ly..." : "Ket qua lan quet"} ({fileQueue.length} file)
          </h2>
          <div className="space-y-3">
            {fileQueue.map((f) => (
              <FileCard key={f.filename} file={f} />
            ))}
          </div>
        </div>
      )}

      {/* History log */}
      {scanStatus && Object.keys(scanStatus.log).length > 0 && (
        <div>
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-sm font-semibold text-gray-700 flex items-center gap-2">
              <Clock className="w-4 h-4 text-gray-400" />
              Lịch sử đã xử lý ({Object.keys(scanStatus.log).length} file)
            </h2>
            <div className="flex items-center gap-2">
              <input
                type="text"
                value={searchText}
                onChange={e => setSearchText(e.target.value)}
                placeholder="Tìm file, PO, style..."
                className="border border-gray-200 rounded-lg px-3 py-1.5 text-xs w-48
                  focus:outline-none focus:ring-2 focus:ring-indigo-400"
              />
              <input
                type="date"
                value={filterDate}
                onChange={e => setFilterDate(e.target.value)}
                className="border border-gray-200 rounded-lg px-3 py-1.5 text-xs
                  focus:outline-none focus:ring-2 focus:ring-indigo-400"
              />
              {(searchText || filterDate) && (
                <button
                  onClick={() => { setSearchText(""); setFilterDate(""); }}
                  className="text-xs text-gray-400 hover:text-red-500 px-2"
                >✕ Xoá</button>
              )}
            </div>
          </div>
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
                {Object.entries(scanStatus.log)
                  .sort((a, b) => b[1].processed_at.localeCompare(a[1].processed_at))
                  .filter(([filename, entry]) => {
                    const q = searchText.toLowerCase();
                    const matchText = !q ||
                      filename.toLowerCase().includes(q) ||
                      (entry.po_number  || "").toLowerCase().includes(q) ||
                      (entry.style_code || "").toLowerCase().includes(q);
                    const matchDate = !filterDate ||
                      entry.processed_at.startsWith(filterDate);
                    return matchText && matchDate;
                  })
                  .map(([filename, entry]) => (
                  <tr key={filename} className="hover:bg-gray-50">
                    <td className="px-4 py-2.5 font-mono text-xs text-gray-700 max-w-48 truncate" title={filename}>{filename}</td>
                    <td className="px-4 py-2.5 text-xs">{entry.po_number || "—"}</td>
                    <td className="px-4 py-2.5 text-xs font-mono">{entry.style_code || "—"}</td>
                    <td className="px-4 py-2.5 text-xs text-right">{entry.total_qty ? entry.total_qty.toLocaleString() : "—"}</td>
                    <td className="px-4 py-2.5 text-xs text-right">{entry.trim_count ? `${entry.trim_count}` : "—"}</td>
                    <td className="px-4 py-2.5 text-xs text-gray-400 whitespace-nowrap">{entry.processed_at.slice(0, 16)}</td>
                    <td className="px-4 py-2.5"><StatusBadge status={entry.status} /></td>
                    <td className="px-4 py-2.5">
                      <div className="flex items-center gap-2">
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
                                  className="text-xs text-rose-600 hover:text-rose-800 flex items-center gap-1"
                                  title="Tải PDF">
                                  <Download className="w-3 h-3" />PDF
                                </button>
                                <button onClick={() => openEmailModal(entry)}
                                  className="text-xs text-emerald-600 hover:text-emerald-800 flex items-center gap-1"
                                  title="Gửi email">
                                  <Send className="w-3 h-3" />
                                </button>
                                <button onClick={() => openTelegramModal(entry)}
                                  className="text-xs text-sky-600 hover:text-sky-800 flex items-center gap-1"
                                  title="Gửi Telegram">
                                  ✈
                                </button>
                              </>
                            )}
                          </>
                        )}
                        <button onClick={() => resetFile(filename)}
                          className="text-xs text-gray-400 hover:text-red-500" title="Xu ly lai">&#8635;</button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Empty state */}
      {scanStatus && Object.keys(scanStatus.log).length === 0 && fileQueue.length === 0 && !loadingInit && (
        <div className="bg-white rounded-xl border border-dashed border-gray-300 p-12 text-center">
          <FolderSearch className="w-10 h-10 text-gray-300 mx-auto mb-3" />
          <p className="text-gray-500 font-medium">Chua co file nao duoc xu ly</p>
          <p className="text-sm text-gray-400 mt-1">Nhan Quet lai de bat dau</p>
        </div>
      )}

      {/* Modal gửi email trimlist */}
      {emailTarget && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-2xl shadow-xl w-full max-w-xl p-6">
            <h3 className="text-base font-semibold text-gray-900 mb-1">Gửi Trim List qua Email</h3>
            <p className="text-xs text-gray-500 mb-4">
              PO: <strong>{emailTarget.po_number || "—"}</strong> ·
              Style: <strong>{emailTarget.style_code || "—"}</strong> ·
              {emailTarget.trim_count} loại trim
            </p>

            {/* Preview table */}
            <div className="mb-4">
              <p className="text-xs font-medium text-gray-600 mb-2">Xem trước nội dung:</p>
              {previewLoading ? (
                <div className="flex items-center gap-2 py-4 justify-center text-xs text-gray-400">
                  <Loader2 className="w-3 h-3 animate-spin" /> Đang tải...
                </div>
              ) : previewItems.length > 0 ? (
                <div className="border border-gray-200 rounded-lg overflow-hidden max-h-48 overflow-y-auto">
                  <table className="w-full text-xs">
                    <thead className="bg-gray-50 sticky top-0">
                      <tr>
                        {["Trim Item", "Spec", "Supplier", "Unit", "Qty"].map(h => (
                          <th key={h} className="px-2 py-1.5 text-left text-gray-500 font-medium whitespace-nowrap">{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-100">
                      {previewItems.map((item, i) => (
                        <tr key={i} className="hover:bg-gray-50">
                          <td className="px-2 py-1 font-medium text-gray-900 max-w-32 truncate" title={item.trim_item}>{item.trim_item}</td>
                          <td className="px-2 py-1 text-gray-600 max-w-24 truncate" title={item.spec}>{item.spec || "—"}</td>
                          <td className="px-2 py-1 text-gray-600 max-w-24 truncate" title={item.supplier}>{item.supplier || "—"}</td>
                          <td className="px-2 py-1 text-gray-500">{item.unit || "—"}</td>
                          <td className="px-2 py-1 text-right font-mono">{Number(item.total_qty || 0).toLocaleString()}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <p className="text-xs text-gray-400 italic py-2">Không có dữ liệu preview</p>
              )}
            </div>

            <label className="block text-sm font-medium text-gray-700 mb-1.5">
              Địa chỉ email nhận
            </label>
            <input
              type="email"
              value={toEmail}
              onChange={e => setToEmail(e.target.value)}
              onKeyDown={e => e.key === "Enter" && handleSendEmail()}
              placeholder="example@gmail.com"
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm
                focus:outline-none focus:ring-2 focus:ring-indigo-500 mb-4"
              autoFocus
            />
            <div className="flex gap-2 justify-end">
              <button
                onClick={() => { setEmailTarget(null); setPreviewItems([]); }}
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

      {/* Modal xác nhận gửi Telegram */}
      {telegramTarget && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-2xl shadow-xl w-full max-w-xl p-6">
            <h3 className="text-base font-semibold text-gray-900 mb-1">Gửi Trim List qua Telegram</h3>
            <p className="text-xs text-gray-500 mb-4">
              PO: <strong>{telegramTarget.po_number || "—"}</strong> ·
              Style: <strong>{telegramTarget.style_code || "—"}</strong> ·
              {telegramTarget.trim_count} loại trim
            </p>

            {/* Preview table */}
            <div className="mb-4">
              <p className="text-xs font-medium text-gray-600 mb-2">Xem trước nội dung:</p>
              {previewLoading ? (
                <div className="flex items-center gap-2 py-4 justify-center text-xs text-gray-400">
                  <Loader2 className="w-3 h-3 animate-spin" /> Đang tải...
                </div>
              ) : previewItems.length > 0 ? (
                <div className="border border-gray-200 rounded-lg overflow-hidden max-h-48 overflow-y-auto">
                  <table className="w-full text-xs">
                    <thead className="bg-gray-50 sticky top-0">
                      <tr>
                        {["Trim Item", "Spec", "Supplier", "Unit", "Qty"].map(h => (
                          <th key={h} className="px-2 py-1.5 text-left text-gray-500 font-medium whitespace-nowrap">{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-100">
                      {previewItems.map((item, i) => (
                        <tr key={i} className="hover:bg-gray-50">
                          <td className="px-2 py-1 font-medium text-gray-900 max-w-32 truncate" title={item.trim_item}>{item.trim_item}</td>
                          <td className="px-2 py-1 text-gray-600 max-w-24 truncate" title={item.spec}>{item.spec || "—"}</td>
                          <td className="px-2 py-1 text-gray-600 max-w-24 truncate" title={item.supplier}>{item.supplier || "—"}</td>
                          <td className="px-2 py-1 text-gray-500">{item.unit || "—"}</td>
                          <td className="px-2 py-1 text-right font-mono">{Number(item.total_qty || 0).toLocaleString()}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <p className="text-xs text-gray-400 italic py-2">Không có dữ liệu preview</p>
              )}
            </div>

            <p className="text-xs text-gray-500 mb-4">
              File sẽ được gửi đến <strong>chat mặc định</strong> đã cấu hình trong hệ thống.
            </p>
            <div className="flex gap-2 justify-end">
              <button
                onClick={() => { setTelegramTarget(null); setPreviewItems([]); }}
                className="px-4 py-2 text-sm text-gray-600 hover:text-gray-900 rounded-lg hover:bg-gray-100"
              >
                Huỷ
              </button>
              <button
                onClick={confirmSendTelegram}
                disabled={sending}
                className="flex items-center gap-2 px-5 py-2 bg-sky-600 text-white text-sm font-medium
                  rounded-lg hover:bg-sky-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                {sending
                  ? <><Loader2 className="w-4 h-4 animate-spin" /> Đang gửi...</>
                  : <>✈ Gửi Telegram</>}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function FileCard({ file }: { file: FileResult }) {
  const isProcessing = file.status === "processing";
  const isWaiting    = file.status === "waiting";

  return (
    <div className={`rounded-xl border p-4 transition-all ${
      isProcessing    ? "bg-indigo-50 border-indigo-200" :
      isWaiting       ? "bg-gray-50 border-gray-200" :
      file.status === "error"   ? "bg-red-50 border-red-200" :
      file.status === "partial" ? "bg-amber-50 border-amber-200" :
                                  "bg-green-50 border-green-200"
    }`}>
      <div className="flex items-start gap-3">
        <div className="flex-shrink-0 mt-0.5">
          {isProcessing
            ? <Loader2     className="w-5 h-5 text-indigo-500 animate-spin" />
            : isWaiting
              ? <Clock       className="w-5 h-5 text-gray-400" />
              : file.status === "error"
                ? <XCircle     className="w-5 h-5 text-red-500" />
                : file.status === "partial"
                  ? <AlertTriangle className="w-5 h-5 text-amber-500" />
                  : <CheckCircle2  className="w-5 h-5 text-green-600" />}
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-sm font-mono font-medium text-gray-900 truncate">{file.filename}</p>
          {isProcessing && <p className="text-xs text-indigo-600 mt-1">Dang goi AI xu ly... (co the mat 1-2 phut)</p>}
          {isWaiting    && <p className="text-xs text-gray-400 mt-1">Cho den luot...</p>}
          {file.status === "error" && <p className="text-xs text-red-700 mt-1">{file.error}</p>}
          {file.status !== "error" && !isProcessing && !isWaiting && file.po && (
            <div className="flex flex-wrap gap-3 mt-2">
              <span className="text-xs text-gray-600">PO: <strong>{file.po.po_number || "—"}</strong></span>
              <span className="text-xs text-gray-600">Style: <strong>{file.po.style_code || "—"}</strong></span>
              <span className="text-xs text-gray-600">Qty: <strong>{file.po.total_qty?.toLocaleString() || "—"} pcs</strong></span>
              {file.trimlist && <span className="text-xs text-green-700">Trimlist: <strong>{file.trimlist.item_count} items</strong></span>}
            </div>
          )}
          {file.warning && <p className="text-xs text-amber-700 mt-1">&#9888; {file.warning}</p>}
        </div>
        {file.timestamp && !isProcessing && !isWaiting && (
          <div className="flex items-center gap-2 flex-shrink-0">
            <button onClick={() => downloadAgentPO(file.timestamp!)}
              className="text-xs text-indigo-600 hover:text-indigo-800 flex items-center gap-1 font-medium">
              <Download className="w-3.5 h-3.5" />PO
            </button>
            {file.trimlist && (
              <button onClick={() => downloadAgentTrimlist(file.timestamp!)}
                className="text-xs text-green-600 hover:text-green-800 flex items-center gap-1 font-medium">
                <Download className="w-3.5 h-3.5" />TL
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function StatusBadge({ status }: { status: string }) {
  if (status === "success")
    return <span className="inline-flex px-2 py-0.5 rounded-full text-xs bg-green-100 text-green-700 whitespace-nowrap">&#10003; Xong</span>;
  if (status === "partial")
    return <span className="inline-flex px-2 py-0.5 rounded-full text-xs bg-amber-100 text-amber-700 whitespace-nowrap">&#9888; 1 phan</span>;
  return <span className="inline-flex px-2 py-0.5 rounded-full text-xs bg-red-100 text-red-700 whitespace-nowrap">&#10007; Loi</span>;
}
