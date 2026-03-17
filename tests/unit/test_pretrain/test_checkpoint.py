"""Unit tests for CheckpointManager."""

from __future__ import annotations

from pathlib import Path

import pytest
import torch
import torch.nn as nn

from src.models.pretrain.checkpoint import CheckpointManager, CheckpointMeta
from src.models.pretrain.config import PretrainConfig

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _cfg(tmp_path: Path) -> PretrainConfig:
    return PretrainConfig(checkpoint_dir=tmp_path / "ckpts")


def _model() -> nn.Linear:
    return nn.Linear(4, 2)


def _optimizer(model: nn.Module) -> torch.optim.Optimizer:
    return torch.optim.AdamW(model.parameters(), lr=1e-3)


# ---------------------------------------------------------------------------
# Initialization
# ---------------------------------------------------------------------------


class TestCheckpointManagerInit:
    def test_creates_checkpoint_dir(self, tmp_path: Path) -> None:
        cfg = _cfg(tmp_path)
        CheckpointManager(cfg)
        assert cfg.checkpoint_dir.exists()

    def test_best_val_loss_starts_at_infinity(self, tmp_path: Path) -> None:
        mgr = CheckpointManager(_cfg(tmp_path))
        assert mgr.best_val_loss == float("inf")

    def test_best_exists_false_initially(self, tmp_path: Path) -> None:
        mgr = CheckpointManager(_cfg(tmp_path))
        assert not mgr.best_exists()

    def test_latest_exists_false_initially(self, tmp_path: Path) -> None:
        mgr = CheckpointManager(_cfg(tmp_path))
        assert not mgr.latest_exists()


# ---------------------------------------------------------------------------
# Save
# ---------------------------------------------------------------------------


class TestCheckpointManagerSave:
    def test_save_returns_meta(self, tmp_path: Path) -> None:
        mgr   = CheckpointManager(_cfg(tmp_path))
        model = _model()
        opt   = _optimizer(model)
        meta  = mgr.save(model, opt, None, epoch=1,
                         train_loss=0.5, val_loss=0.4)
        assert isinstance(meta, CheckpointMeta)

    def test_first_save_is_best(self, tmp_path: Path) -> None:
        mgr   = CheckpointManager(_cfg(tmp_path))
        model = _model()
        opt   = _optimizer(model)
        meta  = mgr.save(model, opt, None, epoch=1,
                         train_loss=0.5, val_loss=0.4)
        assert meta.is_best

    def test_lower_val_loss_is_best(self, tmp_path: Path) -> None:
        mgr   = CheckpointManager(_cfg(tmp_path))
        model = _model()
        opt   = _optimizer(model)
        mgr.save(model, opt, None, epoch=1, train_loss=0.5, val_loss=0.4)
        meta2 = mgr.save(model, opt, None, epoch=2, train_loss=0.4, val_loss=0.3)
        assert meta2.is_best

    def test_higher_val_loss_not_best(self, tmp_path: Path) -> None:
        mgr   = CheckpointManager(_cfg(tmp_path))
        model = _model()
        opt   = _optimizer(model)
        mgr.save(model, opt, None, epoch=1, train_loss=0.5, val_loss=0.4)
        meta2 = mgr.save(model, opt, None, epoch=2, train_loss=0.5, val_loss=0.9)
        assert not meta2.is_best

    def test_latest_file_created(self, tmp_path: Path) -> None:
        mgr   = CheckpointManager(_cfg(tmp_path))
        model = _model()
        opt   = _optimizer(model)
        mgr.save(model, opt, None, epoch=1, train_loss=0.5, val_loss=0.4)
        assert mgr.latest_exists()

    def test_best_file_created_on_improvement(self, tmp_path: Path) -> None:
        mgr   = CheckpointManager(_cfg(tmp_path))
        model = _model()
        opt   = _optimizer(model)
        mgr.save(model, opt, None, epoch=1, train_loss=0.5, val_loss=0.4)
        assert mgr.best_exists()

    def test_best_val_loss_updated(self, tmp_path: Path) -> None:
        mgr   = CheckpointManager(_cfg(tmp_path))
        model = _model()
        opt   = _optimizer(model)
        mgr.save(model, opt, None, epoch=1, train_loss=0.5, val_loss=0.4)
        assert mgr.best_val_loss == pytest.approx(0.4)


# ---------------------------------------------------------------------------
# Load
# ---------------------------------------------------------------------------


class TestCheckpointManagerLoad:
    def test_load_best_restores_weights(self, tmp_path: Path) -> None:
        mgr    = CheckpointManager(_cfg(tmp_path))
        model  = _model()
        opt    = _optimizer(model)

        # Set a known weight and save
        with torch.no_grad():
            model.weight.fill_(3.14)
        mgr.save(model, opt, None, epoch=1, train_loss=0.5, val_loss=0.3)

        # Corrupt the weight and reload
        with torch.no_grad():
            model.weight.fill_(0.0)
        mgr.load_best(model)

        assert torch.allclose(model.weight, torch.full_like(model.weight, 3.14))

    def test_load_latest_returns_epoch(self, tmp_path: Path) -> None:
        mgr   = CheckpointManager(_cfg(tmp_path))
        model = _model()
        opt   = _optimizer(model)
        mgr.save(model, opt, None, epoch=7, train_loss=0.5, val_loss=0.4)
        saved = mgr.load_latest(model)
        assert saved["epoch"] == 7

    def test_load_best_raises_if_missing(self, tmp_path: Path) -> None:
        mgr   = CheckpointManager(_cfg(tmp_path))
        model = _model()
        with pytest.raises(FileNotFoundError):
            mgr.load_best(model)

    def test_load_latest_raises_if_missing(self, tmp_path: Path) -> None:
        mgr   = CheckpointManager(_cfg(tmp_path))
        model = _model()
        with pytest.raises(FileNotFoundError):
            mgr.load_latest(model)

    def test_best_val_loss_restored_on_reinit(self, tmp_path: Path) -> None:
        cfg   = _cfg(tmp_path)
        mgr1  = CheckpointManager(cfg)
        model = _model()
        opt   = _optimizer(model)
        mgr1.save(model, opt, None, epoch=1, train_loss=0.5, val_loss=0.25)

        # New manager instance — should read best val_loss from disk
        mgr2 = CheckpointManager(cfg)
        assert mgr2.best_val_loss == pytest.approx(0.25)
