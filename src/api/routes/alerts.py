"""
Alerts routes — derive security alerts from anomalous graph paths.

Alerts are synthesised from anomalous CONNECTS_TO edges returned by
Neo4jQueryService.get_anomalous_paths().  A deterministic alert ID is
generated from (src_key, dst_key, window_id) so that the same underlying
edge always produces the same alert ID across requests.

Endpoints:
    GET /api/alerts                 → PaginatedAlertResponse
    GET /api/alerts/{id}            → AlertDetailResponse (includes neighborhood)
"""

from __future__ import annotations

import hashlib
from typing import Annotated, Literal

import structlog
from fastapi import APIRouter, HTTPException, Query, status
from neo4j.exceptions import ServiceUnavailable
from pydantic import BaseModel, Field

from src.api.dependencies import QueryServiceDep
from src.api.routes.graph import EdgeResponse, NodeResponse

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/alerts", tags=["alerts"])

# Minimum score to appear in the alerts feed.
_ALERT_THRESHOLD: float = 0.3

SeverityLiteral = Literal["critical", "high", "medium", "low"]


# ---------------------------------------------------------------------------
# Severity mapping
# ---------------------------------------------------------------------------


def _score_to_severity(score: float) -> SeverityLiteral:
    """Map a continuous attack_score [0, 1] to a four-level severity label."""
    if score >= 0.8:
        return "critical"
    if score >= 0.6:
        return "high"
    if score >= 0.4:
        return "medium"
    return "low"


def _make_alert_id(src_key: str, dst_key: str, window_id: int | None) -> str:
    """
    Generate a stable, URL-safe hex alert ID from edge identity fields.

    Uses SHA-256 of the canonical string ``src|dst|window`` and returns
    the first 16 hex characters (64-bit collision space — sufficient for
    a dashboard context).
    """
    raw = f"{src_key}|{dst_key}|{window_id!s}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class AlertResponse(BaseModel):
    """A single derived security alert."""

    id: str = Field(..., description="Stable 16-char hex alert identifier")
    src_ip: str = Field(..., description="Source node entity_key")
    dst_ip: str = Field(..., description="Destination node entity_key")
    score: float = Field(..., ge=0.0, le=1.0, description="Highest attack_score of src or dst")
    severity: SeverityLiteral = Field(..., description="Severity band: critical/high/medium/low")
    protocol: str = Field(..., description="Network protocol from edge properties")
    label: str = Field(..., description="Traffic classification label from edge properties")
    window_id: int | None = Field(None, description="Time window identifier from edge properties")
    packet_count: int | None = Field(None, description="Packet count from edge properties")
    byte_count: int | None = Field(None, description="Byte count from edge properties")


class PaginatedAlertResponse(BaseModel):
    """Paginated list of alerts with total count."""

    alerts: list[AlertResponse] = Field(..., description="Page of alert objects")
    total: int = Field(..., ge=0, description="Total alerts matching the query")
    limit: int = Field(..., ge=1, description="Page size requested")
    offset: int = Field(..., ge=0, description="Page offset requested")
    has_more: bool = Field(..., description="True when more results are available beyond this page")


class AlertDetailResponse(BaseModel):
    """A single alert with the neighbourhood subgraph for the source IP."""

    alert: AlertResponse = Field(..., description="The alert itself")
    neighborhood_nodes: list[NodeResponse] = Field(
        ..., description="Nodes in the 2-hop neighbourhood of the source IP"
    )
    neighborhood_edges: list[EdgeResponse] = Field(
        ..., description="Edges in the 2-hop neighbourhood of the source IP"
    )


# ---------------------------------------------------------------------------
# Internal helper — fetch and derive all alerts
# ---------------------------------------------------------------------------


