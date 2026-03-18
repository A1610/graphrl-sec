"""
Heterogeneous Temporal GAT Layer — Module 11 T-HetGAT.

This is the CORE NOVELTY of the dissertation.

Standard GAT (Veličković et al., 2018)
---------------------------------------
    α_ij = softmax( LeakyReLU( a^T [ W·h_i ‖ W·h_j ] ) )
    h'_i  = σ( Σ_j α_ij · W·h_j )

    Problems with standard GAT for our task:
        1. Ignores WHEN edges happened (no temporal awareness)
        2. Treats all edge types the same (no heterogeneity)
        3. Cannot distinguish a DDoS burst from normal high-volume traffic

T-HetGAT extension
-------------------
    α_ij = softmax( LeakyReLU( a^T [ W_s·h_i ‖ W_d·h_j ‖ W_t·t_ij ] ) )

    where t_ij = TemporalEdgeEncoder(edge_attr_ij)  — 32-dim temporal embedding

    Key additions:
        W_t · t_ij  — incorporates WHEN/HOW LONG/HOW MUCH the flow was
        Per-edge-type W_s, W_d, W_t, a  — separate weights per relation type
        Multi-head: H=4 heads × D=32 dims = 128-dim output (matches encoder)

Why this beats E-GraphSAGE
---------------------------
    E-GraphSAGE: aggregates neighbours uniformly, no temporal weighting
    T-HetGAT:    attention is modulated by temporal features, so
                 "3am burst of 10K packets to port 22" gets different
                 attention than "9am regular 100-byte SSH keepalive"

Architecture per layer
----------------------
    For each edge type (src_type → dst_type):
        1. src nodes  : W_src(h_src)   → (N_src, H, D)
        2. dst nodes  : W_dst(h_dst)   → (N_dst, H, D)
        3. edge feats : W_temp(t_ij)   → (E,     H, D)
        4. attention  : a^T LeakyReLU([h_src_j ‖ h_dst_i ‖ t_ij])  → (E, H)
        5. softmax    : per-destination normalisation                  → (E, H)
        6. aggregate  : Σ_j α_ij * (W_val·h_src_j + t_ij)            → (N_dst, H*D)

    Then for each dst node type:
        sum contributions from ALL incident edge types
        + residual connection from input
        + LayerNorm

File exports
------------
    TemporalGATConv         — single-edge-type temporal GAT (MessagePassing)
    HeteroTemporalGATLayer  — wraps one TemporalGATConv per edge type
"""

from __future__ import annotations

from typing import Any

import torch
import torch.nn as nn
import torch.nn.functional as F
from torch import Tensor
from torch_geometric.nn import MessagePassing
from torch_geometric.typing import EdgeType, NodeType
from torch_geometric.utils import softmax as pyg_softmax


# ---------------------------------------------------------------------------
# Single-edge-type Temporal GAT Convolution
# ---------------------------------------------------------------------------


