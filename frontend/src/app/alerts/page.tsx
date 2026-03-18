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
          <div className="flex flex-col gap-5">
            <div>
              <p className="mb-1 text-[10px] font-semibold uppercase tracking-widest text-[#58a6ff]">What is this page?</p>
              <p>
                The <strong className="text-[#e6edf3]">Alerts</strong> page is the full incident log —
                every network connection that the T-HetGAT model has scored as anomalous, paginated and
                filterable. Think of it as the &ldquo;threat inbox&rdquo; for the SOC analyst.
              </p>
            </div>

            <div>
              <p className="mb-1 text-[10px] font-semibold uppercase tracking-widest text-[#58a6ff]">How alerts are generated</p>
              <p>
                The <strong className="text-[#e6edf3]">T-HetGAT model</strong> (Temporal Heterogeneous
                Graph Attention Network) reads 60-second network flow windows as heterogeneous graphs.
                For each window it assigns every edge — every connection between two network entities —
                an <strong className="text-[#e6edf3]">attack probability in [0, 1]</strong>.
              </p>
              <p className="mt-2">
                Connections that score above the detection threshold are written to the database as alerts.
                The model achieves <strong className="text-[#e6edf3]">AUROC &gt; 0.98</strong> on the
                held-out test set, outperforming the Node2Vec + Isolation Forest baseline.
              </p>
            </div>

            <div>
              <p className="mb-2 text-[10px] font-semibold uppercase tracking-widest text-[#58a6ff]">Severity bands</p>
              <div className="flex flex-col gap-1.5">
                {[
                  { label: "Critical", range: "score ≥ 0.90", color: "#f85149", desc: "Near-certain attack. Immediate investigation required." },
                  { label: "High",     range: "score ≥ 0.75", color: "#d29922", desc: "Strong indicator of malicious activity. Triage promptly." },
                  { label: "Medium",   range: "score ≥ 0.50", color: "#3fb950", desc: "Above detection threshold. Worth reviewing in bulk." },
                  { label: "Low",      range: "score ≥ 0.25", color: "#58a6ff", desc: "Marginal score. Could be noisy — review in context." },
                ].map((s) => (
                  <div key={s.label} className="rounded-md border border-[#30363d] bg-[#0d1117] px-3 py-2">
                    <div className="mb-0.5 flex items-center justify-between">
                      <span className="text-xs font-semibold" style={{ color: s.color }}>{s.label}</span>
                      <span className="font-mono text-[10px] text-[#8b949e]">{s.range}</span>
                    </div>
                    <p className="text-[11px] text-[#8b949e]">{s.desc}</p>
                  </div>
                ))}
              </div>
            </div>

            <div>
              <p className="mb-2 text-[10px] font-semibold uppercase tracking-widest text-[#58a6ff]">Page features</p>
              <div className="flex flex-col gap-2">
                {[
                  { title: "Severity filter",   desc: "Filter to All / Critical / High / Medium / Low using the pill buttons. Resets pagination to page 1 automatically." },
                  { title: "Pagination",        desc: "50 alerts per page. Use Previous / Next to navigate. The total count updates based on the active filter." },
                  { title: "Alert table",       desc: "Columns: Source IP → Dest IP, Protocol, Attack Score, Severity badge, Label (attack type from ground truth). Click a row to open the detail panel." },
                  { title: "Detail panel",      desc: "Slide-out right panel showing all alert fields (ID, IPs, packets, bytes, window ID) plus the 2-hop neighborhood — the immediate graph context around that connection." },
                ].map((f) => (
                  <div key={f.title} className="rounded-md border border-[#30363d] bg-[#0d1117] px-3 py-2.5">
                    <p className="mb-0.5 text-xs font-semibold text-[#e6edf3]">{f.title}</p>
                    <p className="text-[11px] text-[#8b949e]">{f.desc}</p>
                  </div>
                ))}
              </div>
            </div>

            <div>
              <p className="mb-1 text-[10px] font-semibold uppercase tracking-widest text-[#58a6ff]">What to look for</p>
              <p>
                Focus on <strong className="text-[#f85149]">Critical</strong> alerts first — especially
                those involving internal hosts (10.x.x.x, 192.168.x.x) communicating with external IPs on
                unusual ports. Repeated alerts from the same source IP across multiple windows suggest a
                sustained attack rather than a one-off anomaly.
              </p>
            </div>
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
