# 12 — Module: E-GraphSAGE & Baseline Models

## Phase 3, Module 3.2

---

## 1. What We Are Building

Implementation of baseline GNN models (E-GraphSAGE, DOMINANT) and traditional ML baselines (Random Forest, XGBoost on flow features) for fair benchmarking against T-HetGAT.

**In Simple Terms:** We're building the "competition" — other models that T-HetGAT needs to beat to prove its value.

---

## 2. Why We Are Building It

No research contribution is valid without fair comparison. We need:
- **E-GraphSAGE:** State-of-the-art GNN for intrusion detection
- **DOMINANT:** Graph anomaly detection baseline
- **Random Forest / XGBoost:** Traditional ML baselines (non-graph)
- These prove that our novel architecture actually provides value

---

## 3. Implementation Plan

### Task 3.1: E-GraphSAGE Implementation
```python
# src/models/baselines/egraphsage.py
```
- Implement E-GraphSAGE from Lo et al. (2022)
- GraphSAGE with edge features
- Same training/evaluation pipeline as T-HetGAT

### Task 3.2: DOMINANT (Graph Anomaly Detection)
```python
# src/models/baselines/dominant.py
```
- Graph autoencoder-based anomaly detection
- Reconstruction error = anomaly score

### Task 3.3: Traditional ML Baselines
```python
# src/models/baselines/traditional.py
```
- Random Forest on flow-level features
- XGBoost on flow-level features
- Feature set: bytes, duration, packets, port, protocol (no graph structure)

### Task 3.4: Unified Benchmark Script
```python
# scripts/benchmark.py
```
- Train all models on same train/val/test split
- Compute all metrics consistently
- Generate benchmark table and plots
- Save results to `models/benchmark_results.json`

---

## 4. Folder Structure

```
src/models/baselines/
├── __init__.py
├── egraphsage.py       # E-GraphSAGE implementation
├── dominant.py          # DOMINANT graph autoencoder
└── traditional.py       # RF, XGBoost baselines

scripts/
├── benchmark.py         # Unified benchmarking
```

---

## 5. Definition of Done

- [ ] E-GraphSAGE produces valid anomaly scores
- [ ] DOMINANT produces valid reconstruction-based scores
- [ ] RF/XGBoost trained on flow features
- [ ] All models evaluated on same test set
- [ ] Benchmark table generated with AUROC, F1, Precision, Recall
- [ ] T-HetGAT outperforms all baselines on primary metrics
- [ ] Results saved for dissertation