class TemporalGATConv(MessagePassing):
    """
    Temporal GAT convolution for a single (src_type, rel, dst_type) edge type.

    Implements the T-HetGAT attention mechanism:
        α_ij = softmax( LeakyReLU( a^T [ W_s·h_i ‖ W_d·h_j ‖ W_t·t_ij ] ) )

    Parameters
    ----------
    in_dim:
        Input node feature dimension (same for src and dst, = hidden_dim).
    out_dim:
        Output dimension per head.  Total output = num_heads * out_dim.
    num_heads:
        Number of attention heads.
    temporal_dim:
        Dimension of temporal edge embeddings from TemporalEdgeEncoder.
    dropout:
        Dropout on attention weights.
    """

    def __init__(
        self,
        in_dim: int,
        out_dim: int,
        num_heads: int,
        temporal_dim: int,
        dropout: float = 0.1,
    ) -> None:
        # aggr='add' — attention weights already normalise via softmax,
        # so sum = weighted mean.
        super().__init__(aggr="add", node_dim=0)

        self.in_dim      = in_dim
        self.out_dim     = out_dim
        self.num_heads   = num_heads
        self.temporal_dim = temporal_dim
        self.dropout_p   = dropout

        # ── Source and destination projections ───────────────────────────
        # Each head gets its own slice of the projection
        self.W_src  = nn.Linear(in_dim,      num_heads * out_dim, bias=False)
        self.W_dst  = nn.Linear(in_dim,      num_heads * out_dim, bias=False)
        self.W_temp = nn.Linear(temporal_dim, num_heads * out_dim, bias=False)

        # ── Attention vector a ───────────────────────────────────────────
        # Shape: (1, num_heads, 3 * out_dim)
        # The 3 concatenated parts are: src, dst, temporal
        self.att = nn.Parameter(
            torch.empty(1, num_heads, 3 * out_dim)
        )

        # ── Value projection (what gets aggregated) ──────────────────────
        self.W_val = nn.Linear(in_dim, num_heads * out_dim, bias=False)

        self.dropout = nn.Dropout(dropout)
        self._reset_parameters()

    def _reset_parameters(self) -> None:
        nn.init.xavier_uniform_(self.W_src.weight)
        nn.init.xavier_uniform_(self.W_dst.weight)
        nn.init.xavier_uniform_(self.W_temp.weight)
        nn.init.xavier_uniform_(self.W_val.weight)
        nn.init.xavier_uniform_(self.att.view(1, -1).unsqueeze(0))

    # ------------------------------------------------------------------
    # Forward
    # ------------------------------------------------------------------

    def forward(
        self,
        x_src: Tensor,
        x_dst: Tensor,
        edge_index: Tensor,
        temporal_feat: Tensor,
    ) -> Tensor:
        """
        Parameters
        ----------
        x_src:
            Source node features, shape ``(N_src, in_dim)``.
        x_dst:
            Destination node features, shape ``(N_dst, in_dim)``.
        edge_index:
            Shape ``(2, E)``.  Row 0 = source indices, row 1 = dest indices.
        temporal_feat:
            Temporal edge embeddings from TemporalEdgeEncoder,
            shape ``(E, temporal_dim)``.

        Returns
        -------
        Tensor
            Updated destination embeddings, shape ``(N_dst, num_heads * out_dim)``.
        """
        H, D = self.num_heads, self.out_dim

        H, D = self.num_heads, self.out_dim
        N_src, N_dst = x_src.shape[0], x_dst.shape[0]

        # Project query (dst), key (src), temporal, value (src)
        # Pass as (src_tensor, dst_tensor) tuples so PyG bipartite
        # indexing uses edge_index[0] for _j and edge_index[1] for _i.
        h_src = self.W_src(x_src).view(N_src, H, D)   # (N_src, H, D)
        h_dst = self.W_dst(x_dst).view(N_dst, H, D)   # (N_dst, H, D)
        t_proj = self.W_temp(temporal_feat).view(-1, H, D)  # (E, H, D)
        v_src = self.W_val(x_src).view(N_src, H, D)   # (N_src, H, D)

        return self.propagate(
            edge_index,
            x=(h_src, h_dst),      # bipartite tuple: x_j←src, x_i←dst
            t_proj=t_proj,
            v=(v_src, None),       # bipartite tuple: v_j←src only
            size=(N_src, N_dst),
        )

    def message(
        self,
        x_j:   Tensor,   # (E, H, D) — projected src node (W_src · h_src)
        x_i:   Tensor,   # (E, H, D) — projected dst node (W_dst · h_dst)
        t_proj: Tensor,  # (E, H, D) — temporal embedding
        v_j:   Tensor,   # (E, H, D) — value vector from src
        index: Tensor,   # (E,)       — dst indices for per-node softmax
    ) -> Tensor:
        """
        Compute attention-weighted messages.

        Attention:
            alpha = softmax_i( LeakyReLU( a^T [x_j ‖ x_i ‖ t_proj] ) )
        Message:
            m = alpha * (v_j + t_proj)
        """
        # (E, H, 3D)
        alpha_input = torch.cat([x_j, x_i, t_proj], dim=-1)
        # (E, H)
        alpha = (F.leaky_relu(alpha_input, negative_slope=0.2) * self.att).sum(dim=-1)
        alpha = pyg_softmax(alpha, index)
        alpha = self.dropout(alpha)

        # Value enriched with temporal context: (E, H, D)
        value = v_j + t_proj
        # Weighted: (E, H, D) → (E, H*D)
        weighted = (value * alpha.unsqueeze(-1)).view(value.shape[0], -1)
        return weighted

    def update(self, aggr_out: Tensor) -> Tensor:  # (N_dst, H*D)
        return aggr_out


# ---------------------------------------------------------------------------
# Heterogeneous Temporal GAT Layer
# ---------------------------------------------------------------------------


