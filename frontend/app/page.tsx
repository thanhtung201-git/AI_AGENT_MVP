"use client";
import { useState, useEffect } from "react";
import Link from "next/link";
import {
  GitCompare, Scissors, ArrowRight, AlertTriangle, CheckCircle2,
  RefreshCw, Loader2, ListChecks, Percent, Activity,
} from "lucide-react";
import api from "@/lib/api";

// ── Types ─────────────────────────────────────────────────────────────────────

interface RunA {
  at: string; status: string; match_rate: number | null; rows: number;
  mismatched: number; errors: number; warnings: number;
  po_total: number; go_total: number; qty_diff: number; po_number: string;
}
interface RunB {
  at: string; style_code: string; branch: string; branch_conf: string;
  item_count: number; complete_items: number; incomplete_items: number;
  complete_rate: number | null; errors: number; warnings: number;
  missing: Record<string, number>; recovered: number;
}
interface TrendPoint { at: string; value: number }
interface QueueItem { task: "A" | "B"; at: string; ref: string; headline: string; errors: number; link: string }

interface TaskDash {
  kpi: { runs_a: number; runs_b: number; avg_match: number | null; avg_complete: number | null; open_issues: number };
  task_a: { latest: RunA | null; trend: TrendPoint[] };
  task_b: { latest: RunB | null; trend: TrendPoint[]; missing: Record<string, number> };
  queue: QueueItem[];
}

const MISSING_LABEL: Record<string, string> = {
  missing_code:      "Mã vật liệu",
  missing_supplier:  "Nhà cung cấp",
  missing_spec:      "Spec",
  missing_placement: "Vị trí",
};

// ── Page ─────────────────────────────────────────────────────────────────────

