"use client";

/**
 * KPICard — a metric summary card used across the SOC dashboard.
 *
 * Accepts an optional trend indicator (+/- delta) and a loading state
 * that renders a skeleton placeholder instead of data.
 *
 * Pass `infoContent` + `infoTitle` to show an ℹ button that opens an
 * info modal explaining what this metric means.
 */

import { useState } from "react";
import { Info } from "lucide-react";

import { cn, formatNumber } from "@/lib/utils";
import InfoModal from "@/components/ui/InfoModal";

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
  /** When provided, renders an ℹ button that opens an info modal. */
  infoContent?: React.ReactNode;
  /** Title shown in the info modal header. Defaults to the card title. */
  infoTitle?: string;
}

function SkeletonLine({ className }: { className?: string }) {
  return (
    <div
      className={cn(
        "animate-pulse rounded bg-[#30363d]/60",
        className,
      )}
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
  infoTitle,
}: KPICardProps): React.ReactElement {
  const [infoOpen, setInfoOpen] = useState(false);

  const displayValue =
    typeof value === "number" ? formatNumber(value) : (value ?? "—");

  return (
    <>
      <article
        className="flex flex-col gap-3 rounded-lg border border-[#30363d] bg-[#161b22] p-5"
        aria-label={`KPI: ${title}`}
      >
        {/* Header row */}
        <div className="flex items-center justify-between">
          <span className="text-xs font-semibold uppercase tracking-widest text-[#8b949e]">
            {title}
          </span>

          <div className="flex items-center gap-1.5">
            {/* Info button — only rendered when infoContent is provided */}
            {infoContent != null && (
              <button
                type="button"
                onClick={() => setInfoOpen(true)}
                className="rounded p-1 text-[#8b949e] transition-colors hover:bg-[#30363d] hover:text-[#58a6ff]"
                aria-label={`About ${title}`}
              >
                <Info size={13} aria-hidden="true" />
              </button>
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
      </article>

      {/* Info modal */}
      {infoContent != null && (
        <InfoModal
          open={infoOpen}
          onClose={() => setInfoOpen(false)}
          title={infoTitle ?? title}
        >
          {infoContent}
        </InfoModal>
      )}
    </>
  );
}
