"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { FileText, List, History, Home, Scissors } from "lucide-react";

const nav = [
  { href: "/",          label: "Dashboard",   icon: Home       },
  { href: "/po",        label: "Process PO",  icon: FileText   },
  { href: "/trimlist",  label: "Trim List",   icon: Scissors   },
  { href: "/history",   label: "History",     icon: History    },
];

export default function Sidebar() {
  const pathname = usePathname();
  return (
    <aside className="w-56 bg-white border-r border-gray-200 flex flex-col">
      {/* Logo */}
      <div className="px-6 py-5 border-b border-gray-200">
        <div className="flex items-center gap-2">
          <div className="w-7 h-7 bg-indigo-600 rounded-md flex items-center justify-center">
            <List className="w-4 h-4 text-white" />
          </div>
          <div>
            <p className="text-sm font-bold text-gray-900 leading-tight">AI Agent</p>
            <p className="text-[10px] text-gray-400 leading-tight">Garment MVP</p>
          </div>
        </div>
      </div>

      {/* Nav */}
      <nav className="flex-1 px-3 py-4 space-y-1">
        {nav.map(({ href, label, icon: Icon }) => {
          const active = pathname === href;
          return (
            <Link
              key={href}
              href={href}
              className={`flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors ${
                active
                  ? "bg-indigo-50 text-indigo-700 font-medium"
                  : "text-gray-600 hover:bg-gray-100 hover:text-gray-900"
              }`}
            >
              <Icon className="w-4 h-4 flex-shrink-0" />
              {label}
            </Link>
          );
        })}
      </nav>

      {/* Footer */}
      <div className="px-4 py-3 border-t border-gray-200">
        <p className="text-[10px] text-gray-400 text-center">v1.0.0 — MVP</p>
      </div>
    </aside>
  );
}
