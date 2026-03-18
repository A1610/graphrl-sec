"""
Temporal Edge Feature Encoder — Module 11 T-HetGAT.

What does this do?
------------------
Each edge in our graph has a 12-dimensional feature vector (edge_attr):

    [0]  timestamp_norm     — when did this flow happen within the window?
    [1]  duration_norm      — how long did the flow last?
    [2]  bytes_sent_norm    — data sent
    [3]  bytes_recv_norm    — data received
    [4]  packets_sent_norm  — packets sent
    [5]  packets_recv_norm  — packets received
    [6]  protocol_tcp       — is it TCP?
    [7]  protocol_udp       — is it UDP?
    [8]  protocol_icmp      — is it ICMP?
    [9]  protocol_other     — other protocol?
    [10] port_norm          — which port?
    [11] is_attack          — ground-truth label (used only for loss, NOT input)

This encoder takes features [0–10] (NOT [11] — that would be cheating) and
produces a rich 32-dimensional temporal embedding per edge.

Why sinusoidal encoding for timestamps?
----------------------------------------
Raw timestamps [0, 1] lose phase information — the model can't tell
"is 0.5 closer to the start or end?"  Sinusoidal encoding gives the
model multiple frequency "views" of the same timestamp, letting it
learn time-dependent patterns (e.g. attack bursts at specific intervals).

Architecture
------------
    edge_attr[:, :11]   (E, 11)
          │
          ├─ timestamp [0]   → sin/cos positional encoding → (E, d_model)
          ├─ flow stats [1:6] → Linear projection          → (E, d_model)
          └─ protocol+port [6:11] → Linear projection      → (E, d_model)
                │
          LayerNorm + combine Linear
                │
          temporal_features  (E, temporal_dim=32)
"""

from __future__ import annotations

import math

import torch
import torch.nn as nn
from torch import Tensor


# ---------------------------------------------------------------------------
# Edge attribute slice indices  (edge_attr has 12 cols, last is is_attack)
# ---------------------------------------------------------------------------
_IDX_TIMESTAMP  = 0
_IDX_FLOW_START = 1
_IDX_FLOW_END   = 6    # exclusive — [1,6) = duration, bytes, packets
_IDX_PROTO_START = 6
_IDX_PROTO_END   = 11  # exclusive — [6,11) = protocol + port
_N_FLOW_FEATS    = 5   # duration, bytes_sent, bytes_recv, pkts_sent, pkts_recv
_N_PROTO_FEATS   = 5   # tcp, udp, icmp, other, port_norm


