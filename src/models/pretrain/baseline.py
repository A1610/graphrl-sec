"""
Anomaly Detection Baseline — Module 09.

Trains two classical anomaly detectors on the per-IP behavioral features
produced by BehaviorProfiler, then evaluates them against ground-truth
UNSW-NB15 attack labels.

Models
------
    Isolation Forest  — tree-based, handles high-dimensional data well
    One-Class SVM     — kernel-based, tighter decision boundary

Evaluation
----------
    AUROC             — area under the ROC curve (threshold-independent)
    F1 (best)         — F1 at the threshold that maximises it
    Precision / Recall at that threshold
    Average Precision — area under the Precision-Recall curve

Results are saved to ``models/baseline/baseline_results.json``.
These scores are the benchmark that T-HetGAT (Module 11) must beat.

Both fitted models are serialised to ``models/baseline/`` so they can
be reused to score new IPs without re-training.
"""

from __future__ import annotations

import json
import warnings
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import structlog
from sklearn.ensemble import IsolationForest
from sklearn.metrics import (
    average_precision_score,
    precision_recall_curve,
    roc_auc_score,
)
from sklearn.preprocessing import StandardScaler
from sklearn.svm import OneClassSVM

from src.models.pretrain.profiling import ProfileResult
from src.models.pretrain.node2vec_config import Node2VecConfig, node2vec_settings

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------


@dataclass
class ModelMetrics:
    """Evaluation metrics for one anomaly detector."""

    auroc: float
    f1: float
    precision: float
    recall: float
    avg_precision: float
    best_threshold: float


@dataclass
class BaselineResults:
    """
    Complete baseline evaluation results.

    Attributes
    ----------
    timestamp:
        ISO-8601 UTC timestamp of when the evaluation was run.
    num_ips:
        Total number of unique IPs evaluated.
    num_attack_ips:
        IPs labelled as attack (label == 1).
    attack_ratio:
        Fraction of IPs that are attacks.
    isolation_forest:
        Metrics for the Isolation Forest model.
    one_class_svm:
        Metrics for the One-Class SVM model.
    feature_config:
        Dimension breakdown of the feature matrix used.
    """

    timestamp: str
    num_ips: int
    num_attack_ips: int
    attack_ratio: float
    isolation_forest: ModelMetrics
    one_class_svm: ModelMetrics
    feature_config: dict[str, int]


# ---------------------------------------------------------------------------
# Baseline evaluator
# ---------------------------------------------------------------------------


