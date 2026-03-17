"""
Graph routes — subgraph queries for SOC visualization.

Endpoints:
    GET /api/graph/neighborhood     → NeighborhoodResponse
    GET /api/graph/anomalous        → list[EdgeResponse]
    GET /api/graph/time-window      → TimeWindowResponse
"""

from __future__ import annotations

from typing import Annotated, Any

import structlog
from fastapi import APIRouter, HTTPException, Query, status
from neo4j.exceptions import ServiceUnavailable
from pydantic import BaseModel, Field

from src.api.dependencies import QueryServiceDep

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/graph", tags=["graph"])


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class NodeResponse(BaseModel):
    """A single graph node with its properties."""

    entity_key: str = Field(..., description="Unique node identifier")
    node_label: str = Field(..., description="Neo4j label: Host, ExternalIP, Service, Domain, User")
    properties: dict[str, Any] = Field(default_factory=dict, description="All node properties")


class EdgeResponse(BaseModel):
    """A single graph relationship with its properties."""

    src_key: str = Field(..., description="Source node entity_key")
    dst_key: str = Field(..., description="Destination node entity_key")
    rel_type: str = Field(..., description="Relationship type (e.g., CONNECTS_TO)")
    properties: dict[str, Any] = Field(default_factory=dict, description="All edge properties")


class NeighborhoodResponse(BaseModel):
    """N-hop subgraph centred on a specific IP address."""

    center_ip: str = Field(..., description="The IP address used as the traversal centre")
    hops: int = Field(..., ge=1, le=4, description="Actual hop depth queried")
    nodes: list[NodeResponse] = Field(..., description="All nodes in the subgraph")
    edges: list[EdgeResponse] = Field(..., description="All edges in the subgraph")
    node_count: int = Field(..., ge=0, description="Number of nodes returned")
    edge_count: int = Field(..., ge=0, description="Number of edges returned")


class TimeWindowResponse(BaseModel):
    """All CONNECTS_TO edges in a window_id range."""

    start_window: int = Field(..., description="Inclusive minimum window_id queried")
    end_window: int = Field(..., description="Inclusive maximum window_id queried")
    edges: list[EdgeResponse] = Field(..., description="Edges within the window range")
    edge_count: int = Field(..., ge=0, description="Number of edges returned")


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get(
    "/neighborhood",
    response_model=NeighborhoodResponse,
    summary="Get N-hop neighborhood subgraph",
    description="Returns nodes and edges within N hops of the specified IP address.",
)
async def get_neighborhood(
    service: QueryServiceDep,
    ip: Annotated[str, Query(min_length=1, description="IP address or entity_key to centre on")],
    hops: Annotated[
        int,
        Query(ge=1, le=4, description="Number of relationship hops to traverse"),
    ] = 2,
) -> NeighborhoodResponse:
    """Return the N-hop subgraph around a specific IP."""
    try:
        result = service.get_neighborhood(ip=ip, hops=hops)
    except ServiceUnavailable as exc:
        logger.error("neo4j_unavailable_neighborhood", ip=ip, error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Neo4j database is unreachable.",
        ) from exc

    if not result.nodes:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No nodes found for IP '{ip}'. Verify the entity_key exists in the graph.",
        )

    return NeighborhoodResponse(
        center_ip=result.center_ip,
        hops=result.hops,
        nodes=[
            NodeResponse(
                entity_key=n.entity_key,
                node_label=n.node_label,
                properties=n.properties,
            )
            for n in result.nodes
        ],
        edges=[
            EdgeResponse(
                src_key=e.src_key,
                dst_key=e.dst_key,
                rel_type=e.rel_type,
                properties=e.properties,
            )
            for e in result.edges
        ],
        node_count=len(result.nodes),
        edge_count=len(result.edges),
    )


@router.get(
    "/anomalous",
    response_model=list[EdgeResponse],
    summary="Get anomalous connection edges",
    description=(
        "Returns CONNECTS_TO edges where the source or destination node has an "
        "attack_score at or above the specified threshold."
    ),
)
async def get_anomalous_paths(
    service: QueryServiceDep,
    threshold: Annotated[
        float,
        Query(ge=0.0, le=1.0, description="Minimum attack_score to qualify as anomalous"),
    ] = 0.5,
    limit: Annotated[
        int,
        Query(ge=1, le=5000, description="Maximum number of edges to return"),
    ] = 500,
) -> list[EdgeResponse]:
    """Return edges involving nodes with high attack scores."""
    try:
        edges = service.get_anomalous_paths(score_threshold=threshold, limit=limit)
    except ServiceUnavailable as exc:
        logger.error("neo4j_unavailable_anomalous", threshold=threshold, error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Neo4j database is unreachable.",
        ) from exc

    return [
        EdgeResponse(
            src_key=e.src_key,
            dst_key=e.dst_key,
            rel_type=e.rel_type,
            properties=e.properties,
        )
        for e in edges
    ]


@router.get(
    "/time-window",
    response_model=TimeWindowResponse,
    summary="Get edges in a window_id range",
    description="Returns all CONNECTS_TO edges whose window_id falls within [min_window, max_window].",
)
async def get_time_window(
    service: QueryServiceDep,
    min_window: Annotated[
        int,
        Query(ge=0, description="Inclusive lower bound on window_id"),
    ] = 0,
    max_window: Annotated[
        int,
        Query(ge=0, description="Inclusive upper bound on window_id"),
    ] = 9999,
    limit: Annotated[
        int,
        Query(ge=1, le=10000, description="Maximum number of edges to return"),
    ] = 1000,
) -> TimeWindowResponse:
    """Return edges whose window_id is within the specified range."""
    if min_window > max_window:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"min_window ({min_window}) must be less than or equal to "
                f"max_window ({max_window})."
            ),
        )

    try:
        result = service.get_time_window_edges(
            min_window_id=min_window,
            max_window_id=max_window,
            limit=limit,
        )
    except ServiceUnavailable as exc:
        logger.error(
            "neo4j_unavailable_time_window",
            min_window=min_window,
            max_window=max_window,
            error=str(exc),
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Neo4j database is unreachable.",
        ) from exc

    return TimeWindowResponse(
        start_window=min_window,
        end_window=max_window,
        edges=[
            EdgeResponse(
                src_key=e.src_key,
                dst_key=e.dst_key,
                rel_type=e.rel_type,
                properties=e.properties,
            )
            for e in result.edges
        ],
        edge_count=len(result.edges),
    )
