"use client";

/**
 * Analytics page — detailed graph statistics, top communicators table,
 * and system metadata about the GraphRL-Sec dataset.
 */

import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, Database, Server, Zap } from "lucide-react";

import Header from "@/components/layout/Header";

import apiClient from "@/lib/api";
import { formatNumber } from "@/lib/utils";
import type { CommunicatorResponse, GraphStatsResponse } from "@/types/api";
import { NODE_COLORS } from "@/types/graph";

// ---------------------------------------------------------------------------
// Query functions
// ---------------------------------------------------------------------------

async function fetchStats(): Promise<GraphStatsResponse> {
  const { data } = await apiClient.get<GraphStatsResponse>("/api/stats");
  return data;
}

async function fetchTopCommunicators(): Promise<CommunicatorResponse[]> {
  const { data } = await apiClient.get<CommunicatorResponse[]>(
    "/api/stats/top-communicators",
    { params: { limit: 20 } },
  );
  return data;
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function ErrorBanner({ message }: { message: string }): React.ReactElement {
  return (
    <div
      className="flex items-center gap-3 rounded-lg border border-[#f85149]/30 bg-[#f85149]/10 px-4 py-3 text-sm text-[#f85149]"
      role="alert"
      aria-live="assertive"
    >
      <AlertTriangle size={16} aria-hidden="true" />
      {message}
    </div>
  );
}

function StatRow({
  label,
  value,
  color,
}: {
  label: string;
  value: number;
  color?: string;
}): React.ReactElement {
  return (
    <tr className="border-b border-[#30363d]/50 hover:bg-[#30363d]/10">
      <td className="py-2.5 pr-4">
        <div className="flex items-center gap-2">
          {color != null && (
            <span
              className="h-2 w-2 shrink-0 rounded-full"
              style={{ backgroundColor: color }}
              aria-hidden="true"
            />
          )}
          <span className="text-sm text-[#e6edf3]">{label}</span>
        </div>
      </td>
      <td className="py-2.5 text-right font-mono text-sm font-semibold text-[#e6edf3]">
        {formatNumber(value)}
      </td>
    </tr>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function AnalyticsPage(): React.ReactElement {
  const statsQuery = useQuery({
    queryKey: ["graph-stats"],
    queryFn: fetchStats,
    staleTime: 30_000,
    refetchInterval: 30_000,
  });

  const communicatorsQuery = useQuery({
    queryKey: ["top-communicators", 20],
    queryFn: fetchTopCommunicators,
    staleTime: 30_000,
    refetchInterval: 30_000,
  });

  const stats = statsQuery.data;
  const communicators = communicatorsQuery.data ?? [];

  return (
    <div className="flex flex-col overflow-auto">
      <Header
        title="Analytics"
        subtitle="Graph statistics and top talker analysis"
      />

      <div className="flex flex-col gap-6 p-6">
        {/* --- Graph Stats Summary --------------------------------------- */}
        <section aria-label="Graph statistics summary">
          <div className="rounded-lg border border-[#30363d] bg-[#161b22] p-5">
            <div className="mb-4 flex items-center gap-2">
              <Database
                size={14}
                className="text-[#58a6ff]"
                aria-hidden="true"
              />
              <h2 className="text-xs font-semibold uppercase tracking-widest text-[#8b949e]">
                Graph Statistics
              </h2>
            </div>

            {statsQuery.isError && (
              <ErrorBanner message="Failed to load graph statistics." />
            )}

            {statsQuery.isLoading ? (
              <div className="space-y-2">
                {[...Array(9)].map((_, i) => (
                  <div
                    key={i}
                    className="h-8 animate-pulse rounded bg-[#30363d]/40"
                  />
                ))}
              </div>
            ) : stats != null ? (
              <div className="grid gap-6 md:grid-cols-2">
                {/* Nodes */}
                <div>
                  <h3 className="mb-3 text-[11px] font-semibold uppercase tracking-widest text-[#8b949e]">
                    Nodes
                  </h3>
                  <table className="w-full" aria-label="Node count by type">
                    <thead>
                      <tr>
                        <th className="pb-2 text-left text-[10px] font-semibold text-[#8b949e]">
                          Type
                        </th>
                        <th className="pb-2 text-right text-[10px] font-semibold text-[#8b949e]">
                          Count
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      <StatRow
                        label="Host"
                        value={stats.host_count}
                        color={NODE_COLORS.Host}
                      />
                      <StatRow
                        label="ExternalIP"
                        value={stats.external_ip_count}
                        color={NODE_COLORS.ExternalIP}
                      />
                      <StatRow
                        label="Service"
                        value={stats.service_count}
                        color={NODE_COLORS.Service}
                      />
                      <StatRow
                        label="Domain"
                        value={stats.domain_count}
                        color={NODE_COLORS.Domain}
                      />
                      <StatRow
                        label="User"
                        value={stats.user_count}
                        color={NODE_COLORS.User}
                      />
                    </tbody>
                    <tfoot>
                      <tr className="border-t border-[#30363d]">
                        <td className="pt-2 text-sm font-bold text-[#e6edf3]">
                          Total
                        </td>
                        <td className="pt-2 text-right font-mono text-sm font-bold text-[#58a6ff]">
                          {formatNumber(stats.total_nodes)}
                        </td>
                      </tr>
                    </tfoot>
                  </table>
                </div>

                {/* Edges */}
                <div>
                  <h3 className="mb-3 text-[11px] font-semibold uppercase tracking-widest text-[#8b949e]">
                    Edges
                  </h3>
                  <table className="w-full" aria-label="Edge count by type">
                    <thead>
                      <tr>
                        <th className="pb-2 text-left text-[10px] font-semibold text-[#8b949e]">
                          Type
                        </th>
                        <th className="pb-2 text-right text-[10px] font-semibold text-[#8b949e]">
                          Count
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      <StatRow
                        label="CONNECTS_TO"
                        value={stats.connects_to_count}
                      />
                      <StatRow
                        label="USES_SERVICE"
                        value={stats.uses_service_count}
                      />
                      <StatRow
                        label="RESOLVES_DOMAIN"
                        value={stats.resolves_domain_count}
                      />
                      <StatRow
                        label="AUTHENTICATED_AS"
                        value={stats.authenticated_as_count}
                      />
                    </tbody>
                    <tfoot>
                      <tr className="border-t border-[#30363d]">
                        <td className="pt-2 text-sm font-bold text-[#e6edf3]">
                          Total
                        </td>
                        <td className="pt-2 text-right font-mono text-sm font-bold text-[#58a6ff]">
                          {formatNumber(stats.total_edges)}
                        </td>
                      </tr>
                    </tfoot>
                  </table>
                </div>
              </div>
            ) : null}
          </div>
        </section>

        {/* --- Top Communicators Table ----------------------------------- */}
        <section aria-label="Top 20 communicators">
          <div className="rounded-lg border border-[#30363d] bg-[#161b22] p-5">
            <div className="mb-4 flex items-center gap-2">
              <Zap size={14} className="text-[#d29922]" aria-hidden="true" />
              <h2 className="text-xs font-semibold uppercase tracking-widest text-[#8b949e]">
                Top 20 Communicators
              </h2>
            </div>

            {communicatorsQuery.isError && (
              <ErrorBanner message="Failed to load top communicators." />
            )}

            {communicatorsQuery.isLoading ? (
              <div className="space-y-2">
                {[...Array(8)].map((_, i) => (
                  <div
                    key={i}
                    className="h-10 animate-pulse rounded bg-[#30363d]/40"
                  />
                ))}
              </div>
            ) : (
              <div className="overflow-x-auto rounded border border-[#30363d]">
                <table
                  className="w-full border-collapse"
                  aria-label="Top communicators ranked by outbound connections"
                >
                  <thead>
                    <tr className="border-b border-[#30363d] bg-[#0d1117]">
                      <th
                        scope="col"
                        className="px-4 py-2.5 text-left text-[10px] font-semibold uppercase tracking-widest text-[#8b949e]"
                      >
                        Rank
                      </th>
                      <th
                        scope="col"
                        className="px-4 py-2.5 text-left text-[10px] font-semibold uppercase tracking-widest text-[#8b949e]"
                      >
                        IP / Entity
                      </th>
                      <th
                        scope="col"
                        className="px-4 py-2.5 text-left text-[10px] font-semibold uppercase tracking-widest text-[#8b949e]"
                      >
                        Type
                      </th>
                      <th
                        scope="col"
                        className="px-4 py-2.5 text-right text-[10px] font-semibold uppercase tracking-widest text-[#8b949e]"
                      >
                        Outbound
                      </th>
                      <th
                        scope="col"
                        className="px-4 py-2.5 text-right text-[10px] font-semibold uppercase tracking-widest text-[#8b949e]"
                      >
                        Destinations
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {communicators.length === 0 && (
                      <tr>
                        <td
                          colSpan={5}
                          className="py-8 text-center text-sm text-[#8b949e]"
                        >
                          No communicator data available.
                        </td>
                      </tr>
                    )}
                    {communicators.map((c, idx) => {
                      const labelColor =
                        NODE_COLORS[
                          c.node_label as keyof typeof NODE_COLORS
                        ] ?? "#8b949e";
                      return (
                        <tr
                          key={c.entity_key}
                          className="border-b border-[#30363d]/50 hover:bg-[#30363d]/10"
                        >
                          <td className="px-4 py-2.5 text-sm font-semibold text-[#8b949e]">
                            {idx + 1}
                          </td>
                          <td className="px-4 py-2.5 font-mono text-xs text-[#e6edf3]">
                            {c.entity_key}
                          </td>
                          <td className="px-4 py-2.5">
                            <span
                              className="text-xs font-medium"
                              style={{ color: labelColor }}
                            >
                              {c.node_label}
                            </span>
                          </td>
                          <td className="px-4 py-2.5 text-right font-mono text-sm font-semibold text-[#e6edf3]">
                            {formatNumber(c.outbound_count)}
                          </td>
                          <td className="px-4 py-2.5 text-right font-mono text-sm text-[#8b949e]">
                            {formatNumber(c.unique_destinations)}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </section>

        {/* --- System Info ----------------------------------------------- */}
        <section aria-label="System information">
          <div className="rounded-lg border border-[#30363d] bg-[#161b22] p-5">
            <div className="mb-4 flex items-center gap-2">
              <Server size={14} className="text-[#3fb950]" aria-hidden="true" />
              <h2 className="text-xs font-semibold uppercase tracking-widest text-[#8b949e]">
                System Information
              </h2>
            </div>

            <div className="grid gap-4 md:grid-cols-3">
              {[
                {
                  label: "Dataset Sources",
                  value: "UNSW-NB15 + CICIDS2017",
                  sub: "~9GB combined raw data",
                },
                {
                  label: "Graph Backend",
                  value: "Neo4j",
                  sub: "Bolt protocol · Local instance",
                },
                {
                  label: "ML Pipeline",
                  value: "GNN + Deep RL",
                  sub: "TH-ETGAT encoder · DQN/PPO agent",
                },
              ].map((item) => (
                <div
                  key={item.label}
                  className="rounded-md border border-[#30363d] bg-[#0d1117] px-4 py-3"
                >
                  <p className="mb-1 text-[10px] font-semibold uppercase tracking-widest text-[#8b949e]">
                    {item.label}
                  </p>
                  <p className="text-sm font-semibold text-[#e6edf3]">
                    {item.value}
                  </p>
                  <p className="text-[11px] text-[#8b949e]">{item.sub}</p>
                </div>
              ))}
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}
