"""
Checkpoint manager for pre-training.

Saves and loads model state, optimizer state, and training metrics.
Tracks the best checkpoint (lowest validation loss) and supports
resuming interrupted training runs.

Saved file format (PyTorch .pt):
    {
        "epoch":        int,
        "model_state":  dict,
        "optim_state":  dict,
        "scheduler_state": dict | None,
        "train_loss":   float,
        "val_loss":     float,
        "config":       dict,       # PretrainConfig as plain dict
    }
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import structlog
import torch
import torch.nn as nn

from src.models.pretrain.config import PretrainConfig, pretrain_settings

logger = structlog.get_logger(__name__)


@dataclass
class CheckpointMeta:
    """Metadata returned after saving a checkpoint."""

    path:       Path
    epoch:      int
    train_loss: float
    val_loss:   float
    is_best:    bool


class CheckpointManager:
    """
    Saves model checkpoints and tracks the best one (lowest val loss).

    Usage::

        ckpt_mgr = CheckpointManager(config)

        # inside training loop:
        meta = ckpt_mgr.save(
            model, optimizer, scheduler,
            epoch=epoch, train_loss=train_loss, val_loss=val_loss,
        )
        if meta.is_best:
            print("New best model!")

        # resume from last checkpoint:
        state = ckpt_mgr.load_latest(model, optimizer, scheduler)
        start_epoch = state["epoch"] + 1
    """

    _LATEST_NAME = "checkpoint_latest.pt"
    _BEST_NAME   = "checkpoint_best.pt"

    def __init__(self, config: PretrainConfig | None = None) -> None:
        self._cfg  = config or pretrain_settings
        self._dir  = self._cfg.checkpoint_dir
        self._dir.mkdir(parents=True, exist_ok=True)
        self._best_val_loss: float = float("inf")
        self._log  = logger.bind(checkpoint_dir=str(self._dir))

        # Restore best_val_loss from existing best checkpoint if present
        best_path = self._dir / self._BEST_NAME
        if best_path.exists():
            try:
                saved = torch.load(best_path, map_location="cpu", weights_only=True)
                self._best_val_loss = float(saved.get("val_loss", float("inf")))
                self._log.debug("checkpoint_best_val_loss_restored",
                                val_loss=self._best_val_loss)
            except Exception as exc:  # noqa: BLE001
                self._log.warning("checkpoint_load_meta_failed", error=str(exc))

    # ------------------------------------------------------------------
    # Save
    # ------------------------------------------------------------------

    def save(
        self,
        model:     nn.Module,
        optimizer: torch.optim.Optimizer,
        scheduler: torch.optim.lr_scheduler.LRScheduler | None,
        epoch:     int,
        train_loss: float,
        val_loss:   float,
    ) -> CheckpointMeta:
        """
        Persist a checkpoint.

        Always overwrites `checkpoint_latest.pt`.
        Overwrites `checkpoint_best.pt` when val_loss improves.

        Returns
        -------
        CheckpointMeta with the path and whether this is the new best.
        """
        is_best = val_loss < self._best_val_loss

        payload: dict[str, object] = {
            "epoch":            epoch,
            "model_state":      model.state_dict(),
            "optim_state":      optimizer.state_dict(),
            "scheduler_state":  scheduler.state_dict() if scheduler is not None else None,  # type: ignore[no-untyped-call]
            "train_loss":       train_loss,
            "val_loss":         val_loss,
            "config":           self._cfg.model_dump(mode="json"),
        }

        latest_path = self._dir / self._LATEST_NAME
        torch.save(payload, latest_path)
        self._log.debug("checkpoint_saved", epoch=epoch, val_loss=val_loss,
                        path=str(latest_path))

        if is_best:
            self._best_val_loss = val_loss
            best_path = self._dir / self._BEST_NAME
            torch.save(payload, best_path)
            self._log.info("checkpoint_best_updated", epoch=epoch,
                           val_loss=val_loss, path=str(best_path))

        return CheckpointMeta(
            path=latest_path, epoch=epoch,
            train_loss=train_loss, val_loss=val_loss, is_best=is_best,
        )

    # ------------------------------------------------------------------
    # Load
    # ------------------------------------------------------------------

    def load_best(
        self,
        model:     nn.Module,
        optimizer: torch.optim.Optimizer | None = None,
        scheduler: torch.optim.lr_scheduler.LRScheduler | None = None,
        device:    str = "cpu",
    ) -> dict[str, object]:
        """
        Load the best checkpoint into *model* (and optionally optimizer/scheduler).

        Returns the raw checkpoint dict (contains 'epoch', 'val_loss', etc.).
        Raises FileNotFoundError if no best checkpoint exists yet.
        """
        return self._load(self._dir / self._BEST_NAME, model, optimizer,
                          scheduler, device)

    def load_latest(
        self,
        model:     nn.Module,
        optimizer: torch.optim.Optimizer | None = None,
        scheduler: torch.optim.lr_scheduler.LRScheduler | None = None,
        device:    str = "cpu",
    ) -> dict[str, object]:
        """
        Load the most recent checkpoint.

        Raises FileNotFoundError if no checkpoint exists yet.
        """
        return self._load(self._dir / self._LATEST_NAME, model, optimizer,
                          scheduler, device)

    def best_exists(self) -> bool:
        """Return True if a best checkpoint file exists on disk."""
        return (self._dir / self._BEST_NAME).exists()

    def latest_exists(self) -> bool:
        """Return True if a latest checkpoint file exists on disk."""
        return (self._dir / self._LATEST_NAME).exists()

    @property
    def best_val_loss(self) -> float:
        """Lowest validation loss seen so far."""
        return self._best_val_loss

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _load(
        self,
        path:      Path,
        model:     nn.Module,
        optimizer: torch.optim.Optimizer | None,
        scheduler: torch.optim.lr_scheduler.LRScheduler | None,
        device:    str,
    ) -> dict[str, object]:
        if not path.exists():
            raise FileNotFoundError(f"Checkpoint not found: {path}")

        saved: dict[str, object] = torch.load(
            path, map_location=device, weights_only=True
        )
        model.load_state_dict(saved["model_state"])  # type: ignore[arg-type]

        if optimizer is not None and "optim_state" in saved:
            optimizer.load_state_dict(saved["optim_state"])

        if (scheduler is not None
                and "scheduler_state" in saved
                and saved["scheduler_state"] is not None):
            scheduler.load_state_dict(saved["scheduler_state"])  # type: ignore[arg-type]

        self._log.info("checkpoint_loaded", path=str(path),
                       epoch=saved.get("epoch"), val_loss=saved.get("val_loss"))
        return saved
