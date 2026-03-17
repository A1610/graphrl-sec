# 09 — Module: Node2Vec Baseline & Feature Engineering

## Phase 2, Module 2.2

---

## 1. What We Are Building

A Node2Vec-based embedding module that creates host/user behavior profiles by learning structural embeddings from the graph. This serves as both a feature source and a baseline to compare against T-HetGAT.

**In Simple Terms:** Node2Vec takes random walks on the graph (like a person randomly wandering through a network map) and learns which nodes are "similar" based on their neighborhoods. It's simpler than GNNs but fast and useful.

---

## 2. Why We Are Building It

- **Baseline Model:** Need something to compare T-HetGAT against
- **Feature Enrichment:** Node2Vec embeddings can be used as additional node features for T-HetGAT
- **Fast Profiling:** Quick way to identify hosts/users with unusual graph positions
- **Interpretability:** Node2Vec embeddings are easy to visualize and explain

---

## 3. How It Works

```
Graph (NetworkX or PyG)
    │
    ▼
[Random Walk Generator]
    - p=1, q=1 (default — BFS/DFS balanced)
    - walk_length=80
    - walks_per_node=10
    │
    ▼
[Word2Vec (Skip-gram)]
    - embedding_dim=64
    - window=5
    │
    ▼
[Node Embeddings] (N × 64)
    │
    ├──▶ Anomaly detection baseline (Isolation Forest on embeddings)
    └──▶ Feature input for T-HetGAT node features
```

---

## 4. Implementation Plan

### Task 4.1: Node2Vec on Heterogeneous Graph
```python
# src/models/pretrain/node2vec.py
```
- Use `torch_geometric.nn.Node2Vec`
- Handle heterogeneous graph by creating a homogeneous projection
- Temporal features included via edge weights

### Task 4.2: Behavior Profiling
```python
# src/models/pretrain/profiling.py
```
- Compute per-host statistics: degree, betweenness, clustering coefficient
- Combine structural features + Node2Vec embeddings
- Create "behavior fingerprint" per host

### Task 4.3: Anomaly Baseline
```python
# src/models/pretrain/baseline.py
```
- Isolation Forest on Node2Vec embeddings
- One-Class SVM on combined features
- Compute AUROC, F1, precision-recall
- This becomes the benchmark to beat with T-HetGAT

---

## 5. Folder Structure

```
src/models/pretrain/
├── ...existing files...
├── node2vec.py          # Node2Vec training
├── profiling.py         # Host behavior profiling
└── baseline.py          # Anomaly detection baseline
```

---

## 6. Expected Output

```
[INFO] Node2Vec Training:
[INFO]   Nodes: 2,139 | Edges: 48,814
[INFO]   Embedding dim: 64
[INFO]   Training time: 45s (CPU)

[INFO] Baseline Anomaly Detection (Isolation Forest):
[INFO]   AUROC: 0.78
[INFO]   F1 (threshold=0.5): 0.65
[INFO]   Precision: 0.71 | Recall: 0.60
[INFO]   → This is our baseline to beat with T-HetGAT
```

---

## 7. Definition of Done

- [ ] Node2Vec produces valid embeddings for all nodes
- [ ] Isolation Forest baseline produces AUROC and F1 scores
- [ ] Results saved to `models/baseline_results.json`
- [ ] Baseline scores documented for Phase 3 comparison
- [ ] All tests pass
