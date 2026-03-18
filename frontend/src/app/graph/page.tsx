"use client";

/**
 * Graph Explorer page — full-height interactive vis-network graph.
 *
 * Features:
 *   - On load: fetches anomalous paths (threshold=0.3, limit=300)
 *   - Left panel: IP search, filter controls
 *   - Right panel: selected node properties + neighborhood
 *   - Node click → loads 2-hop neighborhood and shows it in right panel
 *   - Legend: colour-coded node types
 *   - NetworkGraph is loaded dynamically (SSR disabled) — vis-network requires DOM
 */

import dynamic from "next/dynamic";
import { useCallback, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, Info, Search, X } from "lucide-react";

import Header from "@/components/layout/Header";

import apiClient from "@/lib/api";
import { cn, formatNumber } from "@/lib/utils";
import type { EdgeResponse, NeighborhoodResponse } from "@/types/api";
import type {
  NodeLabel,
  SelectedNodeInfo,
  SocGraphData,
  SocVisEdge,
  SocVisNode,
} from "@/types/graph";
import { NODE_COLORS } from "@/types/graph";

// Dynamic import — prevents SSR crash from vis-network DOM access
const NetworkGraph = dynamic(
  () => import("@/components/graph/NetworkGraph"),
  { ssr: false },
);

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const ANOMALOUS_THRESHOLD = 0.3;
const ANOMALOUS_LIMIT = 300;
const NODE_SIZE_MIN = 10;
const NODE_SIZE_MAX = 40;

const KNOWN_NODE_LABELS: NodeLabel[] = [
  "Host",
  "ExternalIP",
  "Service",
  "Domain",
  "User",
];

// ---------------------------------------------------------------------------
// Graph data conversion helpers
// ---------------------------------------------------------------------------

function nodeSize(eventCount: unknown): number {
  if (typeof eventCount !== "number" || isNaN(eventCount)) return 16;
  const clamped = Math.min(Math.max(eventCount, 0), 1000);
  return NODE_SIZE_MIN + (clamped / 1000) * (NODE_SIZE_MAX - NODE_SIZE_MIN);
}

function inferNodeLabel(entityKey: string): NodeLabel {
  // Heuristic: IPs starting with private ranges are Hosts, others ExternalIP
  if (
    entityKey.startsWith("10.") ||
    entityKey.startsWith("192.168.") ||
    entityKey.match(/^172\.(1[6-9]|2\d|3[01])\./)
  ) {
    return "Host";
  }
  if (entityKey.match(/^\d+\.\d+\.\d+\.\d+$/)) return "ExternalIP";
  if (entityKey.match(/^\d+$/)) return "Service";
  if (entityKey.includes(".") && !entityKey.match(/^\d/)) return "Domain";
  return "Host";
}

function edgesToGraphData(
  edges: EdgeResponse[],
  nodeLabels: Record<string, NodeLabel>,
): SocGraphData {
  const nodesMap = new Map<string, SocVisNode>();
  const edgesArr: SocVisEdge[] = [];

  for (const edge of edges) {
    for (const key of [edge.src_key, edge.dst_key]) {
      if (!nodesMap.has(key)) {
        const label = nodeLabels[key] ?? inferNodeLabel(key);
        const color = NODE_COLORS[label] ?? "#8b949e";
        const eventCount = typeof edge.properties.event_count === "number"
          ? edge.properties.event_count
          : undefined;

        nodesMap.set(key, {
          id: key,
          label: key,
          nodeLabel: label,
          neo4jProperties: {},
          color,
          size: nodeSize(eventCount),
          font: { color: "#e6edf3" },
          borderWidth: 1.5,
          title: `${label}: ${key}`,
        });
      }
    }

    const edgeId = `${edge.src_key}→${edge.dst_key}`;
    if (!edgesArr.some((e) => e.id === edgeId)) {
      edgesArr.push({
        id: edgeId,
        from: edge.src_key,
        to: edge.dst_key,
        relType: edge.rel_type,
        neo4jProperties: edge.properties,
        color: { color: "#30363d", highlight: "#58a6ff", hover: "#8b949e" },
        arrows: "to",
        title: `${edge.rel_type} · protocol: ${edge.properties.protocol ?? "?"} · label: ${edge.properties.label ?? "?"}`,
      });
    }
  }

  return { nodes: [...nodesMap.values()], edges: edgesArr };
}