class TemporalEdgeEncoder(nn.Module):
    """
    Encodes the 11 raw edge features into a ``temporal_dim``-dimensional
    vector capturing WHEN, HOW LONG, HOW MUCH, and WHAT PROTOCOL.

    The ``is_attack`` column (index 11) is deliberately excluded —
    using the label as model input would be data leakage.

    Parameters
    ----------
    temporal_dim:
        Output dimension of the temporal embedding.  Default: 32.
    d_model:
        Internal hidden dimension for each sub-encoder branch.
        Defaults to ``temporal_dim``.
    dropout:
        Dropout on the final combined embedding.

    Input / Output shapes
    ---------------------
    ::

        edge_attr : (E, 12)   — raw edge feature matrix
        output    : (E, temporal_dim)   — temporal embeddings

    Example
    -------
    ::

        enc = TemporalEdgeEncoder(temporal_dim=32)
        t   = enc(data['external_ip', 'connects_to', 'external_ip'].edge_attr)
        # t.shape == (E, 32)
    """

    def __init__(
        self,
        temporal_dim: int = 32,
        d_model: int | None = None,
        dropout: float = 0.1,
    ) -> None:
        super().__init__()
        d = d_model if d_model is not None else temporal_dim

        # ── Branch 1: Sinusoidal timestamp encoding ─────────────────────
        # Encodes the normalised timestamp [0,1] into d sinusoidal features
        # so the model can reason about temporal position in the window.
        self._register_sinusoidal_buffer(d)

        # ── Branch 2: Flow volume statistics ────────────────────────────
        # duration, bytes_sent/recv, packets_sent/recv → linear projection
        self.flow_proj = nn.Sequential(
            nn.Linear(_N_FLOW_FEATS, d),
            nn.ReLU(inplace=True),
        )

        # ── Branch 3: Protocol + port ────────────────────────────────────
        # tcp/udp/icmp/other flags + normalised port → linear projection
        self.proto_proj = nn.Sequential(
            nn.Linear(_N_PROTO_FEATS, d),
            nn.ReLU(inplace=True),
        )

        # ── Combine all 3 branches ───────────────────────────────────────
        self.combine = nn.Sequential(
            nn.Linear(d * 3, temporal_dim),
            nn.LayerNorm(temporal_dim),
            nn.ReLU(inplace=True),
            nn.Dropout(dropout),
        )

    # ------------------------------------------------------------------
    # Forward
    # ------------------------------------------------------------------

    def forward(self, edge_attr: Tensor) -> Tensor:
        """
        Encode raw edge attributes into temporal embeddings.

        Parameters
        ----------
        edge_attr:
            Raw edge feature matrix of shape ``(E, 12)``.
            Column 11 (is_attack) is ignored.

        Returns
        -------
        Tensor
            Shape ``(E, temporal_dim)``.
        """
        # Guard: handle empty edge sets (no edges in this type for this window)
        if edge_attr.shape[0] == 0:
            return edge_attr.new_zeros(0, self.combine[0].out_features)

        # ── Branch 1: timestamp sinusoidal ──────────────────────────────
        ts = edge_attr[:, _IDX_TIMESTAMP]          # (E,)
        t_enc = self._sinusoidal_encode(ts)         # (E, d)

        # ── Branch 2: flow volume ────────────────────────────────────────
        flow = edge_attr[:, _IDX_FLOW_START:_IDX_FLOW_END]   # (E, 5)
        f_enc = self.flow_proj(flow)                           # (E, d)

        # ── Branch 3: protocol + port ────────────────────────────────────
        proto = edge_attr[:, _IDX_PROTO_START:_IDX_PROTO_END] # (E, 5)
        p_enc = self.proto_proj(proto)                          # (E, d)

        # ── Combine ──────────────────────────────────────────────────────
        combined = torch.cat([t_enc, f_enc, p_enc], dim=-1)   # (E, 3d)
        return self.combine(combined)                           # (E, temporal_dim)

    # ------------------------------------------------------------------
    # Sinusoidal helpers
    # ------------------------------------------------------------------

    def _register_sinusoidal_buffer(self, d_model: int) -> None:
        """
        Pre-compute sinusoidal frequency bands and register as a buffer.

        Frequencies: 1 / (10000 ^ (2i / d_model)) for i in 0..d_model//2
        Identical to the transformer positional encoding but applied to
        normalised timestamps in [0, 1] instead of integer positions.
        """
        half_d = d_model // 2
        freq = torch.exp(
            -math.log(10000.0)
            * torch.arange(half_d, dtype=torch.float32)
            / half_d
        )  # (half_d,)
        self.register_buffer("_sin_freq", freq, persistent=False)
        self._d_model = d_model

    def _sinusoidal_encode(self, ts: Tensor) -> Tensor:
        """
        Apply sinusoidal encoding to a batch of normalised timestamps.

        Parameters
        ----------
        ts:
            Shape ``(E,)``, values in ``[0, 1]``.

        Returns
        -------
        Tensor
            Shape ``(E, d_model)``.
        """
        freq: Tensor = self._sin_freq  # type: ignore[assignment]
        # Scale timestamps to [0, 2π] for better frequency coverage
        scaled = ts.unsqueeze(-1) * 2.0 * math.pi          # (E, 1)
        angles = scaled * freq.unsqueeze(0)                  # (E, half_d)

        # Interleave sin and cos
        sin_enc = torch.sin(angles)   # (E, half_d)
        cos_enc = torch.cos(angles)   # (E, half_d)

        # Concat to reach d_model; handle odd d_model by truncating
        enc = torch.cat([sin_enc, cos_enc], dim=-1)          # (E, 2*half_d)
        return enc[:, : self._d_model]                        # (E, d_model)
