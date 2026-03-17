"""
Graph construction configuration — loaded from environment variables.
Controls temporal windowing, memory limits, and Neo4j connectivity.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class GraphConfig(BaseSettings):
    """
    Configuration for the graph construction engine.
    All values read from .env or environment variables.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ------------------------------------------------------------------
    # Neo4j connection
    # ------------------------------------------------------------------
    neo4j_uri: str = Field(default="bolt://localhost:7687")
    neo4j_user: str = Field(default="neo4j")
    neo4j_password: str = Field(default="graphrlsec123")
    neo4j_max_connection_pool_size: int = Field(default=10, ge=1, le=100)
    neo4j_connection_timeout_s: int = Field(default=30, ge=5)
    neo4j_batch_write_size: int = Field(
        default=500,
        ge=10,
        le=5000,
        description="Number of nodes/edges per Neo4j batch write",
    )

    # ------------------------------------------------------------------
    # Temporal windowing
    # ------------------------------------------------------------------
    window_size_hours: float = Field(
        default=1.0,
        ge=0.1,
        le=72.0,
        description="Sliding window duration in hours",
    )
    window_slide_minutes: float = Field(
        default=15.0,
        ge=1.0,
        le=60.0,
        description="Slide step between consecutive windows (minutes)",
    )

    # ------------------------------------------------------------------
    # Memory / size limits (RTX 3050 — 6GB VRAM)
    # ------------------------------------------------------------------
    max_nodes_per_window: int = Field(
        default=50_000,
        ge=100,
        description="Hard cap on nodes per graph window",
    )
    max_edges_per_window: int = Field(
        default=500_000,
        ge=1000,
        description="Hard cap on edges per graph window",
    )
    max_node_degree: int = Field(
        default=5000,
        ge=10,
        description="Max edges per node — fan-out protection for DDoS hosts",
    )

    # ------------------------------------------------------------------
    # IP classification — internal network ranges
    # ------------------------------------------------------------------
    internal_ip_prefixes: list[str] = Field(
        default=["10.", "172.16.", "172.17.", "172.18.", "172.19.",
                 "172.20.", "172.21.", "172.22.", "172.23.", "172.24.",
                 "172.25.", "172.26.", "172.27.", "172.28.", "172.29.",
                 "172.30.", "172.31.", "192.168.", "127."],
        description="IP prefixes classified as internal/private network hosts",
    )

    # ------------------------------------------------------------------
    # Feature dimensions
    # ------------------------------------------------------------------
    host_feature_dim: int = Field(
        default=8,
        description="Feature vector size for Host nodes",
    )
    external_ip_feature_dim: int = Field(
        default=8,
        description="Feature vector size for ExternalIP nodes (same extractor as Host)",
    )
    service_feature_dim: int = Field(
        default=4,
        description="Feature vector size for Service nodes",
    )
    domain_feature_dim: int = Field(
        default=4,
        description="Feature vector size for Domain nodes",
    )
    edge_feature_dim: int = Field(
        default=12,
        description="Feature vector size for edges (all types)",
    )

    # ------------------------------------------------------------------
    # Snapshot serialization
    # ------------------------------------------------------------------
    graphs_dir: Path = Field(
        default=Path("data/graphs"),
        description="Directory for serialized graph snapshots",
    )
    serialize_snapshots: bool = Field(
        default=True,
        description="Save PyG HeteroData snapshots to disk",
    )

    @field_validator("graphs_dir", mode="before")
    @classmethod
    def coerce_path(cls, v: object) -> Path:
        return Path(str(v))


# Module-level singleton
graph_settings = GraphConfig()