function neighborhoodToGraphData(result: NeighborhoodResponse): SocGraphData {
  const nodes: SocVisNode[] = result.nodes.map((n) => {
    const label = (n.node_label as NodeLabel) ?? inferNodeLabel(n.entity_key);
    const color = NODE_COLORS[label] ?? "#8b949e";
    const eventCount = typeof n.properties.event_count === "number"
      ? n.properties.event_count
      : undefined;
    return {
      id: n.entity_key,
      label: n.entity_key,
      nodeLabel: label,
      neo4jProperties: n.properties,
      color,
      size: nodeSize(eventCount),
      font: { color: "#e6edf3" },
      borderWidth: 1.5,
      title: `${label}: ${n.entity_key}`,
    };
  });

  const edges: SocVisEdge[] = result.edges.map((e) => ({
    id: `${e.src_key}→${e.dst_key}`,
    from: e.src_key,
    to: e.dst_key,
    relType: e.rel_type,
    neo4jProperties: e.properties,
    color: { color: "#30363d", highlight: "#58a6ff", hover: "#8b949e" },
    arrows: "to",
    title: `${e.rel_type}`,
  }));

  return { nodes, edges };
}

// ---------------------------------------------------------------------------
// Query functions
// ---------------------------------------------------------------------------

async function fetchAnomalousEdges(): Promise<EdgeResponse[]> {
  const { data } = await apiClient.get<EdgeResponse[]>("/api/graph/anomalous", {
    params: { threshold: ANOMALOUS_THRESHOLD, limit: ANOMALOUS_LIMIT },
  });
  return data;
}

async function fetchNeighborhood(ip: string): Promise<NeighborhoodResponse> {
  const { data } = await apiClient.get<NeighborhoodResponse>(
    "/api/graph/neighborhood",
    { params: { ip, hops: 2 } },
  );
  return data;
}

// ---------------------------------------------------------------------------
// Node properties panel
// ---------------------------------------------------------------------------

interface NodePanelProps {
  nodeInfo: SelectedNodeInfo;
  onClose: () => void;
  neighborhoodLoading: boolean;
  neighborhoodError: boolean;
  neighborhoodData: NeighborhoodResponse | null | undefined;
}

