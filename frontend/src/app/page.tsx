"use client";

/**
 * Dashboard page — SOC overview with KPI cards, charts, and recent alerts.
 *
 * Data sources:
 *   - /api/stats                (graph-wide counts, 30s refresh)
 *   - /api/stats/top-communicators?limit=10
 *   - /api/graph/anomalous?threshold=0.5&limit=20
 *   - /api/alerts?limit=20
 *
 * Every card on the page is clickable — clicking opens a bottom-sheet
 * InfoDrawer that explains what that card/section shows.
 */

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Activity,
  AlertTriangle,
  BarChart2,
  Globe,
  Layers,
  Network,
  PieChart,
  Server,
  Zap,
} from "lucide-react";
import Link from "next/link";

import Header from "@/components/layout/Header";
import KPICard from "@/components/layout/KPICard";
import SeverityDonut from "@/components/charts/SeverityDonut";
import TopCommunicators from "@/components/charts/TopCommunicators";
import AlertTable from "@/components/alerts/AlertTable";
import InfoDrawer, { type InfoDrawerProps } from "@/components/ui/InfoDrawer";

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
// Clickable card wrapper (for non-KPI cards like charts, tables)
// ---------------------------------------------------------------------------

function ClickableCard({
  onClick,
  className,
  children,
}: {
  onClick: () => void;
  className?: string;
  children: React.ReactNode;
}): React.ReactElement {
  return (
    <div
      className={cn(
        "cursor-pointer rounded-lg border border-[#30363d] bg-[#161b22] p-5",
        "transition-colors duration-150 hover:border-[#58a6ff]/50 hover:bg-[#1c2230]",
        className,
      )}
      onClick={onClick}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onClick();
        }
      }}
    >
      {children}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Drawer info definitions  (all content in one place, easy to maintain)
// ---------------------------------------------------------------------------

type DrawerDef = Omit<InfoDrawerProps, "open" | "onClose">;

const DRAWER_TOTAL_NODES: DrawerDef = {
  title: "Total Nodes",
  icon: <Layers size={20} />,
  accentColor: "#58a6ff",
  children: (
    <div className="flex flex-col gap-3">
      <p>
        Total count of every entity node stored in the Neo4j knowledge graph,
        built from UNSW-NB15 and CICIDS2017 network capture data.
      </p>
      <div className="grid grid-cols-2 gap-2">
        {[
          { label: "Host", color: "#58a6ff", desc: "Internal machines on the monitored LAN" },
          { label: "ExternalIP", color: "#f85149", desc: "Public IPs communicating with the network" },
          { label: "Service", color: "#3fb950", desc: "Network ports/services (e.g. :443, :22)" },
          { label: "Domain", color: "#d29922", desc: "DNS domain names resolved by hosts" },
          { label: "User", color: "#bc8cff", desc: "User accounts in authentication logs" },
        ].map((t) => (
          <div key={t.label} className="rounded-md border border-[#30363d] bg-[#0d1117] px-3 py-2">
            <p className="mb-0.5 text-xs font-semibold" style={{ color: t.color }}>{t.label}</p>
            <p className="text-[11px] text-[#8b949e]">{t.desc}</p>
          </div>
        ))}
      </div>
    </div>
  ),
};

const DRAWER_TOTAL_EDGES: DrawerDef = {
  title: "Total Edges",
  icon: <Network size={20} />,
  accentColor: "#3fb950",
  children: (
    <div className="flex flex-col gap-3">
      <p>
        Total count of all relationship edges — each represents a recorded
        interaction between two entities in the network graph.
      </p>
      <div className="flex flex-col gap-2">
        {[
          { label: "CONNECTS_TO", desc: "Network flows between a host and an external IP" },
          { label: "USES_SERVICE", desc: "A host accessing a specific port/service" },
          { label: "RESOLVES_DOMAIN", desc: "DNS resolution — a host looked up a domain name" },
          { label: "AUTHENTICATED_AS", desc: "Authentication event linking a host to a user account" },
        ].map((e) => (
          <div key={e.label} className="flex gap-3 rounded-md border border-[#30363d] bg-[#0d1117] px-3 py-2">
            <code className="shrink-0 text-[11px] text-[#3fb950]">{e.label}</code>
            <p className="text-[11px] text-[#8b949e]">{e.desc}</p>
          </div>
        ))}
      </div>
    </div>
  ),
};

