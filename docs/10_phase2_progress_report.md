# 10 — Phase 2 Progress Report

## Phase 2: Self-Supervised Pre-training (Week 5-8)

---

## Completed Modules

| Module | Status | Notes |
|---|---|---|
| 08: Self-Supervised Graph Pre-training | ✅ Complete | GraphCL contrastive learning, HeteroGraphEncoder, best val_loss=6.766 (epoch 21/31) |
| 09: Node2Vec Baseline & Feature Engineering | ✅ Complete | IP graph (19,179 nodes, 114,081 edges), Isolation Forest + One-Class SVM |

---

## Current System Capabilities After Phase 2

Everything from Phase 1, PLUS:
- Pre-trained HeteroGraphEncoder that understands "normal" network behavior
  - Trained on 17,657 temporal graph snapshots (UNSW-NB15 + CICIDS2017)
  - Best val_loss = 6.766 | Stopped at epoch 31 (patience=10)
  - Saved: `models/pretrain/checkpoint_best.pt`
- Node2Vec embeddings for 19,179 unique IPs (64-dim vectors)
  - Saved: `models/baseline/node2vec.pt`
- Behavior profiles: 76-dim feature vectors per IP
  - 9 flow stats + 3 graph stats (PageRank, clustering, degree) + 64 Node2Vec
- Anomaly detection baseline (Isolation Forest + One-Class SVM)
  - Saved: `models/baseline/iso_forest.joblib`, `oc_svm.joblib`
- Baseline AUROC and F1 scores documented below

---

## Key Metrics

| Metric | Node2Vec + Isolation Forest | Node2Vec + One-Class SVM |
|---|---|---|
| AUROC | **0.9804** | **0.9609** |
| F1 | 0.4912 | 0.6531 |
| Precision | 0.4667 | 0.7273 |
| Recall | 0.5185 | 0.5926 |

> **Note:** F1 is lower than AUROC due to extreme class imbalance —
> only 27 attack IPs out of 19,179 total (0.14%).
> AUROC measures ranking quality and is the primary comparison metric.
> T-HetGAT (Module 11) must beat AUROC > 0.98 AND F1 > 0.65.

---

## Training Run Summary (Module 08)

| Run | Issue | Result |
|---|---|---|
| Run 1 | val_loss = 0.0 bug | Discarded |
| Run 2 | Augmenting two different graphs → shape mismatch | Discarded |
| Run 3 | GraphCL fix: augment same graph twice | ✅ val_loss = 6.766 |

**Root cause fixed:** NT-Xent loss requires equal node counts in both views.
Augmenting `graph_a` + `graph_b` (different windows, different sizes) caused
`collect_node_projections` to return None for mismatched pairs → valid_pairs=0
→ loss=0/0=0.0. Fix: augment `graph_a` twice (proper GraphCL approach).

---

## Next Phase Objectives

- **Phase 3: T-HetGAT Detection Engine** — the core novel model
  - Fine-tune pre-trained encoder on labeled attack data
  - Temporal attention over graph snapshots
  - Beat baseline: AUROC > 0.98, F1 > 0.65
- Benchmark against E-GraphSAGE and other SOTA methods
- Full end-to-end evaluation on held-out test windows
