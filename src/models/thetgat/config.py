"""
T-HetGAT hyperparameter configuration — Module 11.

All hyperparameters for the Temporal Heterogeneous Graph Attention
Network are defined here as a single source of truth.

Architecture summary
--------------------
    HeteroGraphEncoder (pretrained, Module 08)
        → HeteroTemporalGATLayer × num_layers
        → Window-level mean pooling
        → Anomaly scoring MLP → sigmoid → [0, 1]

VRAM budget (RTX 3050, 4 GB)
-----------------------------
    Model weights   :  ~3 MB
    Mini-batch      :  ~200–400 MB  (depends on batch_size + graph size)
    FP16 activations:  halved vs FP32
    Safe ceiling    :  3.5 GB usable (leave headroom for OS/driver)
"""

from __future__ import annotations

from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class THetGATConfig(BaseSettings):
    """
    Hyperparameters for T-HetGAT training and inference.

    Reads from environment variables / .env file (prefix: THETGAT_).
    All defaults are tuned for RTX 3050 4 GB VRAM.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        env_prefix="THETGAT_",
    )

    # ------------------------------------------------------------------
    # Encoder (pretrained Module 08 backbone)
    # ------------------------------------------------------------------
    hidden_dim: int = Field(
        default=128,
        ge=32,
        le=512,
        description="Hidden dimension — must match pretrained encoder.",
    )
    num_encoder_layers: int = Field(
        default=2,
        ge=1,
        le=4,
        description="SAGEConv layers in the pretrained encoder backbone.",
    )

    # ------------------------------------------------------------------
    # Temporal encoder
    # ------------------------------------------------------------------
    temporal_dim: int = Field(
        default=32,
        ge=8,
        le=128,
        description="Output dimension of the temporal edge feature encoder.",
    )

    # ------------------------------------------------------------------
    # T-HetGAT attention layers
    # ------------------------------------------------------------------
    num_gat_layers: int = Field(
        default=3,
        ge=1,
        le=6,
        description="Number of heterogeneous temporal GAT layers.",
    )
    num_heads: int = Field(
        default=4,
        ge=1,
        le=16,
        description="Multi-head attention heads per GAT layer.",
    )
    dropout: float = Field(
        default=0.1,
        ge=0.0,
        lt=1.0,
        description="Dropout probability on attention weights and activations.",
    )

    # ------------------------------------------------------------------
    # Anomaly scoring head
    # ------------------------------------------------------------------
    scorer_hidden_dim: int = Field(
        default=64,
        ge=16,
        le=256,
        description="Hidden dim of the 2-layer MLP anomaly scoring head.",
    )

    # ------------------------------------------------------------------
    # Focal loss
    # ------------------------------------------------------------------
    focal_alpha: float = Field(
        default=0.25,
        gt=0.0,
        le=1.0,
        description="Focal loss alpha — down-weights easy negatives.",
    )
    focal_gamma: float = Field(
        default=2.0,
        ge=0.0,
        le=5.0,
        description="Focal loss gamma — focusing parameter (0 = BCE).",
    )

    # ------------------------------------------------------------------
    # Training loop
    # ------------------------------------------------------------------
    num_epochs: int = Field(
        default=50,
        ge=1,
        description="Maximum training epochs.",
    )
    learning_rate: float = Field(
        default=5e-4,
        gt=0.0,
        description="AdamW initial learning rate.",
    )
    weight_decay: float = Field(
        default=1e-4,
        ge=0.0,
        description="AdamW L2 regularisation.",
    )
    warmup_epochs: int = Field(
        default=5,
        ge=0,
        description="Linear LR warmup epochs before cosine decay.",
    )
    early_stopping_patience: int = Field(
        default=10,
        ge=1,
        description="Stop if val AUROC does not improve for this many epochs.",
    )
    grad_clip_norm: float = Field(
        default=1.0,
        gt=0.0,
        description="Max gradient norm for clipping.",
    )

    # ------------------------------------------------------------------
    # Encoder fine-tuning strategy
    # ------------------------------------------------------------------
    freeze_encoder_epochs: int = Field(
        default=5,
        ge=0,
        description=(
            "Freeze pretrained encoder for this many epochs, then unfreeze. "
            "Allows the GAT layers to stabilise before the encoder adapts."
        ),
    )

    # ------------------------------------------------------------------
    # Mini-batch / memory
    # ------------------------------------------------------------------
    batch_size: int = Field(
        default=16,
        ge=1,
        le=256,
        description="Graph windows per mini-batch. Keep ≤16 for 4 GB VRAM.",
    )
    mixed_precision: bool = Field(
        default=True,
        description="Use FP16 AMP to halve VRAM usage.",
    )

    # ------------------------------------------------------------------
    # Data split
    # ------------------------------------------------------------------
    val_split: float = Field(
        default=0.1,
        gt=0.0,
        lt=1.0,
        description="Fraction of windows held out for validation.",
    )
    test_split: float = Field(
        default=0.1,
        gt=0.0,
        lt=1.0,
        description="Fraction of windows held out for final test evaluation.",
    )

    # ------------------------------------------------------------------
    # Hardware
    # ------------------------------------------------------------------
    device: str = Field(
        default="cuda",
        description="PyTorch device string: 'cuda' or 'cpu'.",
    )

    # ------------------------------------------------------------------
    # Paths
    # ------------------------------------------------------------------
    graphs_dir: Path = Field(
        default=Path("data/graphs"),
        description="Directory of serialised HeteroData window snapshots.",
    )
    pretrained_checkpoint: Path = Field(
        default=Path("models/pretrain/checkpoint_best.pt"),
        description="Path to the Module 08 pretrained encoder checkpoint.",
    )
    checkpoint_dir: Path = Field(
        default=Path("models/thetgat"),
        description="Directory where T-HetGAT checkpoints are saved.",
    )
    results_dir: Path = Field(
        default=Path("models/thetgat"),
        description="Directory where evaluation results are saved.",
    )
    log_every_n_epochs: int = Field(
        default=5,
        ge=1,
        description="Log full metrics every N epochs.",
    )

    @field_validator(
        "graphs_dir", "pretrained_checkpoint",
        "checkpoint_dir", "results_dir",
        mode="before",
    )
    @classmethod
    def _coerce_path(cls, v: object) -> Path:
        return Path(str(v))

    @field_validator("device", mode="before")
    @classmethod
    def _validate_device(cls, v: object) -> str:
        s = str(v).strip().lower()
        if s not in {"cuda", "cpu"} and not s.startswith("cuda:"):
            raise ValueError(f"device must be 'cuda', 'cuda:<N>', or 'cpu' — got {s!r}")
        return s


# Module-level singleton
thetgat_settings = THetGATConfig()
