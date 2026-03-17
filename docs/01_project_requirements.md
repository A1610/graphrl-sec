# 01 — Project Requirements Document

## GraphRL-Sec: Adaptive Cybersecurity Threat Intelligence System

---

## 1. System Overview

GraphRL-Sec is an AI-powered cybersecurity threat intelligence platform that models enterprise networks as dynamic graphs, detects anomalies using Graph Neural Networks (GNNs), autonomously triages alerts using Deep Reinforcement Learning (DRL), and enables privacy-preserving federated threat intelligence sharing across organizations.

**In Simple Terms:** Think of it as an AI SOC analyst that sees your entire network as a living, breathing graph — understanding relationships between hosts, users, services, and IPs — and uses that structural understanding to catch attacks that rule-based systems miss entirely.

---

## 2. Problem Statement

Modern Security Operations Centers (SOCs) face:

- **Alert Fatigue:** 10,000+ alerts/day, 80%+ false positive rate
- **Static Detection:** SIEM/SOAR systems use rule-based detection, missing novel attack patterns
- **Siloed Analysis:** No understanding of graph-structured attack patterns (lateral movement, multi-stage campaigns)
- **Talent Shortage:** 3.5M+ unfilled cybersecurity positions globally
- **No Unified System:** Nothing combines temporal GNNs + DRL triage + federated cross-org intelligence

---

## 3. Functional Requirements

### FR-1: Data Ingestion
- Ingest network logs (syslog, NetFlow/IPFIX) in real-time
- Normalize events into a unified schema
- Stream events via message queue (Kafka)
- Perform real-time feature extraction

### FR-2: Dynamic Network Graph
- Model network as a temporal heterogeneous graph
- Support node types: hosts, users, services, external IPs, domains
- Support edge types: connects-to, authenticates-as, queries-dns, transfers-data
- Maintain sliding window (24-72 hours) with periodic snapshots
- Store persistent structure in graph database (Neo4j)

### FR-3: Anomaly Detection (T-HetGAT)
- Process dynamic network graph in time-windowed snapshots
- Attend to structural AND temporal features
- Output per-node and per-edge anomaly scores
- Self-supervised pre-training on normal traffic
- Fine-tuning with labeled attack data

### FR-4: Alert Triage (DRL Agent)
- Process flagged anomalous subgraphs
- Actions: dismiss, investigate, escalate, correlate
- Learn from SOC analyst feedback
- State = anomaly scores + graph embedding + alert metadata + history
- Trained via DQN with prioritized experience replay

### FR-5: Federated Intelligence
- Share learned threat representations (NOT raw data) across orgs
- Differential privacy on gradient updates
- Secure aggregation server
- Permissioned blockchain for contribution provenance

### FR-6: Attack Campaign Reconstruction
- Cluster related alerts into coherent attack narratives
- Community detection on temporal attention graph
- Louvain + temporal community detection

### FR-7: SOC Dashboard
- Real-time alert visualization
- Attack graph visualization
- Campaign timeline views
- Analyst feedback interface
- Integration with existing SIEM tools (Splunk, Elastic) via REST APIs

---

## 4. Non-Functional Requirements

| Requirement | Target |
|---|---|
| Detection Latency | < 30 seconds from attack packet to alert |
| Detection F1-Score | > 0.92 |
| False Positive Rate | < 5% |
| Alert Triage Reduction | 40% fewer false positive escalations |
| Autonomous Triage Coverage | 80%+ of alerts handled without human |
| GPU Memory Budget | ≤ 6GB VRAM (RTX 3050) for local dev |
| Uptime | 99.9% for detection pipeline |
| Federated Privacy | Rényi Differential Privacy (ε ≤ 8) |

---

## 5. Hardware Constraints (Development)

```
GPU: NVIDIA RTX 3050 (6GB VRAM)
All models MUST:
  - Fit within 6GB VRAM during training AND inference
  - Use mixed precision (FP16) where possible
  - Use mini-batch/neighborhood sampling for large graphs
  - Be profiled for memory usage before scaling
```

---

## 6. Tech Stack

| Layer | Technology |
|---|---|
| **Frontend** | Next.js (latest), Tailwind CSS, D3.js / vis.js for graph viz |
| **Backend API** | FastAPI (Python) |
| **Graph Neural Networks** | PyTorch Geometric (PyG) |
| **Graph Database** | Neo4j Community Edition |
| **RL Framework** | Stable-Baselines3, Gymnasium |
| **Stream Processing** | Apache Kafka (lightweight: Redpanda for local dev) |
| **Log Collection** | Filebeat (lightweight alternative to rsyslog for local dev) |
| **Federated Learning** | Flower (flwr) |
| **Differential Privacy** | Opacus |
| **Containerization** | Docker, Docker Compose |
| **Monitoring** | Grafana + Prometheus |
| **Database** | PostgreSQL (metadata), Redis (caching) |
| **Testing** | pytest, locust (load testing) |

