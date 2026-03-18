"use client";

/**
 * KPICard — a metric summary card used across the SOC dashboard.
 *
 * Accepts an optional trend indicator (+/- delta) and a loading state
 * that renders a skeleton placeholder instead of data.
 *
 * Pass `infoContent` to make the card clickable — clicking toggles an
 * info section that expands inline below the card metrics.
 */

import { useState } from "react";
import { ChevronDown } from "lucide-react";

import { cn, formatNumber } from "@/lib/utils";

interface KPICardProps {
  title: string;
  value: string | number | null;
  subtitle?: string;
  icon: React.ReactNode;
  accentColor?: string;
  loading?: boolean;
  /** Optional delta string, e.g. "+12%" or "-3 nodes" */
  delta?: string;
  deltaPositive?: boolean;
  /** When provided, clicking the card toggles inline info below the metrics. */
  infoContent?: React.ReactNode;
}

function SkeletonLine({ className }: { className?: string }) {
  return (
    <div
      className={cn("animate-pulse rounded bg-[#30363d]/60", className)}
      aria-hidden="true"
    />
  );
}

export default function KPICard({
  title,
  value,
  subtitle,
  icon,
  accentColor = "#58a6ff",
  loading = false,
  delta,
  deltaPositive,
  infoContent,
}: KPICardProps): React.ReactElement {
  const [expanded, setExpanded] = useState(false);

  const displayValue =
    typeof value === "number" ? formatNumber(value) : (value ?? "—");

  const isClickable = infoContent != null;

  return (
    <article
      className={cn(
        "flex flex-col rounded-lg border border-[#30363d] bg-[#161b22]",
        isClickable && "cursor-pointer select-none",
      )}
      aria-label={`KPI: ${title}`}
      onClick={isClickable ? () => setExpanded((v) => !v) : undefined}
      role={isClickable ? "button" : undefined}
      tabIndex={isClickable ? 0 : undefined}
      aria-expanded={isClickable ? expanded : undefined}
      onKeyDown={
        isClickable
          ? (e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                setExpanded((v) => !v);
              }
            }
          : undefined
      }
    >
      {/* Main card content */}
      <div className="flex flex-col gap-3 p-5">
        {/* Header row */}
        <div className="flex items-center justify-between">
          <span className="text-xs font-semibold uppercase tracking-widest text-[#8b949e]">
            {title}
          </span>
          <div className="flex items-center gap-1.5">
            {isClickable && (
              <ChevronDown
                size={13}
                className={cn(
                  "text-[#8b949e] transition-transform duration-200",
                  expanded && "rotate-180",
                )}
                aria-hidden="true"
              />
            )}
            <span
              className="rounded-md p-1.5"
              style={{ color: accentColor, backgroundColor: `${accentColor}18` }}
              aria-hidden="true"
            >
              {icon}
            </span>
          </div>
        </div>

        {/* Value */}
        {loading ? (
          <SkeletonLine className="h-8 w-24" />
        ) : (
          <p
            className="text-3xl font-bold tracking-tight text-[#e6edf3]"
            aria-live="polite"
          >
            {displayValue}
          </p>
        )}

        {/* Subtitle + delta */}
        <div className="flex items-center justify-between">
          {loading ? (
            <SkeletonLine className="h-3.5 w-32" />
          ) : (
            <span className="text-xs text-[#8b949e]">{subtitle ?? " "}</span>
          )}
          {!loading && delta != null && (
            <span
              className={cn(
                "text-xs font-medium",
                deltaPositive === true
                  ? "text-[#3fb950]"
                  : deltaPositive === false
                  ? "text-[#f85149]"
                  : "text-[#8b949e]",
              )}
            >
              {delta}
            </span>
          )}
        </div>
      </div>

      {/* Inline info panel — expands below when card is clicked */}
      {isClickable && expanded && (
        <div
          className="border-t border-[#30363d] px-5 py-4 text-xs leading-relaxed text-[#8b949e]"
          onClick={(e) => e.stopPropagation()}
        >
          {infoContent}
        </div>
      )}
    </article>
  );
}