const DRAWER_ANOMALOUS: DrawerDef = {
  title: "Anomalous Connections",
  icon: <AlertTriangle size={20} />,
  accentColor: "#f85149",
  children: (
    <div className="flex flex-col gap-3">
      <p>
        Edges scored <strong className="text-[#f85149]">≥ 0.5 attack probability</strong> by
        the <strong className="text-[#e6edf3]">T-HetGAT model</strong> (Temporal Heterogeneous
        Graph Attention Network).
      </p>
      <p>
        T-HetGAT reads network flow windows as heterogeneous graphs and uses
        temporal attention to assign each edge an anomaly score in [0, 1].
        It was trained on 17,657 labelled graph windows with FocalLoss to handle
        the 82.5% normal / 17.5% attack class imbalance.
      </p>
      <div className="rounded-md border border-[#30363d] bg-[#0d1117] px-4 py-3">
        <p className="mb-2 text-[10px] font-semibold uppercase tracking-widest text-[#8b949e]">
          Severity thresholds
        </p>
        {[
          { label: "Critical", range: "≥ 0.90", color: "#f85149" },
          { label: "High",     range: "≥ 0.75", color: "#d29922" },
          { label: "Medium",   range: "≥ 0.50", color: "#3fb950" },
          { label: "Low",      range: "≥ 0.25", color: "#58a6ff" },
        ].map((s) => (
          <div key={s.label} className="flex items-center justify-between py-1">
            <span className="text-xs" style={{ color: s.color }}>{s.label}</span>
            <span className="font-mono text-xs text-[#8b949e]">{s.range}</span>
          </div>
        ))}
      </div>
    </div>
  ),
};

const DRAWER_TOP_COMMUNICATOR: DrawerDef = {
  title: "Top Communicator",
  icon: <Zap size={20} />,
  accentColor: "#d29922",
  children: (
    <div className="flex flex-col gap-3">
      <p>
        The single entity with the <strong className="text-[#e6edf3]">highest outbound
        connection count</strong> in the current graph snapshot.
      </p>
      <p>
        Unusually high outbound counts from a single host can indicate:
      </p>
      <ul className="flex flex-col gap-1.5 pl-4">
        {[
          "Port scanning / reconnaissance",
          "Lateral movement across the LAN",
          "Data exfiltration to external IPs",
          "C2 beaconing (command-and-control)",
          "DDoS participation",
        ].map((item) => (
          <li key={item} className="list-disc text-[#8b949e]">{item}</li>
        ))}
      </ul>
      <p className="text-[11px]">
        See the <strong className="text-[#e6edf3]">Analytics</strong> page for the full top-20 ranking.
      </p>
    </div>
  ),
};

const DRAWER_DONUT: DrawerDef = {
  title: "Node Type Distribution",
  icon: <PieChart size={20} />,
  accentColor: "#58a6ff",
  children: (
    <div className="flex flex-col gap-3">
      <p>
        Donut chart showing the <strong className="text-[#e6edf3]">proportion of each node type</strong> in
        the full knowledge graph.
      </p>
      <p>
        A healthy network typically has far more Host and Service nodes than
        ExternalIP or User nodes. A spike in ExternalIP nodes relative to Hosts
        could indicate an active scanning campaign or a broad DDoS.
      </p>
      <p className="text-[11px]">
        Hover over each segment to see the exact count. Data refreshes every 30 s.
      </p>
    </div>
  ),
};

const DRAWER_COMMUNICATORS_CHART: DrawerDef = {
  title: "Top 10 Communicators",
  icon: <BarChart2 size={20} />,
  accentColor: "#3fb950",
  children: (
    <div className="flex flex-col gap-3">
      <p>
        Horizontal bar chart of the <strong className="text-[#e6edf3]">10 most active entities</strong> by
        outbound connection count.
      </p>
      <p>
        Each bar represents one IP/entity. Longer bars = more connections initiated.
        Entities at the top of this list warrant closer investigation — they have the
        highest potential blast radius if compromised.
      </p>
      <p className="text-[11px]">
        The full top-20 table is available on the <strong className="text-[#e6edf3]">Analytics</strong> page.
      </p>
    </div>
  ),
};

