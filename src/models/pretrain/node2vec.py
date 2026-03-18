"""
Node2Vec Embedding Builder — Module 09 Baseline.

Constructs a directed IP-level communication graph from raw UNSW-NB15
network flows, then trains a Node2Vec (random-walk + Skip-gram) model
to produce a 64-dimensional embedding per unique IP address.

These embeddings serve two roles:
    1. Feature matrix for the Isolation Forest anomaly baseline
       (see baseline.py) — this is our Module 09 comparison target.
    2. Additional per-node features enriching T-HetGAT (Module 11).

Graph construction
------------------
    nodes : unique IP addresses extracted from srcip / dstip columns
    edges : directed connections  srcip → dstip  (deduplicated by pair)

Attack labels
-------------
    An IP is labelled attack=1 if it appeared as src OR dst in ANY
    flow whose UNSW-NB15 Label column == 1.

Node2Vec hyper-parameters
-------------------------
    Defaults follow the original Grover & Leskovec (2016) paper:
        walk_length   = 80
        walks_per_node = 10
        context_size  = 5
        p = q = 1  (balanced BFS / DFS)
        embedding_dim = 64
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import structlog
import torch
from torch_geometric.nn import Node2Vec as _PyGNode2Vec

from src.models.pretrain.node2vec_config import Node2VecConfig, node2vec_settings

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# UNSW-NB15 raw CSV layout (no header row)
# Col 0 = srcip,  Col 2 = dstip,  Col 48 = Label
# ---------------------------------------------------------------------------
_UNSW_USECOLS: list[int] = [0, 2, 48]
_UNSW_COL_NAMES: list[str] = ["srcip", "dstip", "label"]

# Glob pattern that matches UNSW-NB15_1.csv … UNSW-NB15_9.csv
# but NOT UNSW-NB15_LIST_EVENTS.csv (digit-only suffix)
_UNSW_RAW_GLOB = "UNSW-NB15_[0-9].csv"


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------


@dataclass
class EmbeddingResult:
    """
    Output produced by :meth:`Node2VecEmbedder.fit`.

    Attributes
    ----------
    embeddings:
        Float32 array of shape ``(num_nodes, embedding_dim)``.
        Row i is the embedding for ``ip_list[i]``.
    ip_list:
        Ordered list of IP strings; ``ip_list[i]`` corresponds to row i.
    ip_to_idx:
        Reverse map: IP string → row index in ``embeddings``.
    ip_labels:
        Integer array of shape ``(num_nodes,)``.
        1 if the IP appeared in any attack flow, 0 otherwise.
    num_nodes:
        Total number of unique IP addresses in the graph.
    num_edges:
        Total number of deduplicated directed IP→IP edges.
    """

    embeddings: np.ndarray
    ip_list: list[str]
    ip_to_idx: dict[str, int]
    ip_labels: np.ndarray
    num_nodes: int
    num_edges: int


# ---------------------------------------------------------------------------
# Embedder
# ---------------------------------------------------------------------------


class Node2VecEmbedder:
    """
    Trains Node2Vec on the UNSW-NB15 IP communication graph.

    Usage::

        # Train and save
        embedder = Node2VecEmbedder()
        result   = embedder.fit()                        # uses config paths
        embedder.save(Path("models/baseline/node2vec.pt"))

        # Load later (no re-training)
        result = Node2VecEmbedder.load(Path("models/baseline/node2vec.pt"))
        embeddings = result.embeddings   # (N, 64)
        labels     = result.ip_labels    # (N,)

    Parameters
    ----------
    config:
        Node2Vec hyper-parameters.  Uses ``node2vec_settings`` singleton
        (reads from ``.env`` / env vars) when ``None``.
    """

    def __init__(self, config: Node2VecConfig | None = None) -> None:
        self._cfg: Node2VecConfig = config or node2vec_settings
        self._result: EmbeddingResult | None = None
        self._model: _PyGNode2Vec | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def fit(
        self,
        csv_paths: list[Path] | None = None,
    ) -> EmbeddingResult:
        """
        Load UNSW-NB15 raw CSVs, build an IP graph, train Node2Vec.

        Parameters
        ----------
        csv_paths:
            Explicit list of raw UNSW CSV file paths.  When ``None``,
            auto-discovers all ``UNSW-NB15_*.csv`` files under
            ``config.raw_unsw_dir``.

        Returns
        -------
        EmbeddingResult
            Contains embeddings, ip_list, ip_labels, and graph stats.
        """
        resolved = self._resolve_csv_paths(csv_paths)
        logger.info("node2vec_fit_start", csv_count=len(resolved))

        # ── Step 1: Load flows ─────────────────────────────────────────
        df = self._load_flows(resolved)

        # ── Step 2: Build homogeneous IP graph ─────────────────────────
        edge_index, ip_to_idx, ip_labels = self._build_ip_graph(df)
        ip_list = [""] * len(ip_to_idx)
        for ip, idx in ip_to_idx.items():
            ip_list[idx] = ip
        num_nodes = len(ip_to_idx)
        num_edges = int(edge_index.shape[1])

        logger.info(
            "node2vec_graph_built",
            num_nodes=num_nodes,
            num_edges=num_edges,
            attack_nodes=int(ip_labels.sum()),
        )

        # ── Step 3: Train Node2Vec ──────────────────────────────────────
        device = torch.device(
            "cuda" if torch.cuda.is_available() else "cpu"
        )
        logger.info("node2vec_training_start", device=str(device))
        embeddings = self._train_node2vec(edge_index, num_nodes, device)

        self._result = EmbeddingResult(
            embeddings=embeddings,
            ip_list=ip_list,
            ip_to_idx=ip_to_idx,
            ip_labels=ip_labels,
            num_nodes=num_nodes,
            num_edges=num_edges,
        )
        logger.info(
            "node2vec_fit_complete",
            embedding_shape=list(embeddings.shape),
        )
        return self._result

    def save(self, path: Path) -> None:
        """
        Persist embeddings + metadata to disk (PyTorch format).

        Parameters
        ----------
        path:
            Destination ``.pt`` file.  Parent directories are created
            automatically.
        """
        if self._result is None:
            raise RuntimeError("Call fit() before save().")
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        torch.save(
            {
                "embeddings": self._result.embeddings,
                "ip_list": self._result.ip_list,
                "ip_labels": self._result.ip_labels,
                "num_nodes": self._result.num_nodes,
                "num_edges": self._result.num_edges,
                "config": {
                    "embedding_dim": self._cfg.embedding_dim,
                    "walk_length": self._cfg.walk_length,
                    "walks_per_node": self._cfg.walks_per_node,
                    "context_size": self._cfg.context_size,
                    "p": self._cfg.p,
                    "q": self._cfg.q,
                },
            },
            path,
        )
        logger.info("node2vec_saved", path=str(path))

    @classmethod
    def load(cls, path: Path) -> EmbeddingResult:
        """
        Load a previously saved :class:`EmbeddingResult` from disk.

        Parameters
        ----------
        path:
            Path to a ``.pt`` file written by :meth:`save`.

        Returns
        -------
        EmbeddingResult
            Ready-to-use result (no re-training needed).
        """
        payload = torch.load(Path(path), weights_only=False)
        ip_list: list[str] = payload["ip_list"]
        ip_to_idx = {ip: i for i, ip in enumerate(ip_list)}
        return EmbeddingResult(
            embeddings=payload["embeddings"],
            ip_list=ip_list,
            ip_to_idx=ip_to_idx,
            ip_labels=payload["ip_labels"],
            num_nodes=payload["num_nodes"],
            num_edges=payload["num_edges"],
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _resolve_csv_paths(
        self,
        explicit: list[Path] | None,
    ) -> list[Path]:
        """Return explicit paths if given, else auto-discover from config dir."""
        if explicit:
            return [Path(p) for p in explicit]
        candidates = sorted(
            Path(self._cfg.raw_unsw_dir).glob(_UNSW_RAW_GLOB)
        )
        if not candidates:
            raise FileNotFoundError(
                f"No UNSW raw CSV files found in {self._cfg.raw_unsw_dir!r}."
                f"  Expected pattern: {_UNSW_RAW_GLOB}"
            )
        return candidates

    def _load_flows(self, csv_paths: list[Path]) -> pd.DataFrame:
        """
        Load srcip, dstip, label columns from all raw UNSW CSVs.

        Handles:
        - No header rows (column indices used directly)
        - Latin-1 encoding for special characters
        - Bad / malformed rows (skipped)
        - Non-numeric label values (coerced to 0)
        """
        frames: list[pd.DataFrame] = []
        for p in csv_paths:
            try:
                chunk = pd.read_csv(
                    p,
                    header=None,
                    usecols=_UNSW_USECOLS,
                    dtype=str,
                    on_bad_lines="skip",
                    encoding="latin1",
                )
                # Rename the 3 selected columns regardless of their index
                chunk.columns = _UNSW_COL_NAMES
                frames.append(chunk)
                logger.debug(
                    "node2vec_csv_loaded",
                    path=str(p),
                    rows=len(chunk),
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "node2vec_csv_skip",
                    path=str(p),
                    error=str(exc),
                )

        if not frames:
            raise RuntimeError("No UNSW CSV files could be loaded.")

        df = pd.concat(frames, ignore_index=True)

        # Drop rows where either IP is missing or blank
        df = df.dropna(subset=["srcip", "dstip"])
        df = df[df["srcip"].str.strip() != ""]
        df = df[df["dstip"].str.strip() != ""]

        # Coerce label; treat unparseable values as normal (0)
        df["label"] = (
            pd.to_numeric(df["label"], errors="coerce")
            .fillna(0)
            .astype(np.int32)
        )

        logger.info(
            "node2vec_flows_loaded",
            total_rows=len(df),
            attack_rows=int((df["label"] == 1).sum()),
        )
        return df

    def _build_ip_graph(
        self,
        df: pd.DataFrame,
    ) -> tuple[torch.Tensor, dict[str, int], np.ndarray]:
        """
        Build a directed homogeneous IP graph from flow records.

        Deduplication: multiple flows between the same IP pair produce
        a single directed edge (structural, not weighted).

        Label assignment: an IP is marked attack=1 if it appeared as
        source OR destination in at least one flow with Label == 1.

        Returns
        -------
        edge_index:
            Shape ``(2, E)``, dtype ``torch.long``.
        ip_to_idx:
            ``{ip_string: node_index}`` for all N unique IPs.
        ip_labels:
            Shape ``(N,)``, dtype ``np.int32``.
            1 = attack IP, 0 = normal IP.
        """
        # Assign stable integer IDs to all unique IPs
        all_ips: np.ndarray = pd.unique(
            pd.concat([df["srcip"], df["dstip"]], ignore_index=True)
        )
        ip_to_idx: dict[str, int] = {ip: i for i, ip in enumerate(all_ips)}

        N = len(ip_to_idx)
        ip_labels = np.zeros(N, dtype=np.int32)

        # Mark any IP touched by an attack flow
        attack_mask = df["label"] == 1
        for col in ("srcip", "dstip"):
            attack_ips = df.loc[attack_mask, col].map(ip_to_idx).dropna()
            ip_labels[attack_ips.astype(int).values] = 1

        # Build edge index: map IP strings → integer indices
        src_idx = df["srcip"].map(ip_to_idx).values.astype(np.int64)
        dst_idx = df["dstip"].map(ip_to_idx).values.astype(np.int64)

        # Deduplicate edges: keep only unique (src, dst) pairs
        edge_pairs = np.unique(
            np.stack([src_idx, dst_idx], axis=0), axis=1
        )
        edge_index = torch.from_numpy(edge_pairs).long()

        return edge_index, ip_to_idx, ip_labels

    def _train_node2vec(
        self,
        edge_index: torch.Tensor,
        num_nodes: int,
        device: torch.device,
    ) -> np.ndarray:
        """
        Train PyG Node2Vec and return the embedding matrix.

        Uses :class:`torch_geometric.nn.Node2Vec` with SparseAdam
        (efficient for large sparse embedding tables).

        Returns
        -------
        np.ndarray
            Shape ``(num_nodes, embedding_dim)``, dtype ``float32``.
        """
        cfg = self._cfg

        model = _PyGNode2Vec(
            edge_index=edge_index.to(device),
            embedding_dim=cfg.embedding_dim,
            walk_length=cfg.walk_length,
            context_size=cfg.context_size,
            walks_per_node=cfg.walks_per_node,
            num_negative_samples=cfg.num_negative_samples,
            p=cfg.p,
            q=cfg.q,
            sparse=True,
            num_nodes=num_nodes,
        ).to(device)

        loader = model.loader(
            batch_size=cfg.loader_batch_size,
            shuffle=True,
            num_workers=0,
        )
        optimizer = torch.optim.SparseAdam(
            list(model.parameters()),
            lr=cfg.learning_rate,
        )

        model.train()
        for epoch in range(1, cfg.num_epochs + 1):
            total_loss = 0.0
            num_batches = 0
            for pos_rw, neg_rw in loader:
                optimizer.zero_grad()
                loss = model.loss(pos_rw.to(device), neg_rw.to(device))
                loss.backward()
                optimizer.step()
                total_loss += loss.item()
                num_batches += 1

            avg_loss = total_loss / max(num_batches, 1)
            if epoch % 10 == 0 or epoch == 1 or epoch == cfg.num_epochs:
                logger.info(
                    "node2vec_epoch",
                    epoch=epoch,
                    total=cfg.num_epochs,
                    loss=round(avg_loss, 4),
                )

        self._model = model

        # Extract all embeddings at once (no gradient needed)
        model.eval()
        with torch.no_grad():
            all_idx = torch.arange(num_nodes, device=device)
            embeddings: np.ndarray = model(all_idx).cpu().numpy()

        return embeddings
