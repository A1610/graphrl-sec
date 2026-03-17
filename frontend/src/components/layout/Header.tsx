"use client";

/**
 * Header — top bar showing page title, live connection status indicator,
 * and the last-updated timestamp from the WebSocket stream.
 */

import { useGraphStream } from "@/hooks/useGraphStream";
import { cn } from "@/lib/utils";

interface HeaderProps {
  title: string;
  subtitle?: string;
}

export default function Header({
  title,
  subtitle,
}: HeaderProps): React.ReactElement {
  const { connected, error } = useGraphStream();

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
    <header className="flex h-14 items-center justify-between border-b border-[#30363d] bg-[#161b22] px-6">
      <div className="flex flex-col justify-center">
        <h1 className="text-sm font-semibold text-[#e6edf3]">{title}</h1>
        {subtitle != null && (
          <p className="text-xs text-[#8b949e]">{subtitle}</p>
        )}
      </div>

      {/* Live status indicator */}
      <div
        className="flex items-center gap-2 rounded-full border border-[#30363d] bg-[#0d1117] px-3 py-1"
        role="status"
        aria-label={`Neo4j connection: ${statusLabel}`}
        aria-live="polite"
      >
        <span className={statusDotClass} aria-hidden="true" />
        <span className="text-xs font-medium text-[#8b949e]">{statusLabel}</span>
      </div>
    </header>
  );
}
