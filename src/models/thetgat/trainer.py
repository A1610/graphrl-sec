"""
T-HetGAT Training Pipeline — Module 11.

Training strategy
-----------------
    Phase A — Encoder frozen (epochs 0…freeze_encoder_epochs-1):
        Only GAT layers + scorer receive gradients.
        The randomly-initialised attention layers stabilise before the
        pre-trained backbone is allowed to adapt.

    Phase B — Full fine-tuning (epochs freeze_encoder_epochs…):
        Encoder unfrozen.  Full end-to-end optimisation.

Optimiser & schedule
---------------------
    AdamW with weight decay.
    Linear warmup over warmup_epochs, then cosine annealing to 0.

Loss
----
    FocalLoss(alpha=0.25, gamma=2.0) for the 82.5% normal / 17.5% attack split.

Early stopping
--------------
    Monitors validation AUROC (higher is better).
    Stops after early_stopping_patience epochs without improvement.
    Best checkpoint (highest val AUROC) is saved to checkpoint_dir.

Mixed precision
---------------
    torch.cuda.amp.GradScaler + autocast when mixed_precision=True.
    Halves VRAM usage on RTX 3050 without measurable accuracy loss.

File exports
------------
    WindowDataset    — lightweight list-based dataset of HeteroData windows
    TrainState       — dataclass with epoch results
    THetGATTrainer   — full training orchestration
"""

from __future__ import annotations

import json
import math
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import structlog
import torch
import torch.nn as nn
from sklearn.metrics import roc_auc_score
from torch import Tensor
from torch.amp import GradScaler, autocast
from torch.optim import AdamW
from torch.optim.lr_scheduler import CosineAnnealingLR, LinearLR, SequentialLR
from torch_geometric.data import HeteroData

from src.models.thetgat.config import THetGATConfig, thetgat_settings
from src.models.thetgat.losses import FocalLoss
from src.models.thetgat.model import THetGATModel

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Dataset
# ---------------------------------------------------------------------------


class WindowDataset:
    """
    Lightweight dataset wrapping a list of HeteroData window snapshots.

    Each window is a single ``.pt`` file on disk (or a pre-loaded object).
    Loading is lazy — only materialised when ``__getitem__`` is called.

    Parameters
    ----------
    paths:
        List of paths to serialised HeteroData ``.pt`` files.
    device:
        Device to map tensors to on load.
    """

    def __init__(self, paths: list[Path], device: str = "cpu") -> None:
        self._paths  = paths
        self._device = device

    def __len__(self) -> int:
        return len(self._paths)

    def __getitem__(self, idx: int) -> HeteroData:
        data: HeteroData = torch.load(
            self._paths[idx], map_location=self._device, weights_only=False
        )
        return data

    def iter_shuffled(self) -> list[Path]:
        """Return a shuffled copy of the path list (does not mutate)."""
        paths = list(self._paths)
        random.shuffle(paths)
        return paths


# ---------------------------------------------------------------------------
# Epoch result dataclass
# ---------------------------------------------------------------------------


@dataclass
class TrainState:
    """Results for a single training epoch."""

    epoch:      int
    train_loss: float
    val_loss:   float
    val_auroc:  float
    lr:         float
    is_best:    bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "epoch":      self.epoch,
            "train_loss": round(self.train_loss, 6),
            "val_loss":   round(self.val_loss,   6),
            "val_auroc":  round(self.val_auroc,  6),
            "lr":         self.lr,
            "is_best":    self.is_best,
        }


# ---------------------------------------------------------------------------
# Trainer
# ---------------------------------------------------------------------------


