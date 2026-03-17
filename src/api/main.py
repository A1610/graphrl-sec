"""
GraphRL-Sec FastAPI application entry point.

Architecture:
    - Lifespan context creates the Neo4jQueryService singleton on startup
      and closes the driver connection pool on shutdown.
    - CORS is configured for the Next.js dev server at localhost:3000.
    - A WebSocket endpoint streams live graph stats every 5 seconds.
    - All domain routes are registered under /api/* prefixes.

Run with:
    uvicorn src.api.main:app --host 0.0.0.0 --port 8000 --reload
"""

from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import structlog
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from neo4j.exceptions import ServiceUnavailable

from src.api.dependencies import clear_query_service, set_query_service
from src.api.routes import alerts, graph, stats
from src.graph.neo4j_queries import Neo4jQueryService

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Lifespan — startup / shutdown
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manage the Neo4jQueryService singleton across the application lifetime."""
    log = logger.bind(component="lifespan")
    log.info("graphrl_api_starting")

    service = Neo4jQueryService()
    set_query_service(service)

    reachable = service.ping()
    if reachable:
        log.info("neo4j_connected")
    else:
        log.warning("neo4j_unreachable_at_startup")

    try:
        yield
    finally:
        log.info("graphrl_api_shutting_down")
        service.close()
        clear_query_service()
        log.info("neo4j_connection_pool_closed")


# ---------------------------------------------------------------------------
# Application factory
# ---------------------------------------------------------------------------


def create_app() -> FastAPI:
    """Construct and configure the FastAPI application."""
    application = FastAPI(
        title="GraphRL-Sec API",
        description=(
            "SOC dashboard backend for the GraphRL-Sec dissertation project. "
            "Provides graph analytics, anomaly detection, and alert management "
            "backed by a live Neo4j knowledge graph."
        ),
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    # ------------------------------------------------------------------
    # CORS — allow the Next.js dev server and production origin
    # ------------------------------------------------------------------
    application.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:3000",
            "http://127.0.0.1:3000",
        ],
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )

    # ------------------------------------------------------------------
    # Routers
    # ------------------------------------------------------------------
    application.include_router(stats.router)
    application.include_router(graph.router)
    application.include_router(alerts.router)

    # ------------------------------------------------------------------
    # Health check
    # ------------------------------------------------------------------

    @application.get(
        "/health",
        tags=["system"],
        summary="Health check",
        description="Returns API liveness and Neo4j reachability.",
    )
    async def health_check() -> dict[str, object]:
        """Lightweight liveness probe used by monitoring and the frontend status indicator."""
        from src.api.dependencies import _query_service  # noqa: PLC0415  (local import intentional)

        neo4j_ok: bool = False
        if _query_service is not None:
            try:
                neo4j_ok = _query_service.ping()
            except ServiceUnavailable:
                neo4j_ok = False

        return {"status": "ok", "neo4j": neo4j_ok}

    # ------------------------------------------------------------------
    # WebSocket — live graph stats stream
    # ------------------------------------------------------------------

    @application.websocket("/ws/graph-stats")
    async def ws_graph_stats(websocket: WebSocket) -> None:
        """
        Stream updated GraphStats every 5 seconds to connected clients.

        Message format (JSON):
        {
            "host_count": int,
            "external_ip_count": int,
            "service_count": int,
            "domain_count": int,
            "user_count": int,
            "total_nodes": int,
            "connects_to_count": int,
            "uses_service_count": int,
            "resolves_domain_count": int,
            "authenticated_as_count": int,
            "total_edges": int,
            "error": null | str
        }
        """
        from src.api.dependencies import _query_service  # noqa: PLC0415

        await websocket.accept()
        ws_log = logger.bind(component="ws_graph_stats", client=websocket.client)
        ws_log.info("ws_client_connected")

        try:
            while True:
                payload: dict[str, object]

                if _query_service is None:
                    payload = {"error": "Neo4j service unavailable"}
                else:
                    try:
                        graph_stats = _query_service.get_graph_stats()
                        payload = {
                            "host_count": graph_stats.host_count,
                            "external_ip_count": graph_stats.external_ip_count,
                            "service_count": graph_stats.service_count,
                            "domain_count": graph_stats.domain_count,
                            "user_count": graph_stats.user_count,
                            "total_nodes": graph_stats.total_nodes,
                            "connects_to_count": graph_stats.connects_to_count,
                            "uses_service_count": graph_stats.uses_service_count,
                            "resolves_domain_count": graph_stats.resolves_domain_count,
                            "authenticated_as_count": graph_stats.authenticated_as_count,
                            "total_edges": graph_stats.total_edges,
                            "error": None,
                        }
                    except ServiceUnavailable as exc:
                        ws_log.warning("ws_neo4j_unavailable", error=str(exc))
                        payload = {"error": "Neo4j database is unreachable"}

                await websocket.send_text(json.dumps(payload))
                await asyncio.sleep(5)

        except WebSocketDisconnect:
            ws_log.info("ws_client_disconnected")

    return application


app = create_app()
