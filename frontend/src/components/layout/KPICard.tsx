"use client";

/**
 * KPICard — a metric summary card used across the SOC dashboard.
 *
 * Pass `onCardClick` to make the card interactive — clicking opens
 * the parent-managed InfoDrawer with context about this metric.
 */

import { cn, formatNumber } from "@/lib/utils";

interface KPICardProps {
  title: string;
  value: string | number | null;
  subtitle?: string;
  icon: React.ReactNode;
  accentColor?: string;
  loading?: boolean;
  delta?: string;
  deltaPositive?: boolean;
  /** When provided the card becomes clickable and shows a hover ring. */
  onCardClick?: () => void;
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
  onCardClick,
}: KPICardProps): React.ReactElement {
  const displayValue =
    typeof value === "number" ? formatNumber(value) : (value ?? "—");

  const clickable = onCardClick != null;

  return (
    <article
      className={cn(
        "flex flex-col gap-3 rounded-lg border border-[#30363d] bg-[#161b22] p-5 transition-colors duration-150",
        clickable &&
          "cursor-pointer select-none hover:border-[#58a6ff]/50 hover:bg-[#1c2230]",
      )}
      aria-label={`KPI: ${title}${clickable ? " — click for details" : ""}`}
      onClick={clickable ? onCardClick : undefined}
      role={clickable ? "button" : undefined}
      tabIndex={clickable ? 0 : undefined}
      onKeyDown={
        clickable
          ? (e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                onCardClick();
              }
            }
          : undefined
      }
    >
      {/* Header */}
      <div className="flex items-center justify-between">
        <span className="text-xs font-semibold uppercase tracking-widest text-[#8b949e]">
          {title}
        </span>
        <span
          className="rounded-md p-1.5"
          style={{ color: accentColor, backgroundColor: `${accentColor}18` }}
          aria-hidden="true"
        >
          {icon}
        </span>
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
    </article>
  );
}
