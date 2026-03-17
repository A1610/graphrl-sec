"use client";

/**
 * NetworkGraph — interactive vis-network graph renderer.
 *
 * This component MUST be imported with `dynamic(..., { ssr: false })` because
 * vis-network directly accesses browser DOM APIs on module load.
 *
 * Props:
 *   - graphData     — SocGraphData (nodes + edges) to render
 *   - onNodeClick   — callback fired when the user clicks a node
 *   - selectedNodeId — optionally highlights a specific node
 *   - loading       — renders an overlay while data is fetching
 *
 * Node sizing: proportional to `event_count` property, clamped [10, 40].
 * Node colours: defined in NODE_COLORS (types/graph.ts).
 */

import { useCallback, useEffect, useRef } from "react";
// vis-data and vis-network are imported at runtime only (no SSR).
// The dynamic() wrapper in the parent page ensures this module is
// never evaluated during server-side rendering.
import { DataSet } from "vis-data";
import { Network, type Options } from "vis-network";

import type { SocGraphData, SocVisEdge, SocVisNode } from "@/types/graph";

interface NetworkGraphProps {
  graphData: SocGraphData;
  onNodeClick?: (nodeId: string) => void;
  selectedNodeId?: string | null;
  loading?: boolean;
}

// vis-network Options — typed via the `Options` import.
// The `chosen` option is intentionally set to `false` (simplest approach that
// avoids fighting with the NodeChosen callback type signatures).
const VIS_OPTIONS: Options = {
  autoResize: true,
  height: "100%",
  width: "100%",
  nodes: {
    shape: "dot",
    borderWidth: 1.5,
    chosen: false,
    font: {
      size: 10,
      color: "#e6edf3",
      face: "monospace",
    },
  },
  edges: {
    width: 1,
    color: {
      color: "#30363d",
      highlight: "#58a6ff",
      hover: "#8b949e",
    },
    smooth: {
      enabled: true,
      type: "dynamic",
      roundness: 0.5,
    },
    arrows: {
      to: {
        enabled: true,
        scaleFactor: 0.5,
      },
    },
    selectionWidth: 2,
  },
  physics: {
    enabled: true,
    solver: "forceAtlas2Based",
    forceAtlas2Based: {
      gravitationalConstant: -50,
      centralGravity: 0.005,
      springLength: 80,
      springConstant: 0.08,
      damping: 0.4,
      avoidOverlap: 0.5,
    },
    maxVelocity: 50,
    minVelocity: 0.1,
    stabilization: {
      enabled: true,
      iterations: 300,
      updateInterval: 25,
    },
  },
  interaction: {
    hover: true,
    tooltipDelay: 200,
    hideEdgesOnDrag: true,
    navigationButtons: false,
    keyboard: {
      enabled: true,
      speed: { x: 10, y: 10, zoom: 0.02 },
    },
  },
  layout: {
    improvedLayout: true,
    randomSeed: 42,
  },
};

// The DataSet type accepts records indexed by a key field.
// We pass our SocVisNode/SocVisEdge objects directly — vis-network reads the
// properties it understands and ignores extra fields.
type VisNodeRecord = SocVisNode & Record<string, unknown>;
type VisEdgeRecord = SocVisEdge & Record<string, unknown>;

