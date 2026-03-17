# 18 — Module: Attack Campaign Reconstruction

## Phase 5, Module 5.2

---

## 1. What We Are Building

A module that clusters related alerts into coherent **attack campaigns** using community detection on the temporal attention graph. Instead of seeing 500 individual alerts, the SOC analyst sees "1 coordinated DDoS campaign targeting 3 servers over 2 hours."

**In Simple Terms:** This module connects the dots — it takes scattered alerts and says "these 50 alerts are actually one coordinated attack, here's the timeline, and here are all the machines involved."

---

## 2. Why We Are Building It

- Individual alerts are overwhelming (10K/day)
- Analysts need **narrative context**, not just scores
- Attack campaigns have graph structure (shared infrastructure, lateral movement)
- Campaign view reduces cognitive load by 10-50x
- Enables automated incident report generation

---

## 3. How It Works

### Pipeline

```
T-HetGAT anomaly scores + attention weights
    │
    ▼
[Alert Subgraph Extraction]
    - Extract subgraph around anomalous nodes
    - Include T-HetGAT attention weights as edge weights
    │
    ▼
[Temporal Community Detection]
    - Louvain algorithm on attention-weighted graph
    - Temporal constraint: alerts in same community must overlap in time
    - Resolution parameter tuning for granularity
    │
    ▼
[Campaign Builder]
    - Each community = one campaign
    - Compute campaign metadata:
        - Start/end time
        - Involved hosts/IPs
        - Attack type classification
        - Severity score (max anomaly score in cluster)
        - Kill chain stage estimation
    │
    ▼
[Campaign Timeline Generator]
    - Chronological event sequence per campaign
    - Attack narrative generation
    - Visualization-ready data
```

---

## 4. Implementation Plan

### Task 4.1: Alert Subgraph Extraction

```python
# src/campaign/subgraph.py
```
- Extract k-hop subgraph around flagged anomalous nodes
- Include attention weights from T-HetGAT as edge weights
- Temporal filtering: only edges within the alert time window
- Output: NetworkX weighted graph

### Task 4.2: Temporal Community Detection

```python
# src/campaign/community.py
```
- Louvain community detection (using `networkx.community` or `python-louvain`)
- Temporal constraint: merge communities only if temporal overlap > threshold
- Resolution parameter: controls granularity (low = fewer large campaigns, high = many small)
- Handle isolated nodes (single-alert "campaigns")

### Task 4.3: Campaign Builder

```python
# src/campaign/builder.py
```
- Aggregate alerts per community into Campaign objects
- Compute campaign-level statistics
- Classify campaign type based on alert composition
- Estimate kill chain stage (reconnaissance → exploitation → lateral movement → exfiltration)

### Task 4.4: Campaign Timeline

```python
# src/campaign/timeline.py
```
- Chronological ordering of events within campaign
- Key moments identification (first alert, peak activity, last alert)
- Generate JSON suitable for frontend timeline visualization

### Task 4.5: Evaluation (NMI)

```python
# src/campaign/evaluate.py
```
- Normalized Mutual Information (NMI) between predicted and ground-truth campaigns
- Ground truth: CICIDS2017 labels group attacks by type + time
- Adjusted Rand Index (ARI) as additional metric

---

## 5. Folder Structure

```
src/campaign/
├── __init__.py
├── subgraph.py          # Alert subgraph extraction
├── community.py         # Temporal community detection
├── builder.py           # Campaign object construction
├── timeline.py          # Timeline generation
├── evaluate.py          # NMI evaluation
└── config.py            # Campaign detection config
```

---

## 6. Data Flow

```
T-HetGAT Output:
    node_anomaly_scores ──▶ Filter: score > threshold ──▶ Anomalous nodes
    attention_weights ──▶ Edge weights for community detection
         │
         ▼
    [Alert Subgraph] ── weighted graph with temporal edges
         │
         ▼
    [Louvain Community Detection]
         │
         ▼
    Communities:
        Campaign 1: {host_A, host_B, ext_IP_1} | 14:00-14:45 | DDoS
        Campaign 2: {host_C, user_X, host_D}   | 15:00-16:30 | Lateral Movement
         │
         ▼
    [Campaign Objects] ──▶ JSON ──▶ API ──▶ Dashboard
```

---

## 7. Expected Output

### Campaign Detection Results:
```
[INFO] Campaign Reconstruction on CICIDS2017 (Friday DDoS)

[INFO] Detected 3 campaigns:

Campaign 1: DDoS Attack
  - Duration: 14:00 - 14:47 (47 minutes)
  - Involved: 12 source IPs → 1 target (192.168.10.50)
  - Alerts: 2,341
  - Severity: CRITICAL (max anomaly score: 0.98)
  - Kill Chain: Weaponization → Delivery

Campaign 2: Port Scan (Reconnaissance)
  - Duration: 15:10 - 15:22 (12 minutes)
  - Involved: 1 source IP → 156 target ports on 3 hosts
  - Alerts: 468
  - Severity: MEDIUM (max anomaly score: 0.72)
  - Kill Chain: Reconnaissance

Campaign 3: Isolated Suspicious Activity
  - Duration: 16:05 - 16:08 (3 minutes)
  - Involved: 1 host, unusual DNS queries
  - Alerts: 12
  - Severity: LOW (max anomaly score: 0.54)
  - Kill Chain: Reconnaissance (possible)

[INFO] NMI Score: 0.82 (ground truth vs predicted campaigns)
```

---

## 8. Testing Strategy

### Unit Tests:
```
tests/unit/test_campaign/
├── test_subgraph.py        # Subgraph extraction
├── test_community.py       # Community detection
├── test_builder.py         # Campaign object construction
├── test_timeline.py        # Timeline generation
└── test_evaluate.py        # NMI computation
```

### Key Tests:
1. Known attack patterns cluster into single campaigns
2. Benign traffic doesn't form campaigns
3. Temporal constraint prevents merging unrelated temporal clusters
4. NMI computation is correct against synthetic ground truth
5. Campaign JSON is valid and complete

---

## 9. Definition of Done

- [ ] Community detection produces meaningful clusters
- [ ] Campaigns have correct metadata (time, hosts, severity)
- [ ] NMI > 0.70 against ground truth labels
- [ ] Campaign timeline JSON generated for frontend
- [ ] Kill chain stage estimation works
- [ ] All tests pass
