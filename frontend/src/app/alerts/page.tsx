"use client";

/**
 * Alerts page — full paginated alert table with severity filter and sort.
 *
 * Features:
 *   - Filter by severity band (All / Critical / High / Medium / Low)
 *   - Sort by any column (client-side within the fetched page)
 *   - Pagination: 50 results per page
 *   - Alert detail slide-out panel (shows neighborhood nodes on demand)
 */

import { useState } from "react";
import { AlertTriangle, ChevronLeft, ChevronRight, X } from "lucide-react";
import { useQuery } from "@tanstack/react-query";

import Header from "@/components/layout/Header";
import AlertTable from "@/components/alerts/AlertTable";

import apiClient from "@/lib/api";
import { cn, formatScore, severityBadgeClass, formatNumber } from "@/lib/utils";
import type {
  AlertDetailResponse,
  AlertResponse,
  PaginatedAlertResponse,
  Severity,
} from "@/types/api";

const PAGE_SIZE = 50;

const SEVERITY_OPTIONS: Array<{ label: string; value: Severity | null }> = [
  { label: "All", value: null },
  { label: "Critical", value: "critical" },
  { label: "High", value: "high" },
  { label: "Medium", value: "medium" },
  { label: "Low", value: "low" },
];

// ---------------------------------------------------------------------------
// Query functions
// ---------------------------------------------------------------------------

async function fetchAlerts(
  offset: number,
  severity: Severity | null,
): Promise<PaginatedAlertResponse> {
  const { data } = await apiClient.get<PaginatedAlertResponse>("/api/alerts", {
    params: {
      limit: PAGE_SIZE,
      offset,
      ...(severity != null ? { severity } : {}),
    },
  });
  return data;
}

async function fetchAlertDetail(id: string): Promise<AlertDetailResponse> {
  const { data } = await apiClient.get<AlertDetailResponse>(
    `/api/alerts/${id}`,
  );
  return data;
}

// ---------------------------------------------------------------------------
// Alert detail panel
// ---------------------------------------------------------------------------

interface DetailPanelProps {
  alertId: string;
  onClose: () => void;
}

