"use client";

/**
 * InfoDrawer — bottom sheet that slides up from the viewport floor.
 *
 * Always rendered (for smooth CSS transitions); hidden via translate-y-full
 * when `open` is false.  Backdrop fades in/out independently.
 *
 * Closes on:  Escape key · backdrop click · X button
 */

import { useEffect } from "react";
import { X } from "lucide-react";
import { cn } from "@/lib/utils";

export interface InfoDrawerProps {
  open: boolean;
  onClose: () => void;
  title: string;
  icon?: React.ReactNode;
  accentColor?: string;
  children?: React.ReactNode;
}

export default function InfoDrawer({
  open,
  onClose,
  title,
  icon,
  accentColor = "#58a6ff",
  children,
}: InfoDrawerProps): React.ReactElement {
  // Close on Escape
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape" && open) onClose();
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [open, onClose]);

  return (
    <>
      {/* ── Backdrop ─────────────────────────────────────────────────── */}
      <div
        className={cn(
          "fixed inset-0 z-40 bg-black/50 backdrop-blur-sm transition-opacity duration-300",
          open ? "opacity-100" : "pointer-events-none opacity-0",
        )}
        aria-hidden="true"
        onClick={onClose}
      />

      {/* ── Sheet ────────────────────────────────────────────────────── */}
      <div
        className={cn(
          "fixed inset-x-0 bottom-0 z-50 transition-transform duration-300 ease-out",
          open ? "translate-y-0" : "translate-y-full",
        )}
        role="dialog"
        aria-modal="true"
        aria-label={title}
      >
        {/* Drag handle pill */}
        <div className="flex justify-center pb-1 pt-3">
          <div className="h-1 w-10 rounded-full bg-[#30363d]" />
        </div>

        {/* Card */}
        <div className="rounded-t-2xl border border-b-0 border-[#30363d] bg-[#161b22] shadow-2xl">
          {/* Header */}
          <div className="flex items-center justify-between border-b border-[#30363d] px-6 py-4">
            <div className="flex items-center gap-3">
              {icon != null && (
                <span
                  className="rounded-lg p-2"
                  style={{
                    color: accentColor,
                    backgroundColor: `${accentColor}20`,
                  }}
                  aria-hidden="true"
                >
                  {icon}
                </span>
              )}
              <h2 className="text-base font-semibold text-[#e6edf3]">
                {title}
              </h2>
            </div>

            <button
              type="button"
              onClick={onClose}
              className="rounded-lg p-1.5 text-[#8b949e] transition-colors hover:bg-[#30363d] hover:text-[#e6edf3]"
              aria-label="Close"
            >
              <X size={16} aria-hidden="true" />
            </button>
          </div>

          {/* Body */}
          <div className="max-h-[45vh] overflow-y-auto px-6 py-5 text-sm leading-relaxed text-[#8b949e]">
            {children}
          </div>
        </div>
      </div>
    </>
  );
}
