"""
Stats routes — aggregate graph statistics and top communicators.

Endpoints:
    GET /api/stats                          → GraphStats
    GET /api/stats/top-communicators        → list[CommunicatorResponse]
"""

from __future__ import annotations

from typing import Annotated

import structlog
from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from src.api.dependencies import QueryServiceDep
from neo4j.exceptions import ServiceUnavailable

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/stats", tags=["stats"])


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class GraphStatsResponse(BaseModel):
    """Aggregate node and edge counts for the entire database."""

    host_count: int = Field(..., ge=0, description="Number of Host nodes")
    external_ip_count: int = Field(..., ge=0, description="Number of ExternalIP nodes")
    service_count: int = Field(..., ge=0, description="Number of Service nodes")
    domain_count: int = Field(..., ge=0, description="Number of Domain nodes")
    user_count: int = Field(..., ge=0, description="Number of User nodes")
    total_nodes: int = Field(..., ge=0, description="Sum of all node counts")
    connects_to_count: int = Field(..., ge=0, description="Number of CONNECTS_TO edges")
    uses_service_count: int = Field(..., ge=0, description="Number of USES_SERVICE edges")
    resolves_domain_count: int = Field(..., ge=0, description="Number of RESOLVES_DOMAIN edges")
    authenticated_as_count: int = Field(..., ge=0, description="Number of AUTHENTICATED_AS edges")
    total_edges: int = Field(..., ge=0, description="Sum of all edge counts")


class CommunicatorResponse(BaseModel):
    """A host ranked by outbound connection volume."""

    entity_key: str = Field(..., description="Unique node identifier (IP address or similar)")
    node_label: str = Field(..., description="Neo4j label: Host, ExternalIP, etc.")
    outbound_count: int = Field(..., ge=0, description="Total outbound CONNECTS_TO relationships")
    unique_destinations: int = Field(..., ge=0, description="Distinct destination entity_keys")


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get(
    "",
    response_model=GraphStatsResponse,
    summary="Get aggregate graph statistics",
    description="Returns node and edge counts for all types in the Neo4j database.",
)
async def get_stats(service: QueryServiceDep) -> GraphStatsResponse:
    """Return graph-wide node and edge counts."""
    try:
        stats = service.get_graph_stats()
    except ServiceUnavailable as exc:
        logger.error("neo4j_unavailable_stats", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Neo4j database is unreachable.",
        ) from exc

    return GraphStatsResponse(
        host_count=stats.host_count,
        external_ip_count=stats.external_ip_count,
        service_count=stats.service_count,
        domain_count=stats.domain_count,
        user_count=stats.user_count,
        total_nodes=stats.total_nodes,
        connects_to_count=stats.connects_to_count,
        uses_service_count=stats.uses_service_count,
        resolves_domain_count=stats.resolves_domain_count,
        authenticated_as_count=stats.authenticated_as_count,
        total_edges=stats.total_edges,
    )


@router.get(
    "/top-communicators",
    response_model=list[CommunicatorResponse],
    summary="Get top communicators by outbound connection count",
    description="Returns hosts ranked by number of outbound CONNECTS_TO edges.",
)
async def get_top_communicators(
    service: QueryServiceDep,
    limit: Annotated[
        int,
        Query(ge=1, le=100, description="Maximum number of hosts to return"),
    ] = 20,
) -> list[CommunicatorResponse]:
    """Return top N hosts by outbound connection count."""
    try:
        communicators = service.get_top_communicators(limit=limit)
    except ServiceUnavailable as exc:
        logger.error("neo4j_unavailable_top_comm", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Neo4j database is unreachable.",
        ) from exc

    return [
        CommunicatorResponse(
            entity_key=c.entity_key,
            node_label=c.node_label,
            outbound_count=c.outbound_count,
            unique_destinations=c.unique_destinations,
        )
        for c in communicators
    ]
