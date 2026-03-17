# 15 — Module: DRL Triage Agent (DQN)

## Phase 4, Module 4.2

---

## 1. What We Are Building

A Deep Q-Network (DQN) agent with Prioritized Experience Replay (PER) that learns to triage SOC alerts autonomously. The agent uses T-HetGAT embeddings as its state representation and learns from simulated analyst feedback.

**In Simple Terms:** This is our AI SOC analyst. It looks at each alert (with its graph context) and decides: "Is this junk? Should someone investigate? Is this an emergency? Is it part of a bigger attack?" It gets better over time by learning from its mistakes.

---

## 2. Why We Are Building It

- SOC analysts are overwhelmed (10K+ alerts/day, 80% false positives)
- DRL agent can handle 80%+ of alerts without human intervention
- Remaining escalations come with full context (graph embeddings, campaign links)
- Reduces mean time to triage from minutes to milliseconds

---

## 3. How It Works

### DQN Architecture

```
Observation (177-dim) ──▶ [MLP: 177 → 256 → 256 → 128] ──▶ Q-values (4 actions)
                              │
                              ├── Dueling architecture:
                              │   Value stream:  128 → 64 → 1 (V(s))
                              │   Advantage stream: 128 → 64 → 4 (A(s,a))
                              │   Q(s,a) = V(s) + A(s,a) - mean(A)
                              │
                              └── Target network (soft update, τ=0.005)
```

### Training Loop

```
1. Agent interacts with SOCTriageEnv
2. Store (state, action, reward, next_state, done) in Replay Buffer
3. Sample prioritized batch from buffer (PER)
4. Compute TD error: δ = r + γ·max_a' Q_target(s', a') - Q(s, a)
5. Update priorities in buffer based on |δ|
6. Update Q-network via gradient descent
7. Soft-update target network
8. Repeat for N episodes
```

---

## 4. Implementation Plan

### Task 4.1: DQN Agent

```python
# src/models/drl/agent.py
```
- Dueling DQN with Stable-Baselines3
- Custom feature extractor for observation space
- Prioritized Experience Replay
- ε-greedy exploration with decay

```python
from stable_baselines3 import DQN
from stable_baselines3.common.torch_layers import BaseFeaturesExtractor

class SOCFeatureExtractor(BaseFeaturesExtractor):
    def __init__(self, observation_space, features_dim=128):
        super().__init__(observation_space, features_dim)
        self.net = nn.Sequential(
            nn.Linear(observation_space.shape[0], 256),
            nn.ReLU(),
            nn.Linear(256, 256),
            nn.ReLU(),
            nn.Linear(256, features_dim),
            nn.ReLU(),
        )

    def forward(self, obs):
        return self.net(obs)
```

### Task 4.2: Training Pipeline

```python
# src/models/drl/trainer.py
```
- Curriculum learning: start with easy alerts (high-confidence), gradually add harder ones
- Warm-up phase: random exploration for first 10K steps
- Total training: 500K-1M steps
- Evaluation every 10K steps
- Early stopping on evaluation reward

### Task 4.3: Evaluation Metrics

```python
# src/models/drl/evaluate.py
```
- False Positive Escalation Rate (FPER) — target: 40% reduction
- True Positive Detection Rate — must maintain T-HetGAT performance
- Mean Time to Triage (MTTT)
- Action distribution analysis (% dismiss/investigate/escalate/correlate)
- Reward curve over training

### Task 4.4: Inference Service

```python
# src/models/drl/inference.py
```
- Load trained DQN model
- Accept alert observation → return triage decision
- Include confidence score (softmax over Q-values)
- Log all decisions for audit trail

---

## 5. Folder Structure

```
src/models/drl/
├── __init__.py
├── soc_env.py            # (from Module 14)
├── observation.py        # (from Module 14)
├── rewards.py            # (from Module 14)
├── alert_generator.py    # (from Module 14)
├── agent.py              # DQN agent definition
├── trainer.py            # Training pipeline
├── evaluate.py           # Evaluation metrics
├── inference.py          # Production inference
└── config.py             # DRL configuration
```

---

## 6. RTX 3050 Optimization

The DQN is a lightweight MLP (not a large model) — VRAM is not a concern.

| Setting | Value |
|---|---|
| Network | MLP: 177 → 256 → 256 → 128 → 4 |
| Parameters | ~200K |
| Replay buffer | 100K transitions (CPU RAM: ~200MB) |
| Batch size | 64 |
| VRAM usage | ~100 MB (minimal) |

---

## 7. Expected Output

### Training:
```
[INFO] DRL Triage Agent Training
[INFO] Environment: SOCTriageEnv (CICIDS2017 alerts)
[INFO] Algorithm: DQN + PER + Dueling

Step 10K   | Reward: -2.3 | ε: 0.90 | FPER: 75% | Random baseline
Step 100K  | Reward: 45.2 | ε: 0.50 | FPER: 52%
Step 300K  | Reward: 89.7 | ε: 0.10 | FPER: 38%
Step 500K  | Reward: 98.1 | ε: 0.05 | FPER: 32% ← TARGET MET (40% reduction)

[INFO] Best model saved: models/drl_agent_step450K.zip
```

### Action Distribution (Final Agent):
```
DISMISS:     55% (vs 80% FP rate → catching more real attacks)
INVESTIGATE: 25%
ESCALATE:    12%
CORRELATE:    8%
```

---

## 8. Testing Strategy

### Unit Tests:
```
tests/unit/test_drl/
├── test_agent.py          # Agent forward pass, action selection
├── test_soc_env.py        # Environment API compliance
├── test_rewards.py        # Reward computation
└── test_inference.py      # Inference service
```

### Key Tests:
1. Agent selects valid actions (0-3)
2. Training reward increases over episodes
3. FPER decreases over training
4. Inference service returns consistent results
5. Action distribution is reasonable (not all one action)

---

## 9. Definition of Done

- [ ] SOC environment works with Gymnasium API
- [ ] DQN agent trains and reward increases
- [ ] FPER reduced by ≥ 40% compared to T-HetGAT threshold-only
- [ ] True positive rate maintained (≥ T-HetGAT baseline)
- [ ] Trained model saved
- [ ] Inference service works
- [ ] All tests pass
