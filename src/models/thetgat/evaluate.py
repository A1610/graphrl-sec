"""
T-HetGAT Evaluation — Module 11.

Loads the best checkpoint (thetgat_best.pt), runs inference on the held-out
test set, and computes a full suite of classification metrics.

Metrics computed
----------------
    AUROC           — primary metric, threshold-independent ranking quality
    Average Precision (AP) — area under precision-recall curve
    Best-threshold F1      — F1 at the threshold that maximises it
    Precision @ best-F1 threshold
    Recall    @ best-F1 threshold
    Confusion matrix       — TP, FP, TN, FN

Baseline comparison
-------------------
    Results are compared against the Node2Vec + Isolation Forest baseline:
        AUROC = 0.9804  |  F1 = 0.4912

    T-HetGAT target: AUROC > 0.9804  AND  F1 > 0.65

Output files
------------
    models/thetgat/thetgat_eval_results.json  — all metrics as JSON

File exports
------------
    EvalResults     — dataclass with all evaluation metrics
    THetGATEvaluator — loads checkpoint + runs test-set evaluation
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import structlog
import torch
from sklearn.metrics import (
    average_precision_score,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from torch.amp import autocast
from torch_geometric.data import HeteroData

from src.models.thetgat.config import THetGATConfig, thetgat_settings
from src.models.thetgat.model import THetGATModel
from src.models.thetgat.trainer import WindowDataset

logger = structlog.get_logger(__name__)

# Node2Vec + Isolation Forest baseline (Module 09)
_BASELINE_AUROC = 0.9804
_BASELINE_F1    = 0.4912


# ---------------------------------------------------------------------------
# Results dataclass
# ---------------------------------------------------------------------------


@dataclass
class EvalResults:
    """All evaluation metrics for one test run."""

    # Primary metrics
    auroc:              float
    average_precision:  float

    # Threshold-dependent metrics (at best-F1 threshold)
    best_f1:            float
    best_threshold:     float
    precision_at_best:  float
    recall_at_best:     float

    # Confusion matrix (at best-F1 threshold)
    true_positives:     int
    false_positives:    int
    true_negatives:     int
    false_negatives:    int

    # Dataset statistics
    n_test_windows:     int
    n_attack_windows:   int
    n_normal_windows:   int
    attack_rate:        float   # fraction of test windows that are attacks

    # Comparison against baseline
    auroc_vs_baseline:  float   # positive = improvement
    f1_vs_baseline:     float

    # Checkpoint info
    checkpoint_epoch:   int
    checkpoint_val_auroc: float

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def print_report(self) -> None:
        """Print a formatted evaluation report to stdout."""
        beat_auroc = self.auroc > _BASELINE_AUROC
        beat_f1    = self.best_f1 > _BASELINE_F1

        print("\n" + "=" * 60)
        print("  T-HetGAT Evaluation Results")
        print("=" * 60)
        print(f"  Test windows : {self.n_test_windows:,}")
        print(f"  Attack       : {self.n_attack_windows:,}  "
              f"({self.attack_rate * 100:.1f}%)")
        print(f"  Normal       : {self.n_normal_windows:,}")
        print("-" * 60)
        print(f"  AUROC        : {self.auroc:.4f}  "
              f"({'[BEATS]' if beat_auroc else '[BELOW]'} baseline {_BASELINE_AUROC})")
        print(f"  Avg Precision: {self.average_precision:.4f}")
        print(f"  Best F1      : {self.best_f1:.4f}  "
              f"({'[BEATS]' if beat_f1 else '[BELOW]'} baseline {_BASELINE_F1})")
        print(f"  Threshold    : {self.best_threshold:.4f}")
        print(f"  Precision    : {self.precision_at_best:.4f}")
        print(f"  Recall       : {self.recall_at_best:.4f}")
        print("-" * 60)
        print(f"  Confusion Matrix (at best-F1 threshold):")
        print(f"    TP={self.true_positives}  FP={self.false_positives}")
        print(f"    FN={self.false_negatives}  TN={self.true_negatives}")
        print("-" * 60)
        print(f"  AUROC  improvement vs baseline: "
              f"{self.auroc_vs_baseline:+.4f}")
        print(f"  F1     improvement vs baseline: "
              f"{self.f1_vs_baseline:+.4f}")
        print("=" * 60 + "\n")


# ---------------------------------------------------------------------------
# Evaluator
# ---------------------------------------------------------------------------


class THetGATEvaluator:
    """
    Loads the best T-HetGAT checkpoint and evaluates it on a test set.

    Parameters
    ----------
    test_paths:
        Paths to held-out test window ``.pt`` files.
    cfg:
        Hyperparameter config.  Defaults to module-level singleton.

    Example
    -------
    ::

        evaluator = THetGATEvaluator(test_paths)
        results   = evaluator.evaluate()
        results.print_report()
    """

    def __init__(
        self,
        test_paths: list[Path],
        cfg: THetGATConfig | None = None,
    ) -> None:
        self._cfg     = cfg or thetgat_settings
        self._device  = torch.device(self._cfg.device)
        self._log     = logger.bind(evaluator="THetGATEvaluator")
        self._test_ds = WindowDataset(test_paths, device=str(self._device))

        self._use_amp = (
            self._cfg.mixed_precision
            and self._device.type == "cuda"
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def evaluate(self) -> EvalResults:
        """
        Load best checkpoint, run inference on the test set, compute metrics.

        Returns
        -------
        EvalResults
            All evaluation metrics.
        """
        model, ckpt_meta = self._load_model()
        results = self._run_inference(model, ckpt_meta)
        self._save_results(results)
        return results

    # ------------------------------------------------------------------
    # Internal — model loading
    # ------------------------------------------------------------------

    def _load_model(self) -> tuple[THetGATModel, dict[str, Any]]:
        """
        Load best checkpoint.

        Builds model from a sample test window (to get metadata),
        then loads the saved state dict.
        """
        best_ckpt = self._cfg.checkpoint_dir / "thetgat_best.pt"
        if not best_ckpt.exists():
            raise FileNotFoundError(
                f"Best checkpoint not found: {best_ckpt}\n"
                "Run training first: python -m src.models.thetgat.runner"
            )

        # Load a sample window to infer graph metadata
        if len(self._test_ds) == 0:
            raise ValueError("Test dataset is empty — no windows to evaluate.")
        sample: HeteroData = self._test_ds[0]

        # Build model with same architecture
        model = THetGATModel(sample.metadata(), self._cfg).to(self._device)

        # Load trained weights
        saved: dict[str, Any] = torch.load(
            best_ckpt, map_location=self._device, weights_only=True
        )
        model.load_state_dict(saved["model_state"])
        model.eval()

        self._log.info(
            "checkpoint_loaded",
            path=str(best_ckpt),
            epoch=saved.get("epoch"),
            val_auroc=saved.get("val_auroc"),
        )
        return model, saved

    # ------------------------------------------------------------------
    # Internal — inference
    # ------------------------------------------------------------------

    def _run_inference(
        self,
        model: THetGATModel,
        ckpt_meta: dict[str, Any],
    ) -> EvalResults:
        """Run model on all test windows, collect labels + probs, compute metrics."""
        all_labels: list[float] = []
        all_probs:  list[float] = []

        with torch.no_grad():
            for i in range(len(self._test_ds)):
                data  = self._test_ds[i]
                label = THetGATModel.get_window_label(data)

                with autocast(device_type=self._device.type, enabled=self._use_amp):
                    logit = model(data)
                    prob  = torch.sigmoid(logit).item()

                all_labels.append(label)
                all_probs.append(prob)

        return self._compute_metrics(all_labels, all_probs, ckpt_meta)

    # ------------------------------------------------------------------
    # Internal — metrics
    # ------------------------------------------------------------------

    def _compute_metrics(
        self,
        labels:    list[float],
        probs:     list[float],
        ckpt_meta: dict[str, Any],
    ) -> EvalResults:
        """Compute all classification metrics from raw labels and probabilities."""
        n_total  = len(labels)
        n_attack = int(sum(labels))
        n_normal = n_total - n_attack

        # --- AUROC & Average Precision -----------------------------------
        unique = set(labels)
        if len(unique) < 2:
            self._log.warning(
                "eval_only_one_class",
                unique_labels=list(unique),
                reason="AUROC and AP are undefined — defaulting to 0.5 / 0.0",
            )
            auroc = 0.5
            ap    = 0.0
        else:
            auroc = float(roc_auc_score(labels, probs))
            ap    = float(average_precision_score(labels, probs))

        # --- Best-threshold F1 ------------------------------------------
        # Search over 100 candidate thresholds in [0.01, 0.99]
        best_f1   = 0.0
        best_thr  = 0.5
        for thr in [t / 100 for t in range(1, 100)]:
            preds = [1 if p >= thr else 0 for p in probs]
            f1 = float(f1_score(labels, preds, zero_division=0))
            if f1 > best_f1:
                best_f1  = f1
                best_thr = thr

        # Final metrics at best threshold
        final_preds = [1 if p >= best_thr else 0 for p in probs]
        prec   = float(precision_score(labels, final_preds, zero_division=0))
        recall = float(recall_score(labels,    final_preds, zero_division=0))

        # Confusion matrix: [[TN, FP], [FN, TP]]
        cm = confusion_matrix(labels, final_preds, labels=[0, 1])
        tn, fp, fn, tp = cm.ravel().tolist()

        return EvalResults(
            auroc              = auroc,
            average_precision  = ap,
            best_f1            = best_f1,
            best_threshold     = best_thr,
            precision_at_best  = prec,
            recall_at_best     = recall,
            true_positives     = int(tp),
            false_positives    = int(fp),
            true_negatives     = int(tn),
            false_negatives    = int(fn),
            n_test_windows     = n_total,
            n_attack_windows   = n_attack,
            n_normal_windows   = n_normal,
            attack_rate        = n_attack / max(n_total, 1),
            auroc_vs_baseline  = auroc - _BASELINE_AUROC,
            f1_vs_baseline     = best_f1 - _BASELINE_F1,
            checkpoint_epoch   = int(ckpt_meta.get("epoch", -1)),
            checkpoint_val_auroc = float(ckpt_meta.get("val_auroc", 0.0)),
        )

    # ------------------------------------------------------------------
    # Internal — save
    # ------------------------------------------------------------------

    def _save_results(self, results: EvalResults) -> None:
        out_path = self._cfg.results_dir / "thetgat_eval_results.json"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with out_path.open("w") as fh:
            json.dump(results.as_dict(), fh, indent=2)
        self._log.info("eval_results_saved", path=str(out_path))
