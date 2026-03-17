"""
Heterogeneous Graph Encoder — shared backbone for pre-training and T-HetGAT.

Architecture:
    1. Per-node-type Linear projection  : raw features → hidden_dim
    2. N × HeteroConv layers            : heterogeneous message passing
       Each edge type gets its own SAGEConv operator.
    3. Per-node-type BatchNorm + ReLU   : after every conv layer
    4. Projection head (MLP 2-layer)    : hidden_dim → projection_dim
       Used only during contrastive pre-training; detached afterwards.

Output:
    forward()      → Dict[node_type, Tensor(N, hidden_dim)]   (for downstream)
    project()      → Dict[node_type, Tensor(N, projection_dim)] (for NT-Xent)

Memory budget (RTX 3050 6 GB):
    ~500 K parameters × 4 bytes = ~2 MB weights
    Mini-batch activations with FP16 ≈ 50–100 MB
    Well within 6 GB VRAM.
"""

from __future__ import annotations

from typing import Any

import torch.nn as nn
import torch.nn.functional as F  # noqa: N812
from torch import Tensor
from torch_geometric.data import HeteroData
from torch_geometric.nn import HeteroConv, SAGEConv
from torch_geometric.typing import EdgeType, NodeType

from src.models.pretrain.config import PretrainConfig, pretrain_settings


class HeteroGraphEncoder(nn.Module):
    """
    Heterogeneous GNN encoder.

    Parameters
    ----------
    metadata:
        (node_types, edge_types) tuple from a HeteroData object.
        Defines which node/edge types the model is built for.
    config:
        Pre-training hyperparameters (hidden_dim, num_layers, etc.).

    Example
    -------
    ::

        encoder = HeteroGraphEncoder(data.metadata(), config)
        embeddings = encoder(data.x_dict, data.edge_index_dict)
        projections = encoder.project(data.x_dict, data.edge_index_dict)
    """

    def __init__(
        self,
        metadata: tuple[list[NodeType], list[EdgeType]],
        config: PretrainConfig | None = None,
    ) -> None:
        super().__init__()
        self._cfg        = config or pretrain_settings
        node_types       = metadata[0]
        edge_types       = metadata[1]
        hidden_dim       = self._cfg.hidden_dim
        projection_dim   = self._cfg.projection_dim
        num_layers       = self._cfg.num_layers

        # ------------------------------------------------------------------
        # 1. Per-node-type input projection  (raw dim → hidden_dim)
        #    Linear(-1, ...) uses PyG lazy init — resolves input dim on first
        #    forward pass, so we never hard-code feature dimensions here.
        # ------------------------------------------------------------------
        self.input_projs = nn.ModuleDict(
            {ntype: nn.LazyLinear(hidden_dim) for ntype in node_types}
        )

        # ------------------------------------------------------------------
        # 2. Heterogeneous message-passing layers
        #    One SAGEConv per edge type per layer.
        # ------------------------------------------------------------------
        self.convs: nn.ModuleList = nn.ModuleList()
        for _ in range(num_layers):
            conv_dict: dict[Any, SAGEConv] = {
                etype: SAGEConv((-1, -1), hidden_dim, aggr="mean")
                for etype in edge_types
            }
            self.convs.append(HeteroConv(conv_dict, aggr="sum"))

        # ------------------------------------------------------------------
        # 3. Per-node-type BatchNorm after each conv layer.
        #    Stored as a flat ModuleDict with key "{layer}_{node_type}" to
        #    avoid nested ModuleList[ModuleDict] which mypy cannot type.
        # ------------------------------------------------------------------
        self.norms = nn.ModuleDict(
            {
                f"{i}_{ntype}": nn.BatchNorm1d(hidden_dim)
                for i in range(num_layers)
                for ntype in node_types
            }
        )

        # ------------------------------------------------------------------
        # 4. Contrastive projection head  hidden_dim → projection_dim
        #    Two-layer MLP: hidden_dim → hidden_dim → projection_dim
        # ------------------------------------------------------------------
        self.proj_head = nn.Sequential(
            nn.Linear(hidden_dim, hidden_dim),
            nn.ReLU(inplace=True),
            nn.Linear(hidden_dim, projection_dim),
        )

    # ------------------------------------------------------------------
    # Forward
    # ------------------------------------------------------------------

    def forward(
        self,
        x_dict: dict[NodeType, Tensor],
        edge_index_dict: dict[EdgeType, Tensor],
    ) -> dict[NodeType, Tensor]:
        """
        Encode node features via heterogeneous message passing.

        Parameters
        ----------
        x_dict:
            Per-node-type feature tensors  {node_type: (N, D)}.
        edge_index_dict:
            Per-edge-type adjacency        {edge_type: (2, E)}.

        Returns
        -------
        Dict[node_type, Tensor(N, hidden_dim)] — node embeddings.
        """
        # Project all node types to hidden_dim
        h_dict: dict[NodeType, Tensor] = {
            ntype: self.input_projs[ntype](x)
            for ntype, x in x_dict.items()
            if ntype in self.input_projs
        }

        # Heterogeneous message passing
        for i, conv in enumerate(self.convs):
            # Only pass edge types where BOTH src and dst node types are
            # present in h_dict — avoids NoneType errors when a snapshot
            # has edge types whose endpoint node types have no features.
            valid_edges = {
                etype: idx
                for etype, idx in edge_index_dict.items()
                if etype[0] in h_dict and etype[2] in h_dict
            }
            h_dict = conv(h_dict, valid_edges)
            h_dict = {
                ntype: F.relu(self.norms[f"{i}_{ntype}"](h), inplace=False)
                for ntype, h in h_dict.items()
                if f"{i}_{ntype}" in self.norms
            }

        return h_dict

    def project(
        self,
        x_dict: dict[NodeType, Tensor],
        edge_index_dict: dict[EdgeType, Tensor],
    ) -> dict[NodeType, Tensor]:
        """
        Encode then project through the contrastive projection head.

        Used only during pre-training loss computation.
        Downstream tasks should use forward() embeddings directly.

        Returns
        -------
        Dict[node_type, Tensor(N, projection_dim)].
        """
        h_dict = self.forward(x_dict, edge_index_dict)
        return {
            ntype: F.normalize(self.proj_head(h), dim=-1)
            for ntype, h in h_dict.items()
        }

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    def reset_parameters(self) -> None:
        """Re-initialise all learnable parameters."""
        for module in self.modules():
            if hasattr(module, "reset_parameters") and module is not self:
                module.reset_parameters()

    @staticmethod
    def from_heterodata(
        data: HeteroData,
        config: PretrainConfig | None = None,
    ) -> HeteroGraphEncoder:
        """Convenience constructor — infers metadata from a HeteroData object."""
        return HeteroGraphEncoder(data.metadata(), config)
