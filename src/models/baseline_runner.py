"""
Module 09 — Node2Vec Baseline Runner.

End-to-end pipeline that trains the Node2Vec IP embedding model,
builds per-IP behavioral profiles, and evaluates the Isolation Forest
and One-Class SVM anomaly baselines against UNSW-NB15 ground truth.

Usage
-----
    python -m src.models.baseline_runner

Output
------
    models/baseline/node2vec.pt          — Node2Vec embeddings + IP list
    models/baseline/iso_forest.joblib    — fitted Isolation Forest
    models/baseline/oc_svm.joblib        — fitted One-Class SVM
    models/baseline/scaler.joblib        — fitted StandardScaler
    models/baseline/baseline_results.json — AUROC / F1 / PR metrics

The JSON scores are the benchmark that T-HetGAT (Module 11) must beat.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import structlog

from src.models.pretrain.baseline import AnomalyBaseline
from src.models.pretrain.node2vec import Node2VecEmbedder
from src.models.pretrain.node2vec_config import node2vec_settings
from src.models.pretrain.profiling import BehaviorProfiler

logger = structlog.get_logger(__name__)


def run() -> None:
    """Execute the full Module 09 pipeline."""
    cfg = node2vec_settings
    output_dir = Path(cfg.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    t_total = time.perf_counter()

    # ------------------------------------------------------------------
    # Step 1: Node2Vec — build IP graph + train embeddings
    # ------------------------------------------------------------------
    logger.info("pipeline_step", step=1, name="Node2Vec training")
    t0 = time.perf_counter()

    n2v_path = output_dir / "node2vec.pt"
    if n2v_path.exists():
        logger.info("node2vec_cache_hit", path=str(n2v_path))
        embedding_result = Node2VecEmbedder.load(n2v_path)
    else:
        embedder = Node2VecEmbedder(cfg)
        embedding_result = embedder.fit()
        embedder.save(n2v_path)

    logger.info(
        "pipeline_step_done",
        step=1,
        elapsed_s=round(time.perf_counter() - t0, 1),
        num_ips=embedding_result.num_nodes,
        num_edges=embedding_result.num_edges,
    )

    # ------------------------------------------------------------------
    # Step 2: Behavior Profiling — flow stats + graph metrics + embeddings
    # ------------------------------------------------------------------
    logger.info("pipeline_step", step=2, name="Behavior profiling")
    t0 = time.perf_counter()

    profiler = BehaviorProfiler(cfg)
    profile = profiler.build_profiles(embedding_result)

    logger.info(
        "pipeline_step_done",
        step=2,
        elapsed_s=round(time.perf_counter() - t0, 1),
        feature_shape=list(profile.features_combined.shape),
        attack_ratio=round(float(profile.ip_labels.mean()), 4),
    )

    # ------------------------------------------------------------------
    # Step 3: Anomaly Baseline — Isolation Forest + One-Class SVM
    # ------------------------------------------------------------------
    logger.info("pipeline_step", step=3, name="Anomaly baseline evaluation")
    t0 = time.perf_counter()

    baseline = AnomalyBaseline(cfg)
    results = baseline.evaluate(profile)
    results_path = baseline.save_results(results, output_dir)

    logger.info(
        "pipeline_step_done",
        step=3,
        elapsed_s=round(time.perf_counter() - t0, 1),
    )

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    elapsed_total = round(time.perf_counter() - t_total, 1)
    iso = results.isolation_forest
    svm = results.one_class_svm

    print()
    print("=" * 58)
    print("  Module 09 — Node2Vec Baseline  COMPLETE")
    print("=" * 58)
    print(f"  IPs evaluated   : {results.num_ips:,}")
    print(f"  Attack IPs      : {results.num_attack_ips:,}  "
          f"({results.attack_ratio:.1%})")
    print(f"  Feature dim     : {results.feature_config['total_features']}")
    print()
    print("  ┌─────────────────────┬────────┬────────┬────────┐")
    print("  │ Model               │  AUROC │   F1   │  Prec  │")
    print("  ├─────────────────────┼────────┼────────┼────────┤")
    print(f"  │ Isolation Forest    │ {iso.auroc:.4f} │ {iso.f1:.4f} │ {iso.precision:.4f} │")
    print(f"  │ One-Class SVM       │ {svm.auroc:.4f} │ {svm.f1:.4f} │ {svm.precision:.4f} │")
    print("  └─────────────────────┴────────┴────────┴────────┘")
    print()
    print(f"  Results saved → {results_path}")
    print(f"  Total time     : {elapsed_total}s")
    print("=" * 58)
    print()
    print("  → These scores are the benchmark for T-HetGAT (Module 11).")
    print()


if __name__ == "__main__":
    run()
    sys.exit(0)