### Hardware-Aware Stack Adjustments

Since we're on RTX 3050 (6GB), we make these trade-offs:
- **No Apache Flink** → Use lightweight Python stream processing (Faust or custom Kafka consumer)
- **No Kubernetes** → Docker Compose for local orchestration
- **No Rust in-memory graph engine** → NetworkX + PyG for graph management
- **No blockchain** → SQLite-based contribution tracking (simulated)
- **PyTorch Geometric over DGL** → Better RTX 3050 compatibility, smaller footprint

---

## 7. Datasets

| Dataset | Purpose | Size |
|---|---|---|
| CICIDS2017 | Labeled intrusion detection (DDoS, brute force, infiltration, botnet) | ~50GB raw, we use sampled subset |
| UNSW-NB15 | 9 attack categories, rich features | ~2GB |
| LANL Unified Host & Network | 58 days enterprise traffic with red team events | ~12GB compressed |
| Custom SOC Simulation | Synthetic enterprise network | Generated locally |

**Note:** We'll start with UNSW-NB15 (smallest) and CICIDS2017 for development, then scale.

---

## 8. Development Phases Overview

| Phase | Timeline | Focus |
|---|---|---|
| Phase 0 | Week 0 | Environment Setup + Project Scaffolding |
| Phase 1 | Week 1-4 | Data Pipeline + Graph Construction |
| Phase 2 | Week 5-8 | Self-Supervised Pre-training |
| Phase 3 | Week 9-13 | T-HetGAT Detection Engine |
| Phase 4 | Week 14-17 | DRL Triage Agent |
| Phase 5 | Week 18-20 | Federated Learning + Campaign Detection |
| Phase 6 | Week 21-22 | Integration + Dashboard + Paper |

---

## 9. Project Directory Structure (Top-Level)

```
graphrl-sec/
├── README.md
├── docker-compose.yml
├── .env.example
├── .gitignore
├── requirements.txt
├── pyproject.toml
├── Makefile
│
├── docs/                          # All numbered markdown docs
│   ├── 01_project_requirements.md
│   ├── 02_system_architecture.md
│   ├── ...
│
├── src/
│   ├── ingestion/                 # Data ingestion pipeline
│   ├── graph/                     # Graph construction & management
│   ├── models/
│   │   ├── thetgat/               # T-HetGAT detection model
│   │   ├── pretrain/              # Self-supervised pre-training
│   │   ├── drl/                   # DRL triage agent
│   │   └── federated/             # Federated learning
│   ├── campaign/                  # Attack campaign reconstruction
│   ├── api/                       # FastAPI backend
│   ├── utils/                     # Shared utilities
│   └── config/                    # Configuration management
│
├── frontend/                      # Next.js dashboard
│   ├── src/
│   ├── public/
│   └── package.json
│
├── tests/
│   ├── unit/
│   ├── integration/
│   └── fixtures/
│
├── data/
│   ├── raw/                       # Downloaded datasets
│   ├── processed/                 # Cleaned & processed data
│   └── graphs/                    # Serialized graph snapshots
│
├── models/                        # Saved model checkpoints
├── notebooks/                     # Exploration notebooks
├── scripts/                       # Utility scripts
└── infra/                         # Docker, deployment configs
    ├── docker/
    └── monitoring/
```

---

## 10. Success Criteria

1. End-to-end pipeline: raw logs → graph → anomaly detection → triage → dashboard
2. Detection F1 > 0.92 on CICIDS2017/UNSW-NB15
3. DRL agent reduces false positive escalations by ≥ 40%
4. Federated learning shows F1 improvement on zero-day attacks
5. Full system runs on RTX 3050 (6GB VRAM) locally
6. Production-grade code: typed, tested, documented, containerized

---

## 11. Risk Register

| Risk | Impact | Mitigation |
|---|---|---|
| 6GB VRAM insufficient for T-HetGAT | High | Mini-batch sampling, FP16, gradient checkpointing |
| Graph too large for memory | High | Sliding window, graph sampling, periodic pruning |
| DRL agent cold-start | Medium | Pre-train on simulated SOC, curriculum learning |
| Dataset quality issues | Medium | Data validation pipeline, synthetic augmentation |
| Federated learning convergence | Medium | FedProx for heterogeneity, careful hyperparameter tuning |
| Scope creep | High | Strict phase gates, MVP-first approach |
