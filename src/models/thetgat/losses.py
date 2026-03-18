"""
Loss functions for T-HetGAT — Module 11.

Why Focal Loss?
---------------
Our dataset has extreme class imbalance:
    ~82.5% normal windows  vs  ~17.5% attack windows

With standard Binary Cross-Entropy (BCE), the model quickly learns to
predict "normal" for everything and achieves ~82% accuracy while never
detecting a single attack.

Focal Loss (Lin et al., 2017 — RetinaNet paper) fixes this by:
    1. Down-weighting easy negatives (correctly classified normal windows)
       via the (1 - p_t)^gamma focusing term.
    2. Optionally balancing classes via the alpha weighting term.

Formula
-------
    FL(p_t) = -alpha_t * (1 - p_t)^gamma * log(p_t)

    where:
        p_t  = model probability for the TRUE class
        alpha = 0.25  (down-weights majority class)
        gamma = 2.0   (focusing — 0 reduces to weighted BCE)

Practical effect on our data
-----------------------------
    Normal window,  model confident (p=0.95 normal):
        BCE loss   = -log(0.95) ≈ 0.051
        Focal loss = (1-0.95)^2 * 0.051 ≈ 0.0001  ← almost ignored

    Attack window,  model uncertain (p=0.55 attack):
        BCE loss   = -log(0.55) ≈ 0.598
        Focal loss = (1-0.55)^2 * 0.598 ≈ 0.121   ← still significant

Result: model focuses its gradient budget on hard, uncertain attack cases.
"""

from __future__ import annotations

import torch
import torch.nn as nn
import torch.nn.functional as F
from torch import Tensor


class FocalLoss(nn.Module):
    """
    Binary Focal Loss for window-level anomaly detection.

    Parameters
    ----------
    alpha:
        Balancing factor for the positive (attack) class.
        Typical value: 0.25.  Set to 0.5 for no class balancing.
    gamma:
        Focusing exponent.  0 → standard weighted BCE.
        Typical values: 1.0–5.0.  Paper recommends 2.0.
    reduction:
        ``'mean'``  — average over all samples (default, used in training).
        ``'sum'``   — sum over all samples.
        ``'none'``  — return per-sample losses (useful for debugging).

    Example
    -------
    ::

        criterion = FocalLoss(alpha=0.25, gamma=2.0)
        loss = criterion(logits, labels)   # logits: (N,), labels: (N,) float
    """

    def __init__(
        self,
        alpha: float = 0.25,
        gamma: float = 2.0,
        reduction: str = "mean",
    ) -> None:
        super().__init__()
        if reduction not in {"mean", "sum", "none"}:
            raise ValueError(
                f"reduction must be 'mean', 'sum', or 'none' — got {reduction!r}"
            )
        self.alpha     = alpha
        self.gamma     = gamma
        self.reduction = reduction

    def forward(self, logits: Tensor, targets: Tensor) -> Tensor:
        """
        Compute focal loss.

        Parameters
        ----------
        logits:
            Raw (pre-sigmoid) predictions, shape ``(N,)`` or ``(N, 1)``.
        targets:
            Binary ground-truth labels ``{0, 1}``, shape ``(N,)`` float32.

        Returns
        -------
        Tensor
            Scalar loss (if reduction='mean'/'sum') or ``(N,)`` tensor.
        """
        logits  = logits.view(-1)
        targets = targets.view(-1).float()

        # Numerically stable: use BCE with logits, then apply focal weight
        bce_loss = F.binary_cross_entropy_with_logits(
            logits, targets, reduction="none"
        )

        # p_t: probability assigned to the TRUE class
        probs = torch.sigmoid(logits)
        p_t   = probs * targets + (1.0 - probs) * (1.0 - targets)

        # alpha_t: per-sample class balancing weight
        alpha_t = self.alpha * targets + (1.0 - self.alpha) * (1.0 - targets)

        # Focal weight: (1 - p_t)^gamma
        focal_weight = (1.0 - p_t).pow(self.gamma)

        loss = alpha_t * focal_weight * bce_loss

        if self.reduction == "mean":
            return loss.mean()
        if self.reduction == "sum":
            return loss.sum()
        return loss  # 'none'

    def extra_repr(self) -> str:
        return f"alpha={self.alpha}, gamma={self.gamma}, reduction={self.reduction!r}"


class WeightedBCELoss(nn.Module):
    """
    Weighted Binary Cross-Entropy — simpler alternative to Focal Loss.

    Assigns ``pos_weight`` to attack samples to compensate for class
    imbalance.  Use when Focal Loss is too aggressive.

    Parameters
    ----------
    pos_weight:
        Weight for positive (attack) class.
        Rule of thumb: ``num_negative / num_positive``.
        For our 82/18 split: pos_weight ≈ 4.7.
    """

    def __init__(self, pos_weight: float = 4.7) -> None:
        super().__init__()
        self.register_buffer(
            "pos_weight_tensor",
            torch.tensor([pos_weight], dtype=torch.float32),
        )

    def forward(self, logits: Tensor, targets: Tensor) -> Tensor:
        return F.binary_cross_entropy_with_logits(
            logits.view(-1),
            targets.view(-1).float(),
            pos_weight=self.pos_weight_tensor,  # type: ignore[arg-type]
        )
