"use client";

/**
 * AlertTable — sortable, paginated alert table with severity badges.
 *
 * Columns: Severity | Source IP | Destination IP | Score | Protocol | Label | Actions
 *
 * Sorting is client-side over the current page data.
 * "View" action opens a detail panel (onSelectAlert callback).
 */

import { useState } from "react";
import { ArrowDown, ArrowUp, ArrowUpDown, Eye } from "lucide-react";

import { cn, formatScore, severityBadgeClass } from "@/lib/utils";
import type { AlertResponse, Severity } from "@/types/api";

type SortField = "score" | "src_ip" | "dst_ip" | "protocol" | "severity";
type SortDir = "asc" | "desc";

interface AlertTableProps {
  alerts: AlertResponse[];
  onSelectAlert?: (alert: AlertResponse) => void;
}

const SEVERITY_ORDER: Record<Severity, number> = {
  critical: 4,
  high: 3,
  medium: 2,
  low: 1,
};

function SortIcon({
  field,
  current,
  dir,
}: {
  field: SortField;
  current: SortField;
  dir: SortDir;
}): React.ReactElement {
  if (field !== current) {
    return <ArrowUpDown size={12} className="text-[#8b949e]" aria-hidden="true" />;
  }
  return dir === "asc"
    ? <ArrowUp size={12} className="text-[#58a6ff]" aria-hidden="true" />
    : <ArrowDown size={12} className="text-[#58a6ff]" aria-hidden="true" />;
}

export default function AlertTable({
  alerts,
  onSelectAlert,
}: AlertTableProps): React.ReactElement {
  const [sortField, setSortField] = useState<SortField>("score");
  const [sortDir, setSortDir] = useState<SortDir>("desc");

  const toggleSort = (field: SortField) => {
    if (sortField === field) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortField(field);
      setSortDir("desc");
    }
  };

  const sorted = [...alerts].sort((a, b) => {
    let cmp = 0;
    switch (sortField) {
      case "score":
        cmp = a.score - b.score;
        break;
      case "src_ip":
        cmp = a.src_ip.localeCompare(b.src_ip);
        break;
      case "dst_ip":
        cmp = a.dst_ip.localeCompare(b.dst_ip);
        break;
      case "protocol":
        cmp = a.protocol.localeCompare(b.protocol);
        break;
      case "severity":
        cmp = SEVERITY_ORDER[a.severity] - SEVERITY_ORDER[b.severity];
        break;
    }
    return sortDir === "asc" ? cmp : -cmp;
  });

  const thClass =
    "px-4 py-3 text-left text-[10px] font-semibold uppercase tracking-widest text-[#8b949e] select-none";
  const tdClass = "px-4 py-3 text-sm text-[#e6edf3] align-middle";

  return (
    <div className="overflow-x-auto rounded-lg border border-[#30363d]">
      <table className="w-full border-collapse" aria-label="Security alerts table">
        <thead>
          <tr className="border-b border-[#30363d] bg-[#0d1117]">
            <th
              scope="col"
              className={cn(thClass, "cursor-pointer")}
              onClick={() => toggleSort("severity")}
              aria-sort={sortField === "severity" ? (sortDir === "asc" ? "ascending" : "descending") : "none"}
            >
              <span className="flex items-center gap-1.5">
                Severity
                <SortIcon field="severity" current={sortField} dir={sortDir} />
              </span>
            </th>
            <th
              scope="col"
              className={cn(thClass, "cursor-pointer")}
              onClick={() => toggleSort("src_ip")}
              aria-sort={sortField === "src_ip" ? (sortDir === "asc" ? "ascending" : "descending") : "none"}
            >
              <span className="flex items-center gap-1.5">
                Source IP
                <SortIcon field="src_ip" current={sortField} dir={sortDir} />
              </span>
            </th>
            <th
              scope="col"
              className={cn(thClass, "cursor-pointer")}
              onClick={() => toggleSort("dst_ip")}
              aria-sort={sortField === "dst_ip" ? (sortDir === "asc" ? "ascending" : "descending") : "none"}
            >
              <span className="flex items-center gap-1.5">
                Destination IP
                <SortIcon field="dst_ip" current={sortField} dir={sortDir} />
              </span>
            </th>
            <th
              scope="col"
              className={cn(thClass, "cursor-pointer")}
              onClick={() => toggleSort("score")}
              aria-sort={sortField === "score" ? (sortDir === "asc" ? "ascending" : "descending") : "none"}
            >
              <span className="flex items-center gap-1.5">
                Score
                <SortIcon field="score" current={sortField} dir={sortDir} />
              </span>
            </th>
            <th
              scope="col"
              className={cn(thClass, "cursor-pointer")}
              onClick={() => toggleSort("protocol")}
              aria-sort={sortField === "protocol" ? (sortDir === "asc" ? "ascending" : "descending") : "none"}
            >
              <span className="flex items-center gap-1.5">
                Protocol
                <SortIcon field="protocol" current={sortField} dir={sortDir} />
              </span>
            </th>
            <th scope="col" className={thClass}>Label</th>
            <th scope="col" className={thClass}>
              <span className="sr-only">Actions</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {sorted.length === 0 && (
            <tr>
              <td
                colSpan={7}
                className="py-12 text-center text-sm text-[#8b949e]"
              >
                No alerts found for the selected filters.
              </td>
            </tr>
          )}
          {sorted.map((alert, idx) => (
            <tr
              key={alert.id}
              className={cn(
                "border-b border-[#30363d]/50 transition-colors hover:bg-[#30363d]/20",
                idx % 2 === 0 ? "bg-[#0d1117]/30" : "bg-transparent",
              )}
            >
              {/* Severity badge */}
              <td className={tdClass}>
                <span
                  className={cn(
                    "inline-block rounded px-2 py-0.5 text-[11px] capitalize",
                    severityBadgeClass(alert.severity),
                  )}
                >
                  {alert.severity}
                </span>
              </td>

              {/* Source IP */}
              <td className={cn(tdClass, "font-mono text-xs")}>{alert.src_ip}</td>

              {/* Destination IP */}
              <td className={cn(tdClass, "font-mono text-xs")}>{alert.dst_ip}</td>

              {/* Score */}
              <td className={tdClass}>
                <span className="font-semibold text-[#e6edf3]">
                  {formatScore(alert.score)}
                </span>
              </td>

              {/* Protocol */}
              <td className={cn(tdClass, "uppercase text-xs text-[#8b949e]")}>
                {alert.protocol}
              </td>

              {/* Label */}
              <td className={cn(tdClass, "max-w-[160px] truncate text-xs text-[#8b949e]")}>
                {alert.label}
              </td>

              {/* Actions */}
              <td className={tdClass}>
                {onSelectAlert != null && (
                  <button
                    type="button"
                    className="flex items-center gap-1 rounded px-2 py-1 text-xs text-[#58a6ff] transition-colors hover:bg-[#58a6ff]/10"
                    onClick={() => onSelectAlert(alert)}
                    aria-label={`View details for alert from ${alert.src_ip} to ${alert.dst_ip}`}
                  >
                    <Eye size={12} aria-hidden="true" />
                    View
                  </button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
