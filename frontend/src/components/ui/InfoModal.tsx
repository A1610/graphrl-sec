"use client";

/**
 * InfoModal — reusable info/help modal overlay.
 *
 * Press Escape or click the backdrop to close.
 * Renders nothing when `open` is false (no layout shift).
 */

import { useEffect } from "react";
import { X } from "lucide-react";

interface InfoModalProps {
  open: boolean;
  onClose: () => void;
  title: string;
  children: React.ReactNode;
}

export default function InfoModal({
  open,
  onClose,
  title,
  children,
}: InfoModalProps): React.ReactElement | null {
  // Close on Escape key
  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
      role="dialog"
      aria-modal="true"
      aria-label={title}
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="relative w-full max-w-2xl rounded-lg border border-[#30363d] bg-[#161b22] shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-[#30363d] px-5 py-4">
          <h2 className="text-sm font-semibold text-[#e6edf3]">{title}</h2>
          <button
            type="button"
            onClick={onClose}
            className="rounded p-1 text-[#8b949e] transition-colors hover:bg-[#30363d] hover:text-[#e6edf3]"
            aria-label="Close info modal"
          >
            <X size={16} aria-hidden="true" />
          </button>
        </div>

        {/* Content */}
        <div className="max-h-[70vh] overflow-y-auto px-5 py-4 text-sm leading-relaxed text-[#8b949e]">
          {children}
        </div>
      </div>
    </div>
  );
}