function NodePanel({
  nodeInfo,
  onClose,
  neighborhoodLoading,
  neighborhoodError,
  neighborhoodData,
}: NodePanelProps): React.ReactElement {
  const color = NODE_COLORS[nodeInfo.node_label] ?? "#8b949e";

  return (
    <aside
      className="flex h-full w-80 flex-col border-l border-[#30363d] bg-[#161b22]"
      aria-label="Selected node details"
    >
      <div className="flex items-center justify-between border-b border-[#30363d] px-4 py-3">
        <div className="flex items-center gap-2">
          <span
            className="h-2.5 w-2.5 rounded-full"
            style={{ backgroundColor: color }}
            aria-hidden="true"
          />
          <h2 className="text-sm font-semibold text-[#e6edf3]">
            {nodeInfo.node_label}
          </h2>
        </div>
        <button
          type="button"
          onClick={onClose}
          className="rounded p-1 text-[#8b949e] transition-colors hover:bg-[#30363d] hover:text-[#e6edf3]"
          aria-label="Close node details panel"
        >
          <X size={16} aria-hidden="true" />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto px-4 py-4">
        {/* Entity key */}
        <div className="mb-4 rounded-md border border-[#30363d] bg-[#0d1117] px-3 py-2">
          <p className="mb-0.5 text-[10px] font-semibold uppercase tracking-widest text-[#8b949e]">
            Entity Key
          </p>
          <p className="break-all font-mono text-sm text-[#e6edf3]">
            {nodeInfo.entity_key}
          </p>
        </div>

        {/* Properties */}
        {Object.keys(nodeInfo.properties).length > 0 && (
          <div className="mb-4 flex flex-col gap-1">
            <p className="mb-1 text-[10px] font-semibold uppercase tracking-widest text-[#8b949e]">
              Properties
            </p>
            {Object.entries(nodeInfo.properties)
              .filter(([, v]) => v !== null && v !== undefined)
              .map(([key, value]) => (
                <div
                  key={key}
                  className="flex items-center justify-between rounded px-2 py-1 hover:bg-[#30363d]/20"
                >
                  <span className="text-xs text-[#8b949e]">{key}</span>
                  <span className="max-w-[140px] truncate font-mono text-xs text-[#e6edf3]">
                    {String(value)}
                  </span>
                </div>
              ))}
          </div>
        )}

        {/* Neighborhood summary */}
        <div className="flex flex-col gap-1">
          <p className="mb-1 text-[10px] font-semibold uppercase tracking-widest text-[#8b949e]">
            2-hop Neighborhood
          </p>
          {neighborhoodLoading && (
            <div className="flex flex-col gap-2">
              {[...Array(3)].map((_, i) => (
                <div
                  key={i}
                  className="h-4 animate-pulse rounded bg-[#30363d]/60"
                />
              ))}
            </div>
          )}
          {neighborhoodError && (
            <div
              className="flex items-center gap-2 rounded border border-[#f85149]/30 bg-[#f85149]/10 px-3 py-2 text-xs text-[#f85149]"
              role="alert"
            >
              <AlertTriangle size={12} aria-hidden="true" />
              Could not load neighborhood.
            </div>
          )}
          {neighborhoodData != null && (
            <div className="flex gap-4">
              <div className="flex flex-col">
                <span className="text-lg font-bold text-[#e6edf3]">
                  {formatNumber(neighborhoodData.node_count)}
                </span>
                <span className="text-[11px] text-[#8b949e]">nodes</span>
              </div>
              <div className="flex flex-col">
                <span className="text-lg font-bold text-[#e6edf3]">
                  {formatNumber(neighborhoodData.edge_count)}
                </span>
                <span className="text-[11px] text-[#8b949e]">edges</span>
              </div>
            </div>
          )}
        </div>
      </div>
    </aside>
  );
}

// ---------------------------------------------------------------------------
// Legend
// ---------------------------------------------------------------------------