const DRAWER_STATS_BREAKDOWN: DrawerDef = {
  title: "Graph Statistics Breakdown",
  icon: <Layers size={20} />,
  accentColor: "#8b949e",
  children: (
    <div className="flex flex-col gap-3">
      <p>
        A flat view of every node type and edge type count from Neo4j — the same
        numbers as the KPI cards but all in one glanceable grid.
      </p>
      <p>
        The first five columns (blue/red/green/yellow/purple) are node types.
        The last four (grey) are edge relationship types.
      </p>
      <p className="text-[11px]">
        These counts reflect the entire graph, not just the anomalous subset shown
        in the Graph Explorer.
      </p>
    </div>
  ),
};

const DRAWER_NODE_TYPES: DrawerDef = {
  title: "Node Types",
  icon: <Server size={20} />,
  accentColor: "#58a6ff",
  children: (
    <div className="flex flex-col gap-3">
      <p>Breakdown of the 5 entity types that make up the knowledge graph nodes:</p>
      <div className="flex flex-col gap-2">
        {[
          { label: "Host", color: "#58a6ff", desc: "Internal machines — workstations, servers, IoT devices on the monitored LAN segment" },
          { label: "ExternalIP", color: "#f85149", desc: "Public internet IPs observed communicating with the internal network" },
          { label: "Service", color: "#3fb950", desc: "Network services identified by port number (e.g. port 443 = HTTPS, port 22 = SSH)" },
          { label: "Domain", color: "#d29922", desc: "DNS domain names resolved during the capture period" },
          { label: "User", color: "#bc8cff", desc: "User account identifiers extracted from authentication and login events" },
        ].map((t) => (
          <div key={t.label} className="flex gap-3 rounded-md border border-[#30363d] bg-[#0d1117] px-3 py-2">
            <span className="mt-0.5 h-2 w-2 shrink-0 rounded-full" style={{ backgroundColor: t.color }} />
            <div>
              <p className="mb-0.5 text-xs font-semibold" style={{ color: t.color }}>{t.label}</p>
              <p className="text-[11px] text-[#8b949e]">{t.desc}</p>
            </div>
          </div>
        ))}
      </div>
    </div>
  ),
};

const DRAWER_EDGE_TYPES: DrawerDef = {
  title: "Edge Types",
  icon: <Activity size={20} />,
  accentColor: "#3fb950",
  children: (
    <div className="flex flex-col gap-3">
      <p>The 4 relationship types that connect nodes in the graph:</p>
      <div className="flex flex-col gap-2">
        {[
          { label: "CONNECTS_TO", desc: "A host established a network flow to an external IP. Carries flow features: bytes, packets, duration, protocol." },
          { label: "USES_SERVICE", desc: "A host accessed a specific port/service. Links hosts to service nodes." },
          { label: "RESOLVES_DOMAIN", desc: "A DNS resolution event. Links a host to the domain name it looked up." },
          { label: "AUTHENTICATED_AS", desc: "An authentication event linking a host to a user account (login, sudo, etc.)." },
        ].map((e) => (
          <div key={e.label} className="rounded-md border border-[#30363d] bg-[#0d1117] px-3 py-2">
            <p className="mb-0.5 font-mono text-[11px] font-semibold text-[#3fb950]">{e.label}</p>
            <p className="text-[11px] text-[#8b949e]">{e.desc}</p>
          </div>
        ))}
      </div>
    </div>
  ),
};

const DRAWER_QUICK_LINKS: DrawerDef = {
  title: "Quick Links",
  icon: <Globe size={20} />,
  accentColor: "#d29922",
  children: (
    <div className="flex flex-col gap-2">
      <p>Jump to other sections of the dashboard:</p>
      <ul className="flex flex-col gap-1.5 pl-4">
        <li className="list-disc"><strong className="text-[#e6edf3]">Alerts</strong> — full paginated list of all anomalous connections with severity filter</li>
        <li className="list-disc"><strong className="text-[#e6edf3]">Graph Explorer</strong> — interactive vis-network graph of anomalous paths, clickable nodes</li>
        <li className="list-disc"><strong className="text-[#e6edf3]">Analytics</strong> — detailed node/edge counts and top-20 communicators table</li>
      </ul>
    </div>
  ),
};

