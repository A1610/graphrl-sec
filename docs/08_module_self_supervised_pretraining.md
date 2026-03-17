# 08 — Module: Self-Supervised Graph Pre-training

## Phase 2, Module 2.1

---

## 1. What We Are Building

A self-supervised contrastive learning pipeline that pre-trains a graph encoder on **normal** network traffic. The encoder learns what "normal" network behavior looks like as graph embeddings. Later, anomaly detection becomes: "how different is this new graph from the learned normal?"

**In Simple Terms:** We're teaching the AI what a healthy network looks like by showing it tons of normal traffic, so it can later spot when something is "off."

---

## 2. Why We Are Building It

The biggest problem in cybersecurity ML is **labeled data scarcity** — attacks are rare, and labeling them is expensive. Self-supervised pre-training solves this:
- Train on abundant **unlabeled normal traffic** (no labels needed)
- Learn rich graph representations without human annotation
- Fine-tune with small amounts of labeled attack data (Phase 3)
- Transfer across deployments (pre-train once, fine-tune per environment)

---

## 3. How It Works

### Contrastive Learning Objective (GraphCL)

```
Normal Traffic:
  Window t  ──encoder──▶ embedding_t
  Window t+1 ──encoder──▶ embedding_t+1

  Loss: embeddings of SAME node in adjacent normal windows → SIMILAR
        embeddings of DIFFERENT nodes → DISSIMILAR

Training:
  1. Take graph snapshots at t and t+1 (both normal traffic)
  2. For each node, compute embeddings in both snapshots
  3. Positive pairs: same node at t and t+1
  4. Negative pairs: different nodes (contrastive sampling)
  5. Minimize NT-Xent (Normalized Temperature-scaled Cross-Entropy) loss
```

### Architecture

```
Graph Snapshot (PyG HeteroData)
    │
    ▼
[Heterogeneous Message Passing]
    │ (HeteroConv with SAGEConv per edge type)
    │ 2-3 layers, hidden_dim=128
    ▼
[Node Embeddings] (N × 128)
    │
    ▼
[Projection Head] (MLP: 128 → 64)
    │
    ▼
[Contrastive Loss] (NT-Xent)
```

---

## 4. Implementation Plan

### Task 4.1: Graph Augmentation Module

```python
# src/models/pretrain/augmentation.py
```
Graph augmentations for contrastive learning:
- **Node feature masking:** Randomly mask 20% of node features with zeros
- **Edge dropout:** Randomly drop 20% of edges
- **Subgraph sampling:** Random walk-based subgraph extraction
- Each augmentation creates a "view" of the same graph

### Task 4.2: Graph Encoder (Base — shared with T-HetGAT)

```python
# src/models/pretrain/encoder.py
```
- Heterogeneous GNN encoder using `HeteroConv`
- Each edge type gets its own `SAGEConv` or `GATConv`
- 2-3 message passing layers
- Hidden dimension: 128 (fits in 6GB VRAM)
- Batch normalization + ReLU between layers

```python
import torch
import torch.nn as nn
from torch_geometric.nn import HeteroConv, SAGEConv, Linear

class HeteroGraphEncoder(nn.Module):
    def __init__(self, metadata, hidden_dim=128, num_layers=2):
        super().__init__()
        # Per-node-type input projection
        self.node_projections = nn.ModuleDict()
        for node_type in metadata[0]:  # node types
            self.node_projections[node_type] = Linear(-1, hidden_dim)

        # Heterogeneous message passing layers
        self.convs = nn.ModuleList()
        for _ in range(num_layers):
            conv_dict = {}
            for edge_type in metadata[1]:  # edge types
                conv_dict[edge_type] = SAGEConv((-1, -1), hidden_dim)
            self.convs.append(HeteroConv(conv_dict, aggr='mean'))

        self.norms = nn.ModuleList([
            nn.ModuleDict({nt: nn.BatchNorm1d(hidden_dim) for nt in metadata[0]})
            for _ in range(num_layers)
        ])

    def forward(self, x_dict, edge_index_dict):
        # Project node features to hidden_dim
        h_dict = {nt: self.node_projections[nt](x) for nt, x in x_dict.items()}

        # Message passing
        for i, conv in enumerate(self.convs):
            h_dict = conv(h_dict, edge_index_dict)
            h_dict = {nt: self.norms[i][nt](h.relu()) for nt, h in h_dict.items()}

        return h_dict  # Dict[node_type, Tensor(N, hidden_dim)]
```

