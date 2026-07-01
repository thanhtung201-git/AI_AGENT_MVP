import Link from "next/link";
import { FileText, Scissors, History, ArrowRight } from "lucide-react";

const cards = [
  {
    href:        "/po",
    icon:        FileText,
    title:       "Process PO",
    description: "Upload file Purchase Order (PDF/Excel) → AI tự động trích xuất header, items, lưu Supabase.",
    color:       "bg-blue-50 text-blue-600",
    border:      "hover:border-blue-300",
  },
  {
    href:        "/trimlist",
    icon:        Scissors,
    title:       "Trim List",
    description: "Upload Tech Pack → AI đọc Section 16 'Expected Trim List' → tạo file Excel trimlist chuẩn.",
    color:       "bg-indigo-50 text-indigo-600",
    border:      "hover:border-indigo-300",
  },
  {
    href:        "/history",
    icon:        History,
    title:       "History",
    description: "Xem lịch sử PO đã xử lý từ Supabase và danh sách trimlist đã tạo.",
    color:       "bg-green-50 text-green-600",
    border:      "hover:border-green-300",
  },
];

export default function Dashboard() {
  return (
    <div className="p-8 max-w-4xl mx-auto">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-gray-900">AI Agent MVP</h1>
        <p className="text-gray-500 mt-1 text-sm">
          Tự động hóa quy trình xử lý Purchase Order và Trim List cho ngành may mặc
        </p>
      </div>

      {/* Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-10">
        {cards.map(({ href, icon: Icon, title, description, color, border }) => (
          <Link
            key={href}
            href={href}
            className={`group block bg-white rounded-xl border border-gray-200 p-5 transition-all hover:shadow-md ${border}`}
          >
            <div className={`w-10 h-10 rounded-lg ${color} flex items-center justify-center mb-3`}>
              <Icon className="w-5 h-5" />
            </div>
            <h2 className="font-semibold text-gray-900 mb-1">{title}</h2>
            <p className="text-sm text-gray-500 leading-relaxed">{description}</p>
            <div className="flex items-center gap-1 mt-3 text-xs font-medium text-gray-400 group-hover:text-gray-600 transition-colors">
              Bắt đầu <ArrowRight className="w-3 h-3" />
            </div>
          </Link>
        ))}
      </div>

      {/* Workflow */}
      <div className="bg-white rounded-xl border border-gray-200 p-5">
        <h3 className="text-sm font-semibold text-gray-900 mb-4">Luồng xử lý</h3>
        <div className="flex items-center gap-3 flex-wrap">
          {["1. Upload PO", "2. AI Extract", "3. Lưu Supabase", "4. Upload Techpack", "5. AI Trim Extract", "6. Export Excel"].map(
            (step, i) => (
              <div key={i} className="flex items-center gap-2">
                <span className="bg-gray-100 text-gray-700 text-xs px-3 py-1 rounded-full">{step}</span>
                {i < 5 && <ArrowRight className="w-3 h-3 text-gray-400 flex-shrink-0" />}
              </div>
            )
          )}
        </div>
      </div>
    </div>
  );
}
