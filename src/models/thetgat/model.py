"""
T-HetGAT Detection Model — Module 11.

Full end-to-end architecture:

    HeteroGraphEncoder  (pretrained Module 08 backbone, optionally frozen)
          ↓  h_dict: {node_type: (N, hidden_dim)}

    TemporalEdgeEncoder (shared across all edge types)
          ↓  temporal_dict: {edge_type: (E, temporal_dim)}

    HeteroTemporalGATLayer × num_gat_layers
          ↓  h_dict: {node_type: (N, hidden_dim)}  (same shape — residual)

    Window-level mean pooling
          ↓  (hidden_dim,)

    AnomalyScorer MLP → logit → sigmoid → p_attack ∈ [0, 1]

Training strategy
-----------------
    Epochs 0…freeze_encoder_epochs-1:
        Encoder frozen → only GAT layers + scorer learn.
        Prevents the pre-trained backbone from being corrupted before the
        randomly-initialised GAT layers have stabilised.

    Epochs freeze_encoder_epochs…:
        Encoder unfrozen → full end-to-end fine-tuning.

Window label extraction
-----------------------
    edge_attr[:, 11] = is_attack (ground truth stored in graph during build).
    A window is an attack window if ANY edge carries is_attack = 1.
    This is the ONLY place ground truth is used — never as a model input.

File exports
------------
    THetGATModel  — full detection model
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import structlog
import torch
import torch.nn as nn
from torch import Tensor
from torch_geometric.data import HeteroData
from torch_geometric.typing import EdgeType, NodeType

from src.models.pretrain.config import PretrainConfig
from src.models.pretrain.encoder import HeteroGraphEncoder
from src.models.thetgat.config import THetGATConfig, thetgat_settings
from src.models.thetgat.hetgat_layer import HeteroTemporalGATLayer
from src.models.thetgat.temporal_encoder import TemporalEdgeEncoder

logger = structlog.get_logger(__name__)

# Column index of the is_attack flag in edge_attr (must match graph builder)
_IS_ATTACK_COL = 11


# ---------------------------------------------------------------------------
# Anomaly Scoring Head
# ---------------------------------------------------------------------------


class AnomalyScorer(nn.Module):
    """
    Two-layer MLP that maps a window-level embedding to an anomaly logit.

    Parameters
    ----------
    in_dim:
        Input dimension (= hidden_dim of the encoder/GAT stack).
    hidden_dim:
        Hidden layer size.
    dropout:
        Dropout probability between the two linear layers.

    Input / Output
    --------------
    ::

        x: (hidden_dim,) or (B, hidden_dim)
        → logit: scalar or (B,)
    """

    def __init__(self, in_dim: int, hidden_dim: int, dropout: float = 0.1) -> None:
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(in_dim, hidden_dim),
            nn.LayerNorm(hidden_dim),
            nn.ReLU(inplace=True),
            nn.Dropout(dropout),
            nn.Linear(hidden_dim, 1),
        )

    def forward(self, x: Tensor) -> Tensor:
        return self.net(x).squeeze(-1)


# ---------------------------------------------------------------------------
# Full T-HetGAT Model
# ---------------------------------------------------------------------------


class THetGATModel(nn.Module):
    """
    Temporal Heterogeneous Graph Attention Network for anomaly detection.

    Combines a pre-trained HeteroGraphEncoder backbone with T-HetGAT attention
    layers and an MLP scoring head to produce a per-window attack probability.

    Parameters
    ----------
    metadata:
        ``(node_types, edge_types)`` from a HeteroData object.
        Must match the metadata used when the encoder was pre-trained.
    cfg:
        T-HetGAT hyperparameters.  Defaults to the module-level singleton.

    Usage
    -----
    ::

        model = THetGATModel(data.metadata())
        THetGATModel.load_pretrained_encoder(model, cfg.pretrained_checkpoint, device)

        logit = model(data)           # scalar
        prob  = torch.sigmoid(logit)  # ∈ [0, 1]

        label = THetGATModel.get_window_label(data)  # 0.0 or 1.0
    """

    def __init__(
        self,
        metadata: tuple[list[NodeType], list[EdgeType]],
        cfg: THetGATConfig | None = None,
    ) -> None:
        super().__init__()
        self._cfg = cfg or thetgat_settings
        self._log = logger.bind(model="THetGATModel")

        hidden_dim  = self._cfg.hidden_dim
        temporal_dim = self._cfg.temporal_dim
        num_heads   = self._cfg.num_heads
        dropout     = self._cfg.dropout

        # ── Pretrained encoder backbone ───────────────────────────────────
        # Build with the same hidden_dim and num_layers used during pre-training
        # so the state dict loads without shape errors.
        pretrain_cfg = PretrainConfig(
            hidden_dim=hidden_dim,
            num_layers=self._cfg.num_encoder_layers,
        )
        self.encoder = HeteroGraphEncoder(metadata, pretrain_cfg)

        # ── Shared temporal edge encoder ──────────────────────────────────
        # Same TemporalEdgeEncoder is applied to every edge type.
        # The per-edge-type differentiation happens inside HeteroTemporalGATLayer
        # (one TemporalGATConv per edge type).
        self.temporal_encoder = TemporalEdgeEncoder(
            temporal_dim=temporal_dim,
            dropout=dropout,
        )

        # ── Heterogeneous temporal GAT layers ─────────────────────────────
        self.gat_layers = nn.ModuleList(
            [
                HeteroTemporalGATLayer(
                    metadata=metadata,
                    hidden_dim=hidden_dim,
                    temporal_dim=temporal_dim,
                    num_heads=num_heads,
                    dropout=dropout,
                )
                for _ in range(self._cfg.num_gat_layers)
            ]
        )

        # ── Anomaly scoring head ──────────────────────────────────────────
        self.scorer = AnomalyScorer(
            in_dim=hidden_dim,
            hidden_dim=self._cfg.scorer_hidden_dim,
            dropout=dropout,
        )

    # ------------------------------------------------------------------
    # Forward
    # ------------------------------------------------------------------

    def forward(self, data: HeteroData) -> Tensor:
        """
        Compute anomaly logit for a single graph window.

        Parameters
        ----------
        data:
            A PyG HeteroData object representing one time window.
            Each edge store must have ``edge_attr`` of shape ``(E, 12)``.

        Returns
        -------
        Tensor
            Scalar logit (pre-sigmoid).  Apply ``torch.sigmoid()`` to get
            attack probability in ``[0, 1]``.
        """
        # ── 1. Pretrained encoder — node embeddings ───────────────────────
        h_dict: dict[NodeType, Tensor] = self.encoder(
            data.x_dict,
            data.edge_index_dict,
        )

        # ── 2. Temporal edge encoder — edge embeddings ────────────────────
        temporal_dict: dict[EdgeType, Tensor] = {}
        for et in data.edge_types:
            ea = getattr(data[et], "edge_attr", None)
            if ea is not None and ea.shape[0] > 0:
                temporal_dict[et] = self.temporal_encoder(ea)

        # ── 3. T-HetGAT attention layers ──────────────────────────────────
        for gat_layer in self.gat_layers:
            h_dict = gat_layer(h_dict, data.edge_index_dict, temporal_dict)

        # ── 4. Window-level pooling ───────────────────────────────────────
        # Mean pool within each node type, then mean across node types.
        # This collapses the entire graph into a single fixed-size vector.
        type_means: list[Tensor] = [
            h.mean(dim=0)
            for h in h_dict.values()
            if h.shape[0] > 0
        ]
        if not type_means:
            # Degenerate graph: return zero logit (scored as normal)
            self._log.warning("forward_empty_graph_all_types_empty")
            return h_dict[next(iter(h_dict))].new_zeros(())

        window_embed = torch.stack(type_means, dim=0).mean(dim=0)  # (hidden_dim,)

        # ── 5. Anomaly score ──────────────────────────────────────────────
        return self.scorer(window_embed)  # scalar logit

    # ------------------------------------------------------------------
    # Training helpers
    # ------------------------------------------------------------------

    def freeze_encoder(self) -> None:
        """
        Freeze all encoder parameters.

        Called for the first ``freeze_encoder_epochs`` epochs so the
        randomly-initialised GAT layers stabilise before the backbone adapts.
        """
        for param in self.encoder.parameters():
            param.requires_grad_(False)
        self._log.info("encoder_frozen")

    def unfreeze_encoder(self) -> None:
        """Unfreeze all encoder parameters for end-to-end fine-tuning."""
        for param in self.encoder.parameters():
            param.requires_grad_(True)
        self._log.info("encoder_unfrozen")

    @property
    def encoder_is_frozen(self) -> bool:
        """Return True if all encoder parameters are currently frozen."""
        return not any(p.requires_grad for p in self.encoder.parameters())

    # ------------------------------------------------------------------
    # Label extraction
    # ------------------------------------------------------------------

    @staticmethod
    def get_window_label(data: HeteroData) -> float:
        """
        Extract the binary window-level attack label from the graph.

        A window is labelled as an attack window (1.0) if at least one edge
        across any edge type carries ``is_attack = 1`` in ``edge_attr[:, 11]``.
        Otherwise it is normal (0.0).

        Parameters
        ----------
        data:
            A PyG HeteroData window snapshot.

        Returns
        -------
        float
            ``1.0`` if any attack edge exists in this window, else ``0.0``.
        """
        for et in data.edge_types:
            ea = getattr(data[et], "edge_attr", None)
            if (
                ea is not None
                and ea.shape[0] > 0
                and ea.shape[1] > _IS_ATTACK_COL
            ):
                if ea[:, _IS_ATTACK_COL].any().item():
                    return 1.0
        return 0.0

    # ------------------------------------------------------------------
    # Checkpoint loading
    # ------------------------------------------------------------------

    @staticmethod
    def load_pretrained_encoder(
        model: THetGATModel,
        checkpoint_path: Path | str,
        device: str = "cpu",
    ) -> dict[str, Any]:
        """
        Load the Module 08 pretrained encoder weights into ``model.encoder``.

        The checkpoint contains the full ``HeteroGraphEncoder`` state dict
        (including the contrastive projection head).  The projection head weights
        are loaded but never used during T-HetGAT forward passes — they carry no
        gradient and do not affect downstream predictions.

        Parameters
        ----------
        model:
            The THetGATModel whose encoder should be initialised.
        checkpoint_path:
            Path to ``checkpoint_best.pt`` saved by Module 08.
        device:
            Map location for loading tensors.

        Returns
        -------
        dict
            The raw checkpoint dict (contains ``epoch``, ``val_loss``, etc.).

        Raises
        ------
        FileNotFoundError
            If ``checkpoint_path`` does not exist.
        KeyError
            If the checkpoint does not contain ``model_state``.
        """
        path = Path(checkpoint_path)
        if not path.exists():
            raise FileNotFoundError(
                f"Pretrained encoder checkpoint not found: {path}\n"
                "Run Module 08 pre-training first (python -m src.models.pretrain.runner)."
            )

        saved: dict[str, Any] = torch.load(
            path, map_location=device, weights_only=True
        )

        if "model_state" not in saved:
            raise KeyError(
                f"Checkpoint at {path} does not contain 'model_state'. "
                f"Available keys: {list(saved.keys())}"
            )

        # Load with strict=False — the pretrained encoder may have been trained
        # on graphs with a different set of edge/node types than the current
        # dataset.  Weights that match (e.g. input_projs for shared node types,
        # SAGEConv layers for shared edge types) are transferred; the rest keep
        # their random initialisation and are fine-tuned from scratch.
        missing, unexpected = model.encoder.load_state_dict(
            saved["model_state"], strict=False
        )

        log = logger.bind(
            checkpoint=str(path),
            epoch=saved.get("epoch"),
            val_loss=saved.get("val_loss"),
        )
        if missing:
            log.warning("encoder_load_missing_keys", keys=missing)
        if unexpected:
            log.warning("encoder_load_unexpected_keys", keys=unexpected)

        log.info("pretrained_encoder_loaded")
        return saved