class HeteroTemporalGATLayer(nn.Module):
    """
    One layer of heterogeneous temporal graph attention.

    Wraps one :class:`TemporalGATConv` per edge type, combines their
    outputs per destination node type, then applies residual + LayerNorm.

    Parameters
    ----------
    metadata:
        ``(node_types, edge_types)`` tuple from a HeteroData object.
    hidden_dim:
        Node hidden dimension (= num_heads × head_dim).
    temporal_dim:
        Dimension of temporal edge embeddings.
    num_heads:
        Attention heads.  Must divide ``hidden_dim`` evenly.
    dropout:
        Dropout on attention weights and activations.

    Input / Output
    --------------
    ::

        h_dict  : {node_type: (N, hidden_dim)}
        t_dict  : {edge_type: (E, temporal_dim)}
        → h_dict : {node_type: (N, hidden_dim)}   (same shape — residual)
    """

    def __init__(
        self,
        metadata: tuple[list[NodeType], list[EdgeType]],
        hidden_dim: int = 128,
        temporal_dim: int = 32,
        num_heads: int = 4,
        dropout: float = 0.1,
    ) -> None:
        super().__init__()

        node_types = metadata[0]
        edge_types = metadata[1]

        if hidden_dim % num_heads != 0:
            raise ValueError(
                f"hidden_dim ({hidden_dim}) must be divisible by "
                f"num_heads ({num_heads})."
            )
        head_dim = hidden_dim // num_heads

        # ── One TemporalGATConv per edge type ────────────────────────────
        # Key: tuple-to-string conversion for ModuleDict (dicts need str keys)
        self.convs = nn.ModuleDict(
            {
                self._edge_key(et): TemporalGATConv(
                    in_dim=hidden_dim,
                    out_dim=head_dim,
                    num_heads=num_heads,
                    temporal_dim=temporal_dim,
                    dropout=dropout,
                )
                for et in edge_types
            }
        )

        # ── Per-destination-type output projection ───────────────────────
        # After summing contributions from multiple edge types,
        # project back to hidden_dim with a learnable linear layer.
        self.out_projs = nn.ModuleDict(
            {ntype: nn.Linear(hidden_dim, hidden_dim) for ntype in node_types}
        )

        # ── LayerNorm per node type ──────────────────────────────────────
        self.norms = nn.ModuleDict(
            {ntype: nn.LayerNorm(hidden_dim) for ntype in node_types}
        )

        self.dropout = nn.Dropout(dropout)
        self._hidden_dim = hidden_dim

    # ------------------------------------------------------------------
    # Forward
    # ------------------------------------------------------------------

    def forward(
        self,
        h_dict: dict[NodeType, Tensor],
        edge_index_dict: dict[EdgeType, Tensor],
        temporal_dict: dict[EdgeType, Tensor],
    ) -> dict[NodeType, Tensor]:
        """
        One forward pass of the heterogeneous temporal GAT layer.

        Parameters
        ----------
        h_dict:
            Per-node-type embeddings ``{node_type: (N, hidden_dim)}``.
        edge_index_dict:
            Per-edge-type adjacency ``{edge_type: (2, E)}``.
        temporal_dict:
            Per-edge-type temporal embeddings ``{edge_type: (E, temporal_dim)}``.

        Returns
        -------
        dict[NodeType, Tensor]
            Updated node embeddings, same structure as ``h_dict``.
        """
        # Accumulate messages per destination node type
        out: dict[NodeType, list[Tensor]] = {nt: [] for nt in h_dict}

        for edge_type, edge_index in edge_index_dict.items():
            src_type, _, dst_type = edge_type

            # Skip if either endpoint is not in h_dict
            if src_type not in h_dict or dst_type not in h_dict:
                continue

            # Skip if temporal features are missing for this edge type
            if edge_type not in temporal_dict:
                continue

            key = self._edge_key(edge_type)
            if key not in self.convs:
                continue

            x_src = h_dict[src_type]
            x_dst = h_dict[dst_type]
            t_feat = temporal_dict[edge_type]

            # Handle empty edge sets gracefully
            if edge_index.shape[1] == 0 or t_feat.shape[0] == 0:
                continue

            msg = self.convs[key](
                x_src=x_src,
                x_dst=x_dst,
                edge_index=edge_index,
                temporal_feat=t_feat,
            )  # (N_dst, hidden_dim)

            out[dst_type].append(msg)

        # Combine, project, residual, LayerNorm per node type
        new_h: dict[NodeType, Tensor] = {}
        for ntype, h in h_dict.items():
            if out[ntype]:
                # Sum contributions from all incident edge types
                aggregated = torch.stack(out[ntype], dim=0).sum(dim=0)  # (N, hidden_dim)
            else:
                # No edges touching this node type — pass through zeros
                aggregated = h.new_zeros(h.shape)

            # Output projection + dropout
            projected = self.dropout(self.out_projs[ntype](aggregated))

            # Residual connection + LayerNorm
            new_h[ntype] = self.norms[ntype](h + projected)

        return new_h

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    @staticmethod
    def _edge_key(edge_type: EdgeType) -> str:
        """Convert edge_type tuple to a valid ModuleDict string key."""
        src, rel, dst = edge_type
        return f"{src}__{rel}__{dst}"