### Task 4.3: Contrastive Learning Framework

```python
# src/models/pretrain/contrastive.py
```
- NT-Xent loss implementation
- Positive pair creation (same node, adjacent windows)
- Hard negative mining (nodes that are structurally similar but different)
- Temperature hyperparameter (default: 0.5)

### Task 4.4: Pre-training Loop

```python
# src/models/pretrain/trainer.py
```
- DataLoader: iterate over temporal graph windows
- For each pair of adjacent windows: compute embeddings, compute loss
- Optimizer: AdamW, lr=1e-3, weight_decay=1e-5
- Mixed precision training (FP16) for VRAM savings
- Gradient checkpointing if needed
- Save best model checkpoint based on validation loss
- Early stopping (patience=10)

### Task 4.5: Embedding Evaluator

```python
# src/models/pretrain/evaluate.py
```
- After pre-training, evaluate embedding quality:
  - **Anomaly Detection AUROC:** Use embeddings as features, train simple classifier
  - **Embedding Visualization:** t-SNE/UMAP of node embeddings, colored by label
  - **Clustering Quality:** Do attack nodes cluster separately from normal?

### Task 4.6: Checkpoint Manager

```python
# src/models/pretrain/checkpoint.py
```
- Save/load model checkpoints
- Track training metrics (loss curves)
- Model versioning

---

## 5. Folder Structure

```
src/models/pretrain/
├── __init__.py
├── augmentation.py       # Graph augmentation strategies
├── encoder.py            # HeteroGraphEncoder (shared base)
├── contrastive.py        # NT-Xent loss, pair creation
├── trainer.py            # Pre-training loop
├── evaluate.py           # Embedding quality evaluation
├── checkpoint.py         # Model checkpoint management
└── config.py             # Pre-training hyperparameters
```

---

## 6. Dependencies Required

```
torch>=2.3.0
torch-geometric>=2.5.0
torch-scatter, torch-sparse  # PyG extensions
scikit-learn>=1.3            # For evaluation metrics
matplotlib>=3.8              # For visualization
umap-learn>=0.5              # For UMAP visualization
```

---

## 7. Data Flow

```
data/processed/graph_snapshots/
    ├── window_001.pt  (HeteroData for hour 1)
    ├── window_002.pt  (HeteroData for hour 2)
    ├── ...
    └── window_168.pt  (HeteroData for hour 168 = 1 week)
         │
         ▼
    [Pre-training DataLoader]
    Pairs: (window_t, window_t+1) for all normal windows
         │
         ▼
    [HeteroGraphEncoder] + [Projection Head]
         │
         ▼
    [NT-Xent Contrastive Loss]
         │
         ▼
    models/pretrained_encoder.pt  (saved checkpoint)
```

---

## 8. RTX 3050 (6GB VRAM) Optimization

| Setting | Value | Why |
|---|---|---|
| hidden_dim | 128 | Smaller than typical 256, fits in VRAM |
| num_layers | 2 | Sufficient for 2-hop neighborhoods |
| batch_size | 16 subgraphs | Mini-batch sampling via NeighborLoader |
| num_neighbors | [15, 10] | Sample 15 first-hop, 10 second-hop neighbors |
| mixed_precision | True | FP16 halves memory usage |
| gradient_checkpointing | True if needed | Trade compute for memory |

### Memory Estimate:
```
Encoder parameters: ~500K params × 4 bytes = ~2 MB (tiny)
Mini-batch subgraph: ~5K nodes × 128 dim × 4 bytes = ~2.5 MB
Intermediate activations: ~50 MB with FP16
Gradient storage: ~50 MB
Total: ~105 MB ← well within 6GB
```

---

## 9. Expected Output

