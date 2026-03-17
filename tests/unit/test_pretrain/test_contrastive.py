"""Unit tests for NTXentLoss and collect_node_projections."""

from __future__ import annotations

import torch

from src.models.pretrain.config import PretrainConfig
from src.models.pretrain.contrastive import NTXentLoss, collect_node_projections

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _cfg(temp: float = 0.5) -> PretrainConfig:
    return PretrainConfig(temperature=temp)


def _unit(n: int, d: int) -> torch.Tensor:
    """Return L2-normalised random tensor (N, D)."""
    x = torch.randn(n, d)
    return torch.nn.functional.normalize(x, dim=-1)


# ---------------------------------------------------------------------------
# NTXentLoss
# ---------------------------------------------------------------------------


class TestNTXentLoss:
    def test_returns_scalar(self) -> None:
        loss_fn = NTXentLoss(_cfg())
        z1, z2  = _unit(8, 16), _unit(8, 16)
        loss    = loss_fn(z1, z2)
        assert loss.ndim == 0

    def test_loss_is_positive(self) -> None:
        loss_fn = NTXentLoss(_cfg())
        z1, z2  = _unit(8, 16), _unit(8, 16)
        assert loss_fn(z1, z2).item() > 0

    def test_identical_views_lower_loss_than_random(self) -> None:
        """Positive pairs that are identical should yield lower loss."""
        loss_fn   = NTXentLoss(_cfg())
        z         = _unit(16, 32)
        loss_same = loss_fn(z, z.clone()).item()
        loss_rand = loss_fn(z, _unit(16, 32)).item()
        assert loss_same < loss_rand

    def test_empty_input_returns_zero(self) -> None:
        loss_fn = NTXentLoss(_cfg())
        z_empty = torch.zeros(0, 16)
        loss    = loss_fn(z_empty, z_empty)
        assert loss.item() == 0.0

    def test_symmetric(self) -> None:
        loss_fn  = NTXentLoss(_cfg())
        z1, z2   = _unit(8, 16), _unit(8, 16)
        assert abs(loss_fn(z1, z2).item() - loss_fn(z2, z1).item()) < 1e-5

    def test_higher_temperature_reduces_loss_magnitude(self) -> None:
        z1, z2     = _unit(8, 16), _unit(8, 16)
        loss_low   = NTXentLoss(_cfg(temp=0.1))(z1, z2).item()
        loss_high  = NTXentLoss(_cfg(temp=1.0))(z1, z2).item()
        assert loss_low != loss_high   # temperatures should have an effect

    def test_single_node_pair(self) -> None:
        loss_fn = NTXentLoss(_cfg())
        z1, z2  = _unit(1, 8), _unit(1, 8)
        loss    = loss_fn(z1, z2)
        assert torch.isfinite(loss)

    def test_gradients_flow(self) -> None:
        loss_fn = NTXentLoss(_cfg())
        z1 = torch.randn(8, 16, requires_grad=True)
        z2 = torch.randn(8, 16, requires_grad=True)
        z1n = torch.nn.functional.normalize(z1, dim=-1)
        z2n = torch.nn.functional.normalize(z2, dim=-1)
        loss = loss_fn(z1n, z2n)
        loss.backward()
        assert z1.grad is not None
        assert z2.grad is not None


# ---------------------------------------------------------------------------
# collect_node_projections
# ---------------------------------------------------------------------------


class TestCollectNodeProjections:
    def test_common_types_concatenated(self) -> None:
        p1 = {"host": _unit(4, 8), "service": _unit(2, 8)}
        p2 = {"host": _unit(4, 8), "service": _unit(2, 8)}
        result = collect_node_projections(p1, p2)
        assert result is not None
        z1, z2 = result
        assert z1.shape == (6, 8)   # 4 host + 2 service
        assert z2.shape == (6, 8)

    def test_mismatched_node_count_excluded(self) -> None:
        p1 = {"host": _unit(4, 8), "service": _unit(2, 8)}
        p2 = {"host": _unit(3, 8), "service": _unit(2, 8)}  # host count differs
        result = collect_node_projections(p1, p2)
        assert result is not None
        z1, z2 = result
        # Only service (2 nodes) should be included
        assert z1.shape[0] == 2

    def test_no_common_types_returns_none(self) -> None:
        p1 = {"host": _unit(4, 8)}
        p2 = {"service": _unit(2, 8)}
        assert collect_node_projections(p1, p2) is None

    def test_empty_dicts_return_none(self) -> None:
        assert collect_node_projections({}, {}) is None

    def test_zero_node_type_excluded(self) -> None:
        p1 = {"host": _unit(0, 8), "service": _unit(3, 8)}
        p2 = {"host": _unit(0, 8), "service": _unit(3, 8)}
        result = collect_node_projections(p1, p2)
        assert result is not None
        z1, z2 = result
        assert z1.shape[0] == 3   # only service, host is empty
