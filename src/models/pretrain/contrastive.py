"""
Contrastive learning objective for self-supervised graph pre-training.

Implements NT-Xent (Normalized Temperature-scaled Cross-Entropy) loss,
the same objective used in SimCLR and GraphCL.

Core idea:
    Given two augmented views of the same graph (view1, view2):
    - Positive pair : same node in view1 and view2
    - Negative pairs: every other node in the batch

    The loss pushes positive pairs together and negative pairs apart
    in the projection space.

Reference:
    Chen et al. "A Simple Framework for Contrastive Learning of Visual
    Representations." ICML 2020.  https://arxiv.org/abs/2002.05709
"""

from __future__ import annotations

import torch
import torch.nn.functional as F  # noqa: N812
from torch import Tensor

from src.models.pretrain.config import PretrainConfig, pretrain_settings


class NTXentLoss:
    """
    NT-Xent (Normalized Temperature-scaled Cross-Entropy) loss.

    Operates on flat node-level projection vectors collected from a batch
    of graph pairs.  Both views must contain the same number of nodes N
    in the same order so that node i in view1 is the positive pair for
    node i in view2.

    Usage::

        loss_fn = NTXentLoss(config)

        # z1, z2: (N, projection_dim) — L2-normalised projection vectors
        loss = loss_fn(z1, z2)

    The loss is symmetric: loss(z1, z2) == loss(z2, z1).
    """

    def __init__(self, config: PretrainConfig | None = None) -> None:
        self._cfg         = config or pretrain_settings
        self._temperature = self._cfg.temperature

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def __call__(self, z1: Tensor, z2: Tensor) -> Tensor:
        """
        Compute symmetric NT-Xent loss.

        Parameters
        ----------
        z1 : Tensor of shape (N, D)
            L2-normalised projections from view 1.
        z2 : Tensor of shape (N, D)
            L2-normalised projections from view 2.

        Returns
        -------
        Scalar loss tensor (mean over all 2N samples).
        """
        return self._nt_xent(z1, z2)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _nt_xent(self, z1: Tensor, z2: Tensor) -> Tensor:
        """
        Full symmetric NT-Xent over 2N representations.

        Concatenates both views into a 2N matrix, then uses the off-diagonal
        cosine-similarity entries as logits and a diagonal positive mask.
        """
        n = z1.shape[0]
        if n == 0:
            return z1.new_zeros(())

        # Ensure unit norm (defensive — caller should already normalise)
        z1 = F.normalize(z1, dim=-1)
        z2 = F.normalize(z2, dim=-1)

        # Concatenate: [z1; z2] → (2N, D)
        z   = torch.cat([z1, z2], dim=0)                    # (2N, D)

        # Cosine similarity matrix (2N, 2N), scaled by temperature
        sim = torch.mm(z, z.t()) / self._temperature         # (2N, 2N)

        # Mask out self-similarities on the diagonal
        mask_self = torch.eye(2 * n, dtype=torch.bool, device=z.device)
        sim = sim.masked_fill(mask_self, float("-inf"))

        # Positive pair indices:
        #   row i   → positive is at row  i + N  (z1_i ↔ z2_i)
        #   row i+N → positive is at row  i      (z2_i ↔ z1_i)
        pos_idx = torch.arange(n, device=z.device)
        labels  = torch.cat([pos_idx + n, pos_idx], dim=0)  # (2N,)

        # Cross-entropy over all 2N rows
        loss = F.cross_entropy(sim, labels)
        return loss


# ---------------------------------------------------------------------------
# Positive-pair builder
# ---------------------------------------------------------------------------


def collect_node_projections(
    proj_dict1: dict[str, Tensor],
    proj_dict2: dict[str, Tensor],
) -> tuple[Tensor, Tensor] | None:
    """
    Concatenate per-type projection tensors from two views into flat matrices.

    Only node types present in **both** views are included.  Node types that
    appear in only one view (e.g. due to edge dropout removing all edges to
    that type) are silently skipped.

    Parameters
    ----------
    proj_dict1 : {node_type: (N_type, D)} from view 1
    proj_dict2 : {node_type: (N_type, D)} from view 2

    Returns
    -------
    (z1, z2) each of shape (N_total, D), or None if no common node types.
    """
    common_types = [
        ntype for ntype in proj_dict1
        if ntype in proj_dict2
        and proj_dict1[ntype].shape[0] == proj_dict2[ntype].shape[0]
        and proj_dict1[ntype].shape[0] > 0
    ]

    if not common_types:
        return None

    z1 = torch.cat([proj_dict1[t] for t in common_types], dim=0)
    z2 = torch.cat([proj_dict2[t] for t in common_types], dim=0)
    return z1, z2
