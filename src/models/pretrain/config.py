"""
Pre-training configuration for self-supervised graph contrastive learning.

All hyperparameters are defined here as a single source of truth.
Values are tuned for an RTX 3050 4 GB VRAM laptop GPU.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class PretrainConfig(BaseSettings):
    """
    Hyperparameters for the self-supervised pre-training pipeline.

    Reads from environment variables / .env file.
    All defaults are safe for RTX 3050 4 GB VRAM.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        env_prefix="PRETRAIN_",
    )

    # ------------------------------------------------------------------
    # Model architecture
    # ------------------------------------------------------------------
    hidden_dim: int = Field(
        default=128,
        ge=32,
        le=512,
        description="Hidden dimension for all GNN layers and projections.",
    )
    projection_dim: int = Field(
        default=64,
        ge=16,
        le=256,
        description="Output dimension of the contrastive projection head.",
    )
    num_layers: int = Field(
        default=2,
        ge=1,
        le=4,
        description="Number of heterogeneous message-passing layers.",
    )

    # ------------------------------------------------------------------
    # Contrastive learning
    # ------------------------------------------------------------------
    temperature: float = Field(
        default=0.5,
        gt=0.0,
        le=2.0,
        description="NT-Xent softmax temperature (lower = sharper distribution).",
    )

    # ------------------------------------------------------------------
    # Graph augmentation
    # ------------------------------------------------------------------
    aug_feature_mask_ratio: float = Field(
        default=0.2,
        ge=0.0,
        lt=1.0,
        description="Fraction of node features to mask (set to 0) per augmentation.",
    )
    aug_edge_drop_ratio: float = Field(
        default=0.2,
        ge=0.0,
        lt=1.0,
        description="Fraction of edges to drop per augmentation.",
    )

    # ------------------------------------------------------------------
    # Training loop
    # ------------------------------------------------------------------
    num_epochs: int = Field(
        default=100,
        ge=1,
        description="Maximum number of training epochs.",
    )
    learning_rate: float = Field(
        default=1e-3,
        gt=0.0,
        description="Initial AdamW learning rate.",
    )
    weight_decay: float = Field(
        default=1e-5,
        ge=0.0,
        description="AdamW weight decay (L2 regularisation).",
    )
    early_stopping_patience: int = Field(
        default=10,
        ge=1,
        description="Stop training if validation loss does not improve for this many epochs.",
    )
    grad_clip_norm: float = Field(
        default=1.0,
        gt=0.0,
        description="Max gradient norm for gradient clipping (0 = disabled).",
    )

    # ------------------------------------------------------------------
    # Mini-batch / memory
    # ------------------------------------------------------------------
    batch_size: int = Field(
        default=4,
        ge=1,
        le=256,
        description="Number of graph window pairs per mini-batch. Keep ≤4 for 4 GB VRAM.",
    )
    num_neighbors: list[int] = Field(
        default=[15, 10],
        description="Neighbour sample counts per hop for NeighborLoader.",
    )
    mixed_precision: bool = Field(
        default=True,
        description="Use FP16 automatic mixed precision to halve VRAM usage.",
    )

    # ------------------------------------------------------------------
    # Hardware
    # ------------------------------------------------------------------
    device: str = Field(
        default="cuda",
        description="PyTorch device string: 'cuda', 'cuda:0', or 'cpu'.",
    )

    # ------------------------------------------------------------------
    # Paths
    # ------------------------------------------------------------------
    graphs_dir: Path = Field(
        default=Path("data/graphs"),
        description="Directory containing serialised PyG HeteroData snapshots.",
    )
    checkpoint_dir: Path = Field(
        default=Path("models/pretrain"),
        description="Directory where model checkpoints are saved.",
    )

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------
    val_split: float = Field(
        default=0.1,
        gt=0.0,
        lt=1.0,
        description="Fraction of windows held out for validation.",
    )
    log_every_n_epochs: int = Field(
        default=10,
        ge=1,
        description="Log training metrics every N epochs.",
    )

    @field_validator("graphs_dir", "checkpoint_dir", mode="before")
    @classmethod
    def _coerce_path(cls, v: object) -> Path:
        return Path(str(v))

    @field_validator("device", mode="before")
    @classmethod
    def _validate_device(cls, v: object) -> str:
        s = str(v).strip().lower()
        if s not in {"cuda", "cpu"} and not s.startswith("cuda:"):
            raise ValueError(
                f"device must be 'cuda', 'cuda:<N>', or 'cpu' — got {s!r}"
            )
        return s


# Module-level singleton with all defaults
pretrain_settings = PretrainConfig()
