"use client";
import { useState, useCallback } from "react";
import { useDropzone } from "react-dropzone";
import toast from "react-hot-toast";
import { Upload, FileText, Download, Loader2, CheckCircle2, XCircle } from "lucide-react";
import { processPO, downloadPO, type POResult } from "@/lib/api";

export default function POPage() {
  const [file, setFile]       = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [result, setResult]   = useState<POResult | null>(null);
  const [error, setError]     = useState<string | null>(null);

  const onDrop = useCallback((accepted: File[]) => {
    if (accepted[0]) {
      setFile(accepted[0]);
      setResult(null);
      setError(null);
    }
  }, []);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: { "application/pdf": [".pdf"], "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": [".xlsx"] },
    maxFiles: 1,
  });

  async function handleProcess() {
    if (!file) return;
    setLoading(true);
    setError(null);
    try {
      const res = await processPO(file);
      setResult(res);
      toast.success(`Trích xuất thành công — ${res.item_count} items`);
    } catch (e: unknown) {
      const msg = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail || "Lỗi không xác định";
      setError(msg);
      toast.error(msg);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="p-8 max-w-5xl mx-auto">
      <h1 className="text-xl font-bold text-gray-900 mb-1">Process Purchase Order</h1>
      <p className="text-sm text-gray-500 mb-6">Upload file PO → AI trích xuất tự động → Export Excel</p>

      {/* Dropzone */}
      <div
        {...getRootProps()}
        className={`border-2 border-dashed rounded-xl p-10 text-center cursor-pointer transition-colors mb-4 ${
          isDragActive ? "border-indigo-400 bg-indigo-50" : "border-gray-300 hover:border-gray-400 bg-white"
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
            <p className="text-sm text-gray-400 mt-1">hoặc click để chọn file (.pdf, .xlsx)</p>
          </div>
        )}
      </div>

      <button
        onClick={handleProcess}
        disabled={!file || loading}
        className="w-full py-2.5 px-4 bg-indigo-600 text-white rounded-lg font-medium text-sm disabled:opacity-50 disabled:cursor-not-allowed hover:bg-indigo-700 transition-colors flex items-center justify-center gap-2"
      >
        {loading ? <><Loader2 className="w-4 h-4 animate-spin" />Đang xử lý...</> : "Chạy AI Agent"}
      </button>

      {/* Error */}
      {error && (
        <div className="mt-4 p-4 bg-red-50 border border-red-200 rounded-lg flex items-start gap-3">
          <XCircle className="w-5 h-5 text-red-500 flex-shrink-0 mt-0.5" />
          <p className="text-sm text-red-700">{error}</p>
        </div>
      )}

      {/* Result */}
      {result && (
        <div className="mt-6 space-y-4">
          {/* Summary */}
          <div className="bg-white rounded-xl border border-gray-200 p-5">
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-2">
                <CheckCircle2 className="w-5 h-5 text-green-500" />
                <h2 className="font-semibold text-gray-900">Kết quả trích xuất</h2>
              </div>
              <button
                onClick={() => downloadPO(result.timestamp)}
                className="flex items-center gap-2 text-sm text-indigo-600 hover:text-indigo-800 font-medium"
              >
                <Download className="w-4 h-4" /> Download Excel
              </button>
            </div>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              {[
                { label: "PO Number",   value: result.po_number  || "—" },
                { label: "Style Code",  value: result.style_code || "—" },
                { label: "Buyer",       value: result.buyer      || "—" },
                { label: "Factory",     value: result.factory    || "—" },
                { label: "Total Qty",   value: result.total_qty ? `${result.total_qty.toLocaleString()} pcs` : "—" },
                { label: "Total Amount",value: result.total_amount ? `$${result.total_amount.toLocaleString()}` : "—" },
                { label: "Style Name",  value: result.style_name || "—" },
                { label: "Items",       value: `${result.item_count} dòng` },
              ].map(({ label, value }) => (
                <div key={label} className="bg-gray-50 rounded-lg p-3">
                  <p className="text-xs text-gray-500 mb-0.5">{label}</p>
                  <p className="text-sm font-medium text-gray-900 truncate">{value}</p>
                </div>
              ))}
            </div>
          </div>

          {/* Items Table */}
          <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
            <div className="px-5 py-3 border-b border-gray-200">
              <h3 className="text-sm font-semibold text-gray-900">Chi tiết items ({result.items.length})</h3>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="bg-gray-50">
                  <tr>
                    {["Style Code", "Style Name", "Color", "Qty", "Unit Price", "Total"].map(h => (
                      <th key={h} className="text-left px-4 py-2.5 text-xs font-medium text-gray-500 uppercase tracking-wide">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {result.items.map((item, i) => (
                    <tr key={i} className="hover:bg-gray-50">
                      <td className="px-4 py-2.5 font-mono text-xs">{item.style_code || "—"}</td>
                      <td className="px-4 py-2.5">{item.style_name || "—"}</td>
                      <td className="px-4 py-2.5">{item.color_name || "—"}</td>
                      <td className="px-4 py-2.5 text-right">{item.total_quantity?.toLocaleString() || "—"}</td>
                      <td className="px-4 py-2.5 text-right">${item.unit_price?.toFixed(2) || "—"}</td>
                      <td className="px-4 py-2.5 text-right font-medium">${item.total_price?.toLocaleString() || "—"}</td>
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
