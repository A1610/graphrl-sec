"""
T-HetGAT Runner — Module 11 CLI entrypoint.

Usage
-----
    python -m src.models.thetgat.runner

What this does
--------------
    1. Discovers all window .pt files in data/graphs/
    2. Stratified train / val / test split (80 / 10 / 10)
       Stratified = preserves the attack/normal ratio across splits.
    3. Loads the pretrained HeteroGraphEncoder from checkpoint_best.pt
    4. Runs THetGATTrainer.fit()
       - Phase A: encoder frozen for freeze_encoder_epochs
       - Phase B: full fine-tuning
       - Early stopping on val AUROC
    5. Runs THetGATEvaluator on held-out test split
    6. Prints and saves evaluation results

All outputs are written to models/thetgat/:
    thetgat_best.pt               — best checkpoint (highest val AUROC)
    thetgat_latest.pt             — most recent checkpoint
    thetgat_train_history.json    — per-epoch loss + AUROC
    thetgat_eval_results.json     — final test-set metrics
"""

from __future__ import annotations

import random
import sys
from pathlib import Path

import structlog
import torch

# ---------------------------------------------------------------------------
# Reproducibility — fix all random seeds before any imports that use RNG
# ---------------------------------------------------------------------------
_SEED = 42
random.seed(_SEED)
torch.manual_seed(_SEED)
if torch.cuda.is_available():
    torch.cuda.manual_seed_all(_SEED)

from src.models.thetgat.config import thetgat_settings  # noqa: E402
from src.models.thetgat.evaluate import THetGATEvaluator  # noqa: E402
from src.models.thetgat.model import THetGATModel  # noqa: E402
from src.models.thetgat.trainer import THetGATTrainer  # noqa: E402

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Data helpers
# ---------------------------------------------------------------------------


def _discover_windows(graphs_dir: Path) -> list[Path]:
    """
    Return all window_*.pt files sorted by name.

    Raises
    ------
    FileNotFoundError
        If graphs_dir does not exist or contains no window files.
    """
    if not graphs_dir.exists():
        raise FileNotFoundError(
            f"Graphs directory not found: {graphs_dir}\n"
            "Run the graph builder first (src/graph/runner.py)."
        )
    paths = sorted(graphs_dir.glob("window_*.pt"))
    if not paths:
        raise FileNotFoundError(
            f"No window_*.pt files found in {graphs_dir}."
        )
    return paths


def _get_window_label_from_path(path: Path, device: str) -> float:
    """Load a single window and extract its label (without keeping it in memory)."""
    data = torch.load(path, map_location=device, weights_only=False)
    return THetGATModel.get_window_label(data)