class THetGATTrainer:
    """
    Orchestrates the full T-HetGAT training loop.

    Parameters
    ----------
    model:
        The :class:`THetGATModel` to train (already has pretrained encoder loaded).
    train_paths:
        Paths to training window ``.pt`` files.
    val_paths:
        Paths to validation window ``.pt`` files.
    cfg:
        Hyperparameter config.  Defaults to module-level singleton.

    Example
    -------
    ::

        model = THetGATModel(metadata)
        THetGATModel.load_pretrained_encoder(model, cfg.pretrained_checkpoint, device)
        model.to(device)

        trainer = THetGATTrainer(model, train_paths, val_paths)
        history = trainer.fit()
    """

    def __init__(
        self,
        model:       THetGATModel,
        train_paths: list[Path],
        val_paths:   list[Path],
        cfg:         THetGATConfig | None = None,
    ) -> None:
        self._cfg    = cfg or thetgat_settings
        self._model  = model
        self._device = torch.device(self._cfg.device)
        self._log    = logger.bind(trainer="THetGATTrainer")

        # Datasets (lazy loading)
        self._train_ds = WindowDataset(train_paths, device=str(self._device))
        self._val_ds   = WindowDataset(val_paths,   device=str(self._device))

        # Loss
        self._criterion = FocalLoss(
            alpha=self._cfg.focal_alpha,
            gamma=self._cfg.focal_gamma,
        )

        # Optimiser — weight decay applied to all params initially;
        # we update param groups in _build_optimizer after freeze/unfreeze.
        self._optimizer = AdamW(
            filter(lambda p: p.requires_grad, model.parameters()),
            lr=self._cfg.learning_rate,
            weight_decay=self._cfg.weight_decay,
        )

        # LR scheduler: linear warmup → cosine annealing
        self._scheduler = self._build_scheduler()

        # AMP scaler (no-op when mixed_precision=False or on CPU)
        self._use_amp = (
            self._cfg.mixed_precision
            and self._device.type == "cuda"
        )
        self._scaler = GradScaler("cuda", enabled=self._use_amp)

        # Checkpoint directory
        self._ckpt_dir = self._cfg.checkpoint_dir
        self._ckpt_dir.mkdir(parents=True, exist_ok=True)

        # Early stopping state
        self._best_auroc:   float = -1.0
        self._patience_ctr: int   = 0

        self._log.info(
            "trainer_init",
            train_windows=len(train_paths),
            val_windows=len(val_paths),
            device=str(self._device),
            use_amp=self._use_amp,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def fit(self) -> list[TrainState]:
        """
        Run the full training loop.

        Returns
        -------
        list[TrainState]
            Per-epoch results for the full training run.
        """
        history: list[TrainState] = []

        # Freeze encoder for the warm-up phase
        self._model.freeze_encoder()
        self._log.info("phase_A_start", freeze_epochs=self._cfg.freeze_encoder_epochs)

        for epoch in range(self._cfg.num_epochs):
            # ── Phase transition: unfreeze encoder ───────────────────────
            if epoch == self._cfg.freeze_encoder_epochs:
                self._model.unfreeze_encoder()
                # Rebuild optimizer to include all encoder parameters
                self._optimizer = AdamW(
                    self._model.parameters(),
                    lr=self._cfg.learning_rate,
                    weight_decay=self._cfg.weight_decay,
                )
                self._scheduler = self._build_scheduler(
                    last_epoch_offset=epoch
                )
                self._log.info("phase_B_start", epoch=epoch)

            # ── Train ─────────────────────────────────────────────────
            train_loss = self._run_epoch_train(epoch)

            # ── Validate ──────────────────────────────────────────────
            val_loss, val_auroc = self._run_epoch_val(epoch)

            # ── LR step ───────────────────────────────────────────────
            current_lr = self._optimizer.param_groups[0]["lr"]
            self._scheduler.step()

            # ── Checkpoint ────────────────────────────────────────────
            is_best = val_auroc > self._best_auroc
            if is_best:
                self._best_auroc   = val_auroc
                self._patience_ctr = 0
                self._save_checkpoint(epoch, train_loss, val_loss, val_auroc, best=True)
            else:
                self._patience_ctr += 1
                self._save_checkpoint(epoch, train_loss, val_loss, val_auroc, best=False)

            state = TrainState(
                epoch=epoch,
                train_loss=train_loss,
                val_loss=val_loss,
                val_auroc=val_auroc,
                lr=current_lr,
                is_best=is_best,
            )
            history.append(state)

            # ── Logging ───────────────────────────────────────────────
            if (epoch % self._cfg.log_every_n_epochs == 0) or is_best:
                self._log.info(
                    "epoch",
                    **state.as_dict(),
                    patience=self._patience_ctr,
                )

            # ── Early stopping ────────────────────────────────────────
            if self._patience_ctr >= self._cfg.early_stopping_patience:
                self._log.info(
                    "early_stopping",
                    epoch=epoch,
                    best_auroc=round(self._best_auroc, 4),
                    patience=self._cfg.early_stopping_patience,
                )
                break

        self._save_history(history)
        self._log.info(
            "training_complete",
            epochs_run=len(history),
            best_val_auroc=round(self._best_auroc, 4),
        )
        return history

    # ------------------------------------------------------------------
    # Internal — train epoch
    # ------------------------------------------------------------------

    def _run_epoch_train(self, epoch: int) -> float:
        """One training epoch — returns mean Focal loss."""
        self._model.train()
        # Keep the pretrained encoder's BatchNorm1d layers in eval mode.
        # Graph windows can contain as few as 1 node per type, and
        # BatchNorm1d raises when batch_size=1 in training mode.
        # Using running statistics (eval mode) is also more stable for
        # fine-tuning since the pretrained running mean/var are reliable.
        self._model.encoder.eval()
        total_loss = 0.0
        n_windows  = 0

        # Shuffle each epoch for stochasticity
        for path in self._train_ds.iter_shuffled():
            data: HeteroData = torch.load(
                path, map_location=self._device, weights_only=False
            )
            label = torch.tensor(
                THetGATModel.get_window_label(data),
                dtype=torch.float32,
                device=self._device,
            )

            self._optimizer.zero_grad(set_to_none=True)

            with autocast(device_type=self._device.type, enabled=self._use_amp):
                logit: Tensor = self._model(data)
                loss: Tensor  = self._criterion(logit.unsqueeze(0), label.unsqueeze(0))

            self._scaler.scale(loss).backward()
            self._scaler.unscale_(self._optimizer)
            nn.utils.clip_grad_norm_(
                self._model.parameters(), self._cfg.grad_clip_norm
            )
            self._scaler.step(self._optimizer)
            self._scaler.update()

            total_loss += loss.item()
            n_windows  += 1

        return total_loss / max(n_windows, 1)

    # ------------------------------------------------------------------
    # Internal — validation epoch
    # ------------------------------------------------------------------

    def _run_epoch_val(self, epoch: int) -> tuple[float, float]:
        """
        One validation pass.

        Returns
        -------
        tuple[float, float]
            ``(mean_val_loss, val_auroc)``
        """
        self._model.eval()
        total_loss = 0.0
        all_labels: list[float] = []
        all_probs:  list[float] = []

        with torch.no_grad():
            for i in range(len(self._val_ds)):
                data  = self._val_ds[i]
                label = THetGATModel.get_window_label(data)
                label_t = torch.tensor(
                    label, dtype=torch.float32, device=self._device
                )

                with autocast(device_type=self._device.type, enabled=self._use_amp):
                    logit = self._model(data)
                    loss  = self._criterion(
                        logit.unsqueeze(0), label_t.unsqueeze(0)
                    )

                total_loss += loss.item()
                all_labels.append(label)
                all_probs.append(torch.sigmoid(logit).item())

        mean_loss = total_loss / max(len(self._val_ds), 1)

        # AUROC requires at least one positive and one negative sample
        unique_labels = set(all_labels)
        if len(unique_labels) < 2:
            self._log.warning(
                "val_auroc_undefined",
                epoch=epoch,
                unique_labels=list(unique_labels),
                reason="Only one class present in validation set",
            )
            auroc = 0.5  # Random-chance fallback
        else:
            auroc = float(roc_auc_score(all_labels, all_probs))

        return mean_loss, auroc

    # ------------------------------------------------------------------
    # Internal — checkpointing
    # ------------------------------------------------------------------

    def _save_checkpoint(
        self,
        epoch:      int,
        train_loss: float,
        val_loss:   float,
        val_auroc:  float,
        best:       bool,
    ) -> None:
        payload: dict[str, Any] = {
            "epoch":         epoch,
            "model_state":   self._model.state_dict(),
            "optim_state":   self._optimizer.state_dict(),
            "scheduler_state": self._scheduler.state_dict(),
            "train_loss":    train_loss,
            "val_loss":      val_loss,
            "val_auroc":     val_auroc,
            "config":        self._cfg.model_dump(mode="json"),
        }

        latest = self._ckpt_dir / "thetgat_latest.pt"
        torch.save(payload, latest)

        if best:
            best_path = self._ckpt_dir / "thetgat_best.pt"
            torch.save(payload, best_path)
            self._log.info(
                "checkpoint_best_saved",
                epoch=epoch,
                val_auroc=round(val_auroc, 4),
                path=str(best_path),
            )

    def _save_history(self, history: list[TrainState]) -> None:
        out_path = self._cfg.results_dir / "thetgat_train_history.json"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with out_path.open("w") as fh:
            json.dump([s.as_dict() for s in history], fh, indent=2)
        self._log.info("history_saved", path=str(out_path))

    # ------------------------------------------------------------------
    # Internal — scheduler construction
    # ------------------------------------------------------------------

    def _build_scheduler(
        self, last_epoch_offset: int = 0
    ) -> SequentialLR:
        """
        Build a warmup + cosine schedule.

        Linear warmup from lr/10 → lr over ``warmup_epochs`` epochs,
        then cosine annealing from lr → 0 over the remaining epochs.
        """
        warmup_epochs = self._cfg.warmup_epochs
        total_epochs  = self._cfg.num_epochs - last_epoch_offset
        cosine_epochs = max(total_epochs - warmup_epochs, 1)

        warmup = LinearLR(
            self._optimizer,
            start_factor=0.1,
            end_factor=1.0,
            total_iters=warmup_epochs,
        )
        cosine = CosineAnnealingLR(
            self._optimizer,
            T_max=cosine_epochs,
            eta_min=self._cfg.learning_rate * 1e-3,
        )
        return SequentialLR(
            self._optimizer,
            schedulers=[warmup, cosine],
            milestones=[warmup_epochs],
        )
