/**
 * API response types — mirrors the Pydantic v2 models defined in the FastAPI backend.
 * All fields are typed strictly; no `any` is used.
 */

// ---------------------------------------------------------------------------
// Stats
// ---------------------------------------------------------------------------

export interface GraphStatsResponse {
  host_count: number;
  external_ip_count: number;
  service_count: number;
  domain_count: number;
  user_count: number;
  total_nodes: number;
  connects_to_count: number;
  uses_service_count: number;
  resolves_domain_count: number;
  authenticated_as_count: number;
  total_edges: number;
}

export interface CommunicatorResponse {
  entity_key: string;
  node_label: string;
  outbound_count: number;
  unique_destinations: number;
}

// ---------------------------------------------------------------------------
// Graph
// ---------------------------------------------------------------------------

export interface NodeResponse {
  entity_key: string;
  node_label: string;
  properties: Record<string, unknown>;
}

export interface EdgeResponse {
  src_key: string;
  dst_key: string;
  rel_type: string;
  properties: Record<string, unknown>;
}

export interface NeighborhoodResponse {
  center_ip: string;
  hops: number;
  nodes: NodeResponse[];
  edges: EdgeResponse[];
  node_count: number;
  edge_count: number;
}

export interface TimeWindowResponse {
  start_window: number;
  end_window: number;
  edges: EdgeResponse[];
  edge_count: number;
}

// ---------------------------------------------------------------------------
// Alerts
// ---------------------------------------------------------------------------

export type Severity = "critical" | "high" | "medium" | "low";

export interface AlertResponse {
  id: string;
  src_ip: string;
  dst_ip: string;
  score: number;
  severity: Severity;
  protocol: string;
  label: string;
  window_id: number | null;
  packet_count: number | null;
  byte_count: number | null;
}

export interface PaginatedAlertResponse {
  alerts: AlertResponse[];
  total: number;
  limit: number;
  offset: number;
  has_more: boolean;
}

export interface AlertDetailResponse {
  alert: AlertResponse;
  neighborhood_nodes: NodeResponse[];
  neighborhood_edges: EdgeResponse[];
}

// ---------------------------------------------------------------------------
// Health
// ---------------------------------------------------------------------------

export interface HealthResponse {
  status: "ok" | "error";
  neo4j: boolean;
}
