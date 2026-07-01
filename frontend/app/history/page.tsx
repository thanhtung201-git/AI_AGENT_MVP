"use client";
import { useEffect, useState } from "react";
import { getPOHistory, getTrimlistHistory, downloadTrimlist, type POHistory, type TrimlistHistory } from "@/lib/api";
import { Download, RefreshCw, FileText, Scissors } from "lucide-react";
import toast from "react-hot-toast";

export default function HistoryPage() {
  const [poList,       setPoList]       = useState<POHistory[]>([]);
  const [trimList,     setTrimList]     = useState<TrimlistHistory[]>([]);
  const [loadingPO,    setLoadingPO]    = useState(true);
  const [loadingTrim,  setLoadingTrim]  = useState(true);
  const [tab,          setTab]          = useState<"po" | "trimlist">("po");

  async function loadAll() {
    setLoadingPO(true); setLoadingTrim(true);
    try {
      const po = await getPOHistory();
      setPoList(po);
    } catch { toast.error("Không lấy được lịch sử PO"); }
    finally { setLoadingPO(false); }

    try {
      const trim = await getTrimlistHistory();
      setTrimList(trim);
    } catch { toast.error("Không lấy được lịch sử Trimlist"); }
    finally { setLoadingTrim(false); }
  }

  useEffect(() => { loadAll(); }, []);

  return (
    <div className="p-8 max-w-5xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-xl font-bold text-gray-900">History</h1>
          <p className="text-sm text-gray-500 mt-0.5">Lịch sử xử lý PO và Trim List</p>
        </div>
        <button onClick={loadAll} className="flex items-center gap-2 text-sm text-gray-600 hover:text-gray-900 border border-gray-300 rounded-lg px-3 py-1.5 hover:bg-gray-50">
          <RefreshCw className="w-4 h-4" /> Refresh
        </button>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 mb-4 bg-gray-100 p-1 rounded-lg w-fit">
        {(["po", "trimlist"] as const).map(t => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`flex items-center gap-2 px-4 py-1.5 rounded-md text-sm font-medium transition-colors ${
              tab === t ? "bg-white text-gray-900 shadow-sm" : "text-gray-500 hover:text-gray-700"
            }`}
          >
            {t === "po" ? <FileText className="w-4 h-4" /> : <Scissors className="w-4 h-4" />}
            {t === "po" ? `Purchase Orders (${poList.length})` : `Trim Lists (${trimList.length})`}
          </button>
        ))}
      </div>

      {/* PO Table */}
      {tab === "po" && (
        <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
          {loadingPO ? (
            <div className="p-10 text-center text-sm text-gray-400">Đang tải...</div>
          ) : poList.length === 0 ? (
            <div className="p-10 text-center text-sm text-gray-400">Chưa có PO nào được xử lý</div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="bg-gray-50">
                  <tr>
                    {["PO Number", "Buyer", "Order Date", "Delivery Date", "Total Qty", "Total Amount", "Created"].map(h => (
                      <th key={h} className="text-left px-4 py-2.5 text-xs font-medium text-gray-500 uppercase tracking-wide whitespace-nowrap">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {poList.map((po) => (
                    <tr key={po.id} className="hover:bg-gray-50">
                      <td className="px-4 py-3 font-mono text-xs font-medium text-indigo-600">{po.po_number || "—"}</td>
                      <td className="px-4 py-3">{po.buyer || "—"}</td>
                      <td className="px-4 py-3 text-gray-500">{po.order_date || "—"}</td>
                      <td className="px-4 py-3 text-gray-500">{po.delivery_date || "—"}</td>
                      <td className="px-4 py-3 text-right">{po.total_quantity?.toLocaleString() || "—"}</td>
                      <td className="px-4 py-3 text-right">{po.total_amount ? `$${po.total_amount.toLocaleString()}` : "—"}</td>
                      <td className="px-4 py-3 text-gray-400 text-xs">{po.created_at ? new Date(po.created_at).toLocaleString("vi-VN") : "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* Trimlist Table */}
      {tab === "trimlist" && (
        <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
          {loadingTrim ? (
            <div className="p-10 text-center text-sm text-gray-400">Đang tải...</div>
          ) : trimList.length === 0 ? (
            <div className="p-10 text-center text-sm text-gray-400">Chưa có Trim List nào được tạo</div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="bg-gray-50">
                  <tr>
                    {["File", "Created At", "Size", "Download"].map(h => (
                      <th key={h} className="text-left px-4 py-2.5 text-xs font-medium text-gray-500 uppercase tracking-wide">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {trimList.map((t) => (
                    <tr key={t.timestamp} className="hover:bg-gray-50">
                      <td className="px-4 py-3 font-mono text-xs">{t.filename}</td>
                      <td className="px-4 py-3 text-gray-500">{t.created_at}</td>
                      <td className="px-4 py-3 text-gray-500">{t.size_kb} KB</td>
                      <td className="px-4 py-3">
                        <button
                          onClick={() => downloadTrimlist(t.timestamp)}
                          className="flex items-center gap-1.5 text-sm text-indigo-600 hover:text-indigo-800 font-medium"
                        >
                          <Download className="w-4 h-4" /> Download
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
