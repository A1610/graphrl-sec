/**
 * Shared utility functions.
 *
 * - `cn`        — className merger (clsx + tailwind-merge)
 * - `severityColor`  — hex colour for a severity band
 * - `severityBg`     — Tailwind arbitrary-value bg + text classes for badges
 * - `formatScore`    — format attack score as a percentage string
 * - `truncate`       — truncate a string to a maximum length
 */

import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

import type { Severity } from "@/types/api";

// ---------------------------------------------------------------------------
// className helper
// ---------------------------------------------------------------------------

export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}

// ---------------------------------------------------------------------------
// Severity helpers
// ---------------------------------------------------------------------------

/** Returns the hex colour associated with each severity level. */
export function severityColor(severity: Severity): string {
  const map: Record<Severity, string> = {
    critical: "#f85149",
    high: "#d29922",
    medium: "#3fb950",
    low: "#58a6ff",
  };
  return map[severity];
}

/**
 * Returns a combined className string for a severity badge.
 * Uses Tailwind arbitrary value syntax compatible with TailwindCSS 4.
 */
export function severityBadgeClass(severity: Severity): string {
  const map: Record<Severity, string> = {
    critical:
      "bg-[#f85149]/15 text-[#f85149] border border-[#f85149]/30 font-semibold",
    high: "bg-[#d29922]/15 text-[#d29922] border border-[#d29922]/30 font-semibold",
    medium:
      "bg-[#3fb950]/15 text-[#3fb950] border border-[#3fb950]/30 font-semibold",
    low: "bg-[#58a6ff]/15 text-[#58a6ff] border border-[#58a6ff]/30 font-semibold",
  };
  return map[severity];
}

// ---------------------------------------------------------------------------
// Formatting helpers
// ---------------------------------------------------------------------------

/** Format a 0–1 attack score as a two-decimal percentage string. */
export function formatScore(score: number): string {
  return `${(score * 100).toFixed(1)}%`;
}

/** Truncate a string to `maxLen` characters, appending ellipsis if truncated. */
export function truncate(value: string, maxLen: number): string {
  if (value.length <= maxLen) return value;
  return `${value.slice(0, maxLen - 1)}…`;
}

/** Format large numbers with locale-aware thousand separators. */
export function formatNumber(n: number): string {
  return n.toLocaleString("en-GB");
}
