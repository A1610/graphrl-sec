"""
Embedding quality evaluator for the pre-trained HeteroGraphEncoder.

Evaluates how well the learned node embeddings capture security-relevant
structure without any fine-tuning (zero-shot anomaly detection).

Metrics computed:
    1. Anomaly Detection AUROC
       Linear probe: train a LogisticRegression on 80% of labelled nodes,
       evaluate ROC-AUC on the remaining 20%.

    2. Silhouette Score
       Measures cluster separation between attack and normal embeddings.
       Range [-1, 1]; higher is better.  > 0 means attack nodes are
       separable from normal nodes in embedding space.

    3. Embedding statistics
       Mean, std, and per-type norms — useful for detecting collapse
       (all embeddings identical → std ≈ 0).

All evaluation is CPU-side (sklearn) so no GPU memory is consumed.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import numpy.typing as npt
import structlog
import torch
from torch_geometric.data import HeteroData

from src.models.pretrain.checkpoint import CheckpointManager
from src.models.pretrain.config import PretrainConfig, pretrain_settings
from src.models.pretrain.encoder import HeteroGraphEncoder

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EmbeddingStats:
    """Per-node-type embedding statistics."""

    node_type:  str
    num_nodes:  int
    mean_norm:  float    # mean L2 norm — near 0 = collapsed embeddings
    std:        float    # std across all embedding dimensions


@dataclass
class EvalResult:
    """Full evaluation result from EmbeddingEvaluator.evaluate()."""

    auroc:            float              # ROC-AUC, linear probe (0.5 = random)
    silhouette:       float              # Silhouette score (-1 to 1)
    num_nodes_total:  int
    num_attack_nodes: int
    num_normal_nodes: int
    embedding_stats:  list[EmbeddingStats] = field(default_factory=list)

    @property
    def attack_ratio(self) -> float:
        if self.num_nodes_total == 0:
            return 0.0
        return self.num_attack_nodes / self.num_nodes_total


# ---------------------------------------------------------------------------
# Evaluator
# ---------------------------------------------------------------------------


class EmbeddingEvaluator:
    """
    Evaluates the quality of pre-trained node embeddings.

    Usage::

        evaluator = EmbeddingEvaluator(config)
        result    = evaluator.evaluate(
            snapshots   = snapshots,          # list[HeteroData]
            attack_mask = attack_mask,        # bool array, True = attack node
        )
        print(f"AUROC: {result.auroc:.3f}")
    """

    def __init__(self, config: PretrainConfig | None = None) -> None:
        self._cfg = config or pretrain_settings
        self._log = logger.bind(component="embedding_evaluator")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def evaluate(
        self,
        snapshots:    list[HeteroData],
        attack_mask:  npt.NDArray[np.bool_],
        model:        HeteroGraphEncoder | None = None,
    ) -> EvalResult:
        """
        Generate embeddings and compute evaluation metrics.

        Parameters
        ----------
        snapshots :
            List of HeteroData graph snapshots.
        attack_mask :
            Boolean array of length N (total nodes across all snapshots).
            True = attack node, False = normal node.
        model :
            Pre-trained encoder.  If None, loads best checkpoint from disk.

        Returns
        -------
        EvalResult with AUROC, silhouette score, and embedding statistics.
        """
        if model is None:
            model = self._load_best_model(snapshots[0])

        device = torch.device("cpu")   # evaluation always on CPU
        model  = model.to(device)
        model.eval()

        # --- Generate embeddings ---
        all_embeddings = self._generate_embeddings(model, snapshots, device)

        if len(all_embeddings) == 0:
            self._log.warning("no_embeddings_generated")
            return EvalResult(
                auroc=0.5, silhouette=0.0,
                num_nodes_total=0, num_attack_nodes=0, num_normal_nodes=0,
            )

        embeddings_np = all_embeddings.numpy()  # (N, D)

        # Align mask length with actual node count
        n = min(len(embeddings_np), len(attack_mask))
        embeddings_np = embeddings_np[:n]
        labels        = attack_mask[:n].astype(np.int32)

        # --- Metrics ---
        auroc       = self._compute_auroc(embeddings_np, labels)
        silhouette  = self._compute_silhouette(embeddings_np, labels)
        stats       = self._compute_stats(snapshots, model, device)

        result = EvalResult(
            auroc=auroc,
            silhouette=silhouette,
            num_nodes_total=n,
            num_attack_nodes=int(labels.sum()),
            num_normal_nodes=int((1 - labels).sum()),
            embedding_stats=stats,
        )

        self._log.info(
            "eval_complete",
            auroc=round(auroc, 4),
            silhouette=round(silhouette, 4),
            num_nodes=n,
            attack_ratio=round(result.attack_ratio, 3),
        )
        return result

    # ------------------------------------------------------------------
    # Internal — embedding generation
    # ------------------------------------------------------------------

    @torch.no_grad()
    def _generate_embeddings(
        self,
        model:     HeteroGraphEncoder,
        snapshots: list[HeteroData],
        device:    torch.device,
    ) -> torch.Tensor:
        """
        Forward all snapshots through the encoder and collect node embeddings.

        Concatenates embeddings across all node types and all snapshots into
        a single (N_total, hidden_dim) tensor.
        """
        all_vecs: list[torch.Tensor] = []

        for data in snapshots:
            data = data.to(device)
            try:
                h_dict = model(data.x_dict, data.edge_index_dict)
            except Exception as exc:  # noqa: BLE001
                self._log.warning("embedding_forward_failed", error=str(exc))
                continue

            for ntype in sorted(h_dict):   # deterministic order
                all_vecs.append(h_dict[ntype].cpu())

        if not all_vecs:
            return torch.empty(0)

        return torch.cat(all_vecs, dim=0)   # (N_total, hidden_dim)

    # ------------------------------------------------------------------
    # Internal — metrics
    # ------------------------------------------------------------------

    def _compute_auroc(
        self,
        embeddings: npt.NDArray[np.float32],
        labels:     npt.NDArray[np.int32],
    ) -> float:
        """
        Linear-probe AUROC: LogisticRegression trained on 80% of data,
        evaluated on remaining 20%.
        """
        try:
            from sklearn.linear_model import LogisticRegression
            from sklearn.metrics import roc_auc_score
            from sklearn.model_selection import train_test_split
            from sklearn.preprocessing import StandardScaler
        except ImportError:
            self._log.warning("sklearn_not_available_auroc_skipped")
            return 0.5

        unique_labels = np.unique(labels)
        if len(unique_labels) < 2:
            self._log.warning("auroc_skipped_single_class",
                              unique_labels=unique_labels.tolist())
            return 0.5

        scaler       = StandardScaler()
        x_all        = scaler.fit_transform(embeddings)
        x_tr, x_te, y_tr, y_te = train_test_split(
            x_all, labels, test_size=0.2, random_state=42, stratify=labels
        )

        clf = LogisticRegression(max_iter=1000, random_state=42, n_jobs=-1)
        clf.fit(x_tr, y_tr)
        proba = clf.predict_proba(x_te)[:, 1]
        return float(roc_auc_score(y_te, proba))

    def _compute_silhouette(
        self,
        embeddings: npt.NDArray[np.float32],
        labels:     npt.NDArray[np.int32],
    ) -> float:
        """Silhouette score — measures cluster separation (attack vs normal)."""
        try:
            from sklearn.metrics import silhouette_score
        except ImportError:
            self._log.warning("sklearn_not_available_silhouette_skipped")
            return 0.0

        unique_labels = np.unique(labels)
        if len(unique_labels) < 2:
            return 0.0

        # Subsample for speed (silhouette is O(N^2))
        max_samples = 5_000
        if len(embeddings) > max_samples:
            rng  = np.random.default_rng(42)
            idx  = rng.choice(len(embeddings), max_samples, replace=False)
            embeddings = embeddings[idx]
            labels     = labels[idx]

        try:
            return float(silhouette_score(embeddings, labels, metric="cosine"))
        except Exception as exc:  # noqa: BLE001
            self._log.warning("silhouette_failed", error=str(exc))
            return 0.0

    def _compute_stats(
        self,
        snapshots: list[HeteroData],
        model:     HeteroGraphEncoder,
        device:    torch.device,
    ) -> list[EmbeddingStats]:
        """Per-node-type embedding norm statistics."""
        type_vecs: dict[str, list[torch.Tensor]] = {}

        with torch.no_grad():
            for data in snapshots[:10]:   # sample first 10 for speed
                data = data.to(device)
                try:
                    h_dict = model(data.x_dict, data.edge_index_dict)
                except Exception:  # noqa: BLE001
                    continue
                for ntype, h in h_dict.items():
                    type_vecs.setdefault(ntype, []).append(h.cpu())

        stats: list[EmbeddingStats] = []
        for ntype, vecs in sorted(type_vecs.items()):
            mat       = torch.cat(vecs, dim=0)           # (N, D)
            norms     = mat.norm(dim=-1)                 # (N,)
            stats.append(EmbeddingStats(
                node_type  = ntype,
                num_nodes  = mat.shape[0],
                mean_norm  = float(norms.mean()),
                std        = float(mat.std()),
            ))

        return stats

    # ------------------------------------------------------------------
    # Internal — model loading
    # ------------------------------------------------------------------

    def _load_best_model(self, sample_graph: HeteroData) -> HeteroGraphEncoder:
        """Load the best checkpoint from disk."""
        ckpt_mgr = CheckpointManager(self._cfg)
        if not ckpt_mgr.best_exists():
            raise FileNotFoundError(
                f"No best checkpoint found in {self._cfg.checkpoint_dir}. "
                "Run pre-training first:\n"
                "  python -m src.models.pretrain.trainer"
            )
        model = HeteroGraphEncoder.from_heterodata(sample_graph, self._cfg)
        ckpt_mgr.load_best(model, device="cpu")
        return model
