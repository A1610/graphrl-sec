"""
Node2Vec Embedding Builder — Module 09 Baseline.

Constructs a directed IP-level communication graph from raw UNSW-NB15
AND CICIDS2017 network flows, then trains a Node2Vec (random-walk +
Skip-gram) model to produce a 64-dimensional embedding per unique IP.

Why both datasets?
    UNSW-NB15 alone has only ~50 unique IPs (controlled lab testbed) —
    too few for Node2Vec to learn meaningful structural patterns.
    CICIDS2017 adds ~19 K real-world IPs, giving the model a rich graph
    to learn from.  Combined: ~19 K nodes, ~300 K deduplicated edges.

These embeddings serve two roles:
    1. Feature matrix for the Isolation Forest anomaly baseline
       (see baseline.py) — this is our Module 09 comparison target.
    2. Additional per-node features enriching T-HetGAT (Module 11).

Graph construction
------------------
    nodes : unique IP addresses from UNSW srcip/dstip + CICIDS Source/Dest
    edges : directed connections  src → dst  (deduplicated by pair)

Attack labels
-------------
    UNSW-NB15 : Label column == 1  →  attack IP
    CICIDS2017: Label column != 'BENIGN'  →  attack IP

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
_UNSW_RAW_GLOB = "UNSW-NB15_[0-9].csv"

# ---------------------------------------------------------------------------
# CICIDS2017 CSV layout (has header row, column names have leading spaces)
# ---------------------------------------------------------------------------
_CICIDS_SRC_COL  = " Source IP"
_CICIDS_DST_COL  = " Destination IP"
_CICIDS_LBL_COL  = " Label"
_CICIDS_RAW_GLOB = "*.csv"


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
        Load UNSW-NB15 + CICIDS2017 raw CSVs, build an IP graph, train Node2Vec.

        Parameters
        ----------
        csv_paths:
            Explicit list of UNSW raw CSV file paths.  When ``None``,
            auto-discovers ``UNSW-NB15_[0-9].csv`` under ``config.raw_unsw_dir``
            AND all ``*.csv`` under ``config.raw_cicids_dir``.

        Returns
        -------
        EmbeddingResult
            Contains embeddings, ip_list, ip_labels, and graph stats.
        """
        unsw_paths   = self._resolve_unsw_paths(csv_paths)
        cicids_paths = self._resolve_cicids_paths()
        logger.info(
            "node2vec_fit_start",
            unsw_csv_count=len(unsw_paths),
            cicids_csv_count=len(cicids_paths),
        )

        # ── Step 1: Load flows from both datasets ──────────────────────
        df_unsw   = self._load_unsw_flows(unsw_paths)
        df_cicids = self._load_cicids_flows(cicids_paths)
        df = pd.concat([df_unsw, df_cicids], ignore_index=True)
        logger.info(
            "node2vec_flows_merged",
            unsw_rows=len(df_unsw),
            cicids_rows=len(df_cicids),
            total_rows=len(df),
            attack_rows=int((df["label"] == 1).sum()),
        )

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

    def _resolve_unsw_paths(
        self,
        explicit: list[Path] | None,
    ) -> list[Path]:
        """Return explicit UNSW paths if given, else auto-discover."""
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

    def _resolve_cicids_paths(self) -> list[Path]:
        """Auto-discover all CICIDS2017 CSV files from config dir."""
        candidates = sorted(
            Path(self._cfg.raw_cicids_dir).glob(_CICIDS_RAW_GLOB)
        )
        if not candidates:
            logger.warning(
                "node2vec_cicids_not_found",
                dir=str(self._cfg.raw_cicids_dir),
            )
        return candidates

    def _load_unsw_flows(self, csv_paths: list[Path]) -> pd.DataFrame:
        """
        Load srcip, dstip, label from raw UNSW-NB15 CSVs (no header row).
        Returns a DataFrame with columns: srcip, dstip, label (0/1 int).
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
                chunk.columns = _UNSW_COL_NAMES
                frames.append(chunk)
                logger.debug("node2vec_unsw_loaded", path=str(p), rows=len(chunk))
            except Exception as exc:  # noqa: BLE001
                logger.warning("node2vec_unsw_skip", path=str(p), error=str(exc))

        if not frames:
            raise RuntimeError("No UNSW CSV files could be loaded.")

        df = self._clean_flow_df(frames)
        # UNSW label is numeric 0/1
        df["label"] = (
            pd.to_numeric(df["label"], errors="coerce")
            .fillna(0)
            .astype(np.int32)
        )
        return df

    def _load_cicids_flows(self, csv_paths: list[Path]) -> pd.DataFrame:
        """
        Load srcip, dstip, label from CICIDS2017 CSVs (has header row).
        Label is a string ('BENIGN' or attack category name).
        Returns a DataFrame with columns: srcip, dstip, label (0/1 int).
        """
        if not csv_paths:
            return pd.DataFrame(columns=["srcip", "dstip", "label"])

        frames: list[pd.DataFrame] = []
        for p in csv_paths:
            try:
                chunk = pd.read_csv(
                    p,
                    usecols=[_CICIDS_SRC_COL, _CICIDS_DST_COL, _CICIDS_LBL_COL],
                    dtype=str,
                    on_bad_lines="skip",
                    encoding="latin1",
                )
                chunk = chunk.rename(columns={
                    _CICIDS_SRC_COL: "srcip",
                    _CICIDS_DST_COL: "dstip",
                    _CICIDS_LBL_COL: "label",
                })
                frames.append(chunk)
                logger.debug("node2vec_cicids_loaded", path=str(p), rows=len(chunk))
            except Exception as exc:  # noqa: BLE001
                logger.warning("node2vec_cicids_skip", path=str(p), error=str(exc))

        if not frames:
            return pd.DataFrame(columns=["srcip", "dstip", "label"])

        df = self._clean_flow_df(frames)
        # CICIDS label: 'BENIGN' → 0, everything else → 1
        df["label"] = (
            df["label"].str.strip().ne("BENIGN").astype(np.int32)
        )
        return df

    def _clean_flow_df(self, frames: list[pd.DataFrame]) -> pd.DataFrame:
        """Concatenate frames, drop blanks, strip IP strings."""
        df = pd.concat(frames, ignore_index=True)
        df = df.dropna(subset=["srcip", "dstip"])
        df["srcip"] = df["srcip"].str.strip()
        df["dstip"] = df["dstip"].str.strip()
        df = df[(df["srcip"] != "") & (df["dstip"] != "")]
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