export default function Dashboard() {
  const [data, setData]       = useState<TaskDash | null>(null);
  const [loading, setLoading] = useState(true);

  const load = async () => {
    setLoading(true);
    try {
      const { data: d } = await api.get<TaskDash>("/api/dashboard/tasks");
      setData(d);
    } catch {
      // backend chưa chạy — hiện empty state
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => { load(); }, []);

  const a = data?.task_a.latest;
  const b = data?.task_b.latest;

  return (
    <div className="p-8 max-w-6xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Dashboard</h1>
          <p className="text-sm text-gray-500 mt-0.5">
            Tổng quan PO ↔ GO Compare và Trimlist
          </p>
        </div>
        <button onClick={load} disabled={loading}
          className="flex items-center gap-2 px-3 py-1.5 text-sm text-gray-600 bg-white border border-gray-200 rounded-lg hover:bg-gray-50 disabled:opacity-50">
          {loading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <RefreshCw className="w-3.5 h-3.5" />}
          Làm mới
        </button>
      </div>

      {loading && !data && (
        <div className="flex items-center justify-center py-20">
          <Loader2 className="w-6 h-6 animate-spin text-indigo-500" />
        </div>
      )}

      {data && (
        <>
          {/* KPI */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
            <Kpi label="Tỷ lệ khớp PO↔GO" value={pct(data.kpi.avg_match)}
                 icon={<Percent className="w-4 h-4" />} tone="indigo" sub="trung bình" />
            <Kpi label="Độ hoàn chỉnh Trimlist" value={pct(data.kpi.avg_complete)}
                 icon={<CheckCircle2 className="w-4 h-4" />} tone="green" sub="trung bình" />
            <Kpi label="Lượt chạy" value={`${data.kpi.runs_a + data.kpi.runs_b}`}
                 icon={<Activity className="w-4 h-4" />} tone="blue"
                 sub={`A: ${data.kpi.runs_a} · B: ${data.kpi.runs_b}`} />
            <Kpi label="Việc cần xử lý" value={`${data.kpi.open_issues}`}
                 icon={<AlertTriangle className="w-4 h-4" />}
                 tone={data.kpi.open_issues > 0 ? "amber" : "green"} sub="lượt cần rà" />
          </div>

          {/* 2 task cards */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-5 mb-6">
            {/* Task A */}
            <Panel title="PO ↔ GO Compare" href="/task-a"
                   icon={<GitCompare className="w-4 h-4 text-indigo-600" />}>
              {a ? (
                <>
                  <div className="flex items-baseline gap-3 mb-3">
                    <span className="text-3xl font-bold text-gray-900">{pct(a.match_rate)}</span>
                    <StatusPill status={a.status} />
                  </div>
                  <div className="grid grid-cols-3 gap-2 mb-4">
                    <Stat label="Dòng lệch" value={a.mismatched} warn={a.mismatched > 0} />
                    <Stat label="Chênh qty" value={`${a.qty_diff > 0 ? "+" : ""}${a.qty_diff ?? 0}`} warn={!!a.qty_diff} />
                    <Stat label="Lỗi" value={a.errors} warn={a.errors > 0} />
                  </div>
                  <Trend points={data.task_a.trend} color="bg-indigo-500" />
                  <p className="text-[11px] text-gray-400 mt-2">
                    Gần nhất: {a.po_number || "—"} · {a.at?.slice(5, 16)}
                  </p>
                </>
              ) : <Empty text="Chưa có lượt chạy Task A" />}
            </Panel>

            {/* Task B */}
            <Panel title="Trimlist (Task B)" href="/task-b"
                   icon={<Scissors className="w-4 h-4 text-emerald-600" />}>
              {b ? (
                <>
                  <div className="flex items-baseline gap-3 mb-3">
                    <span className="text-3xl font-bold text-gray-900">{pct(b.complete_rate)}</span>
                    <span className="text-xs text-gray-500">
                      {b.complete_items}/{b.item_count} dòng đủ trường
                    </span>
                  </div>
                  <div className="grid grid-cols-3 gap-2 mb-4">
                    <Stat label="Thiếu" value={b.incomplete_items} warn={b.incomplete_items > 0} />
                    <Stat label="Thu hồi" value={b.recovered} warn={b.recovered > 0} />
                    <Stat label="Lỗi" value={b.errors} warn={b.errors > 0} />
                  </div>
                  <MissingBars missing={data.task_b.missing} total={b.item_count} />
                  <p className="text-[11px] text-gray-400 mt-2">
                    Gần nhất: {b.style_code || "—"} · nhánh {b.branch || "?"} · {b.at?.slice(5, 16)}
                  </p>
                </>
              ) : <Empty text="Chưa có lượt chạy Task B" />}
            </Panel>
          </div>

          {/* Action queue */}
          <div className="bg-white rounded-xl border border-gray-200 overflow-hidden mb-6">
            <div className="px-5 py-3 border-b border-gray-100 bg-gray-50 flex items-center gap-2">
              <ListChecks className="w-4 h-4 text-amber-600" />
              <h2 className="text-sm font-semibold text-gray-800">Hàng đợi cần xử lý</h2>
              <span className="text-xs text-gray-400">({data.queue.length})</span>
            </div>
            {data.queue.length === 0 ? (
              <div className="px-5 py-8 text-center text-sm text-gray-400">
                <CheckCircle2 className="w-6 h-6 text-green-400 mx-auto mb-2" />
                Không có việc tồn — mọi lượt chạy đều ổn.
              </div>
            ) : (
              <table className="w-full text-sm">
                <tbody className="divide-y divide-gray-100">
                  {data.queue.map((q, i) => (
                    <tr key={i} className="hover:bg-gray-50">
                      <td className="px-4 py-2.5 w-16">
                        <span className={`text-[10px] font-semibold px-2 py-0.5 rounded ${
                          q.task === "A" ? "bg-indigo-100 text-indigo-700" : "bg-emerald-100 text-emerald-700"}`}>
                          Task {q.task}
                        </span>
                      </td>
                      <td className="px-3 py-2.5 font-mono text-xs text-gray-700">{q.ref || "—"}</td>
                      <td className="px-3 py-2.5 text-xs text-gray-600">{q.headline}</td>
                      <td className="px-3 py-2.5 text-xs text-gray-400 whitespace-nowrap">{q.at?.slice(5, 16)}</td>
                      <td className="px-4 py-2.5 text-right">
                        <Link href={q.link} className="text-xs text-indigo-600 hover:text-indigo-800 inline-flex items-center gap-1">
                          Mở <ArrowRight className="w-3 h-3" />
                        </Link>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>

          {/* Quick nav */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <NavCard href="/task-a" icon={<GitCompare className="w-4 h-4" />} tone="bg-indigo-50 text-indigo-600"
                     title="PO ↔ GO Compare" desc="Tạo Batch GO từ PO và đối chiếu" />
            <NavCard href="/task-b" icon={<Scissors className="w-4 h-4" />} tone="bg-emerald-50 text-emerald-600"
                     title="Trimlist" desc="Tech Pack + Trim Master → Trimlist" />
          </div>
        </>
      )}

      {!loading && !data && (
        <div className="bg-white rounded-xl border border-dashed border-gray-300 p-12 text-center">
          <Activity className="w-10 h-10 text-gray-300 mx-auto mb-3" />
          <p className="text-gray-500 font-medium">Chưa kết nối được Backend</p>
          <p className="text-sm text-gray-400 mt-1">Khởi động backend rồi làm mới trang</p>
        </div>
      )}
    </div>
  );
}

// ── Bits ──────────────────────────────────────────────────────────────────────

const pct = (v: number | null | undefined) => (v === null || v === undefined ? "—" : `${v}%`);

function Kpi({ label, value, icon, tone, sub }: {
  label: string; value: string; icon: React.ReactNode;
  tone: "indigo" | "green" | "blue" | "amber"; sub?: string;
}) {
  const tones = {
    indigo: "bg-indigo-50 text-indigo-600",
    green:  "bg-green-50 text-green-600",
    blue:   "bg-blue-50 text-blue-600",
    amber:  "bg-amber-50 text-amber-600",
  };
  return (
    <div className="bg-white rounded-xl border border-gray-200 p-4">
      <div className={`w-8 h-8 rounded-lg ${tones[tone]} flex items-center justify-center mb-3`}>{icon}</div>
      <p className="text-2xl font-bold text-gray-900">{value}</p>
      {sub && <p className="text-[11px] text-gray-400">{sub}</p>}
      <p className="text-xs text-gray-500 mt-0.5">{label}</p>
    </div>
  );
}

function Panel({ title, href, icon, children }: {
  title: string; href: string; icon: React.ReactNode; children: React.ReactNode;
}) {
  return (
    <div className="bg-white rounded-xl border border-gray-200 p-5">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          {icon}
          <h2 className="text-sm font-semibold text-gray-900">{title}</h2>
        </div>
        <Link href={href} className="text-xs text-gray-400 hover:text-indigo-600 inline-flex items-center gap-1">
          Mở <ArrowRight className="w-3 h-3" />
        </Link>
      </div>
      {children}
    </div>
  );
}

function Stat({ label, value, warn }: { label: string; value: number | string; warn?: boolean }) {
  return (
    <div className={`rounded-lg border p-2 ${warn ? "border-amber-200 bg-amber-50/40" : "border-gray-200"}`}>
      <p className={`text-lg font-bold ${warn ? "text-amber-700" : "text-gray-900"}`}>{value}</p>
      <p className="text-[10px] text-gray-500">{label}</p>
    </div>
  );
}

function StatusPill({ status }: { status: string }) {
  const map: Record<string, [string, string]> = {
    OK:       ["KHỚP", "bg-green-100 text-green-700"],
    PARTIAL:  ["CẦN KIỂM TRA", "bg-amber-100 text-amber-700"],
    MISMATCH: ["SAI LỆCH", "bg-red-100 text-red-700"],
  };
  const [label, cls] = map[status] || ["—", "bg-gray-100 text-gray-500"];
  return <span className={`text-[10px] font-semibold px-2 py-0.5 rounded-full ${cls}`}>{label}</span>;
}

function Trend({ points, color }: { points: TrendPoint[]; color: string }) {
  if (!points.length) return <p className="text-[11px] text-gray-400">Chưa đủ dữ liệu để vẽ xu hướng</p>;
  return (
    <div>
      <p className="text-[10px] text-gray-400 mb-1">Xu hướng {points.length} lượt gần nhất</p>
      <div className="flex items-end gap-1 h-14">
        {points.map((p, i) => (
          <div key={i} className="flex-1 group relative" title={`${p.at}: ${p.value}%`}>
            <div className={`w-full rounded-t ${color}`}
                 style={{ height: `${Math.max(6, (p.value / 100) * 56)}px`, opacity: 0.85 }} />
          </div>
        ))}
      </div>
    </div>
  );
}

function MissingBars({ missing, total }: { missing: Record<string, number>; total: number }) {
  const entries = Object.entries(missing || {}).filter(([, v]) => v > 0)
    .sort((x, y) => y[1] - x[1]).slice(0, 4);
  if (!entries.length) return <p className="text-[11px] text-green-600">Không thiếu trường nào ✓</p>;
  return (
    <div className="space-y-1.5">
      <p className="text-[10px] text-gray-400">Thiếu nhiều nhất</p>
      {entries.map(([k, v]) => (
        <div key={k}>
          <div className="flex justify-between text-[11px] mb-0.5">
            <span className="text-gray-600">{MISSING_LABEL[k] || k}</span>
            <span className="text-gray-500 font-medium">{v}</span>
          </div>
          <div className="h-1.5 bg-gray-100 rounded-full overflow-hidden">
            <div className="h-full bg-amber-400 rounded-full"
                 style={{ width: `${total ? Math.min(100, (v / total) * 100) : 0}%` }} />
          </div>
        </div>
      ))}
    </div>
  );
}

function Empty({ text }: { text: string }) {
  return <p className="text-sm text-gray-400 py-6 text-center">{text}</p>;
}

function NavCard({ href, icon, tone, title, desc }: {
  href: string; icon: React.ReactNode; tone: string; title: string; desc: string;
}) {
  return (
    <Link href={href} className="group bg-white rounded-xl border border-gray-200 p-4 transition-all hover:shadow-md hover:border-indigo-300">
      <div className={`w-9 h-9 rounded-lg ${tone} flex items-center justify-center mb-3`}>{icon}</div>
      <p className="font-semibold text-gray-900 text-sm mb-0.5">{title}</p>
      <p className="text-xs text-gray-500">{desc}</p>
      <div className="flex items-center gap-1 mt-3 text-xs text-gray-400 group-hover:text-gray-600">
        Mở <ArrowRight className="w-3 h-3" />
      </div>
    </Link>
  );
}
