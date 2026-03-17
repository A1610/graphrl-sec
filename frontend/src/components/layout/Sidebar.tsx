"use client";

/**
 * Sidebar — left-hand navigation for the SOC dashboard.
 *
 * Highlights the active route using Next.js `usePathname()`.
 * Uses semantic <nav> with aria-label for accessibility.
 */

import Link from "next/link";
import { usePathname } from "next/navigation";

import {
  Activity,
  AlertTriangle,
  BarChart2,
  Network,
  ShieldAlert,
} from "lucide-react";

import { cn } from "@/lib/utils";

interface NavItem {
  href: string;
  label: string;
  icon: React.ReactNode;
}

const NAV_ITEMS: NavItem[] = [
  {
    href: "/",
    label: "Dashboard",
    icon: <Activity size={18} aria-hidden="true" />,
  },
  {
    href: "/alerts",
    label: "Alerts",
    icon: <AlertTriangle size={18} aria-hidden="true" />,
  },
  {
    href: "/graph",
    label: "Graph Explorer",
    icon: <Network size={18} aria-hidden="true" />,
  },
  {
    href: "/analytics",
    label: "Analytics",
    icon: <BarChart2 size={18} aria-hidden="true" />,
  },
];

export default function Sidebar(): React.ReactElement {
  const pathname = usePathname();

  const isActive = (href: string): boolean =>
    href === "/" ? pathname === "/" : pathname.startsWith(href);

  return (
    <aside
      className="flex h-screen w-60 flex-col border-r border-[#30363d] bg-[#161b22]"
      aria-label="Primary navigation"
    >
      {/* Brand */}
      <div className="flex items-center gap-2 border-b border-[#30363d] px-5 py-4">
        <ShieldAlert
          size={22}
          className="shrink-0 text-[#58a6ff]"
          aria-hidden="true"
        />
        <span className="text-sm font-semibold tracking-wide text-[#e6edf3]">
          GraphRL-Sec
        </span>
      </div>

      {/* Navigation */}
      <nav className="flex flex-1 flex-col gap-1 px-3 py-4">
        <p className="mb-1 px-2 text-[10px] font-semibold uppercase tracking-widest text-[#8b949e]">
          SOC Dashboard
        </p>
        {NAV_ITEMS.map((item) => (
          <Link
            key={item.href}
            href={item.href}
            className={cn(
              "flex items-center gap-3 rounded-md px-3 py-2 text-sm transition-colors",
              isActive(item.href)
                ? "bg-[#58a6ff]/10 text-[#58a6ff]"
                : "text-[#8b949e] hover:bg-[#30363d]/60 hover:text-[#e6edf3]",
            )}
            aria-current={isActive(item.href) ? "page" : undefined}
          >
            {item.icon}
            {item.label}
          </Link>
        ))}
      </nav>

      {/* Footer */}
      <div className="border-t border-[#30363d] px-5 py-3">
        <p className="text-[11px] text-[#8b949e]">
          Dissertation © 2026
        </p>
      </div>
    </aside>
  );
}
