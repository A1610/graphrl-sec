"use client";

/**
 * Dashboard page — SOC overview with KPI cards, charts, and recent alerts.
 *
 * Data sources:
 *   - /api/stats                (graph-wide counts, 30s refresh)
 *   - /api/stats/top-communicators?limit=10
 *   - /api/graph/anomalous?threshold=0.5&limit=20
 *   - /api/alerts?limit=20
 */

import { useQuery } from "@tanstack/react-query";
import {
  Activity,
  AlertTriangle,
  Globe,
  Layers,
  Network,
  Server,
  Zap,
} from "lucide-react";
import Link from "next/link";

import Header from "@/components/layout/Header";
import KPICard from "@/components/layout/KPICard";
import SeverityDonut from "@/components/charts/SeverityDonut";
import TopCommunicators from "@/components/charts/TopCommunicators";
import AlertTable from "@/components/alerts/AlertTable";

import apiClient from "@/lib/api";
import { formatNumber, severityBadgeClass, cn } from "@/lib/utils";
import type {
  AlertResponse,
  CommunicatorResponse,
  EdgeResponse,
  GraphStatsResponse,
} from "@/types/api";

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
    { params: { limit: 10 } },
  );
  return data;
}

async function fetchAnomalousEdges(): Promise<EdgeResponse[]> {
  const { data } = await apiClient.get<EdgeResponse[]>("/api/graph/anomalous", {
    params: { threshold: 0.5, limit: 20 },
  });
  return data;
}

async function fetchRecentAlerts(): Promise<AlertResponse[]> {
  const { data } = await apiClient.get<{ alerts: AlertResponse[] }>(
    "/api/alerts",
    { params: { limit: 20, offset: 0 } },
  );
  return data.alerts;
}

// ---------------------------------------------------------------------------
// Error state component
// ---------------------------------------------------------------------------