function AlertDetailPanel({
  alertId,
  onClose,
}: DetailPanelProps): React.ReactElement {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["alert-detail", alertId],
    queryFn: () => fetchAlertDetail(alertId),
    staleTime: 60_000,
  });

  return (
    <aside
      className="flex h-full w-96 flex-col border-l border-[#30363d] bg-[#161b22]"
      aria-label="Alert details panel"
    >
      {/* Header */}
      <div className="flex items-center justify-between border-b border-[#30363d] px-4 py-3">
        <h2 className="text-sm font-semibold text-[#e6edf3]">Alert Details</h2>
        <button
          type="button"
          onClick={onClose}
          className="rounded p-1 text-[#8b949e] transition-colors hover:bg-[#30363d] hover:text-[#e6edf3]"
          aria-label="Close alert details panel"
        >
          <X size={16} aria-hidden="true" />
        </button>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto px-4 py-4">
        {isLoading && (
          <div className="flex flex-col gap-3">
            {[...Array(6)].map((_, i) => (
              <div
                key={i}
                className="h-5 animate-pulse rounded bg-[#30363d]/60"
              />
            ))}
          </div>
        )}

        {isError && (
          <div
            className="flex items-center gap-2 rounded border border-[#f85149]/30 bg-[#f85149]/10 px-3 py-2 text-sm text-[#f85149]"
            role="alert"
          >
            <AlertTriangle size={14} aria-hidden="true" />
            Failed to load alert details.
          </div>
        )}

        {data != null && (
          <div className="flex flex-col gap-5">
            {/* Summary */}
            <div className="flex flex-col gap-2">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold uppercase tracking-widest text-[#8b949e]">
                  Severity
                </span>
                <span
                  className={cn(
                    "rounded px-2 py-0.5 text-[11px] capitalize",
                    severityBadgeClass(data.alert.severity),
                  )}
                >
                  {data.alert.severity}
                </span>
              </div>

              <div className="flex flex-col gap-1 rounded-md border border-[#30363d] bg-[#0d1117] px-3 py-3">
                {(
                  [
                    ["ID", data.alert.id],
                    ["Source IP", data.alert.src_ip],
                    ["Dest IP", data.alert.dst_ip],
                    ["Score", formatScore(data.alert.score)],
                    ["Protocol", data.alert.protocol.toUpperCase()],
                    ["Label", data.alert.label],
                    ["Window ID", data.alert.window_id?.toString() ?? "—"],
                    [
                      "Packets",
                      data.alert.packet_count != null
                        ? formatNumber(data.alert.packet_count)
                        : "—",
                    ],
                    [
                      "Bytes",
                      data.alert.byte_count != null
                        ? formatNumber(data.alert.byte_count)
                        : "—",
                    ],
                  ] as [string, string][]
                ).map(([label, value]) => (
                  <div key={label} className="flex items-center justify-between">
                    <span className="text-xs text-[#8b949e]">{label}</span>
                    <span className="font-mono text-xs text-[#e6edf3]">
                      {value}
                    </span>
                  </div>
                ))}
              </div>
            </div>

            {/* Neighborhood nodes */}
            <div className="flex flex-col gap-2">
              <span className="text-xs font-semibold uppercase tracking-widest text-[#8b949e]">
                2-hop Neighborhood ({data.neighborhood_nodes.length} nodes,{" "}
                {data.neighborhood_edges.length} edges)
              </span>
              <div className="flex flex-col gap-1">
                {data.neighborhood_nodes.slice(0, 20).map((node) => (
                  <div
                    key={node.entity_key}
                    className="flex items-center justify-between rounded px-2 py-1 hover:bg-[#30363d]/30"
                  >
                    <span className="font-mono text-xs text-[#e6edf3]">
                      {node.entity_key}
                    </span>
                    <span className="text-[10px] text-[#8b949e]">
                      {node.node_label}
                    </span>
                  </div>
                ))}
                {data.neighborhood_nodes.length > 20 && (
                  <p className="pt-1 text-center text-xs text-[#8b949e]">
                    +{data.neighborhood_nodes.length - 20} more nodes
                  </p>
                )}
              </div>
            </div>
          </div>
        )}
      </div>
    </aside>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function AlertsPage(): React.ReactElement {
  const [severity, setSeverity] = useState<Severity | null>(null);
  const [page, setPage] = useState(0);
  const [selectedAlert, setSelectedAlert] = useState<AlertResponse | null>(null);

  // Reset to page 0 when filter changes
  const handleSeverityChange = (value: Severity | null) => {
    setSeverity(value);
    setPage(0);
  };

  const offset = page * PAGE_SIZE;

  const { data, isLoading, isError, isFetching } = useQuery({
    queryKey: ["alerts-page", PAGE_SIZE, offset, severity],
    queryFn: () => fetchAlerts(offset, severity),
    staleTime: 30_000,
    refetchInterval: 30_000,
  });

  const alerts = data?.alerts ?? [];
  const total = data?.total ?? 0;
  const totalPages = Math.ceil(total / PAGE_SIZE);

  return (
    <div className="flex h-full flex-col overflow-hidden">
      <Header
        title="Alerts"
        subtitle="Security alerts derived from anomalous graph paths"
        infoContent={
          <div className="flex flex-col gap-3">
            <p>
              This page lists all network connections that the{" "}
              <strong className="text-[#e6edf3]">T-HetGAT model</strong> has
              flagged as anomalous, sorted by attack probability score.
            </p>
            <p>
              <strong className="text-[#e6edf3]">Severity</strong> is derived from the
              model&apos;s attack score:
            </p>
            <ul className="list-disc pl-4 flex flex-col gap-1">
              <li><strong className="text-[#f85149]">Critical</strong> — score ≥ 0.90</li>
              <li><strong className="text-[#d29922]">High</strong> — score ≥ 0.75</li>
              <li><strong className="text-[#3fb950]">Medium</strong> — score ≥ 0.50</li>
              <li><strong className="text-[#58a6ff]">Low</strong> — score ≥ 0.25</li>
            </ul>
            <p>
              Click any row to open the detail panel, which shows the alert
              properties and its{" "}
              <strong className="text-[#e6edf3]">2-hop neighborhood</strong> in the graph.
            </p>
          </div>
        }
      />

      <div className="flex flex-1 overflow-hidden">
        {/* Main panel */}
        <div className="flex flex-1 flex-col overflow-auto p-6">
          {/* Filter bar */}
          <div className="mb-5 flex flex-wrap items-center gap-2">
            <span className="text-xs font-semibold uppercase tracking-widest text-[#8b949e]">
              Filter by severity:
            </span>
            {SEVERITY_OPTIONS.map((opt) => (
              <button
                key={opt.label}
                type="button"
                onClick={() => handleSeverityChange(opt.value)}
                className={cn(
                  "rounded-full px-3 py-1 text-xs font-medium transition-colors",
                  severity === opt.value
                    ? "bg-[#58a6ff]/20 text-[#58a6ff] ring-1 ring-[#58a6ff]/40"
                    : "bg-[#161b22] text-[#8b949e] hover:bg-[#30363d]/60 hover:text-[#e6edf3]",
                )}
                aria-pressed={severity === opt.value}
              >
                {opt.label}
              </button>
            ))}

            {/* Result count */}
            {data != null && (
              <span className="ml-auto text-xs text-[#8b949e]">
                {isFetching && !isLoading ? "Refreshing… " : ""}
                {formatNumber(total)} alert{total !== 1 ? "s" : ""}
                {severity != null ? ` (${severity})` : ""}
              </span>
            )}
          </div>

          {/* Error state */}
          {isError && (
            <div
              className="mb-4 flex items-center gap-3 rounded-lg border border-[#f85149]/30 bg-[#f85149]/10 px-4 py-3 text-sm text-[#f85149]"
              role="alert"
              aria-live="assertive"
            >
              <AlertTriangle size={16} aria-hidden="true" />
              Failed to load alerts. Check that the API server is running.
            </div>
          )}

          {/* Loading skeleton */}
          {isLoading ? (
            <div className="space-y-2">
              {[...Array(10)].map((_, i) => (
                <div
                  key={i}
                  className="h-12 animate-pulse rounded bg-[#161b22]"
                />
              ))}
            </div>
          ) : (
            <AlertTable alerts={alerts} onSelectAlert={setSelectedAlert} />
          )}

          {/* Pagination */}
          {totalPages > 1 && (
            <nav
              className="mt-5 flex items-center justify-between"
              aria-label="Alert pagination"
            >
              <button
                type="button"
                disabled={page === 0}
                onClick={() => setPage((p) => Math.max(0, p - 1))}
                className="flex items-center gap-1 rounded-md border border-[#30363d] px-3 py-1.5 text-xs text-[#8b949e] transition-colors disabled:cursor-not-allowed disabled:opacity-40 hover:enabled:bg-[#30363d]/60 hover:enabled:text-[#e6edf3]"
                aria-label="Previous page"
              >
                <ChevronLeft size={14} aria-hidden="true" />
                Previous
              </button>

              <span className="text-xs text-[#8b949e]">
                Page {page + 1} of {totalPages} · {formatNumber(total)} total
              </span>

              <button
                type="button"
                disabled={page >= totalPages - 1}
                onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
                className="flex items-center gap-1 rounded-md border border-[#30363d] px-3 py-1.5 text-xs text-[#8b949e] transition-colors disabled:cursor-not-allowed disabled:opacity-40 hover:enabled:bg-[#30363d]/60 hover:enabled:text-[#e6edf3]"
                aria-label="Next page"
              >
                Next
                <ChevronRight size={14} aria-hidden="true" />
              </button>
            </nav>
          )}
        </div>

        {/* Detail panel */}
        {selectedAlert != null && (
          <AlertDetailPanel
            alertId={selectedAlert.id}
            onClose={() => setSelectedAlert(null)}
          />
        )}
      </div>
    </div>
  );
}