export default function NetworkGraph({
  graphData,
  onNodeClick,
  selectedNodeId,
  loading = false,
}: NetworkGraphProps): React.ReactElement {
  const containerRef = useRef<HTMLDivElement>(null);
  const networkRef = useRef<Network | null>(null);
  const nodesDatasetRef = useRef<DataSet<VisNodeRecord> | null>(null);
  const edgesDatasetRef = useRef<DataSet<VisEdgeRecord> | null>(null);

  // Initialise network once on mount
  useEffect(() => {
    if (containerRef.current == null) return;

    const nodesDs = new DataSet<VisNodeRecord>([]);
    const edgesDs = new DataSet<VisEdgeRecord>([]);
    nodesDatasetRef.current = nodesDs;
    edgesDatasetRef.current = edgesDs;

    const network = new Network(
      containerRef.current,
      { nodes: nodesDs as DataSet<Record<string, unknown>>, edges: edgesDs as DataSet<Record<string, unknown>> },
      VIS_OPTIONS,
    );
    networkRef.current = network;

    return () => {
      network.destroy();
      networkRef.current = null;
      nodesDatasetRef.current = null;
      edgesDatasetRef.current = null;
    };
  }, []);

  // Register click handler
  const handleClick = useCallback(
    (params: { nodes: string[] }) => {
      if (params.nodes.length > 0 && onNodeClick != null) {
        onNodeClick(params.nodes[0]);
      }
    },
    [onNodeClick],
  );

  useEffect(() => {
    const net = networkRef.current;
    if (net == null) return;
    // vis-network's event system uses `any` internally — cast appropriately
    net.on("click", handleClick as Parameters<typeof net.on>[1]);
    return () => {
      net.off("click", handleClick as Parameters<typeof net.on>[1]);
    };
  }, [handleClick]);

  // Update graph data when props change — diff update avoids full redraws
  useEffect(() => {
    const nodesDs = nodesDatasetRef.current;
    const edgesDs = edgesDatasetRef.current;
    if (nodesDs == null || edgesDs == null) return;

    const currentNodeIds = new Set(nodesDs.getIds() as string[]);
    const newNodeIds = new Set(graphData.nodes.map((n) => n.id));

    const toRemoveNodes = [...currentNodeIds].filter((id) => !newNodeIds.has(id));
    const toAddNodes = graphData.nodes.filter(
      (n) => !currentNodeIds.has(n.id),
    ) as unknown as VisNodeRecord[];
    const toUpdateNodes = graphData.nodes.filter((n) =>
      currentNodeIds.has(n.id),
    ) as unknown as VisNodeRecord[];

    if (toRemoveNodes.length > 0) nodesDs.remove(toRemoveNodes);
    if (toAddNodes.length > 0) nodesDs.add(toAddNodes);
    if (toUpdateNodes.length > 0) nodesDs.update(toUpdateNodes);

    const currentEdgeIds = new Set(edgesDs.getIds() as string[]);
    const newEdgeIds = new Set(graphData.edges.map((e) => e.id));

    const toRemoveEdges = [...currentEdgeIds].filter((id) => !newEdgeIds.has(id));
    const toAddEdges = graphData.edges.filter(
      (e) => !currentEdgeIds.has(e.id),
    ) as unknown as VisEdgeRecord[];

    if (toRemoveEdges.length > 0) edgesDs.remove(toRemoveEdges);
    if (toAddEdges.length > 0) edgesDs.add(toAddEdges);
  }, [graphData]);

  // Highlight selected node
  useEffect(() => {
    const net = networkRef.current;
    if (net == null) return;
    if (selectedNodeId != null) {
      net.selectNodes([selectedNodeId]);
      net.focus(selectedNodeId, {
        scale: 1.2,
        animation: { duration: 600, easingFunction: "easeInOutQuad" },
      });
    } else {
      net.unselectAll();
    }
  }, [selectedNodeId]);

  return (
    <div className="relative h-full w-full bg-[#0d1117]">
      <div
        ref={containerRef}
        className="h-full w-full"
        role="img"
        aria-label="Interactive network graph showing connections between hosts"
      />

      {/* Loading overlay */}
      {loading && (
        <div
          className="absolute inset-0 flex items-center justify-center bg-[#0d1117]/80 backdrop-blur-sm"
          role="status"
          aria-live="polite"
        >
          <div className="flex flex-col items-center gap-3">
            <div className="h-8 w-8 animate-spin rounded-full border-2 border-[#30363d] border-t-[#58a6ff]" />
            <p className="text-sm text-[#8b949e]">Loading graph data…</p>
          </div>
        </div>
      )}
    </div>
  );
}
