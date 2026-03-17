# 11 — Module: T-HetGAT Detection Engine

## Phase 3, Module 3.1 — THE CORE NOVEL MODEL

---

## 1. What We Are Building

The **Temporal Heterogeneous Graph Attention Network (T-HetGAT)** — the novel GNN architecture that is the primary research contribution of GraphRL-Sec. It processes dynamic network graphs with heterogeneous node types and temporal edge features to detect anomalous structural patterns indicative of cyber attacks.

**In Simple Terms:** T-HetGAT is a specialized neural network that looks at the network graph, pays attention to both WHO is communicating (structure) and WHEN/HOW communication patterns change (temporal), and scores every node and edge for "how suspicious is this?"

---

## 2. Why We Are Building It

This is the **core novel contribution** of the dissertation:
- Existing GNNs (E-GraphSAGE) don't model temporal dynamics
- Static anomaly detection misses evolving attack patterns
- T-HetGAT handles heterogeneous nodes (hosts ≠ users ≠ services)
- Temporal attention reveals WHEN behavior changed, not just IF

---

## 3. How It Works

### Architecture Overview

```
Input: HeteroData graph snapshot
    │
    ▼
[Temporal Edge Feature Encoder]
    - Encodes timestamps, duration, bytes as temporal features
    - Positional encoding for time (sinusoidal)
    │
    ▼
[Heterogeneous Graph Attention Layer × 3]
    - Per-edge-type attention (different weights for CONNECTS_TO vs QUERIES_DNS)
    - Multi-head attention (4 heads)
    - Incorporates temporal edge features into attention scores
    │
    ▼
[Temporal Aggregation Module]
    - Aggregates embeddings across time windows
    - GRU over sequential snapshots
    - Captures temporal evolution of node behavior
    │
    ▼
[Anomaly Scoring Head]
    - Per-node anomaly score: MLP(node_embedding) → [0, 1]
    - Per-edge anomaly score: MLP(concat(src, dst, edge_feat)) → [0, 1]
    │
    ▼
Output: anomaly_scores_nodes, anomaly_scores_edges
```

### Key Innovation: Temporal Attention

Standard GAT attention:
```
α_ij = softmax(LeakyReLU(a^T [Wh_i || Wh_j]))
```

T-HetGAT temporal attention:
```
α_ij = softmax(LeakyReLU(a^T [Wh_i || Wh_j || W_t·temporal_encoding(e_ij)]))
```

Where `temporal_encoding(e_ij)` encodes the edge's timestamp, duration, and frequency relative to the node's historical patterns.

---

## 4. Implementation Plan

### Task 4.1: Temporal Edge Feature Encoder

```python
# src/models/thetgat/temporal_encoder.py
```
- Sinusoidal positional encoding for timestamps
- Relative time encoding (time since last event for this node)
- Frequency encoding (events per minute for this edge type)
- Output: `temporal_features (E × d_temporal)` where d_temporal=32

```python
class TemporalEncoder(nn.Module):
    def __init__(self, d_model=32):
        super().__init__()
        self.time_proj = nn.Linear(1, d_model)
        self.freq_proj = nn.Linear(1, d_model)
        self.duration_proj = nn.Linear(1, d_model)
        self.combine = nn.Linear(d_model * 3, d_model)

    def forward(self, timestamps, durations, frequencies):
        t_enc = torch.sin(self.time_proj(timestamps.unsqueeze(-1)))
        f_enc = self.freq_proj(frequencies.unsqueeze(-1))
        d_enc = self.duration_proj(durations.unsqueeze(-1))
        return self.combine(torch.cat([t_enc, f_enc, d_enc], dim=-1))
```

### Task 4.2: Heterogeneous Temporal GAT Layer

```python
# src/models/thetgat/hetgat_layer.py
```
- Custom `MessagePassing` layer with temporal attention
- Different attention weights per edge type
- Multi-head attention (4 heads, head_dim=32, total=128)
- Edge features incorporated into attention computation
- Residual connections + LayerNorm

### Task 4.3: Temporal Aggregation (Cross-Window)

```python
# src/models/thetgat/temporal_aggregation.py
```
- GRU that processes node embeddings across sequential time windows
- Input: sequence of node embeddings from K windows
- Output: temporally-aware node embedding
- Handles nodes that appear/disappear across windows

