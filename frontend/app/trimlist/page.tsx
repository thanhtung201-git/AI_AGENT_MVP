"use client";
import { useState, useCallback } from "react";
import { useDropzone } from "react-dropzone";
import toast from "react-hot-toast";
import {
  Upload, Download, Loader2, CheckCircle2, XCircle,
  Scissors, FileText, FolderSearch, AlertTriangle,
} from "lucide-react";
import { runAgent, downloadAgentPO, downloadAgentTrimlist, type AgentResult } from "@/lib/api";

type Step = "idle" | "extracting_po" | "finding_techpack" | "extracting_trim" | "done" | "error";

export default function TrimlistPage() {
  const [file,    setFile]    = useState<File | null>(null);
  const [step,    setStep]    = useState<Step>("idle");
  const [result,  setResult]  = useState<AgentResult | null>(null);
  const [error,   setError]   = useState<string | null>(null);

  const onDrop = useCallback((accepted: File[]) => {
    if (accepted[0]) { setFile(accepted[0]); setResult(null); setError(null); setStep("idle"); }
  }, []);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      "application/pdf": [".pdf"],
      "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": [".xlsx"],
    },
    maxFiles: 1,
  });

  async function handleRun() {
    if (!file) return;
    setError(null);
    setResult(null);

    // Hiển thị tiến trình giả lập (backend xử lý async, không có streaming)
    setStep("extracting_po");
    try {
      // Sau 2s chuyển bước (chỉ UI)
      const timer1 = setTimeout(() => setStep("finding_techpack"), 2000);
      const timer2 = setTimeout(() => setStep("extracting_trim"),  4000);

      const res = await runAgent(file);
      clearTimeout(timer1);
      clearTimeout(timer2);
      setResult(res);
      setStep("done");

      if (res.status === "partial") {
        toast(res.warning || "Xử lý một phần", { icon: "⚠️" });
      } else {
        toast.success(`Hoàn tất — ${res.trimlist?.item_count} trim items`);
      }
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } }; message?: string };
      const msg = err?.response?.data?.detail || err?.message || "Lỗi không xác định";
      setError(msg);
      setStep("error");
      toast.error(msg);
    }
  }

  const steps = [
    { key: "extracting_po",      icon: FileText,     label: "Đọc & trích xuất PO" },
    { key: "finding_techpack",   icon: FolderSearch, label: "Tìm Techpack khớp Style Code" },
    { key: "extracting_trim",    icon: Scissors,     label: "Trích xuất Trim List từ Techpack" },
  ] as const;

  const stepOrder: Step[] = ["extracting_po", "finding_techpack", "extracting_trim", "done"];

  return (
    <div className="p-8 max-w-5xl mx-auto">
      <h1 className="text-xl font-bold text-gray-900 mb-1">Trim List</h1>
      <p className="text-sm text-gray-500 mb-6">
        Upload file PO → AI tự tìm Techpack khớp → Trích xuất Trim List → Export Excel
      </p>

      {/* Upload + Button */}
      <div className="bg-white rounded-xl border border-gray-200 p-5 mb-4">
        <label className="block text-sm font-medium text-gray-700 mb-2">File Purchase Order (PDF / Excel)</label>
        <div
          {...getRootProps()}
          className={`border-2 border-dashed rounded-xl p-10 text-center cursor-pointer transition-colors ${
            isDragActive ? "border-indigo-400 bg-indigo-50" : "border-gray-300 hover:border-gray-400 bg-gray-50"
          }`}
        >
          <input {...getInputProps()} />
          <Upload className="w-8 h-8 text-gray-400 mx-auto mb-3" />
          {file ? (
            <div>
              <p className="font-medium text-gray-900">{file.name}</p>
              <p className="text-sm text-gray-400 mt-1">{(file.size / 1024).toFixed(1)} KB</p>
            </div>
          ) : (
            <div>
              <p className="text-gray-600">Kéo thả file PO vào đây</p>
              <p className="text-sm text-gray-400 mt-1">hoặc click để chọn (.pdf, .xlsx)</p>
            </div>
          )}
        </div>

        <button
          onClick={handleRun}
          disabled={!file || (step !== "idle" && step !== "done" && step !== "error")}
          className="mt-4 w-full py-2.5 px-4 bg-indigo-600 text-white rounded-lg font-medium text-sm
            disabled:opacity-50 disabled:cursor-not-allowed hover:bg-indigo-700 transition-colors
            flex items-center justify-center gap-2"
        >
          {step !== "idle" && step !== "done" && step !== "error"
            ? <><Loader2 className="w-4 h-4 animate-spin" />Đang xử lý...</>
            : <><Scissors className="w-4 h-4" />Chạy AI Agent</>}
        </button>
      </div>

      {/* Progress Steps */}
      {step !== "idle" && step !== "error" && (
        <div className="bg-white rounded-xl border border-gray-200 p-5 mb-4">
          <p className="text-sm font-medium text-gray-700 mb-4">Tiến trình xử lý</p>
          <div className="space-y-3">
            {steps.map(({ key, icon: Icon, label }) => {
              const currentIdx = stepOrder.indexOf(step);
              const thisIdx    = stepOrder.indexOf(key);
              const isDone     = currentIdx > thisIdx || step === "done";
              const isActive   = step === key;
              return (
                <div key={key} className="flex items-center gap-3">
                  <div className={`w-7 h-7 rounded-full flex items-center justify-center flex-shrink-0 ${
                    isDone   ? "bg-green-100" :
                    isActive ? "bg-indigo-100" : "bg-gray-100"
                  }`}>
                    {isDone
                      ? <CheckCircle2 className="w-4 h-4 text-green-600" />
                      : isActive
                        ? <Loader2 className="w-4 h-4 text-indigo-600 animate-spin" />
                        : <Icon className="w-4 h-4 text-gray-400" />}
                  </div>
                  <span className={`text-sm ${isDone ? "text-green-700" : isActive ? "text-indigo-700 font-medium" : "text-gray-400"}`}>
                    {label}
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Error */}
      {error && (
        <div className="mb-4 p-4 bg-red-50 border border-red-200 rounded-lg flex items-start gap-3">
          <XCircle className="w-5 h-5 text-red-500 flex-shrink-0 mt-0.5" />
          <p className="text-sm text-red-700">{error}</p>
        </div>
      )}

      {/* Warning (partial) */}
      {result?.status === "partial" && result.warning && (
        <div className="mb-4 p-4 bg-amber-50 border border-amber-200 rounded-lg flex items-start gap-3">
          <AlertTriangle className="w-5 h-5 text-amber-500 flex-shrink-0 mt-0.5" />
          <p className="text-sm text-amber-800">{result.warning}</p>
        </div>
      )}

      {/* Results */}
      {result && (
        <div className="space-y-4">
          {/* PO Summary */}
          <div className="bg-white rounded-xl border border-gray-200 p-5">
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2">
                <FileText className="w-4 h-4 text-blue-500" />
                <h2 className="text-sm font-semibold text-gray-900">Kết quả PO</h2>
              </div>
              <button
                onClick={() => downloadAgentPO(result.timestamp)}
                className="flex items-center gap-1.5 text-sm text-indigo-600 hover:text-indigo-800 font-medium"
              >
                <Download className="w-4 h-4" /> Download PO Excel
              </button>
            </div>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              {[
                { label: "PO Number",  value: result.po.po_number  || "—" },
                { label: "Style Code", value: result.po.style_code || "—" },
                { label: "Buyer",      value: result.po.buyer      || "—" },
                { label: "Factory",    value: result.po.factory    || "—" },
                { label: "Total Qty",  value: result.po.total_qty ? `${result.po.total_qty.toLocaleString()} pcs` : "—" },
                { label: "Amount",     value: result.po.total_amount ? `$${result.po.total_amount.toLocaleString()}` : "—" },
                { label: "Style Name", value: result.po.style_name || "—" },
                { label: "Techpack",   value: result.techpack_found.length ? result.techpack_found.join(", ") : "Không tìm thấy" },
              ].map(({ label, value }) => (
                <div key={label} className="bg-gray-50 rounded-lg p-3">
                  <p className="text-xs text-gray-500 mb-0.5">{label}</p>
                  <p className="text-sm font-medium text-gray-900 truncate" title={value}>{value}</p>
                </div>
              ))}
            </div>
          </div>

          {/* Trimlist */}
          {result.trimlist && (
            <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
              <div className="px-5 py-3 border-b border-gray-200 flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <CheckCircle2 className="w-4 h-4 text-green-500" />
                  <h2 className="text-sm font-semibold text-gray-900">
                    Trim List — {result.trimlist.item_count} items
                  </h2>
                </div>
                <button
                  onClick={() => downloadAgentTrimlist(result.timestamp)}
                  className="flex items-center gap-1.5 text-sm text-indigo-600 hover:text-indigo-800 font-medium"
                >
                  <Download className="w-4 h-4" /> Download Trimlist Excel
                </button>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="bg-gray-50">
                    <tr>
                      {["#", "Trim Item", "Spec", "Supplier", "Code", "Qty/Pc", "Unit", "Total Qty"].map(h => (
                        <th key={h} className="text-left px-4 py-2.5 text-xs font-medium text-gray-500 uppercase tracking-wide whitespace-nowrap">{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-100">
                    {result.trimlist.trim_items.map((item, i) => (
                      <tr key={i} className="hover:bg-gray-50">
                        <td className="px-4 py-2.5 text-gray-400 text-xs">{i + 1}</td>
                        <td className="px-4 py-2.5 font-medium text-gray-900 whitespace-nowrap">{item.trim_item}</td>
                        <td className="px-4 py-2.5 text-gray-500 text-xs max-w-48 truncate">{item.spec || "—"}</td>
                        <td className="px-4 py-2.5 text-gray-700 whitespace-nowrap">{item.supplier || "—"}</td>
                        <td className="px-4 py-2.5 font-mono text-xs text-gray-500">{item.supplier_code || "—"}</td>
                        <td className="px-4 py-2.5 text-right">{item.qty_per_garment}</td>
                        <td className="px-4 py-2.5 text-gray-500">{item.unit}</td>
                        <td className="px-4 py-2.5 text-right font-medium">
                          {item.total_qty ? item.total_qty.toLocaleString() : "—"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
