"use client";

/**
 * Header — top bar showing page title, live connection status indicator,
 * and the last-updated timestamp from the WebSocket stream.
 *
 * Pass `infoContent` + `infoTitle` to render an "About this page" button
 * that opens an info modal describing what the page shows.
 */

import { useState } from "react";
import { Info } from "lucide-react";

import { useGraphStream } from "@/hooks/useGraphStream";
import { cn } from "@/lib/utils";
import InfoModal from "@/components/ui/InfoModal";

interface HeaderProps {
  title: string;
  subtitle?: string;
  /** When provided, renders an "About" button that opens an info modal. */
  infoContent?: React.ReactNode;
  /** Title shown in the info modal. Defaults to "About {title}". */
  infoTitle?: string;
}

export default function Header({
  title,
  subtitle,
  infoContent,
  infoTitle,
}: HeaderProps): React.ReactElement {
  const { connected, error } = useGraphStream();
  const [infoOpen, setInfoOpen] = useState(false);

  const statusLabel = error != null
    ? "Error"
    : connected
    ? "Live"
    : "Connecting…";

  const statusDotClass = cn(
    "h-2 w-2 rounded-full",
    error != null
      ? "bg-[#f85149]"
      : connected
      ? "bg-[#3fb950] animate-pulse"
      : "bg-[#d29922] animate-pulse",
  );

  return (
    <>
      <header className="flex h-14 items-center justify-between border-b border-[#30363d] bg-[#161b22] px-6">
        {/* Left: title + subtitle */}
        <div className="flex flex-col justify-center">
          <h1 className="text-sm font-semibold text-[#e6edf3]">{title}</h1>
          {subtitle != null && (
            <p className="text-xs text-[#8b949e]">{subtitle}</p>
          )}
        </div>

        {/* Right: Page Info → Live */}
        <div className="flex items-center gap-2">
          {infoContent != null && (
            <button
              type="button"
              onClick={() => setInfoOpen(true)}
              className="flex items-center gap-1.5 rounded-full border border-[#30363d] bg-[#0d1117] px-2.5 py-1 text-[#8b949e] transition-colors hover:border-[#58a6ff]/60 hover:bg-[#58a6ff]/10 hover:text-[#58a6ff]"
              aria-label={`Page info: ${title}`}
            >
              <Info size={11} aria-hidden="true" />
              <span className="text-[10px] font-medium tracking-wide">Page Info</span>
            </button>
          )}

          <div
            className="flex items-center gap-2 rounded-full border border-[#30363d] bg-[#0d1117] px-3 py-1"
            role="status"
            aria-label={`Neo4j connection: ${statusLabel}`}
            aria-live="polite"
          >
            <span className={statusDotClass} aria-hidden="true" />
            <span className="text-xs font-medium text-[#8b949e]">{statusLabel}</span>
          </div>
        </div>
      </header>

      {/* Page info modal */}
      {infoContent != null && (
        <InfoModal
          open={infoOpen}
          onClose={() => setInfoOpen(false)}
          title={infoTitle ?? `About ${title}`}
        >
          {infoContent}
        </InfoModal>
      )}
    </>
  );
}