def _derive_alerts(
    service: "QueryServiceDep",  # type: ignore[valid-type]
    severity_filter: SeverityLiteral | None,
) -> list[AlertResponse]:
    """
    Query anomalous paths and convert each EdgeResult into an AlertResponse.

    The score used for each alert is the maximum of the ``attack_score``
    properties stored in the edge's ``props`` dict (keyed as
    ``src_attack_score`` / ``dst_attack_score`` if available, otherwise
    the threshold itself as a lower bound).
    """
    edges = service.get_anomalous_paths(
        score_threshold=_ALERT_THRESHOLD,
        limit=5000,
    )

    alerts: list[AlertResponse] = []
    for edge in edges:
        props = edge.properties
        # Derive the best available attack score for this edge
        src_score: float = float(props.get("src_attack_score") or props.get("attack_score") or _ALERT_THRESHOLD)
        dst_score: float = float(props.get("dst_attack_score") or _ALERT_THRESHOLD)
        score = max(src_score, dst_score)
        score = min(max(score, 0.0), 1.0)

        window_id_raw = props.get("window_id")
        window_id = int(window_id_raw) if window_id_raw is not None else None

        alert = AlertResponse(
            id=_make_alert_id(edge.src_key, edge.dst_key, window_id),
            src_ip=edge.src_key,
            dst_ip=edge.dst_key,
            score=round(score, 4),
            severity=_score_to_severity(score),
            protocol=str(props.get("protocol") or "unknown"),
            label=str(props.get("label") or "unknown"),
            window_id=window_id,
            packet_count=int(props["packet_count"]) if props.get("packet_count") is not None else None,
            byte_count=int(props["byte_count"]) if props.get("byte_count") is not None else None,
        )
        alerts.append(alert)

    # Sort by score descending — highest risk first
    alerts.sort(key=lambda a: a.score, reverse=True)

    if severity_filter is not None:
        alerts = [a for a in alerts if a.severity == severity_filter]

    return alerts


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get(
    "",
    response_model=PaginatedAlertResponse,
    summary="List security alerts",
    description=(
        "Returns paginated alerts derived from anomalous graph paths "
        "(attack_score >= 0.3). Sorted by score descending."
    ),
)
async def list_alerts(
    service: QueryServiceDep,
    limit: Annotated[
        int,
        Query(ge=1, le=200, description="Maximum alerts per page"),
    ] = 50,
    offset: Annotated[
        int,
        Query(ge=0, description="Zero-based offset into the full result set"),
    ] = 0,
    severity: Annotated[
        SeverityLiteral | None,
        Query(description="Filter to a specific severity band"),
    ] = None,
) -> PaginatedAlertResponse:
    """Return paginated alerts, optionally filtered by severity."""
    try:
        all_alerts = _derive_alerts(service, severity_filter=severity)
    except ServiceUnavailable as exc:
        logger.error("neo4j_unavailable_alerts", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Neo4j database is unreachable.",
        ) from exc

    total = len(all_alerts)
    page = all_alerts[offset : offset + limit]

    return PaginatedAlertResponse(
        alerts=page,
        total=total,
        limit=limit,
        offset=offset,
        has_more=(offset + limit) < total,
    )


@router.get(
    "/{alert_id}",
    response_model=AlertDetailResponse,
    summary="Get alert details with neighborhood graph",
    description=(
        "Returns a single alert by its stable ID along with the 2-hop "
        "neighbourhood subgraph around the source IP."
    ),
)
async def get_alert(
    alert_id: str,
    service: QueryServiceDep,
) -> AlertDetailResponse:
    """Return a single alert with its source IP neighborhood."""
    try:
        all_alerts = _derive_alerts(service, severity_filter=None)
    except ServiceUnavailable as exc:
        logger.error("neo4j_unavailable_alert_detail", alert_id=alert_id, error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Neo4j database is unreachable.",
        ) from exc

    matched = next((a for a in all_alerts if a.id == alert_id), None)
    if matched is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Alert '{alert_id}' not found.",
        )

    # Fetch 2-hop neighbourhood around the source IP
    try:
        neighborhood = service.get_neighborhood(ip=matched.src_ip, hops=2)
    except ServiceUnavailable as exc:
        logger.error(
            "neo4j_unavailable_alert_neighborhood",
            alert_id=alert_id,
            src_ip=matched.src_ip,
            error=str(exc),
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Neo4j database is unreachable.",
        ) from exc

    neighborhood_nodes = [
        NodeResponse(
            entity_key=n.entity_key,
            node_label=n.node_label,
            properties=n.properties,
        )
        for n in neighborhood.nodes
    ]
    neighborhood_edges = [
        EdgeResponse(
            src_key=e.src_key,
            dst_key=e.dst_key,
            rel_type=e.rel_type,
            properties=e.properties,
        )
        for e in neighborhood.edges
    ]

    return AlertDetailResponse(
        alert=matched,
        neighborhood_nodes=neighborhood_nodes,
        neighborhood_edges=neighborhood_edges,
    )