### Training Logs:
```
[INFO] Pre-training started
[INFO] Dataset: 168 graph windows (1 week normal traffic)
[INFO] Config: hidden_dim=128, layers=2, lr=1e-3, temp=0.5

Epoch [1/100] | Loss: 4.523 | LR: 1.00e-3 | GPU: 1.2 GB
Epoch [10/100] | Loss: 2.187 | LR: 1.00e-3 | GPU: 1.2 GB
Epoch [50/100] | Loss: 0.834 | LR: 5.00e-4 | GPU: 1.2 GB
Epoch [100/100] | Loss: 0.412 | LR: 1.00e-4 | GPU: 1.2 GB

[INFO] Best model saved: models/pretrained_encoder_epoch87.pt
[INFO] Validation loss: 0.398
```

### Embedding Evaluation:
```
[INFO] Anomaly Detection (using pre-trained embeddings + Linear probe):
[INFO]   AUROC: 0.87 (without fine-tuning!)
[INFO]   Precision@10%: 0.72
[INFO]   This confirms embeddings capture meaningful structure.
```

---

## 10. Edge Cases

| Edge Case | Handling |
|---|---|
| Empty graph window (no events) | Skip window, don't create pair |
| Very small graph (<10 nodes) | Pad or skip |
| GPU OOM during training | Reduce batch_size, enable gradient checkpointing |
| Embeddings collapse (all same) | Add diversity regularization, check temperature |
| Node appears in only one window | No positive pair → exclude from loss |

---

## 11. Testing Strategy

### Unit Tests:
```
tests/unit/test_pretrain/
├── test_augmentation.py     # Augmentations preserve graph structure
├── test_encoder.py          # Forward pass produces correct shapes
├── test_contrastive.py      # Loss computation is correct
└── test_checkpoint.py       # Save/load works correctly
```

### Key Tests:
1. Encoder output shape matches expected `(N, hidden_dim)` per node type
2. Augmented graph has correct proportion of dropped edges/masked features
3. NT-Xent loss decreases over training iterations
4. Saved checkpoint loads correctly and produces same embeddings
5. Memory usage stays under 4GB during training

---

## 12. Definition of Done

- [x] HeteroGraphEncoder produces valid embeddings for all node types
- [x] Graph augmentations work correctly (feature masking, edge dropout)
- [ ] Contrastive loss converges during training *(needs graph snapshots from ingestion)*
- [ ] Pre-trained encoder saved as checkpoint *(needs actual training run)*
- [ ] Embedding evaluation shows AUROC > 0.80 (without fine-tuning) *(needs actual training run)*
- [ ] Training runs within 4GB VRAM on RTX 3050 *(needs actual training run)*
- [ ] t-SNE visualization shows meaningful clustering *(needs actual training run)*
- [x] All unit tests pass (55/55 ✅)

---

## 13. Implementation Status

### Completed — 2026-03-17

| File | Description | Tests |
|---|---|---|
| `src/models/pretrain/config.py` | `PretrainConfig` — pydantic-settings, `PRETRAIN_` env prefix | — |
| `src/models/pretrain/augmentation.py` | `GraphAugmentor` — feature masking + edge dropout | 11 ✅ |
| `src/models/pretrain/encoder.py` | `HeteroGraphEncoder` — LazyLinear + SAGEConv + BatchNorm + projection head | 16 ✅ |
| `src/models/pretrain/contrastive.py` | `NTXentLoss` + `collect_node_projections` | 13 ✅ |
| `src/models/pretrain/trainer.py` | `PretrainTrainer` — AdamW + CosineAnnealingLR + GradScaler FP16 + early stopping | — |
| `src/models/pretrain/checkpoint.py` | `CheckpointManager` — save/load best & latest | 16 ✅ |
| `src/models/pretrain/evaluate.py` | `EmbeddingEvaluator` — AUROC linear probe + silhouette + collapse detection | — |
| `tests/unit/test_pretrain/` | Full unit test suite | **55/55 ✅** |

**Code quality:** ruff ✅ mypy ✅

### Pending (blocked on dataset ingestion)

1. Run ingestion pipeline to generate `.pt` graph snapshots:
   ```
   python -m src.ingestion.cli ingest --dataset unsw --path data/raw/unsw/ --mode batch
   ```
2. Run pre-training:
   ```
   python -m src.models.pretrain.trainer
   ```
3. Evaluate embeddings and produce t-SNE visualization.