function GraphLegend(): React.ReactElement {
  return (
    <div className="absolute bottom-4 left-4 flex flex-col gap-1.5 rounded-lg border border-[#30363d] bg-[#161b22]/90 px-3 py-3 backdrop-blur-sm">
      <p className="mb-0.5 text-[10px] font-semibold uppercase tracking-widest text-[#8b949e]">
        Node Types
      </p>
      {KNOWN_NODE_LABELS.map((label) => (
        <div key={label} className="flex items-center gap-2">
          <span
            className="h-2 w-2 shrink-0 rounded-full"
            style={{ backgroundColor: NODE_COLORS[label] }}
            aria-hidden="true"
          />
          <span className="text-xs text-[#e6edf3]">{label}</span>
        </div>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function GraphPage(): React.ReactElement {
  const [searchInput, setSearchInput] = useState("");
  const [searchedIp, setSearchedIp] = useState<string | null>(null);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [selectedNodeInfo, setSelectedNodeInfo] =
    useState<SelectedNodeInfo | null>(null);

  // Anomalous edges query — initial graph load
  const anomalousQuery = useQuery({
    queryKey: ["anomalous-graph", ANOMALOUS_THRESHOLD, ANOMALOUS_LIMIT],
    queryFn: fetchAnomalousEdges,
    staleTime: 60_000,
  });

  // Neighborhood query — triggered on node click or IP search
  const neighborhoodQuery = useQuery({
    queryKey: ["neighborhood-graph", searchedIp ?? selectedNodeId, 2],
    queryFn: () => fetchNeighborhood((searchedIp ?? selectedNodeId)!),
    enabled: searchedIp != null || selectedNodeId != null,
    staleTime: 60_000,
  });

  // Convert edge data to vis-network graph data
  const baseGraphData = useMemo<SocGraphData>(() => {
    if (anomalousQuery.data == null) return { nodes: [], edges: [] };
    return edgesToGraphData(anomalousQuery.data, {});
  }, [anomalousQuery.data]);

  // If a neighborhood was loaded, overlay it on the base graph
  const graphData = useMemo<SocGraphData>(() => {
    if (neighborhoodQuery.data == null) return baseGraphData;
    const nbGraph = neighborhoodToGraphData(neighborhoodQuery.data);

    // Merge: combine nodes and edges, deduplicating by id
    const nodeMap = new Map<string, SocVisNode>(
      baseGraphData.nodes.map((n) => [n.id as string, n]),
    );
    for (const n of nbGraph.nodes) {
      nodeMap.set(n.id as string, n);
    }

    const edgeMap = new Map<string, SocVisEdge>(
      baseGraphData.edges.map((e) => [e.id as string, e]),
    );
    for (const e of nbGraph.edges) {
      edgeMap.set(e.id as string, e);
    }

    return {
      nodes: [...nodeMap.values()],
      edges: [...edgeMap.values()],
    };
  }, [baseGraphData, neighborhoodQuery.data]);

  const handleNodeClick = useCallback(
    (nodeId: string) => {
      setSelectedNodeId(nodeId);
      setSearchedIp(null);

      // Find properties from existing graph data
      const node = graphData.nodes.find((n) => n.id === nodeId);
      if (node != null) {
        setSelectedNodeInfo({
          entity_key: node.id as string,
          node_label: node.nodeLabel,
          properties: node.neo4jProperties,
        });
      }
    },
    [graphData.nodes],
  );

  const handleSearch = () => {
    const trimmed = searchInput.trim();
    if (trimmed.length === 0) return;
    setSearchedIp(trimmed);
    setSelectedNodeId(trimmed);
    setSelectedNodeInfo(null);
  };

  const handleSearchKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter") handleSearch();
  };

  const handleClearSelection = () => {
    setSelectedNodeId(null);
    setSelectedNodeInfo(null);
    setSearchedIp(null);
    setSearchInput("");
  };

  const isLoading = anomalousQuery.isLoading;
  const isError = anomalousQuery.isError;

  return (
    <div className="flex h-full flex-col overflow-hidden">
      <Header
        title="Graph Explorer"
        subtitle="Interactive network topology visualization"
        infoContent={
          <div className="flex flex-col gap-3">
            <p>
              The <strong className="text-[#e6edf3]">Graph Explorer</strong> renders
              the network knowledge graph as an interactive force-directed diagram
              using vis-network.
            </p>
            <p>
              On load, it shows the top{" "}
              <strong className="text-[#e6edf3]">300 anomalous edges</strong> (attack
              score ≥ 0.3) detected by the T-HetGAT model.
            </p>
            <ul className="list-disc pl-4 flex flex-col gap-1">
              <li><strong className="text-[#e6edf3]">Click a node</strong> — loads its 2-hop neighborhood and shows properties in the right panel</li>
              <li><strong className="text-[#e6edf3]">Search by IP</strong> — type an IP address and press Enter to focus on that entity</li>
              <li><strong className="text-[#e6edf3]">Scroll</strong> — zoom in/out</li>
              <li><strong className="text-[#e6edf3]">Drag</strong> — pan the canvas or reposition nodes</li>
            </ul>
            <p>Node size scales with connection count. Colors indicate node type (see legend at bottom-left).</p>
          </div>
        }
      />

      {/* Error banner */}
      {isError && (
        <div
          className="flex items-center gap-3 border-b border-[#f85149]/30 bg-[#f85149]/10 px-6 py-2 text-sm text-[#f85149]"
          role="alert"
          aria-live="assertive"
        >
          <AlertTriangle size={14} aria-hidden="true" />
          Failed to load graph data. Is the API server running?
        </div>
      )}

      <div className="flex flex-1 overflow-hidden">
        {/* Controls sidebar */}
        <div className="flex w-64 flex-col gap-4 border-r border-[#30363d] bg-[#161b22] px-4 py-4">
          {/* Search */}
          <div className="flex flex-col gap-2">
            <label
              htmlFor="ip-search"
              className="text-[10px] font-semibold uppercase tracking-widest text-[#8b949e]"
            >
              Search by IP
            </label>
            <div className="flex gap-1.5">
              <input
                id="ip-search"
                type="text"
                value={searchInput}
                onChange={(e) => setSearchInput(e.target.value)}
                onKeyDown={handleSearchKeyDown}
                placeholder="e.g. 192.168.1.1"
                className="min-w-0 flex-1 rounded border border-[#30363d] bg-[#0d1117] px-2.5 py-1.5 text-xs text-[#e6edf3] placeholder-[#8b949e]/60 outline-none focus:border-[#58a6ff] focus:ring-1 focus:ring-[#58a6ff]/30"
                aria-label="Search graph by IP address"
              />
              <button
                type="button"
                onClick={handleSearch}
                className="rounded border border-[#30363d] bg-[#0d1117] px-2.5 py-1.5 text-[#8b949e] transition-colors hover:border-[#58a6ff] hover:text-[#58a6ff]"
                aria-label="Execute IP search"
              >
                <Search size={13} aria-hidden="true" />
              </button>
            </div>
          </div>

          {/* Graph stats */}
          <div className="flex flex-col gap-1 rounded-md border border-[#30363d] bg-[#0d1117] px-3 py-3">
            <p className="mb-1 text-[10px] font-semibold uppercase tracking-widest text-[#8b949e]">
              Current View
            </p>
            <div className="flex items-center justify-between">
              <span className="text-xs text-[#8b949e]">Nodes</span>
              <span className="text-xs font-semibold text-[#e6edf3]">
                {formatNumber(graphData.nodes.length)}
              </span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-xs text-[#8b949e]">Edges</span>
              <span className="text-xs font-semibold text-[#e6edf3]">
                {formatNumber(graphData.edges.length)}
              </span>
            </div>
            {neighborhoodQuery.isFetching && (
              <p className="mt-1 text-[10px] text-[#58a6ff]">
                Loading neighborhood…
              </p>
            )}
          </div>

          {/* Selected node summary */}
          {selectedNodeInfo != null && (
            <div className="flex flex-col gap-1 rounded-md border border-[#30363d] bg-[#0d1117] px-3 py-3">
              <div className="flex items-center justify-between">
                <p className="text-[10px] font-semibold uppercase tracking-widest text-[#8b949e]">
                  Selected Node
                </p>
                <button
                  type="button"
                  onClick={handleClearSelection}
                  className="text-[#8b949e] hover:text-[#e6edf3]"
                  aria-label="Clear node selection"
                >
                  <X size={12} aria-hidden="true" />
                </button>
              </div>
              <p className="break-all font-mono text-xs text-[#e6edf3]">
                {selectedNodeInfo.entity_key}
              </p>
              <p
                className="text-[11px]"
                style={{ color: NODE_COLORS[selectedNodeInfo.node_label] ?? "#8b949e" }}
              >
                {selectedNodeInfo.node_label}
              </p>
            </div>
          )}

          {/* Info tip */}
          <div className="mt-auto flex items-start gap-2 rounded-md border border-[#30363d] bg-[#0d1117] px-3 py-2">
            <Info size={12} className="mt-0.5 shrink-0 text-[#8b949e]" aria-hidden="true" />
            <p className="text-[11px] text-[#8b949e]">
              Click a node to explore its 2-hop neighborhood. Scroll to zoom.
            </p>
          </div>
        </div>

        {/* Graph canvas */}
        <div className="relative flex-1 overflow-hidden">
          <NetworkGraph
            graphData={graphData}
            onNodeClick={handleNodeClick}
            selectedNodeId={selectedNodeId}
            loading={isLoading}
          />
          <GraphLegend />
        </div>

        {/* Node detail panel */}
        {selectedNodeInfo != null && (
          <NodePanel
            nodeInfo={selectedNodeInfo}
            onClose={handleClearSelection}
            neighborhoodLoading={neighborhoodQuery.isFetching}
            neighborhoodError={neighborhoodQuery.isError}
            neighborhoodData={neighborhoodQuery.data}
          />
        )}
      </div>
    </div>
  );
}
