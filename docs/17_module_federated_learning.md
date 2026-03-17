# 17 — Module: Federated SOC Intelligence

## Phase 5, Module 5.1

---

## 1. What We Are Building

A federated learning system that enables multiple organizations to collaboratively improve their threat detection models WITHOUT sharing raw network data. Each organization trains its local T-HetGAT model and shares only model gradient updates (with differential privacy noise) to a central aggregation server.

**In Simple Terms:** Multiple companies can help each other catch hackers by sharing "what they've learned" (model weights) — not their actual network data. If Company A gets hit by a new zero-day attack, Company B and C automatically learn to detect it too.

---

## 2. Why We Are Building It

- **Zero-day propagation:** One org discovers a new attack → pattern propagates to all participants within hours
- **Privacy preservation:** Raw network topology is never exposed
- **Collective defense:** Small organizations benefit from large org attack diversity
- **Regulatory compliance:** No raw data sharing = easier GDPR/HIPAA compliance

---

## 3. How It Works

### Federated Learning Architecture

```
┌───────────────┐   ┌───────────────┐   ┌───────────────┐
│   SOC Org A    │   │   SOC Org B    │   │   SOC Org C    │
│                │   │                │   │                │
│ Local T-HetGAT │   │ Local T-HetGAT │   │ Local T-HetGAT │
│ Local Data     │   │ Local Data     │   │ Local Data     │
│                │   │                │   │                │
│ Train locally  │   │ Train locally  │   │ Train locally  │
│ Compute grads  │   │ Compute grads  │   │ Compute grads  │
│ + DP noise     │   │ + DP noise     │   │ + DP noise     │
└───────┬────────┘   └───────┬────────┘   └───────┬────────┘
        │                     │                     │
        └─────────────────────┼─────────────────────┘
                              │ Encrypted gradient updates
                              ▼
                ┌──────────────────────────┐
                │   Aggregation Server      │
                │   (FedProx Aggregation)   │
                │                          │
                │   Weighted average of     │
                │   gradient updates        │
                │                          │
                │   Contribution tracking   │
                │   (SQLite ledger)         │
                └────────────┬─────────────┘
                             │ Updated global model
                             ▼
                  Distribute to all participants
```

### Privacy Mechanism

```
Local gradients ──▶ [Opacus: Rényi DP] ──▶ Noised gradients ──▶ Server
                         │
                         ├── Per-sample gradient clipping (max_norm=1.0)
                         ├── Gaussian noise (σ calibrated for ε ≤ 8)
                         └── Privacy budget tracking (ε accounting)
```

---

## 4. Implementation Plan

### Task 4.1: Flower Server (Aggregation)

```python
# src/models/federated/server.py
```
- Flower (flwr) federated server
- FedProx aggregation strategy (handles heterogeneous networks)
- Weighted averaging based on dataset size per client
- Configurable rounds (default: 50)
- Global model checkpoint saving

### Task 4.2: Flower Client (Local Training)

```python
# src/models/federated/client.py
```
- Flower client wrapping local T-HetGAT trainer
- Local training: 5 epochs per federated round
- Opacus integration for differential privacy
- Returns model updates (not full model) to reduce communication

### Task 4.3: Differential Privacy Integration

```python
# src/models/federated/privacy.py
```
- Opacus `PrivacyEngine` wrapping the T-HetGAT optimizer
- Privacy budget: ε = 8, δ = 1e-5 (standard for utility-privacy trade-off)
- Per-sample gradient clipping: max_norm = 1.0
- Privacy accounting: track cumulative ε across rounds

### Task 4.4: Multi-Organization Simulator

```python
# src/models/federated/simulator.py
```
- Simulates N organizations (default: 3-5)
- Each org gets a different subset of the dataset
- Non-IID data distribution (each org sees different attack types)
- Measures: federated F1 vs. isolated F1 on held-out zero-day attacks

### Task 4.5: Contribution Tracking

```python
# src/models/federated/contribution.py
```
- SQLite-based contribution ledger (simulates blockchain)
- Records: which org contributed, when, data size, quality score
- Shapley value approximation for fair contribution assessment

---

## 5. Folder Structure

