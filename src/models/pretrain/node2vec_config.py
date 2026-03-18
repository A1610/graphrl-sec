"""
Node2Vec hyper-parameter configuration — Module 09 Baseline.

All defaults follow the original Node2Vec paper (Grover & Leskovec, 2016).
Values are tuned for the combined UNSW-NB15 + CICIDS2017 IP graph
(~19 K unique IPs, ~5.4 M directed flows across both datasets).
"""

from __future__ import annotations

from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Node2VecConfig(BaseSettings):
    """
    Hyper-parameters for the Node2Vec IP embedding baseline.

    Reads from environment variables / .env file (prefix: NODE2VEC_).
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        env_prefix="NODE2VEC_",
    )

    # ------------------------------------------------------------------
    # Embedding
    # ------------------------------------------------------------------
    embedding_dim: int = Field(
        default=64,
        ge=8,
        le=256,
        description="Dimensionality of the learned IP embedding vectors.",
    )

    # ------------------------------------------------------------------
    # Random walk
    # ------------------------------------------------------------------
    walk_length: int = Field(
        default=80,
        ge=5,
        description="Number of nodes in each random walk (Node2Vec paper default).",
    )
    context_size: int = Field(
        default=5,
        ge=1,
        description="Window size for the Skip-gram context (Node2Vec paper default).",
    )
    walks_per_node: int = Field(
        default=10,
        ge=1,
        description="Number of random walks started from each node.",
    )
    num_negative_samples: int = Field(
        default=1,
        ge=1,
        description="Negative samples per positive pair for the Skip-gram loss.",
    )
    p: float = Field(
        default=1.0,
        gt=0.0,
        description="Return parameter p (higher = BFS-like; p=1 balanced).",
    )
    q: float = Field(
        default=1.0,
        gt=0.0,
        description="In-out parameter q (lower = DFS-like; q=1 balanced).",
    )

    # ------------------------------------------------------------------
    # Training
    # ------------------------------------------------------------------
    num_epochs: int = Field(
        default=50,
        ge=1,
        description="Training epochs for the Skip-gram model.",
    )
    learning_rate: float = Field(
        default=0.01,
        gt=0.0,
        description="Learning rate for SparseAdam optimizer.",
    )
    loader_batch_size: int = Field(
        default=128,
        ge=1,
        description="Number of walk-start nodes per training batch.",
    )

    # ------------------------------------------------------------------
    # Paths
    # ------------------------------------------------------------------
    raw_unsw_dir: Path = Field(
        default=Path("data/raw/unsw"),
        description="Directory containing raw UNSW-NB15 CSV files with IP columns.",
    )
    raw_cicids_dir: Path = Field(
        default=Path("data/raw/cicids"),
        description="Directory containing CICIDS2017 CSV files with IP columns.",
    )
    output_dir: Path = Field(
        default=Path("models/baseline"),
        description="Directory where Node2Vec embeddings are saved.",
    )

    @field_validator("raw_unsw_dir", "raw_cicids_dir", "output_dir", mode="before")
    @classmethod
    def _coerce_path(cls, v: object) -> Path:
        return Path(str(v))


# Module-level singleton with all defaults
node2vec_settings = Node2VecConfig()