def _stratified_split(
    paths:      list[Path],
    val_frac:   float,
    test_frac:  float,
    device:     str,
) -> tuple[list[Path], list[Path], list[Path], tuple[list, list]]:
    """
    Stratified train / val / test split that preserves the attack/normal ratio.
    Also collects the union of all node/edge types seen across every window so
    that the model can be built with the full graph schema.

    Attack windows are rare (~17.5%) — random splitting could leave the
    val or test set with zero attacks.  Stratified splitting guarantees
    each split has at least some attack windows.

    Parameters
    ----------
    paths:
        All window paths, sorted.
    val_frac:
        Fraction of total windows allocated to validation.
    test_frac:
        Fraction of total windows allocated to test.
    device:
        Device string for label loading.

    Returns
    -------
    train_paths, val_paths, test_paths, metadata
        metadata is a (node_types, edge_types) tuple — union across all windows.
    """
    log = logger.bind(step="stratified_split")
    log.info("loading_labels_and_metadata", n_windows=len(paths))

    # Separate attack vs normal paths; collect graph metadata union in the
    # same pass so we only load each window once.
    attack_paths: list[Path] = []
    normal_paths: list[Path] = []
    node_types_union: set = set()
    edge_types_union: set = set()

    for p in paths:
        data = torch.load(p, map_location=device, weights_only=False)
        node_types_union.update(data.node_types)
        edge_types_union.update(data.edge_types)
        if THetGATModel.get_window_label(data) == 1.0:
            attack_paths.append(p)
        else:
            normal_paths.append(p)

    metadata = (sorted(node_types_union), sorted(edge_types_union))
    log.info(
        "label_counts",
        n_attack=len(attack_paths),
        n_normal=len(normal_paths),
        node_types=metadata[0],
        edge_types=[f"{s}__{r}__{d}" for s, r, d in metadata[1]],
    )

    def _split_list(lst: list[Path]) -> tuple[list[Path], list[Path], list[Path]]:
        """Split a list into train/val/test by fractions."""
        n      = len(lst)
        n_test = max(1, round(n * test_frac))
        n_val  = max(1, round(n * val_frac))
        shuffled = list(lst)
        random.shuffle(shuffled)
        test  = shuffled[:n_test]
        val   = shuffled[n_test : n_test + n_val]
        train = shuffled[n_test + n_val :]
        return train, val, test

    a_train, a_val, a_test = _split_list(attack_paths)
    n_train, n_val, n_test = _split_list(normal_paths)

    train = a_train + n_train
    val   = a_val   + n_val
    test  = a_test  + n_test

    # Shuffle each split so attack/normal windows are interleaved
    random.shuffle(train)
    random.shuffle(val)
    random.shuffle(test)

    log.info(
        "split_complete",
        train=len(train),
        val=len(val),
        test=len(test),
    )
    return train, val, test, metadata


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    cfg    = thetgat_settings
    device = cfg.device
    log    = logger.bind(module="thetgat_runner")

    log.info(
        "runner_start",
        device=device,
        graphs_dir=str(cfg.graphs_dir),
        pretrained_checkpoint=str(cfg.pretrained_checkpoint),
    )

    # ── 1. Discover windows ───────────────────────────────────────────
    all_paths = _discover_windows(cfg.graphs_dir)
    log.info("windows_found", total=len(all_paths))

    # ── 2. Stratified split + full metadata union ─────────────────────
    # Metadata is collected in the same pass as label loading (zero extra I/O).
    # Using the union of all windows ensures the model handles every node/edge
    # type it will encounter during training and evaluation.
    train_paths, val_paths, test_paths, metadata = _stratified_split(
        all_paths, cfg.val_split, cfg.test_split, device
    )

    # ── 3. Build model with full graph schema ─────────────────────────
    log.info("building_model", node_types=metadata[0])
    model = THetGATModel(metadata, cfg).to(device)

    # ── 4. Load pretrained encoder ────────────────────────────────────
    ckpt_info = THetGATModel.load_pretrained_encoder(
        model, cfg.pretrained_checkpoint, device
    )
    log.info(
        "pretrained_encoder_loaded",
        pretrain_epoch=ckpt_info.get("epoch"),
        pretrain_val_loss=ckpt_info.get("val_loss"),
    )

    # ── 5. Count parameters ───────────────────────────────────────────
    total_params    = sum(p.numel() for p in model.parameters())
    trainable_params = sum(p.numel() for p in model.parameters() if p.requires_grad)
    print(f"\nModel parameters: {total_params:,} total | "
          f"{trainable_params:,} trainable (encoder frozen initially)\n")

    # ── 6. Train ──────────────────────────────────────────────────────
    log.info("training_start")
    trainer = THetGATTrainer(model, train_paths, val_paths, cfg)
    history = trainer.fit()

    # Print training summary
    best_state = max(history, key=lambda s: s.val_auroc)
    print(f"\nTraining complete — {len(history)} epochs")
    print(f"  Best val AUROC : {best_state.val_auroc:.4f}  (epoch {best_state.epoch})")
    print(f"  Best val loss  : {best_state.val_loss:.4f}")

    # ── 7. Evaluate on test set ───────────────────────────────────────
    log.info("evaluation_start")
    evaluator = THetGATEvaluator(test_paths, cfg)
    results   = evaluator.evaluate()
    results.print_report()

    # ── 8. Exit code — non-zero if target not met ─────────────────────
    # AUROC > 0.9804 (Node2Vec baseline) is the success criterion.
    if results.auroc <= 0.9804:
        log.warning(
            "target_not_met",
            auroc=results.auroc,
            target=0.9804,
        )
        sys.exit(1)

    log.info("runner_complete", auroc=results.auroc, f1=results.best_f1)


if __name__ == "__main__":
    main()
