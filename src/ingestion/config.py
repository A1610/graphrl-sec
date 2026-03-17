"""
Ingestion pipeline configuration — loaded from environment variables.
All settings validated at startup via Pydantic Settings.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class IngestionConfig(BaseSettings):
    """
    Configuration for the data ingestion pipeline.
    Values are read from environment variables or .env file.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ------------------------------------------------------------------
    # Kafka / Redpanda
    # ------------------------------------------------------------------
    kafka_bootstrap_servers: str = Field(
        default="localhost:9092",
        description="Comma-separated Kafka broker addresses",
    )
    kafka_topic_normalized_events: str = Field(
        default="normalized-events",
        description="Topic where normalized UnifiedEvents are published",
    )
    kafka_topic_raw_events: str = Field(
        default="raw-events",
        description="Topic for raw unparsed events (debugging)",
    )
    kafka_producer_batch_size: int = Field(
        default=16384,
        ge=1024,
        le=1_048_576,
        description="Kafka producer batch size in bytes",
    )
    kafka_producer_linger_ms: int = Field(
        default=5,
        ge=0,
        le=1000,
        description="Time to wait before flushing batch (ms)",
    )
    kafka_producer_compression: Literal["none", "gzip", "snappy", "lz4", "zstd"] = Field(
        default="lz4",
        description="Kafka message compression codec",
    )
    kafka_producer_acks: Literal["0", "1", "all"] = Field(
        default="1",
        description="Kafka producer acknowledgement level",
    )

    # ------------------------------------------------------------------
    # Ingestion rate control
    # ------------------------------------------------------------------
    ingestion_rate_limit: int = Field(
        default=1000,
        ge=1,
        le=100_000,
        description="Maximum events per second to publish to Kafka",
    )
    ingestion_chunk_size: int = Field(
        default=50_000,
        ge=1000,
        le=1_000_000,
        description="Rows per chunk when reading large CSV files",
    )

    # ------------------------------------------------------------------
    # Data paths
    # ------------------------------------------------------------------
    data_raw_dir: Path = Field(
        default=Path("data/raw"),
        description="Root directory for raw dataset files",
    )
    data_processed_dir: Path = Field(
        default=Path("data/processed"),
        description="Root directory for processed/cached files",
    )

    # ------------------------------------------------------------------
    # Deduplication
    # ------------------------------------------------------------------
    dedup_enabled: bool = Field(
        default=True,
        description="Enable event deduplication using SHA-256 hash",
    )

    # ------------------------------------------------------------------
    # Logging
    # ------------------------------------------------------------------
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = Field(
        default="INFO",
    )

    @field_validator("data_raw_dir", "data_processed_dir", mode="before")
    @classmethod
    def coerce_path(cls, v: object) -> Path:
        return Path(str(v))


# Module-level singleton — import this everywhere
settings = IngestionConfig()
