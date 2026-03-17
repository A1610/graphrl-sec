"""Unit tests for GraphAugmentor."""

from __future__ import annotations

import torch
from torch_geometric.data import HeteroData

from src.models.pretrain.augmentation import GraphAugmentor
from src.models.pretrain.config import PretrainConfig

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_graph() -> HeteroData:
    """Minimal HeteroData: 2 node types, 1 edge type."""
    data = HeteroData()
    data["host"].x        = torch.ones(10, 8)
    data["service"].x     = torch.ones(5, 4)
    data["host", "connects_to", "host"].edge_index = torch.tensor(
        [[0, 1, 2, 3], [1, 2, 3, 4]], dtype=torch.long
    )
    data["host", "connects_to", "host"].edge_attr = torch.ones(4, 12)
    return data


def _cfg(mask: float = 0.2, drop: float = 0.2) -> PretrainConfig:
    return PretrainConfig(aug_feature_mask_ratio=mask, aug_edge_drop_ratio=drop)


# ---------------------------------------------------------------------------
# __call__ — produces two views
# ---------------------------------------------------------------------------


class TestGraphAugmentorCall:
    def test_returns_two_views(self) -> None:
        aug = GraphAugmentor(_cfg())
        v1, v2 = aug(_make_graph())
        assert isinstance(v1, HeteroData)
        assert isinstance(v2, HeteroData)

    def test_views_are_independent_copies(self) -> None:
        aug = GraphAugmentor(_cfg())
        v1, v2 = aug(_make_graph())
        # Modifying v1 must not affect v2
        v1["host"].x[:] = 99.0
        assert v2["host"].x.max().item() != 99.0

    def test_original_graph_unchanged(self) -> None:
        aug  = GraphAugmentor(_cfg())
        data = _make_graph()
        aug(data)
        assert data["host"].x.eq(1.0).all()


# ---------------------------------------------------------------------------
# feature_mask
# ---------------------------------------------------------------------------


class TestFeatureMask:
    def test_some_features_zeroed(self) -> None:
        aug  = GraphAugmentor(_cfg(mask=0.5))
        data = _make_graph()
        aug.feature_mask(data)
        assert (data["host"].x == 0.0).any()

    def test_zero_mask_ratio_leaves_features_intact(self) -> None:
        aug  = GraphAugmentor(_cfg(mask=0.0))
        data = _make_graph()
        aug.feature_mask(data)
        assert data["host"].x.eq(1.0).all()

    def test_output_shape_preserved(self) -> None:
        aug  = GraphAugmentor(_cfg(mask=0.3))
        data = _make_graph()
        original_shape = data["host"].x.shape
        aug.feature_mask(data)
        assert data["host"].x.shape == original_shape

    def test_no_negative_values_after_mask(self) -> None:
        aug  = GraphAugmentor(_cfg(mask=0.5))
        data = _make_graph()
        aug.feature_mask(data)
        assert (data["host"].x >= 0.0).all()


# ---------------------------------------------------------------------------
# edge_dropout
# ---------------------------------------------------------------------------


class TestEdgeDropout:
    def test_zero_drop_ratio_keeps_all_edges(self) -> None:
        aug  = GraphAugmentor(_cfg(drop=0.0))
        data = _make_graph()
        n_before = data["host", "connects_to", "host"].edge_index.shape[1]
        aug.edge_dropout(data)
        n_after  = data["host", "connects_to", "host"].edge_index.shape[1]
        assert n_after == n_before

    def test_high_drop_ratio_reduces_edges(self) -> None:
        torch.manual_seed(0)
        aug  = GraphAugmentor(_cfg(drop=0.99))
        data = _make_graph()
        n_before = data["host", "connects_to", "host"].edge_index.shape[1]
        aug.edge_dropout(data)
        n_after  = data["host", "connects_to", "host"].edge_index.shape[1]
        assert n_after < n_before

    def test_edge_attr_kept_in_sync(self) -> None:
        aug  = GraphAugmentor(_cfg(drop=0.5))
        data = _make_graph()
        aug.edge_dropout(data)
        store    = data["host", "connects_to", "host"]
        n_edges  = store.edge_index.shape[1]
        n_attr   = store.edge_attr.shape[0]
        assert n_edges == n_attr

    def test_empty_edge_type_not_crashed(self) -> None:
        aug  = GraphAugmentor(_cfg(drop=0.5))
        data = HeteroData()
        data["host"].x = torch.ones(5, 8)
        data["host", "connects_to", "host"].edge_index = torch.zeros(2, 0, dtype=torch.long)
        aug.edge_dropout(data)   # must not raise