### Task 4.4: T-HetGAT Full Model

```python
# src/models/thetgat/model.py
```
- Combines: encoder (from pre-training) + temporal attention + temporal aggregation + anomaly scoring
- Load pre-trained weights from Phase 2
- Freeze/unfreeze strategy: freeze encoder for first few epochs, then fine-tune all

```python
class THetGAT(nn.Module):
    def __init__(self, metadata, hidden_dim=128, num_layers=3,
                 num_heads=4, num_windows=4, dropout=0.1):
        super().__init__()
        self.temporal_encoder = TemporalEncoder(d_model=32)
        self.hetgat_layers = nn.ModuleList([
            HeteroTemporalGATLayer(hidden_dim, num_heads, metadata)
            for _ in range(num_layers)
        ])
        self.temporal_agg = nn.GRU(hidden_dim, hidden_dim, batch_first=True)
        self.node_scorer = nn.Sequential(
            nn.Linear(hidden_dim, 64), nn.ReLU(), nn.Dropout(dropout),
            nn.Linear(64, 1), nn.Sigmoid()
        )
        self.edge_scorer = nn.Sequential(
            nn.Linear(hidden_dim * 2 + 32, 64), nn.ReLU(), nn.Dropout(dropout),
            nn.Linear(64, 1), nn.Sigmoid()
        )
```

### Task 4.5: Training Pipeline

```python
# src/models/thetgat/trainer.py
```
- Load pre-trained encoder weights
- Fine-tune on labeled data (CICIDS2017, UNSW-NB15)
- Loss: Binary Cross-Entropy with focal loss for imbalanced data
- Class weights to handle attack rarity
- Optimizer: AdamW, lr=5e-4
- Scheduler: CosineAnnealing with warmup
- Mini-batch training via NeighborLoader
- Mixed precision (FP16)
- Gradient clipping (max_norm=1.0)

### Task 4.6: Evaluation & Benchmarking

```python
# src/models/thetgat/evaluate.py
```
- Compute: AUROC, F1, Precision, Recall, FPR
- Compare against baselines: Node2Vec+IF, E-GraphSAGE, DOMINANT
- Per-attack-type breakdown (DDoS, brute force, infiltration, etc.)
- Confusion matrix visualization
- ROC curve plotting

---

## 5. Folder Structure

```
src/models/thetgat/
├── __init__.py
├── temporal_encoder.py      # Temporal edge feature encoding
├── hetgat_layer.py          # Heterogeneous Temporal GAT layer
├── temporal_aggregation.py  # Cross-window GRU aggregation
├── model.py                 # Full T-HetGAT model
├── trainer.py               # Training pipeline
├── evaluate.py              # Evaluation & benchmarking
├── losses.py                # Focal loss, custom losses
└── config.py                # Model hyperparameters
```

---

## 6. Dependencies Required

```
torch>=2.3.0
torch-geometric>=2.5.0
torchmetrics>=1.2
matplotlib>=3.8
seaborn>=0.13
```

---

## 7. Data Flow

```
Phase 1 output: graph_snapshots/ (HeteroData .pt files)
    │
    ├── Filter: normal windows → pre-training (Phase 2, done)
    └── All windows (normal + attack) → fine-tuning (Phase 3)
         │
         ▼
    [NeighborLoader] — mini-batch sampling
         │
         ▼
    [T-HetGAT Model]
         │
         ├── node_anomaly_scores: Tensor(N,) in [0, 1]
         └── edge_anomaly_scores: Tensor(E,) in [0, 1]
         │
         ▼
    [Binary Cross-Entropy + Focal Loss]
         │
         ▼
    models/thetgat_best.pt (saved checkpoint)
```

---

## 8. RTX 3050 (6GB VRAM) Optimization

| Setting | Value | Rationale |
|---|---|---|
| hidden_dim | 128 | Balance quality vs VRAM |
| num_layers | 3 | Sufficient for 3-hop context |
| num_heads | 4 | 4 heads × 32 dim = 128 |
| batch_size | 512 target nodes | NeighborLoader samples subgraph |
| num_neighbors | [15, 10, 5] | 3-layer sampling |
| num_windows | 4 | GRU processes 4 sequential windows |
| mixed_precision | True | FP16 everywhere |
| gradient_checkpointing | True | For 3-layer model |

