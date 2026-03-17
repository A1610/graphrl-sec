# 14 — Module: Simulated SOC Environment (Gymnasium)

## Phase 4, Module 4.1

---

## 1. What We Are Building

A custom Gymnasium environment that simulates a Security Operations Center (SOC). The DRL agent interacts with this environment to learn alert triage. The environment presents alerts (with graph context), the agent decides what to do, and the environment provides rewards based on whether the decision was correct.

**In Simple Terms:** We're building a "training simulator" for our AI SOC analyst. Just like a flight simulator trains pilots, this SOC simulator trains our AI to handle alerts.

---

## 2. Why We Are Building It

DRL agents learn by interacting with environments. We can't train on a live SOC (too risky), so we build a simulator that:
- Generates realistic alert streams from our dataset
- Provides graph context (T-HetGAT embeddings) with each alert
- Simulates analyst feedback (using ground-truth labels)
- Tracks metrics: false positive rate, time to triage, escalation quality

---

## 3. How It Works

### Environment Specification

```python
# Gymnasium Environment
class SOCTriageEnv(gymnasium.Env):
    """
    Observation Space:
        - anomaly_score: float [0, 1] (from T-HetGAT)
        - graph_embedding: float[128] (local neighborhood embedding)
        - alert_metadata: float[16] (protocol, bytes, duration, etc.)
        - historical_context: float[32] (past decisions on similar alerts)
        Total: 177-dimensional vector

    Action Space:
        0: DISMISS (mark as false positive)
        1: INVESTIGATE (assign to analyst with context)
        2: ESCALATE (critical — immediate response)
        3: CORRELATE (link to existing attack campaign)

    Reward:
        Correct DISMISS of benign:      +1.0
        Correct ESCALATE of attack:     +3.0 (higher reward for catching attacks)
        Correct INVESTIGATE:            +1.5
        Correct CORRELATE:              +2.0
        Wrong DISMISS of real attack:   -5.0 (severe penalty — missed attack!)
        Wrong ESCALATE of benign:       -1.0 (wasted analyst time)
        Wrong INVESTIGATE of benign:    -0.5
    """
```

### Episode Structure

```
Reset: Load next batch of alerts (e.g., 100 alerts from one time window)
    │
    ▼
Step 1: Agent observes alert_1 (observation vector)
    │ Agent picks action (DISMISS/INVESTIGATE/ESCALATE/CORRELATE)
    │ Environment computes reward based on ground truth
    │
Step 2: Agent observes alert_2
    │ ...
    │
Step N: Last alert in batch
    │
Done: Episode complete. Return total reward + metrics.
```

---

## 4. Implementation Plan

### Task 4.1: SOC Environment

```python
# src/models/drl/soc_env.py
```
- Custom Gymnasium environment
- Loads pre-computed T-HetGAT embeddings and anomaly scores
- Alert queue from dataset (in chronological order)
- Ground truth labels for reward computation
- Episode management (batch of alerts per episode)

### Task 4.2: Observation Builder

```python
# src/models/drl/observation.py
```
- Combines T-HetGAT embedding + anomaly score + metadata + history
- Normalizes all features to [-1, 1] or [0, 1]
- Maintains a history buffer of past N decisions for context

### Task 4.3: Reward Shaping

```python
# src/models/drl/rewards.py
```
- Asymmetric rewards (missing attacks is much worse than false alarms)
- Campaign bonus: extra reward if agent correctly links alerts to campaign
- Efficiency bonus: reward for quick triage decisions
- Configurable reward weights for tuning

### Task 4.4: Alert Generator

```python
# src/models/drl/alert_generator.py
```
- Converts T-HetGAT output (anomaly scores) into alert stream
- Threshold-based alert generation (score > 0.5 → alert)
- Enriches alerts with graph context
- Supports both dataset-driven and synthetic alert generation

---

## 5. Folder Structure

```
src/models/drl/
├── __init__.py
├── soc_env.py            # Gymnasium SOC environment
├── observation.py        # Observation vector construction
├── rewards.py            # Reward shaping
├── alert_generator.py    # Alert stream generation
└── config.py             # Environment configuration
```

---

## 6. Expected Output

### Environment Test:
```python
env = SOCTriageEnv(alerts_path="data/processed/alerts.json")
obs, info = env.reset()
print(f"Observation shape: {obs.shape}")  # (177,)
print(f"Action space: {env.action_space}")  # Discrete(4)

action = env.action_space.sample()
obs, reward, done, truncated, info = env.step(action)
print(f"Reward: {reward}, Done: {done}")
```

---

## 7. Definition of Done

- [ ] SOC environment passes Gymnasium API check
- [ ] Observations have correct shape (177,)
- [ ] All 4 actions produce valid rewards
- [ ] Episodes terminate correctly
- [ ] Random agent achieves baseline performance
- [ ] Environment renders readable statistics