class AnomalyBaseline:
    """
    Trains Isolation Forest and One-Class SVM on IP behavioral features
    and evaluates them against ground-truth attack labels.

    Usage::

        baseline = AnomalyBaseline()
        results  = baseline.evaluate(profile_result)
        baseline.save_results(results, Path("models/baseline"))

    Parameters
    ----------
    config:
        Node2Vec config (reused for output_dir path).
        Uses ``node2vec_settings`` singleton when ``None``.
    contamination:
        Expected fraction of anomalies in the data for Isolation Forest.
        ``"auto"`` lets sklearn estimate it.
    """

    def __init__(
        self,
        config: Node2VecConfig | None = None,
        contamination: float | str = "auto",
    ) -> None:
        self._cfg = config or node2vec_settings
        self._contamination = contamination
        self._scaler: StandardScaler | None = None
        self._iso_forest: IsolationForest | None = None
        self._oc_svm: OneClassSVM | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def evaluate(self, profile: ProfileResult) -> BaselineResults:
        """
        Fit both models and compute evaluation metrics.

        The anomaly detectors are trained on the full feature matrix
        (unsupervised — no labels used during training).  Labels are
        only used for computing AUROC / F1 afterwards.

        Parameters
        ----------
        profile:
            Output of :meth:`~src.models.pretrain.profiling.BehaviorProfiler.build_profiles`.

        Returns
        -------
        BaselineResults
        """
        X = profile.features_combined                  # (N, 76)
        y = profile.ip_labels.astype(np.int32)         # (N,) — 0/1
        N = X.shape[0]
        n_attack = int(y.sum())

        logger.info(
            "baseline_evaluate_start",
            num_ips=N,
            num_attack=n_attack,
            attack_ratio=round(n_attack / max(N, 1), 4),
            feature_dim=X.shape[1],
        )

        # Guard: AUROC requires at least one sample from each class
        if n_attack == 0 or n_attack == N:
            raise ValueError(
                f"Need both normal and attack IPs to compute AUROC.  "
                f"Got {n_attack} attack IPs out of {N} total."
            )

        # ── Step 1: Preprocess ─────────────────────────────────────────
        X_scaled = self._preprocess(X)

        # ── Step 2: Isolation Forest ───────────────────────────────────
        logger.info("baseline_fitting_isolation_forest")
        iso_metrics = self._fit_and_evaluate_iso_forest(X_scaled, y)
        logger.info(
            "baseline_iso_forest_done",
            auroc=iso_metrics.auroc,
            f1=iso_metrics.f1,
            precision=iso_metrics.precision,
            recall=iso_metrics.recall,
        )

        # ── Step 3: One-Class SVM ──────────────────────────────────────
        logger.info("baseline_fitting_one_class_svm")
        svm_metrics = self._fit_and_evaluate_oc_svm(X_scaled, y)
        logger.info(
            "baseline_oc_svm_done",
            auroc=svm_metrics.auroc,
            f1=svm_metrics.f1,
            precision=svm_metrics.precision,
            recall=svm_metrics.recall,
        )

        feature_config = {
            "structural_features": profile.features.shape[1],
            "embedding_dim": profile.embedding_dim,
            "total_features": X.shape[1],
        }

        results = BaselineResults(
            timestamp=datetime.now(timezone.utc).isoformat(),
            num_ips=N,
            num_attack_ips=n_attack,
            attack_ratio=round(n_attack / N, 6),
            isolation_forest=iso_metrics,
            one_class_svm=svm_metrics,
            feature_config=feature_config,
        )

        logger.info(
            "baseline_evaluate_complete",
            iso_auroc=iso_metrics.auroc,
            svm_auroc=svm_metrics.auroc,
        )
        return results

    def save_results(
        self,
        results: BaselineResults,
        output_dir: Path | None = None,
    ) -> Path:
        """
        Serialise evaluation results + fitted models to disk.

        Writes:
            ``<output_dir>/baseline_results.json`` — metrics (human-readable)
            ``<output_dir>/iso_forest.joblib``     — fitted Isolation Forest
            ``<output_dir>/oc_svm.joblib``         — fitted One-Class SVM
            ``<output_dir>/scaler.joblib``         — fitted StandardScaler

        Returns
        -------
        Path
            Path to the written ``baseline_results.json``.
        """
        if self._iso_forest is None or self._oc_svm is None:
            raise RuntimeError("Call evaluate() before save_results().")

        out = Path(output_dir) if output_dir else Path(self._cfg.output_dir)
        out.mkdir(parents=True, exist_ok=True)

        # JSON metrics
        results_path = out / "baseline_results.json"
        payload = asdict(results)
        results_path.write_text(
            json.dumps(payload, indent=2),
            encoding="utf-8",
        )
        logger.info("baseline_results_saved", path=str(results_path))

        # Fitted models
        joblib.dump(self._iso_forest, out / "iso_forest.joblib")
        joblib.dump(self._oc_svm,    out / "oc_svm.joblib")
        joblib.dump(self._scaler,    out / "scaler.joblib")
        logger.info("baseline_models_saved", dir=str(out))

        return results_path

    # ------------------------------------------------------------------
    # Internal: preprocessing
    # ------------------------------------------------------------------

    def _preprocess(self, X: np.ndarray) -> np.ndarray:
        """
        Replace NaN/Inf, then StandardScale to zero mean and unit variance.

        StandardScaler is especially important for One-Class SVM (RBF kernel
        is sensitive to feature scale).  Isolation Forest is scale-invariant
        by design, but scaling still helps in combined structural + embedding
        feature spaces.
        """
        X_clean = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)
        self._scaler = StandardScaler()
        return self._scaler.fit_transform(X_clean)

    # ------------------------------------------------------------------
    # Internal: model fitting
    # ------------------------------------------------------------------

    def _fit_and_evaluate_iso_forest(
        self,
        X: np.ndarray,
        y: np.ndarray,
    ) -> ModelMetrics:
        """Fit Isolation Forest and compute anomaly score metrics."""
        self._iso_forest = IsolationForest(
            n_estimators=200,
            contamination=self._contamination,
            max_samples="auto",
            random_state=42,
            n_jobs=-1,
        )
        self._iso_forest.fit(X)

        # decision_function returns "normality score" — negate for anomaly score
        anomaly_scores = -self._iso_forest.decision_function(X)
        return _compute_metrics(y, anomaly_scores)

    def _fit_and_evaluate_oc_svm(
        self,
        X: np.ndarray,
        y: np.ndarray,
    ) -> ModelMetrics:
        """
        Fit One-Class SVM and compute anomaly score metrics.

        Trained on a random 20 K subsample to keep runtime manageable
        (full fit on 45 K nodes with RBF kernel is O(N²)).  Scoring is
        always done on the full dataset.
        """
        max_fit_samples = 20_000
        n = X.shape[0]
        if n > max_fit_samples:
            rng = np.random.default_rng(seed=42)
            idx = rng.choice(n, size=max_fit_samples, replace=False)
            X_fit = X[idx]
        else:
            X_fit = X

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")  # suppress convergence warnings
            self._oc_svm = OneClassSVM(kernel="rbf", nu=0.1, gamma="scale")
            self._oc_svm.fit(X_fit)

        anomaly_scores = -self._oc_svm.decision_function(X)
        return _compute_metrics(y, anomaly_scores)


# ---------------------------------------------------------------------------
# Helper: metrics from anomaly scores
# ---------------------------------------------------------------------------


def _compute_metrics(y_true: np.ndarray, scores: np.ndarray) -> ModelMetrics:
    """
    Derive AUROC, best-threshold F1, Precision, Recall, Average Precision.

    Parameters
    ----------
    y_true:
        Binary labels (0 = normal, 1 = attack).
    scores:
        Continuous anomaly scores (higher = more anomalous).

    Returns
    -------
    ModelMetrics
    """
    auroc = float(roc_auc_score(y_true, scores))
    avg_precision = float(average_precision_score(y_true, scores))

    # Find the threshold that maximises F1
    precisions, recalls, thresholds = precision_recall_curve(y_true, scores)

    # precision_recall_curve returns one more value than thresholds
    # — last element corresponds to threshold = ∞ (precision=1, recall=0)
    f1_scores = np.where(
        (precisions[:-1] + recalls[:-1]) > 0,
        2 * precisions[:-1] * recalls[:-1] / (precisions[:-1] + recalls[:-1]),
        0.0,
    )

    best_idx = int(np.argmax(f1_scores))
    best_f1        = float(f1_scores[best_idx])
    best_precision = float(precisions[best_idx])
    best_recall    = float(recalls[best_idx])
    best_threshold = float(thresholds[best_idx])

    return ModelMetrics(
        auroc=round(auroc, 4),
        f1=round(best_f1, 4),
        precision=round(best_precision, 4),
        recall=round(best_recall, 4),
        avg_precision=round(avg_precision, 4),
        best_threshold=round(best_threshold, 6),
    )