### Memory Estimate:
```
Model parameters: ~2M × 4 bytes ≈ 8 MB
Mini-batch (512 targets, sampled neighbors): ~20K nodes
  - Features: 20K × 128 × 2 bytes (FP16) ≈ 5 MB
  - Attention weights: 20K × 15 × 4 × 2 bytes ≈ 2.4 MB
  - Temporal features: 50K × 32 × 2 bytes ≈ 3.2 MB
  - Intermediate activations: ~100 MB (with checkpointing)
  - Gradients: ~100 MB
Total: ~220 MB ← WELL within 6GB
```

---

## 9. Expected Output

### Training Logs:
```
[INFO] T-HetGAT Training (Fine-tuning on CICIDS2017)
[INFO] Pre-trained weights loaded from: models/pretrained_encoder_epoch87.pt
[INFO] Config: layers=3, heads=4, hidden=128, lr=5e-4

Epoch [1/50]  | Train Loss: 0.654 | Val AUROC: 0.82 | Val F1: 0.74 | GPU: 2.1 GB
Epoch [10/50] | Train Loss: 0.312 | Val AUROC: 0.91 | Val F1: 0.86 | GPU: 2.1 GB
Epoch [30/50] | Train Loss: 0.098 | Val AUROC: 0.95 | Val F1: 0.93 | GPU: 2.1 GB
Epoch [50/50] | Train Loss: 0.054 | Val AUROC: 0.96 | Val F1: 0.94 | GPU: 2.1 GB

[INFO] Best model saved: models/thetgat_best_epoch42.pt
```

### Benchmark Results:
```
╔═══════════════════════╦════════╦═══════╦═══════════╦════════╗
║ Model                 ║ AUROC  ║  F1   ║ Precision ║ Recall ║
╠═══════════════════════╬════════╬═══════╬═══════════╬════════╣
║ Isolation Forest      ║  0.78  ║ 0.65  ║   0.71    ║  0.60  ║
║ Node2Vec + RF         ║  0.82  ║ 0.72  ║   0.75    ║  0.69  ║
║ E-GraphSAGE           ║  0.89  ║ 0.84  ║   0.82    ║  0.86  ║
║ T-HetGAT (ours)       ║  0.96  ║ 0.94  ║   0.93    ║  0.95  ║
╚═══════════════════════╩════════╩═══════╩═══════════╩════════╝
```

---

## 10. Edge Cases

| Edge Case | Handling |
|---|---|
| Class imbalance (99% normal, 1% attack) | Focal loss + class weights + oversampling |
| Node type missing in some windows | Zero-pad, mask in attention |
| Very sparse graph windows | Add self-loops, ensure minimum connectivity |
| Attention weights all equal (no learning) | Check learning rate, add diversity loss |
| OOM during backprop | Enable gradient checkpointing, reduce batch_size |

---

## 11. Testing Strategy

### Unit Tests:
```
tests/unit/test_thetgat/
├── test_temporal_encoder.py     # Temporal encoding shapes
├── test_hetgat_layer.py         # Single layer forward pass
├── test_temporal_agg.py         # GRU aggregation
├── test_model.py                # Full model forward + backward
├── test_losses.py               # Focal loss computation
└── test_evaluation.py           # Metric computation
```

### Key Tests:
1. Model forward pass produces correct output shapes
2. Gradient flows through all parameters (no dead layers)
3. Focal loss handles extreme class imbalance
4. NeighborLoader produces valid subgraphs
5. Pre-trained weight loading works correctly
6. VRAM usage stays under 4GB during training

---

## 12. Definition of Done

- [ ] T-HetGAT model forward pass works on HeteroData input
- [ ] Pre-trained weights loaded successfully
- [ ] Training converges with decreasing loss
- [ ] AUROC > 0.92 on CICIDS2017 test set (project target)
- [ ] F1 > 0.90 on test set
- [ ] FPR < 5% (project target)
- [ ] Benchmark table with ≥ 3 baselines generated
- [ ] Training runs within 4GB VRAM on RTX 3050
- [ ] Best model checkpoint saved
- [ ] All unit tests pass