```
src/models/federated/
├── __init__.py
├── server.py              # Flower aggregation server
├── client.py              # Flower client (local T-HetGAT)
├── privacy.py             # Opacus DP integration
├── simulator.py           # Multi-org simulation
├── contribution.py        # Contribution tracking (SQLite)
├── strategies.py          # FedProx, FedAvg strategies
└── config.py              # Federated learning config
```

---

## 6. Data Flow

```
Dataset Split (simulate 3 organizations):
    Org A: CICIDS2017 (DDoS, PortScan)     → 40% of data
    Org B: CICIDS2017 (BruteForce, Bot)     → 30% of data
    Org C: UNSW-NB15 (mixed attacks)        → 30% of data

Federated Round:
    1. Server sends global model to all clients
    2. Each client trains locally for 5 epochs
    3. Each client clips gradients + adds DP noise
    4. Clients send noised updates to server
    5. Server aggregates (FedProx weighted average)
    6. Server evaluates global model on held-out test set
    7. Repeat for 50 rounds

Zero-Day Evaluation:
    - Hold out "Infiltration" attack type (only appears in Org A's data)
    - After federated training, Org B and C should detect Infiltration
    - Compare: federated F1 vs. isolated F1 on Infiltration
```

---

## 7. RTX 3050 Optimization

Federated learning simulation runs **sequentially** (not in parallel) to fit in 6GB VRAM:

```
Round 1:
    Train Org A (load to GPU → train → unload)
    Train Org B (load to GPU → train → unload)
    Train Org C (load to GPU → train → unload)
    Aggregate on CPU
    Evaluate on GPU
```

| Setting | Value |
|---|---|
| Clients per round | 3 (sequential, not parallel) |
| Local epochs | 5 per round |
| Federated rounds | 50 |
| GPU usage per client | ~2 GB (same as T-HetGAT training) |
| Total training time | ~2-4 hours (estimated) |

---

## 8. Expected Output

### Federated Training:
```
[INFO] Federated Learning Simulation
[INFO] Organizations: 3 | Rounds: 50 | DP: ε=8, δ=1e-5

Round [1/50]  | Global F1: 0.72 | Avg Local Loss: 0.45
Round [10/50] | Global F1: 0.85 | Avg Local Loss: 0.28
Round [30/50] | Global F1: 0.91 | Avg Local Loss: 0.15
Round [50/50] | Global F1: 0.93 | Avg Local Loss: 0.09

[INFO] Privacy budget consumed: ε = 7.2 (within budget of 8)
```

### Zero-Day Evaluation:
```
╔═══════════════════════╦═════════════════╦════════════════╗
║                       ║ Isolated F1     ║ Federated F1   ║
║                       ║ (no sharing)    ║ (with sharing) ║
╠═══════════════════════╬═════════════════╬════════════════╣
║ Org A (has zero-day)  ║ 0.88            ║ 0.93           ║
║ Org B (no zero-day)   ║ 0.12            ║ 0.78           ║ ← BIG improvement
║ Org C (no zero-day)   ║ 0.15            ║ 0.76           ║ ← BIG improvement
╚═══════════════════════╩═════════════════╩════════════════╝

[INFO] Federated learning enables zero-day detection without data sharing!
```

---

## 9. Testing Strategy

### Unit Tests:
```
tests/unit/test_federated/
├── test_server.py          # Aggregation logic
├── test_client.py          # Local training + DP
├── test_privacy.py         # DP noise calibration
├── test_simulator.py       # Multi-org data split
└── test_contribution.py    # Ledger recording
```

### Key Tests:
1. FedProx aggregation produces valid model weights
2. DP noise is correctly calibrated (ε accounting)
3. Per-sample gradient clipping works
4. Data splits are non-IID as configured
5. Global model improves over rounds

---

## 10. Definition of Done

- [ ] Flower server + client work for T-HetGAT
- [ ] Opacus DP integration (ε ≤ 8)
- [ ] Multi-org simulation runs end-to-end
- [ ] Federated F1 > Isolated F1 on zero-day attacks
- [ ] Privacy budget tracking works
- [ ] Contribution ledger records all updates
- [ ] All tests pass