function ErrorState({ message }: { message: string }): React.ReactElement {
  return (
    <div
      className="flex items-center gap-3 rounded-lg border border-[#f85149]/30 bg-[#f85149]/10 px-4 py-3 text-sm text-[#f85149]"
      role="alert"
      aria-live="assertive"
    >
      <AlertTriangle size={16} aria-hidden="true" />
      <span>{message}</span>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Skeleton card
// ---------------------------------------------------------------------------

function SkeletonCard(): React.ReactElement {
  return (
    <div className="flex flex-col gap-3 rounded-lg border border-[#30363d] bg-[#161b22] p-5">
      <div className="h-3 w-24 animate-pulse rounded bg-[#30363d]/60" />
      <div className="h-8 w-16 animate-pulse rounded bg-[#30363d]/60" />
      <div className="h-3 w-32 animate-pulse rounded bg-[#30363d]/60" />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function DashboardPage(): React.ReactElement {
  const statsQuery = useQuery({
    queryKey: ["graph-stats"],
    queryFn: fetchStats,
    staleTime: 30_000,
    refetchInterval: 30_000,
  });

  const communicatorsQuery = useQuery({
    queryKey: ["top-communicators", 10],
    queryFn: fetchTopCommunicators,
    staleTime: 30_000,
    refetchInterval: 30_000,
  });

  const anomalousQuery = useQuery({
    queryKey: ["anomalous-edges", 0.5, 20],
    queryFn: fetchAnomalousEdges,
    staleTime: 30_000,
    refetchInterval: 30_000,
  });

  const alertsQuery = useQuery({
    queryKey: ["alerts", 20, 0, null],
    queryFn: fetchRecentAlerts,
    staleTime: 30_000,
    refetchInterval: 30_000,
  });

  const stats = statsQuery.data;
  const communicators = communicatorsQuery.data ?? [];
  const anomalousEdges = anomalousQuery.data ?? [];
  const recentAlerts = alertsQuery.data ?? [];

  // Derive top communicator label
  const topCommunicator =
    communicators.length > 0 ? communicators[0].entity_key : "—";

  // ---------------------------------------------------------------------------
  // Info content — page-level and per-card explanations
  // ---------------------------------------------------------------------------

  const pageInfo = (
    <div className="flex flex-col gap-3">
      <p>
        The <strong className="text-[#e6edf3]">Dashboard</strong> gives you a
        real-time overview of the entire network knowledge graph built from
        UNSW-NB15 and CICIDS2017 datasets.
      </p>
      <p>
        All metrics auto-refresh every <strong className="text-[#e6edf3]">30 seconds</strong>.
        The live status indicator in the top-right shows whether the backend
        WebSocket stream is connected.
      </p>
      <ul className="list-disc pl-4 flex flex-col gap-1">
        <li>KPI cards — headline counts at a glance</li>
        <li>Donut chart — node type distribution</li>
        <li>Bar chart — top 10 most active communicators</li>
        <li>Recent alerts — latest anomalous connections</li>
      </ul>
    </div>
  );

  return (
    <div className="flex flex-col overflow-auto">
      <Header
        title="Dashboard"
        subtitle="GraphRL-Sec Security Operations Centre"
        infoContent={pageInfo}
      />

      <div className="flex flex-col gap-6 p-6">
        {/* --- KPI Cards ------------------------------------------------- */}
        <section aria-label="Key performance indicators">
          {statsQuery.isError && (
            <ErrorState message="Failed to load graph statistics. Is the API server running?" />
          )}
          <div className="grid grid-cols-2 gap-4 xl:grid-cols-4">
            {statsQuery.isLoading ? (
              <>
                <SkeletonCard />
                <SkeletonCard />
                <SkeletonCard />
                <SkeletonCard />
              </>
            ) : (
              <>
                <KPICard
                  title="Total Nodes"
                  value={stats?.total_nodes ?? null}
                  subtitle="Hosts + IPs + Services + Domains + Users"
                  icon={<Layers size={18} />}
                  accentColor="#58a6ff"
                  infoTitle="Total Nodes"
                  infoContent={
                    <div className="flex flex-col gap-2">
                      <p>The total count of all entity nodes currently stored in the Neo4j knowledge graph.</p>
                      <p>Node types included:</p>
                      <ul className="list-disc pl-4 flex flex-col gap-1">
                        <li><strong className="text-[#58a6ff]">Host</strong> — internal machines on the monitored network</li>
                        <li><strong className="text-[#f85149]">ExternalIP</strong> — public IP addresses seen communicating with hosts</li>
                        <li><strong className="text-[#3fb950]">Service</strong> — network ports/services (e.g. port 443, port 22)</li>
                        <li><strong className="text-[#d29922]">Domain</strong> — DNS domain names resolved by hosts</li>
                        <li><strong className="text-[#bc8cff]">User</strong> — user accounts seen in authentication events</li>
                      </ul>
                    </div>
                  }
                />
                <KPICard
                  title="Total Edges"
                  value={stats?.total_edges ?? null}
                  subtitle="All relationship types"
                  icon={<Network size={18} />}
                  accentColor="#3fb950"
                  infoTitle="Total Edges"
                  infoContent={
                    <div className="flex flex-col gap-2">
                      <p>The total count of all relationship edges in the knowledge graph, representing interactions between entities.</p>
                      <p>Edge types included:</p>
                      <ul className="list-disc pl-4 flex flex-col gap-1">
                        <li><strong className="text-[#e6edf3]">CONNECTS_TO</strong> — network flows between hosts and external IPs</li>
                        <li><strong className="text-[#e6edf3]">USES_SERVICE</strong> — a host using a specific port/service</li>
                        <li><strong className="text-[#e6edf3]">RESOLVES_DOMAIN</strong> — DNS resolution events</li>
                        <li><strong className="text-[#e6edf3]">AUTHENTICATED_AS</strong> — login/auth events linking hosts to users</li>
                      </ul>
                    </div>
                  }
                />
                <KPICard
                  title="Anomalous Connections"
                  value={anomalousEdges.length}
                  subtitle="Attack score ≥ 0.5"
                  icon={<AlertTriangle size={18} />}
                  accentColor="#f85149"
                  infoTitle="Anomalous Connections"
                  infoContent={
                    <div className="flex flex-col gap-2">
                      <p>
                        Count of network edges that the{" "}
                        <strong className="text-[#e6edf3]">T-HetGAT model</strong> scored
                        with an attack probability of{" "}
                        <strong className="text-[#f85149]">≥ 0.5</strong> (50%).
                      </p>
                      <p>
                        T-HetGAT is a Temporal Heterogeneous Graph Attention Network trained
                        on labelled network flow windows. It assigns each edge an anomaly
                        score in [0, 1] — higher means more likely to be an attack.
                      </p>
                      <p>A score ≥ 0.5 is the default detection threshold. Connections above this are surfaced as alerts.</p>
                    </div>
                  }
                />
                <KPICard
                  title="Top Communicator"
                  value={topCommunicator}
                  subtitle={
                    communicators.length > 0
                      ? `${formatNumber(communicators[0].outbound_count)} outbound connections`
                      : "No data"
                  }
                  icon={<Zap size={18} />}
                  accentColor="#d29922"
                  infoTitle="Top Communicator"
                  infoContent={
                    <div className="flex flex-col gap-2">
                      <p>
                        The entity (host, IP, or service) with the{" "}
                        <strong className="text-[#e6edf3]">highest number of outbound connections</strong>{" "}
                        in the current graph.
                      </p>
                      <p>
                        High outbound connection counts can indicate port scanning, lateral movement,
                        data exfiltration, or a C2 beaconing host.
                      </p>
                      <p>See the Analytics page for the full top-20 communicators ranking.</p>
                    </div>
                  }
                />
              </>
            )}
          </div>
        </section>

        {/* --- Charts row ------------------------------------------------ */}
        <section
          className="grid gap-4 xl:grid-cols-2"
          aria-label="Analytics charts"
        >
          {/* Node type donut */}
          <div className="rounded-lg border border-[#30363d] bg-[#161b22] p-5">
            {statsQuery.isLoading ? (
              <div className="flex flex-col gap-3">
                <div className="h-3 w-32 animate-pulse rounded bg-[#30363d]/60" />
                <div className="h-64 animate-pulse rounded bg-[#30363d]/30" />
              </div>
            ) : statsQuery.isError || stats == null ? (
              <ErrorState message="Chart data unavailable." />
            ) : (
              <SeverityDonut stats={stats} />
            )}
          </div>

          {/* Top communicators bar chart */}
          <div className="rounded-lg border border-[#30363d] bg-[#161b22] p-5">
            {communicatorsQuery.isLoading ? (
              <div className="flex flex-col gap-3">
                <div className="h-3 w-32 animate-pulse rounded bg-[#30363d]/60" />
                <div className="h-64 animate-pulse rounded bg-[#30363d]/30" />
              </div>
            ) : communicatorsQuery.isError ? (
              <ErrorState message="Top communicators unavailable." />
            ) : (
              <TopCommunicators communicators={communicators} />
            )}
          </div>
        </section>

        {/* --- Stats breakdown ------------------------------------------- */}
        {stats != null && (
          <section aria-label="Graph statistics breakdown">
            <div className="rounded-lg border border-[#30363d] bg-[#161b22] p-5">
              <h2 className="mb-4 text-xs font-semibold uppercase tracking-widest text-[#8b949e]">
                Graph Statistics Breakdown
              </h2>
              <div className="grid grid-cols-3 gap-4 sm:grid-cols-5 lg:grid-cols-9">
                {[
                  { label: "Hosts", value: stats.host_count, color: "#58a6ff" },
                  { label: "Ext. IPs", value: stats.external_ip_count, color: "#f85149" },
                  { label: "Services", value: stats.service_count, color: "#3fb950" },
                  { label: "Domains", value: stats.domain_count, color: "#d29922" },
                  { label: "Users", value: stats.user_count, color: "#bc8cff" },
                  { label: "CONNECTS_TO", value: stats.connects_to_count, color: "#8b949e" },
                  { label: "USES_SERVICE", value: stats.uses_service_count, color: "#8b949e" },
                  { label: "RESOLVES", value: stats.resolves_domain_count, color: "#8b949e" },
                  { label: "AUTH_AS", value: stats.authenticated_as_count, color: "#8b949e" },
                ].map((item) => (
                  <div key={item.label} className="flex flex-col gap-1">
                    <span
                      className="text-lg font-bold"
                      style={{ color: item.color }}
                    >
                      {formatNumber(item.value)}
                    </span>
                    <span className="text-[11px] text-[#8b949e]">
                      {item.label}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          </section>
        )}

        {/* --- Node type row --------------------------------------------- */}
        <section aria-label="Additional statistics">
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
            <div className="rounded-lg border border-[#30363d] bg-[#161b22] p-5">
              <div className="mb-3 flex items-center gap-2">
                <Server size={14} className="text-[#58a6ff]" aria-hidden="true" />
                <h2 className="text-xs font-semibold uppercase tracking-widest text-[#8b949e]">
                  Node Types
                </h2>
              </div>
              {statsQuery.isLoading ? (
                <div className="space-y-2">
                  {[...Array(5)].map((_, i) => (
                    <div key={i} className="h-4 animate-pulse rounded bg-[#30363d]/60" />
                  ))}
                </div>
              ) : stats != null ? (
                <div className="space-y-2">
                  {[
                    { name: "Host", count: stats.host_count, color: "#58a6ff" },
                    { name: "ExternalIP", count: stats.external_ip_count, color: "#f85149" },
                    { name: "Service", count: stats.service_count, color: "#3fb950" },
                    { name: "Domain", count: stats.domain_count, color: "#d29922" },
                    { name: "User", count: stats.user_count, color: "#bc8cff" },
                  ].map((item) => (
                    <div key={item.name} className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <span
                          className="h-2 w-2 rounded-full"
                          style={{ backgroundColor: item.color }}
                          aria-hidden="true"
                        />
                        <span className="text-sm text-[#e6edf3]">{item.name}</span>
                      </div>
                      <span className="text-sm font-semibold text-[#8b949e]">
                        {formatNumber(item.count)}
                      </span>
                    </div>
                  ))}
                </div>
              ) : null}
            </div>

            <div className="rounded-lg border border-[#30363d] bg-[#161b22] p-5">
              <div className="mb-3 flex items-center gap-2">
                <Activity size={14} className="text-[#3fb950]" aria-hidden="true" />
                <h2 className="text-xs font-semibold uppercase tracking-widest text-[#8b949e]">
                  Edge Types
                </h2>
              </div>
              {statsQuery.isLoading ? (
                <div className="space-y-2">
                  {[...Array(4)].map((_, i) => (
                    <div key={i} className="h-4 animate-pulse rounded bg-[#30363d]/60" />
                  ))}
                </div>
              ) : stats != null ? (
                <div className="space-y-2">
                  {[
                    { name: "CONNECTS_TO", count: stats.connects_to_count },
                    { name: "USES_SERVICE", count: stats.uses_service_count },
                    { name: "RESOLVES_DOMAIN", count: stats.resolves_domain_count },
                    { name: "AUTHENTICATED_AS", count: stats.authenticated_as_count },
                  ].map((item) => (
                    <div key={item.name} className="flex items-center justify-between">
                      <span className="font-mono text-xs text-[#8b949e]">{item.name}</span>
                      <span className="text-sm font-semibold text-[#e6edf3]">
                        {formatNumber(item.count)}
                      </span>
                    </div>
                  ))}
                </div>
              ) : null}
            </div>

            <div className="rounded-lg border border-[#30363d] bg-[#161b22] p-5">
              <div className="mb-3 flex items-center gap-2">
                <Globe size={14} className="text-[#d29922]" aria-hidden="true" />
                <h2 className="text-xs font-semibold uppercase tracking-widest text-[#8b949e]">
                  Quick Links
                </h2>
              </div>
              <div className="flex flex-col gap-2">
                <Link
                  href="/alerts"
                  className="flex items-center justify-between rounded-md px-3 py-2 text-sm text-[#58a6ff] transition-colors hover:bg-[#58a6ff]/10"
                >
                  View All Alerts
                  <AlertTriangle size={13} aria-hidden="true" />
                </Link>
                <Link
                  href="/graph"
                  className="flex items-center justify-between rounded-md px-3 py-2 text-sm text-[#58a6ff] transition-colors hover:bg-[#58a6ff]/10"
                >
                  Open Graph Explorer
                  <Network size={13} aria-hidden="true" />
                </Link>
                <Link
                  href="/analytics"
                  className="flex items-center justify-between rounded-md px-3 py-2 text-sm text-[#58a6ff] transition-colors hover:bg-[#58a6ff]/10"
                >
                  Analytics
                  <Activity size={13} aria-hidden="true" />
                </Link>
              </div>
            </div>
          </div>
        </section>

        {/* --- Recent anomalous connections ------------------------------ */}
        <section aria-label="Recent anomalous connections">
          <div className="rounded-lg border border-[#30363d] bg-[#161b22] p-5">
            <div className="mb-4 flex items-center justify-between">
              <h2 className="text-xs font-semibold uppercase tracking-widest text-[#8b949e]">
                Recent Alerts (last 20)
              </h2>
              <Link
                href="/alerts"
                className="text-xs text-[#58a6ff] hover:underline"
              >
                View all →
              </Link>
            </div>

            {alertsQuery.isLoading ? (
              <div className="space-y-2">
                {[...Array(5)].map((_, i) => (
                  <div key={i} className="h-10 animate-pulse rounded bg-[#30363d]/40" />
                ))}
              </div>
            ) : alertsQuery.isError ? (
              <ErrorState message="Failed to load recent alerts." />
            ) : (
              <AlertTable alerts={recentAlerts} />
            )}
          </div>
        </section>
      </div>
    </div>
  );
}