const DRAWER_RECENT_ALERTS: DrawerDef = {
  title: "Recent Alerts",
  icon: <AlertTriangle size={20} />,
  accentColor: "#f85149",
  children: (
    <div className="flex flex-col gap-3">
      <p>
        The <strong className="text-[#e6edf3]">20 most recent anomalous connections</strong> flagged
        by the T-HetGAT model, shown in a condensed table.
      </p>
      <p>
        Each row shows the source IP, destination IP, protocol, attack score,
        and severity band. Click a row on the Alerts page to open the full
        detail panel with the 2-hop neighborhood graph.
      </p>
      <p>
        Severity is derived from the model score:
      </p>
      <div className="flex flex-col gap-1">
        {[
          { label: "Critical ≥ 0.90", color: "#f85149" },
          { label: "High     ≥ 0.75", color: "#d29922" },
          { label: "Medium   ≥ 0.50", color: "#3fb950" },
          { label: "Low      ≥ 0.25", color: "#58a6ff" },
        ].map((s) => (
          <div key={s.label} className="flex items-center gap-2">
            <span className="h-2 w-2 rounded-full" style={{ backgroundColor: s.color }} />
            <span className="font-mono text-[11px]" style={{ color: s.color }}>{s.label}</span>
          </div>
        ))}
      </div>
    </div>
  ),
};

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function DashboardPage(): React.ReactElement {
  // ── Data queries ──────────────────────────────────────────────────────────
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

  const topCommunicator =
    communicators.length > 0 ? communicators[0].entity_key : "—";

  // ── Drawer state ─────────────────────────────────────────────────────────
  const [drawerDef, setDrawerDef] = useState<DrawerDef | null>(null);
  const openDrawer = (def: DrawerDef) => setDrawerDef(def);
  const closeDrawer = () => setDrawerDef(null);

  // ── Page-level info (header Page Info button) ────────────────────────────
  const pageInfo = (
    <div className="flex flex-col gap-5">
      <div>
        <p className="mb-1 text-[10px] font-semibold uppercase tracking-widest text-[#58a6ff]">What is this page?</p>
        <p>
          The <strong className="text-[#e6edf3]">Dashboard</strong> is the central command view of the
          GraphRL-Sec Security Operations Centre. It gives you a live, high-level picture of the entire
          network knowledge graph — how many entities exist, which connections are suspicious, and where
          attack activity is concentrated.
        </p>
      </div>

      <div>
        <p className="mb-1 text-[10px] font-semibold uppercase tracking-widest text-[#58a6ff]">Data sources</p>
        <p>
          All data originates from two public cybersecurity datasets —{" "}
          <strong className="text-[#e6edf3]">UNSW-NB15</strong> (~2 GB) and{" "}
          <strong className="text-[#e6edf3]">CICIDS2017</strong> (~7 GB) — containing real network packet
          captures with ground-truth attack labels. Raw flows are feature-engineered and loaded into a
          Neo4j graph database as a heterogeneous knowledge graph (5 node types, 4 edge types).
        </p>
      </div>

      <div>
        <p className="mb-1 text-[10px] font-semibold uppercase tracking-widest text-[#58a6ff]">How anomalies are detected</p>
        <p>
          A <strong className="text-[#e6edf3]">T-HetGAT model</strong> (Temporal Heterogeneous Graph
          Attention Network) is trained on 17,657 labelled graph windows. For each 60-second time window,
          it reads the network graph and assigns every edge an{" "}
          <strong className="text-[#e6edf3]">attack probability score in [0, 1]</strong>. Edges scoring
          ≥ 0.5 are flagged as anomalous and surface as alerts.
        </p>
      </div>

      <div>
        <p className="mb-2 text-[10px] font-semibold uppercase tracking-widest text-[#58a6ff]">Sections on this page</p>
        <div className="flex flex-col gap-2">
          {[
            { title: "KPI Cards",              desc: "4 headline metrics: total nodes, total edges, anomalous connection count, and the most active communicator. Auto-refresh every 30 s. Click any card for a detailed explanation." },
            { title: "Node Type Donut",        desc: "Proportion of each entity type (Host, ExternalIP, Service, Domain, User) in the full graph. A surge in ExternalIP nodes relative to Hosts can indicate a scanning campaign." },
            { title: "Top 10 Communicators",   desc: "Bar chart of the 10 entities with the highest outbound connection count. Unusually active hosts may be compromised, scanning, or exfiltrating data." },
            { title: "Graph Statistics Breakdown", desc: "Flat grid of all node and edge type counts — same numbers as the KPI cards but together in one glanceable view." },
            { title: "Node Types / Edge Types", desc: "Detailed lists showing counts per entity type and relationship type. Useful for understanding the shape of the current graph snapshot." },
            { title: "Recent Alerts",          desc: "The 20 most recently flagged anomalous connections. Click 'View all →' to go to the full Alerts page with filter, sort, and detail panel." },
          ].map((s) => (
            <div key={s.title} className="rounded-md border border-[#30363d] bg-[#0d1117] px-3 py-2.5">
              <p className="mb-0.5 text-xs font-semibold text-[#e6edf3]">{s.title}</p>
              <p className="text-[11px] text-[#8b949e]">{s.desc}</p>
            </div>
          ))}
        </div>
      </div>

      <div>
        <p className="mb-1 text-[10px] font-semibold uppercase tracking-widest text-[#58a6ff]">Refresh behaviour</p>
        <p>
          All queries use a <strong className="text-[#e6edf3]">30-second stale time and refetch interval</strong>.
          The live status indicator (top-right of the header) shows whether the WebSocket stream to Neo4j
          is active. If it shows &ldquo;Error&rdquo;, the backend API server is likely not running.
        </p>
      </div>
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
        {/* ── KPI Cards ─────────────────────────────────────────────────── */}
        <section aria-label="Key performance indicators">
          {statsQuery.isError && (
            <ErrorState message="Failed to load graph statistics. Is the API server running?" />
          )}
          <div className="grid grid-cols-2 gap-4 xl:grid-cols-4">
            {statsQuery.isLoading ? (
              <>
                <SkeletonCard /><SkeletonCard />
                <SkeletonCard /><SkeletonCard />
              </>
            ) : (
              <>
                <KPICard
                  title="Total Nodes"
                  value={stats?.total_nodes ?? null}
                  subtitle="Hosts + IPs + Services + Domains + Users"
                  icon={<Layers size={18} />}
                  accentColor="#58a6ff"
                  onCardClick={() => openDrawer(DRAWER_TOTAL_NODES)}
                />
                <KPICard
                  title="Total Edges"
                  value={stats?.total_edges ?? null}
                  subtitle="All relationship types"
                  icon={<Network size={18} />}
                  accentColor="#3fb950"
                  onCardClick={() => openDrawer(DRAWER_TOTAL_EDGES)}
                />
                <KPICard
                  title="Anomalous Connections"
                  value={anomalousEdges.length}
                  subtitle="Attack score ≥ 0.5"
                  icon={<AlertTriangle size={18} />}
                  accentColor="#f85149"
                  onCardClick={() => openDrawer(DRAWER_ANOMALOUS)}
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
                  onCardClick={() => openDrawer(DRAWER_TOP_COMMUNICATOR)}
                />
              </>
            )}
          </div>
        </section>

        {/* ── Charts row ────────────────────────────────────────────────── */}
        <section className="grid gap-4 xl:grid-cols-2" aria-label="Analytics charts">
          {/* Node type donut */}
          <ClickableCard onClick={() => openDrawer(DRAWER_DONUT)}>
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
          </ClickableCard>

          {/* Top communicators bar */}
          <ClickableCard onClick={() => openDrawer(DRAWER_COMMUNICATORS_CHART)}>
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
          </ClickableCard>
        </section>

        {/* ── Stats breakdown ───────────────────────────────────────────── */}
        {stats != null && (
          <section aria-label="Graph statistics breakdown">
            <ClickableCard onClick={() => openDrawer(DRAWER_STATS_BREAKDOWN)}>
              <h2 className="mb-4 text-xs font-semibold uppercase tracking-widest text-[#8b949e]">
                Graph Statistics Breakdown
              </h2>
              <div className="grid grid-cols-3 gap-4 sm:grid-cols-5 lg:grid-cols-9">
                {[
                  { label: "Hosts",        value: stats.host_count,            color: "#58a6ff" },
                  { label: "Ext. IPs",     value: stats.external_ip_count,     color: "#f85149" },
                  { label: "Services",     value: stats.service_count,         color: "#3fb950" },
                  { label: "Domains",      value: stats.domain_count,          color: "#d29922" },
                  { label: "Users",        value: stats.user_count,            color: "#bc8cff" },
                  { label: "CONNECTS_TO",  value: stats.connects_to_count,     color: "#8b949e" },
                  { label: "USES_SERVICE", value: stats.uses_service_count,    color: "#8b949e" },
                  { label: "RESOLVES",     value: stats.resolves_domain_count, color: "#8b949e" },
                  { label: "AUTH_AS",      value: stats.authenticated_as_count,color: "#8b949e" },
                ].map((item) => (
                  <div key={item.label} className="flex flex-col gap-1">
                    <span className="text-lg font-bold" style={{ color: item.color }}>
                      {formatNumber(item.value)}
                    </span>
                    <span className="text-[11px] text-[#8b949e]">{item.label}</span>
                  </div>
                ))}
              </div>
            </ClickableCard>
          </section>
        )}

        {/* ── Node / Edge types + Quick Links ───────────────────────────── */}
        <section aria-label="Additional statistics">
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
            {/* Node Types */}
            <ClickableCard onClick={() => openDrawer(DRAWER_NODE_TYPES)}>
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
                    { name: "Host",       count: stats.host_count,         color: "#58a6ff" },
                    { name: "ExternalIP", count: stats.external_ip_count,  color: "#f85149" },
                    { name: "Service",    count: stats.service_count,      color: "#3fb950" },
                    { name: "Domain",     count: stats.domain_count,       color: "#d29922" },
                    { name: "User",       count: stats.user_count,         color: "#bc8cff" },
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
            </ClickableCard>

            {/* Edge Types */}
            <ClickableCard onClick={() => openDrawer(DRAWER_EDGE_TYPES)}>
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
                    { name: "CONNECTS_TO",     count: stats.connects_to_count },
                    { name: "USES_SERVICE",    count: stats.uses_service_count },
                    { name: "RESOLVES_DOMAIN", count: stats.resolves_domain_count },
                    { name: "AUTHENTICATED_AS",count: stats.authenticated_as_count },
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
            </ClickableCard>

            {/* Quick Links */}
            <ClickableCard onClick={() => openDrawer(DRAWER_QUICK_LINKS)}>
              <div className="mb-3 flex items-center gap-2">
                <Globe size={14} className="text-[#d29922]" aria-hidden="true" />
                <h2 className="text-xs font-semibold uppercase tracking-widest text-[#8b949e]">
                  Quick Links
                </h2>
              </div>
              <div className="flex flex-col gap-2">
                <Link
                  href="/alerts"
                  onClick={(e) => e.stopPropagation()}
                  className="flex items-center justify-between rounded-md px-3 py-2 text-sm text-[#58a6ff] transition-colors hover:bg-[#58a6ff]/10"
                >
                  View All Alerts
                  <AlertTriangle size={13} aria-hidden="true" />
                </Link>
                <Link
                  href="/graph"
                  onClick={(e) => e.stopPropagation()}
                  className="flex items-center justify-between rounded-md px-3 py-2 text-sm text-[#58a6ff] transition-colors hover:bg-[#58a6ff]/10"
                >
                  Open Graph Explorer
                  <Network size={13} aria-hidden="true" />
                </Link>
                <Link
                  href="/analytics"
                  onClick={(e) => e.stopPropagation()}
                  className="flex items-center justify-between rounded-md px-3 py-2 text-sm text-[#58a6ff] transition-colors hover:bg-[#58a6ff]/10"
                >
                  Analytics
                  <Activity size={13} aria-hidden="true" />
                </Link>
              </div>
            </ClickableCard>
          </div>
        </section>

        {/* ── Recent Alerts ─────────────────────────────────────────────── */}
        <section aria-label="Recent anomalous connections">
          <ClickableCard onClick={() => openDrawer(DRAWER_RECENT_ALERTS)}>
            <div className="mb-4 flex items-center justify-between">
              <h2 className="text-xs font-semibold uppercase tracking-widest text-[#8b949e]">
                Recent Alerts (last 20)
              </h2>
              <Link
                href="/alerts"
                onClick={(e) => e.stopPropagation()}
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
          </ClickableCard>
        </section>
      </div>

      {/* ── Bottom sheet info drawer ───────────────────────────────────── */}
      <InfoDrawer
        open={drawerDef != null}
        onClose={closeDrawer}
        title={drawerDef?.title ?? ""}
        icon={drawerDef?.icon}
        accentColor={drawerDef?.accentColor}
      >
        {drawerDef?.children}
      </InfoDrawer>
    </div>
  );
}
