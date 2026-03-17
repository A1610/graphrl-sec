"""
Graph augmentation strategies for contrastive self-supervised learning.

Two views of each graph are created by applying stochastic augmentations.
The encoder must learn representations that are invariant to these
perturbations — this is the core inductive bias of GraphCL.

Augmentations implemented:
    1. Node feature masking  — randomly zero-out a fraction of features
    2. Edge dropout          — randomly remove a fraction of edges

Both augmentations are applied in-place on a *copy* of the graph so the
original HeteroData object is never modified.
"""

from __future__ import annotations

import copy

import torch
from torch_geometric.data import HeteroData

from src.models.pretrain.config import PretrainConfig, pretrain_settings


class GraphAugmentor:
    """
    Produces two augmented views of a HeteroData graph for contrastive learning.

    Usage::

        aug = GraphAugmentor(config)
        view1, view2 = aug(graph)   # both are independent augmented copies

    The same augmentor instance is safe to call repeatedly and from a
    DataLoader worker (all operations use torch, no Python RNG state).
    """

    def __init__(self, config: PretrainConfig | None = None) -> None:
        self._cfg = config or pretrain_settings

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def __call__(
        self, data: HeteroData
    ) -> tuple[HeteroData, HeteroData]:
        """Return two independently augmented views of *data*."""
        view1 = self._augment(copy.deepcopy(data))
        view2 = self._augment(copy.deepcopy(data))
        return view1, view2

    def feature_mask(self, data: HeteroData) -> HeteroData:
        """Apply node feature masking only (modifies *data* in-place)."""
        for node_type in data.node_types:
            store = data[node_type]
            if not hasattr(store, "x") or store.x is None:
                continue
            x    = store.x                          # (N, D)
            mask = torch.bernoulli(
                torch.full(x.shape, self._cfg.aug_feature_mask_ratio,
                           dtype=torch.float32, device=x.device)
            ).bool()
            store.x = x.masked_fill(mask, 0.0)
        return data

    def edge_dropout(self, data: HeteroData) -> HeteroData:
        """Apply edge dropout only (modifies *data* in-place)."""
        for edge_type in data.edge_types:
            store = data[edge_type]
            if not hasattr(store, "edge_index") or store.edge_index is None:
                continue
            num_edges = store.edge_index.shape[1]
            if num_edges == 0:
                continue

            # Keep mask: 1 = keep, 0 = drop
            keep_prob = 1.0 - self._cfg.aug_edge_drop_ratio
            keep_mask = torch.bernoulli(
                torch.full((num_edges,), keep_prob,
                           dtype=torch.float32, device=store.edge_index.device)
            ).bool()

            store.edge_index = store.edge_index[:, keep_mask]
            if hasattr(store, "edge_attr") and store.edge_attr is not None:
                store.edge_attr = store.edge_attr[keep_mask]
        return data

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _augment(self, data: HeteroData) -> HeteroData:
        """Apply both augmentations sequentially."""
        data = self.feature_mask(data)
        data = self.edge_dropout(data)
        return data
