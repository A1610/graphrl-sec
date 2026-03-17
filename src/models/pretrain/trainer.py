"""
Self-supervised pre-training loop for HeteroGraphEncoder.

Training objective: GraphCL contrastive learning.
    For each pair of adjacent temporal graph windows (t, t+1):
        1. Create two augmented views via GraphAugmentor
        2. Encode both views with HeteroGraphEncoder
        3. Project via the contrastive projection head
        4. Compute NT-Xent loss over all node pairs

Hardware target: RTX 3050 6 GB VRAM
    - FP16 automatic mixed precision (halves VRAM)
    - Configurable batch size (default 16 graphs per batch)
    - Gradient clipping to stabilise training

Entry point::

    python -m src.models.pretrain.trainer

Or programmatically::

    trainer = PretrainTrainer(config)
    result  = trainer.train(snapshot_dir=Path("data/graphs"))
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path

import structlog
import torch
import torch.nn as nn
from torch.amp import GradScaler, autocast
from torch_geometric.data import Batch, HeteroData

from src.models.pretrain.augmentation import GraphAugmentor
from src.models.pretrain.checkpoint import CheckpointManager
from src.models.pretrain.config import PretrainConfig, pretrain_settings
from src.models.pretrain.contrastive import NTXentLoss, collect_node_projections
from src.models.pretrain.encoder import HeteroGraphEncoder

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Training result
# ---------------------------------------------------------------------------


@dataclass
class PretrainResult:
    """Summary returned by PretrainTrainer.train()."""

    best_val_loss:  float
    final_epoch:    int
    train_losses:   list[float] = field(default_factory=list)
    val_losses:     list[float] = field(default_factory=list)
    elapsed_s:      float = 0.0
    stopped_early:  bool  = False


# ---------------------------------------------------------------------------
# Snapshot dataset helpers
# ---------------------------------------------------------------------------


def _load_snapshots(snapshot_dir: Path) -> list[HeteroData]:
    """
    Load all serialised HeteroData snapshots from *snapshot_dir*.

    Files must be PyTorch .pt files saved by PyGConverter (or manually).
    Returns snapshots sorted by filename so temporal order is preserved.
    """
    pt_files = sorted(snapshot_dir.glob("*.pt"))
    if not pt_files:
        raise FileNotFoundError(
            f"No .pt snapshot files found in {snapshot_dir}. "
            "Run the ingestion pipeline first:\n"
            "  python -m src.ingestion.cli ingest --dataset unsw "
            "--path data/raw/unsw/ --mode batch"
        )

    snapshots: list[HeteroData] = []
    for path in pt_files:
        data: HeteroData = torch.load(path, map_location="cpu", weights_only=False)
        snapshots.append(data)

    logger.info("snapshots_loaded", count=len(snapshots), dir=str(snapshot_dir))
    return snapshots


def _build_pairs(snapshots: list[HeteroData]) -> list[tuple[HeteroData, HeteroData]]:
    """
    Create (window_t, window_t+1) adjacent pairs for contrastive learning.

    Each pair shares the same underlying graph structure — the encoder
    must learn representations invariant to the two augmented views.
    """
    return [(snapshots[i], snapshots[i + 1]) for i in range(len(snapshots) - 1)]


def _train_val_split(
    pairs:      list[tuple[HeteroData, HeteroData]],
    val_split:  float,
) -> tuple[list[tuple[HeteroData, HeteroData]], list[tuple[HeteroData, HeteroData]]]:
    """Split pairs into train / validation sets (chronological split, no shuffle)."""
    n_val  = max(1, int(len(pairs) * val_split))
    n_train = len(pairs) - n_val
    return pairs[:n_train], pairs[n_train:]


# ---------------------------------------------------------------------------
# Trainer
# ---------------------------------------------------------------------------


class PretrainTrainer:
    """
    Manages the full pre-training lifecycle.

    Parameters
    ----------
    config : PretrainConfig, optional
        Hyperparameters.  Defaults to pretrain_settings (env / .env).

    Example
    -------
    ::

        trainer = PretrainTrainer()
        result  = trainer.train(snapshot_dir=Path("data/graphs"))
        print(f"Best val loss: {result.best_val_loss:.4f}")
    """

    def __init__(self, config: PretrainConfig | None = None) -> None:
        self._cfg     = config or pretrain_settings
        self._log     = logger.bind(
            hidden_dim=self._cfg.hidden_dim,
            num_layers=self._cfg.num_layers,
            device=self._cfg.device,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def train(self, snapshot_dir: Path | None = None) -> PretrainResult:
        """
        Run the full pre-training loop.

        Parameters
        ----------
        snapshot_dir :
            Directory containing .pt HeteroData snapshots.
            Defaults to config.graphs_dir.

        Returns
        -------
        PretrainResult with loss curves and best checkpoint info.
        """
        graphs_dir = snapshot_dir or self._cfg.graphs_dir
        device     = torch.device(
            self._cfg.device
            if (self._cfg.device != "cuda" or torch.cuda.is_available())
            else "cpu"
        )

        self._log.info("pretrain_start", device=str(device),
                       graphs_dir=str(graphs_dir))

        # --- Data ---
        snapshots = _load_snapshots(graphs_dir)
        pairs     = _build_pairs(snapshots)
        if not pairs:
            raise ValueError(
                f"Need at least 2 snapshots to form a training pair, "
                f"got {len(snapshots)}."
            )

        train_pairs, val_pairs = _train_val_split(pairs, self._cfg.val_split)
        self._log.info("data_split", train_pairs=len(train_pairs),
                       val_pairs=len(val_pairs))

        # --- Model + optimiser ---
        # Infer graph metadata from the first snapshot
        metadata = snapshots[0].metadata()
        model    = HeteroGraphEncoder(metadata, self._cfg).to(device)
        optimizer = torch.optim.AdamW(
            model.parameters(),
            lr=self._cfg.learning_rate,
            weight_decay=self._cfg.weight_decay,
        )
        scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(
            optimizer,
            T_max=self._cfg.num_epochs,
            eta_min=self._cfg.learning_rate * 0.01,
        )

        # --- Supporting objects ---
        augmentor   = GraphAugmentor(self._cfg)
        loss_fn     = NTXentLoss(self._cfg)
        ckpt_mgr    = CheckpointManager(self._cfg)
        use_amp     = self._cfg.mixed_precision and device.type == "cuda"
        scaler      = GradScaler("cuda", enabled=use_amp)

        result = PretrainResult(best_val_loss=float("inf"), final_epoch=0)
        patience_counter = 0
        t0 = time.monotonic()

        for epoch in range(1, self._cfg.num_epochs + 1):
            # ---- Train ----
            train_loss = self._run_epoch(
                model, optimizer, scaler, augmentor, loss_fn,
                train_pairs, device, use_amp, training=True,
            )
            scheduler.step()

            # ---- Validate ----
            val_loss = self._run_epoch(
                model, None, scaler, augmentor, loss_fn,
                val_pairs, device, use_amp, training=False,
            )

            result.train_losses.append(train_loss)
            result.val_losses.append(val_loss)

            # ---- Checkpoint ----
            meta = ckpt_mgr.save(
                model, optimizer, scheduler,
                epoch=epoch, train_loss=train_loss, val_loss=val_loss,
            )

            # ---- Logging ----
            if epoch % self._cfg.log_every_n_epochs == 0 or epoch == 1:
                self._log.info(
                    "epoch",
                    epoch=epoch,
                    train_loss=round(train_loss, 4),
                    val_loss=round(val_loss, 4),
                    lr=round(scheduler.get_last_lr()[0], 6),
                    best=meta.is_best,
                    gpu_mb=round(
                        torch.cuda.memory_allocated(device) / 1_048_576, 1
                    ) if device.type == "cuda" else 0,
                )

            # ---- Early stopping ----
            if meta.is_best:
                result.best_val_loss = val_loss
                patience_counter = 0
            else:
                patience_counter += 1
                if patience_counter >= self._cfg.early_stopping_patience:
                    self._log.info("early_stopping", epoch=epoch,
                                   patience=self._cfg.early_stopping_patience)
                    result.stopped_early = True
                    break

        result.final_epoch = epoch  # noqa: B023  (defined in loop, always runs ≥1)
        result.elapsed_s   = round(time.monotonic() - t0, 2)

        self._log.info(
            "pretrain_complete",
            best_val_loss=round(result.best_val_loss, 4),
            final_epoch=result.final_epoch,
            elapsed_s=result.elapsed_s,
            stopped_early=result.stopped_early,
        )
        return result

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _run_epoch(
        self,
        model:      HeteroGraphEncoder,
        optimizer:  torch.optim.Optimizer | None,
        scaler:     GradScaler,
        augmentor:  GraphAugmentor,
        loss_fn:    NTXentLoss,
        pairs:      list[tuple[HeteroData, HeteroData]],
        device:     torch.device,
        use_amp:    bool,
        training:   bool,
    ) -> float:
        """Run one full pass (train or eval) over all pairs. Returns mean loss."""
        model.train(training)
        total_loss  = 0.0
        valid_pairs = 0

        ctx = torch.enable_grad() if training else torch.no_grad()  # type: ignore[no-untyped-call]
        with ctx:
            batch_size = self._cfg.batch_size
            for start in range(0, len(pairs), batch_size):
                mini = pairs[start : start + batch_size]

                # GraphCL: augment each source graph TWICE → guaranteed equal node counts.
                # We use graph_a (window t) as the anchor; graph_b is intentionally
                # unused here because two views of the same graph is the standard
                # GraphCL positive-pair definition and avoids shape-mismatch issues
                # that arise when adjacent windows have different node populations.
                views_a: list[HeteroData] = []
                views_b: list[HeteroData] = []
                for graph_a, _graph_b in mini:
                    src = graph_a.to(device)
                    v1, _ = augmentor(src)
                    v2, _ = augmentor(src)
                    views_a.append(v1)
                    views_b.append(v2)

                # Batch all graphs in the mini-batch into two disconnected unions
                batch_a = Batch.from_data_list(views_a)
                batch_b = Batch.from_data_list(views_b)

                with autocast("cuda", enabled=use_amp):
                    proj1 = model.project(batch_a.x_dict, batch_a.edge_index_dict)
                    proj2 = model.project(batch_b.x_dict, batch_b.edge_index_dict)

                    pair_tensors = collect_node_projections(proj1, proj2)
                    if pair_tensors is None:
                        continue

                    z1, z2 = pair_tensors
                    loss   = loss_fn(z1, z2)

                if training and optimizer is not None:
                    optimizer.zero_grad()
                    scaler.scale(loss).backward()
                    if self._cfg.grad_clip_norm > 0:
                        scaler.unscale_(optimizer)
                        nn.utils.clip_grad_norm_(
                            model.parameters(), self._cfg.grad_clip_norm
                        )
                    scaler.step(optimizer)
                    scaler.update()

                total_loss  += loss.item()
                valid_pairs += 1

        return total_loss / valid_pairs if valid_pairs > 0 else 0.0


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Run pre-training from the command line."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Self-supervised pre-training for HeteroGraphEncoder"
    )
    parser.add_argument(
        "--graphs-dir",
        type=Path,
        default=None,
        help="Directory of .pt HeteroData snapshots (default: config.graphs_dir)",
    )
    args = parser.parse_args()

    trainer = PretrainTrainer()
    result  = trainer.train(snapshot_dir=args.graphs_dir)

    print("\nPre-training complete.")
    print(f"  Best val loss : {result.best_val_loss:.4f}")
    print(f"  Final epoch   : {result.final_epoch}")
    print(f"  Elapsed       : {result.elapsed_s:.1f}s")
    print(f"  Early stopped : {result.stopped_early}")
    print(f"\nCheckpoints saved to: {pretrain_settings.checkpoint_dir}")


if __name__ == "__main__":
    main()
