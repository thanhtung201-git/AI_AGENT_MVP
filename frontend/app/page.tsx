"use client";
import { useState, useEffect } from "react";
import Link from "next/link";
import {
  FileText, Scissors, ClipboardCheck, ArrowRight,
  CheckCircle2, AlertTriangle, XCircle, Clock,
  TrendingUp, Package, Download, RefreshCw, Loader2,
} from "lucide-react";
import api, { downloadAgentPO, downloadAgentTrimlist } from "@/lib/api";

interface Overview {
  total_files:      number;
  processed:        number;
  success:          number;
  partial:          number;
  failed:           number;
  pending:          number;
  total_trim_items: number;
  total_qty:        number;
  trimlist_files:   number;
}

interface DayActivity {
  date:  string;
  count: number;
}

interface RecentFile {
  filename:     string;
  processed_at: string;
  status:       "success" | "partial" | "error";
  po_number:    string;
  style_code:   string;
  total_qty:    number;
  trim_count:   number;
  timestamp:    string;
}

interface DashboardData {
  overview:        Overview;
  activity_7days:  DayActivity[];
  recent_files:    RecentFile[];
}

export default function Dashboard() {
  const [data,    setData]    = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);

  const load = async () => {
    setLoading(true);
    try {
      const { data: d } = await api.get<DashboardData>("/api/dashboard/stats");
      setData(d);
    } catch {
      // backend chua chay — show empty state
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const maxCount = data ? Math.max(...data.activity_7days.map(d => d.count), 1) : 1;

  return (
    <div className="p-8 max-w-5xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Dashboard</h1>
          <p className="text-sm text-gray-500 mt-0.5">
            Tong quan he thong xu ly PO tu dong
          </p>
        </div>
        <button
          onClick={load}
          disabled={loading}
          className="flex items-center gap-2 px-3 py-1.5 text-sm text-gray-600 bg-white border border-gray-200 rounded-lg hover:bg-gray-50 disabled:opacity-50"
        >
          {loading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <RefreshCw className="w-3.5 h-3.5" />}
          Lam moi
        </button>
      </div>

      {loading && !data && (
        <div className="flex items-center justify-center py-20">
          <Loader2 className="w-6 h-6 animate-spin text-indigo-500" />
        </div>
      )}

      {data && (
        <>
          {/* KPI cards */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
            <KpiCard
              label="Tong file PO"
              value={data.overview.total_files}
              icon={<FileText className="w-4 h-4" />}
              color="blue"
            />
            <KpiCard
              label="Xu ly thanh cong"
              value={data.overview.success}
              icon={<CheckCircle2 className="w-4 h-4" />}
              color="green"
              sub={data.overview.partial > 0 ? `+ ${data.overview.partial} mot phan` : undefined}
            />
            <KpiCard
              label="Tong Trim Items"
              value={data.overview.total_trim_items}
              icon={<Scissors className="w-4 h-4" />}
              color="indigo"
            />
            <KpiCard
              label="Tong so luong"
              value={data.overview.total_qty.toLocaleString()}
              icon={<Package className="w-4 h-4" />}
              color="purple"
              sub="pcs"
            />
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-5 mb-6">
            {/* Activity chart */}
            <div className="md:col-span-2 bg-white rounded-xl border border-gray-200 p-5">
              <div className="flex items-center gap-2 mb-4">
                <TrendingUp className="w-4 h-4 text-indigo-500" />
                <h2 className="text-sm font-semibold text-gray-900">Hoat dong 7 ngay qua</h2>
              </div>
              <div className="flex items-end gap-2 h-32">
                {data.activity_7days.map((d) => (
                  <div key={d.date} className="flex-1 flex flex-col items-center gap-1">
                    <span className="text-xs text-gray-500">{d.count > 0 ? d.count : ""}</span>
                    <div
                      className="w-full rounded-t-md bg-indigo-500 transition-all"
                      style={{
                        height: `${d.count === 0 ? 4 : Math.max(8, (d.count / maxCount) * 96)}px`,
                        opacity: d.count === 0 ? 0.15 : 1,
                      }}
                    />
                    <span className="text-[10px] text-gray-400">{d.date}</span>
                  </div>
                ))}
              </div>
            </div>

            {/* Status breakdown */}
            <div className="bg-white rounded-xl border border-gray-200 p-5">
              <h2 className="text-sm font-semibold text-gray-900 mb-4">Trang thai xu ly</h2>
              <div className="space-y-3">
                <StatusRow
                  icon={<CheckCircle2 className="w-4 h-4 text-green-500" />}
                  label="Thanh cong"
                  count={data.overview.success}
                  total={data.overview.processed}
                  color="bg-green-500"
                />
                <StatusRow
                  icon={<AlertTriangle className="w-4 h-4 text-amber-500" />}
                  label="Mot phan"
                  count={data.overview.partial}
                  total={data.overview.processed}
                  color="bg-amber-400"
                />
                <StatusRow
                  icon={<XCircle className="w-4 h-4 text-red-500" />}
                  label="Loi"
                  count={data.overview.failed}
                  total={data.overview.processed}
                  color="bg-red-400"
                />
                <StatusRow
                  icon={<Clock className="w-4 h-4 text-gray-400" />}
                  label="Chua xu ly"
                  count={data.overview.pending}
                  total={data.overview.total_files}
                  color="bg-gray-300"
                />
              </div>
            </div>
          </div>

          {/* Recent files */}
          {data.recent_files.length > 0 && (
            <div className="bg-white rounded-xl border border-gray-200 overflow-hidden mb-6">
              <div className="px-5 py-3 border-b border-gray-200 flex items-center justify-between">
                <h2 className="text-sm font-semibold text-gray-900">File xu ly gan day</h2>
                <Link href="/trimlist" className="text-xs text-indigo-600 hover:text-indigo-800">
                  Xem tat ca
                </Link>
              </div>
              <table className="w-full text-sm">
                <thead className="bg-gray-50">
                  <tr>
                    {["File", "PO Number", "Style", "Qty", "Trim", "Luc", "TT", ""].map(h => (
                      <th key={h} className="text-left px-4 py-2.5 text-xs font-medium text-gray-500 uppercase tracking-wide whitespace-nowrap">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {data.recent_files.map((f) => (
                    <tr key={f.filename} className="hover:bg-gray-50">
                      <td className="px-4 py-2.5 font-mono text-xs text-gray-700 max-w-40 truncate" title={f.filename}>{f.filename}</td>
                      <td className="px-4 py-2.5 text-xs">{f.po_number || "—"}</td>
                      <td className="px-4 py-2.5 text-xs font-mono">{f.style_code || "—"}</td>
                      <td className="px-4 py-2.5 text-xs text-right">{f.total_qty ? f.total_qty.toLocaleString() : "—"}</td>
                      <td className="px-4 py-2.5 text-xs text-right">{f.trim_count ? `${f.trim_count}` : "—"}</td>
                      <td className="px-4 py-2.5 text-xs text-gray-400 whitespace-nowrap">{f.processed_at.slice(0, 16)}</td>
                      <td className="px-4 py-2.5"><MiniStatus status={f.status} /></td>
                      <td className="px-4 py-2.5">
                        {f.timestamp && (
                          <div className="flex items-center gap-2">
                            <button onClick={() => downloadAgentPO(f.timestamp)}
                              className="text-xs text-indigo-600 hover:text-indigo-800 flex items-center gap-1">
                              <Download className="w-3 h-3" />PO
                            </button>
                            {!!f.trim_count && (
                              <button onClick={() => downloadAgentTrimlist(f.timestamp)}
                                className="text-xs text-green-600 hover:text-green-800 flex items-center gap-1">
                                <Download className="w-3 h-3" />TL
                              </button>
                            )}
                          </div>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {/* Quick nav */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {[
              { href: "/po",     icon: FileText,        color: "bg-blue-50 text-blue-600",   border: "hover:border-blue-300",   title: "Process PO",   desc: "Upload file PO moi de AI xu ly" },
              { href: "/trimlist", icon: Scissors,      color: "bg-indigo-50 text-indigo-600", border: "hover:border-indigo-300", title: "Trim List",    desc: "Xem ket qua va quet file moi" },
              { href: "/recap",  icon: ClipboardCheck,  color: "bg-purple-50 text-purple-600", border: "hover:border-purple-300", title: "Recap Order",  desc: "Doi chieu don dat hang voi trimlist" },
            ].map(({ href, icon: Icon, color, border, title, desc }) => (
              <Link key={href} href={href}
                className={`group bg-white rounded-xl border border-gray-200 p-4 transition-all hover:shadow-md ${border}`}>
                <div className={`w-9 h-9 rounded-lg ${color} flex items-center justify-center mb-3`}>
                  <Icon className="w-4 h-4" />
                </div>
                <p className="font-semibold text-gray-900 text-sm mb-0.5">{title}</p>
                <p className="text-xs text-gray-500">{desc}</p>
                <div className="flex items-center gap-1 mt-3 text-xs text-gray-400 group-hover:text-gray-600">
                  Mo <ArrowRight className="w-3 h-3" />
                </div>
              </Link>
            ))}
          </div>
        </>
      )}

      {/* Empty state khi backend chua chay */}
      {!loading && !data && (
        <div className="bg-white rounded-xl border border-dashed border-gray-300 p-12 text-center">
          <FileText className="w-10 h-10 text-gray-300 mx-auto mb-3" />
          <p className="text-gray-500 font-medium">Chua ket noi duoc Backend</p>
          <p className="text-sm text-gray-400 mt-1">Khoi dong backend roi lam moi trang</p>
        </div>
      )}
    </div>
  );
}

function KpiCard({ label, value, icon, color, sub }: {
  label: string; value: number | string; icon: React.ReactNode;
  color: "blue" | "green" | "indigo" | "purple"; sub?: string;
}) {
  const colors = {
    blue:   "bg-blue-50 text-blue-600",
    green:  "bg-green-50 text-green-600",
    indigo: "bg-indigo-50 text-indigo-600",
    purple: "bg-purple-50 text-purple-600",
  };
  return (
    <div className="bg-white rounded-xl border border-gray-200 p-4">
      <div className={`w-8 h-8 rounded-lg ${colors[color]} flex items-center justify-center mb-3`}>
        {icon}
      </div>
      <p className="text-2xl font-bold text-gray-900">{value}</p>
      {sub && <p className="text-xs text-gray-400">{sub}</p>}
      <p className="text-xs text-gray-500 mt-0.5">{label}</p>
    </div>
  );
}

function StatusRow({ icon, label, count, total, color }: {
  icon: React.ReactNode; label: string; count: number; total: number; color: string;
}) {
  const pct = total > 0 ? Math.round((count / total) * 100) : 0;
  return (
    <div>
      <div className="flex items-center justify-between mb-1">
        <div className="flex items-center gap-1.5">
          {icon}
          <span className="text-xs text-gray-700">{label}</span>
        </div>
        <span className="text-xs font-medium text-gray-900">{count}</span>
      </div>
      <div className="h-1.5 bg-gray-100 rounded-full overflow-hidden">
        <div className={`h-full ${color} rounded-full transition-all`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

function MiniStatus({ status }: { status: string }) {
  if (status === "success")
    return <span className="inline-flex px-2 py-0.5 rounded-full text-xs bg-green-100 text-green-700">Xong</span>;
  if (status === "partial")
    return <span className="inline-flex px-2 py-0.5 rounded-full text-xs bg-amber-100 text-amber-700">1 phan</span>;
  return <span className="inline-flex px-2 py-0.5 rounded-full text-xs bg-red-100 text-red-700">Loi</span>;
}
