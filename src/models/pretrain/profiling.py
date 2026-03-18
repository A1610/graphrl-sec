"""
Host Behavior Profiler — Module 09 Baseline.

Computes per-IP behavioral fingerprints by combining:

    1. Flow-level statistics  (from raw UNSW-NB15 CSV)
       9 features per IP:
           out_degree      — unique destination IPs
           in_degree       — unique source IPs
           num_out_flows   — flows where this IP is source
           num_in_flows    — flows where this IP is destination
           bytes_sent_mean — mean sbytes per outgoing flow
           bytes_recv_mean — mean dbytes per incoming flow
           unique_dst_ports — unique destination ports used
           unique_src_ports — unique source ports seen
           unique_protocols — unique transport protocols

    2. Graph structural statistics  (via NetworkX)
       3 features per IP:
           pagerank          — importance by link structure
           clustering_coeff  — local graph density
           degree_centrality — normalised total degree

    3. Node2Vec embedding  (embedding_dim = 64 by default)

Final feature matrix:  (N_ips,  12 + embedding_dim)  = (N_ips, 76)

This combined representation is the input to the Isolation Forest
anomaly baseline in baseline.py.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import networkx as nx
import numpy as np
import pandas as pd
import structlog
import torch

from src.models.pretrain.node2vec import EmbeddingResult
from src.models.pretrain.node2vec_config import Node2VecConfig, node2vec_settings

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# UNSW-NB15 raw CSV column layout (no header row)
# ---------------------------------------------------------------------------
_PROFILE_COLS: list[int] = [0, 1, 2, 3, 4, 7, 8, 48]
_PROFILE_NAMES: list[str] = [
    "srcip", "sport", "dstip", "dsport",
    "proto", "sbytes", "dbytes", "label",
]
_UNSW_RAW_GLOB = "UNSW-NB15_[0-9].csv"

# Feature names (matches column order in ProfileResult.features)
FLOW_FEATURE_NAMES: list[str] = [
    "out_degree",
    "in_degree",
    "num_out_flows",
    "num_in_flows",
    "bytes_sent_mean",
    "bytes_recv_mean",
    "unique_dst_ports",
    "unique_src_ports",
    "unique_protocols",
]
GRAPH_FEATURE_NAMES: list[str] = [
    "pagerank",
    "clustering_coeff",
    "degree_centrality",
]
STRUCTURAL_FEATURE_NAMES: list[str] = FLOW_FEATURE_NAMES + GRAPH_FEATURE_NAMES


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------


@dataclass
class ProfileResult:
    """
    Output produced by :meth:`BehaviorProfiler.build_profiles`.

    Attributes
    ----------
    features:
        Structural-only feature matrix, shape ``(N, 12)``.
        Column order matches :data:`STRUCTURAL_FEATURE_NAMES`.
    features_combined:
        Full feature matrix, shape ``(N, 12 + embedding_dim)``.
        = structural features  ‖  Node2Vec embeddings
    feature_names:
        Human-readable names for all columns of ``features_combined``.
    ip_list:
        Ordered IP strings; row i corresponds to ``ip_list[i]``.
    ip_labels:
        Shape ``(N,)``, 1 = attack IP, 0 = normal IP.
    embedding_dim:
        Dimensionality of the Node2Vec embedding block.
    """

    features: np.ndarray
    features_combined: np.ndarray
    feature_names: list[str]
    ip_list: list[str]
    ip_labels: np.ndarray
    embedding_dim: int = field(default=64)


# ---------------------------------------------------------------------------
# Profiler
# ---------------------------------------------------------------------------


class BehaviorProfiler:
    """
    Builds per-IP behavioral feature vectors.

    Requires a completed :class:`~src.models.pretrain.node2vec.EmbeddingResult`
    so that Node2Vec embeddings can be appended to the structural features.

    Usage::

        from src.models.pretrain.node2vec import Node2VecEmbedder
        from src.models.pretrain.profiling import BehaviorProfiler

        result   = Node2VecEmbedder().fit()
        profiler = BehaviorProfiler()
        profile  = profiler.build_profiles(result)

        # profile.features_combined : (N_ips, 76)
        # profile.ip_labels         : (N_ips,) — 0/1 attack flag

    Parameters
    ----------
    config:
        Node2Vec config (reused for raw_unsw_dir path).
        Uses ``node2vec_settings`` singleton when ``None``.
    """

    def __init__(self, config: Node2VecConfig | None = None) -> None:
        self._cfg: Node2VecConfig = config or node2vec_settings

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def build_profiles(
        self,
        embedding_result: EmbeddingResult,
        csv_paths: list[Path] | None = None,
    ) -> ProfileResult:
        """
        Compute the full per-IP feature matrix.

        Parameters
        ----------
        embedding_result:
            Output of :meth:`~src.models.pretrain.node2vec.Node2VecEmbedder.fit`.
            Provides the Node2Vec embeddings and the IP→index mapping.
        csv_paths:
            Raw UNSW CSV paths for flow statistics.  When ``None``,
            auto-discovers ``UNSW-NB15_[0-9].csv`` under ``config.raw_unsw_dir``.

        Returns
        -------
        ProfileResult
        """
        resolved = self._resolve_csv_paths(csv_paths)
        logger.info(
            "profiler_start",
            num_ips=embedding_result.num_nodes,
            csv_count=len(resolved),
        )

        # ── Step 1: Load flow data for statistical features ────────────
        df = self._load_flow_data(resolved)

        # ── Step 2: Flow-level features (vectorised pandas groupby) ────
        flow_feats = self._compute_flow_features(
            df, embedding_result.ip_list, embedding_result.ip_to_idx
        )
        logger.info("profiler_flow_features_done", shape=list(flow_feats.shape))

        # ── Step 3: Graph structural features (NetworkX) ───────────────
        graph_feats = self._compute_graph_features(
            embedding_result.ip_to_idx,
            embedding_result.num_nodes,
            df,
        )
        logger.info("profiler_graph_features_done", shape=list(graph_feats.shape))

        # ── Step 4: Assemble final matrices ────────────────────────────
        structural = np.concatenate([flow_feats, graph_feats], axis=1)  # (N, 12)
        embeddings = embedding_result.embeddings.astype(np.float32)      # (N, 64)
        combined   = np.concatenate([structural, embeddings], axis=1)    # (N, 76)

        embedding_col_names = [
            f"n2v_{i}" for i in range(embeddings.shape[1])
        ]
        feature_names = STRUCTURAL_FEATURE_NAMES + embedding_col_names

        logger.info(
            "profiler_complete",
            structural_dim=structural.shape[1],
            combined_dim=combined.shape[1],
        )

        return ProfileResult(
            features=structural.astype(np.float32),
            features_combined=combined.astype(np.float32),
            feature_names=feature_names,
            ip_list=embedding_result.ip_list,
            ip_labels=embedding_result.ip_labels,
            embedding_dim=embeddings.shape[1],
        )

    # ------------------------------------------------------------------
    # Internal: data loading
    # ------------------------------------------------------------------

    def _resolve_csv_paths(self, explicit: list[Path] | None) -> list[Path]:
        if explicit:
            return [Path(p) for p in explicit]
        candidates = sorted(Path(self._cfg.raw_unsw_dir).glob(_UNSW_RAW_GLOB))
        if not candidates:
            raise FileNotFoundError(
                f"No UNSW raw CSV files found in {self._cfg.raw_unsw_dir!r}."
            )
        return candidates

    def _load_flow_data(self, csv_paths: list[Path]) -> pd.DataFrame:
        """Load the 8 profiling columns from all raw UNSW CSVs."""
        frames: list[pd.DataFrame] = []
        for p in csv_paths:
            try:
                chunk = pd.read_csv(
                    p,
                    header=None,
                    usecols=_PROFILE_COLS,
                    dtype=str,
                    on_bad_lines="skip",
                    encoding="latin1",
                )
                chunk.columns = _PROFILE_NAMES
                frames.append(chunk)
                logger.debug("profiler_csv_loaded", path=str(p), rows=len(chunk))
            except Exception as exc:  # noqa: BLE001
                logger.warning("profiler_csv_skip", path=str(p), error=str(exc))

        if not frames:
            raise RuntimeError("No UNSW CSV files could be loaded.")

        df = pd.concat(frames, ignore_index=True)
        df = df.dropna(subset=["srcip", "dstip"])
        df = df[df["srcip"].str.strip() != ""]
        df = df[df["dstip"].str.strip() != ""]

        # Numeric coercions
        for col in ("sbytes", "dbytes"):
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)
        for col in ("sport", "dsport"):
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(-1).astype(int)

        df["label"] = (
            pd.to_numeric(df["label"], errors="coerce")
            .fillna(0)
            .astype(np.int32)
        )
        return df

    # ------------------------------------------------------------------
    # Internal: flow features
    # ------------------------------------------------------------------

    def _compute_flow_features(
        self,
        df: pd.DataFrame,
        ip_list: list[str],
        ip_to_idx: dict[str, int],
    ) -> np.ndarray:
        """
        Build a (N, 9) float32 matrix of per-IP flow statistics.

        All computations are vectorised with pandas groupby — no Python loops
        over individual IPs.
        """
        N = len(ip_list)
        feat = np.zeros((N, len(FLOW_FEATURE_NAMES)), dtype=np.float64)
        col = {name: i for i, name in enumerate(FLOW_FEATURE_NAMES)}

        # ── Out-direction aggregations  (srcip == this IP) ─────────────
        src_grp = df.groupby("srcip", sort=False)

        # out_degree: unique destination IPs
        out_deg = src_grp["dstip"].nunique()
        # num_out_flows
        out_cnt = src_grp["srcip"].count()
        # bytes_sent_mean
        bytes_sent = src_grp["sbytes"].mean()
        # unique_dst_ports
        udp = src_grp["dsport"].nunique()
        # unique_protocols (aggregate on srcip side)
        uproto = src_grp["proto"].nunique()

        # ── In-direction aggregations  (dstip == this IP) ──────────────
        dst_grp = df.groupby("dstip", sort=False)

        # in_degree: unique source IPs
        in_deg = dst_grp["srcip"].nunique()
        # num_in_flows
        in_cnt = dst_grp["dstip"].count()
        # bytes_recv_mean
        bytes_recv = dst_grp["dbytes"].mean()
        # unique_src_ports (ports used to reach this IP)
        usp = dst_grp["sport"].nunique()

        # ── Fill matrix by IP list order ───────────────────────────────
        for series, col_name in [
            (out_deg,   "out_degree"),
            (out_cnt,   "num_out_flows"),
            (bytes_sent, "bytes_sent_mean"),
            (udp,       "unique_dst_ports"),
            (uproto,    "unique_protocols"),
            (in_deg,    "in_degree"),
            (in_cnt,    "num_in_flows"),
            (bytes_recv, "bytes_recv_mean"),
            (usp,       "unique_src_ports"),
        ]:
            c = col[col_name]
            for ip, val in series.items():
                idx = ip_to_idx.get(str(ip))
                if idx is not None:
                    feat[idx, c] = float(val) if not np.isnan(float(val)) else 0.0

        return feat.astype(np.float32)

    # ------------------------------------------------------------------
    # Internal: graph features
    # ------------------------------------------------------------------

    def _compute_graph_features(
        self,
        ip_to_idx: dict[str, int],
        num_nodes: int,
        df: pd.DataFrame,
    ) -> np.ndarray:
        """
        Build a (N, 3) float32 matrix of per-IP graph structural features.

        Features computed via NetworkX:
            - PageRank (100 iterations, damping=0.85)
            - Clustering coefficient (undirected local clustering)
            - Degree centrality (total degree / (N-1))

        The IP graph is constructed from deduplicated edges in ``df``.
        """
        logger.info("profiler_building_networkx_graph", num_nodes=num_nodes)

        # Build a directed NetworkX graph from deduplicated IP pairs
        edge_df = df[["srcip", "dstip"]].drop_duplicates()
        G_directed = nx.from_pandas_edgelist(
            edge_df,
            source="srcip",
            target="dstip",
            create_using=nx.DiGraph,
        )

        # PageRank on directed graph
        logger.info("profiler_computing_pagerank")
        pagerank: dict[str, float] = nx.pagerank(
            G_directed,
            alpha=0.85,
            max_iter=100,
            tol=1e-6,
        )

        # Clustering coefficient on undirected projection
        logger.info("profiler_computing_clustering")
        G_undirected = G_directed.to_undirected()
        clustering: dict[str, float] = nx.clustering(G_undirected)

        # Degree centrality on undirected graph (in+out combined, normalised)
        logger.info("profiler_computing_degree_centrality")
        degree_cent: dict[str, float] = nx.degree_centrality(G_undirected)

        # ── Fill matrix ────────────────────────────────────────────────
        feat = np.zeros((num_nodes, len(GRAPH_FEATURE_NAMES)), dtype=np.float64)
        col = {name: i for i, name in enumerate(GRAPH_FEATURE_NAMES)}

        for ip, idx in ip_to_idx.items():
            feat[idx, col["pagerank"]]          = pagerank.get(ip, 0.0)
            feat[idx, col["clustering_coeff"]]  = clustering.get(ip, 0.0)
            feat[idx, col["degree_centrality"]] = degree_cent.get(ip, 0.0)

        logger.info("profiler_graph_features_complete")
        return feat.astype(np.float32)
