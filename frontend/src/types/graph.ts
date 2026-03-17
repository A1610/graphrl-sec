/**
 * vis-network node and edge type definitions for the SOC graph explorer.
 *
 * These types extend the vis-network library types with domain-specific
 * properties from the GraphRL-Sec Neo4j schema.
 */

// ---------------------------------------------------------------------------
// Node label constants
// ---------------------------------------------------------------------------

export type NodeLabel = "Host" | "ExternalIP" | "Service" | "Domain" | "User";

export const NODE_COLORS: Record<NodeLabel, string> = {
  Host: "#58a6ff",
  ExternalIP: "#f85149",
  Service: "#3fb950",
  Domain: "#d29922",
  User: "#bc8cff",
};

// ---------------------------------------------------------------------------
// Extended vis-network node — carries our domain properties.
// We define these as plain objects; vis-network accepts them at runtime.
// ---------------------------------------------------------------------------

export interface SocVisNode {
  id: string;
  label: string;
  nodeLabel: NodeLabel;
  /** Raw properties from Neo4j node */
  neo4jProperties: Record<string, unknown>;
  color: string;
  size: number;
  font: { color: string };
  borderWidth: number;
  title?: string;
}

// ---------------------------------------------------------------------------
// Extended vis-network edge
// ---------------------------------------------------------------------------

export interface SocVisEdge {
  id: string;
  from: string;
  to: string;
  relType: string;
  /** Raw properties from Neo4j relationship */
  neo4jProperties: Record<string, unknown>;
  color: { color: string; highlight: string; hover: string };
  arrows: string;
  title?: string;
}

// ---------------------------------------------------------------------------
// Graph data container passed to NetworkGraph component
// ---------------------------------------------------------------------------

export interface SocGraphData {
  nodes: SocVisNode[];
  edges: SocVisEdge[];
}

// ---------------------------------------------------------------------------
// Selected node info (shown in the sidebar panel)
// ---------------------------------------------------------------------------

export interface SelectedNodeInfo {
  entity_key: string;
  node_label: NodeLabel;
  properties: Record<string, unknown>;
}
