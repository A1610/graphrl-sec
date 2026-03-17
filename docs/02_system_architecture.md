# 02 — System Architecture

## GraphRL-Sec: Complete System Architecture

---

## 1. What This Document Covers

This document defines the complete system architecture for GraphRL-Sec — how every component connects, communicates, and flows data. Read this BEFORE writing any code.

---

## 2. High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        GraphRL-Sec System                               │
│                                                                         │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────────────────┐  │
│  │  DATA SOURCES │───▶│  INGESTION   │───▶│   MESSAGE QUEUE (Kafka)  │  │
│  │  - NetFlow    │    │  LAYER       │    │   - raw-events topic     │  │
│  │  - Syslog     │    │  - Parsers   │    │   - normalized topic     │  │
│  │  - Filebeat   │    │  - Normalizer│    │   - graph-updates topic  │  │
│  └──────────────┘    └──────────────┘    └────────────┬─────────────┘  │
│                                                        │                │
│                                           ┌────────────▼─────────────┐  │
│                                           │  GRAPH CONSTRUCTION      │  │
│                                           │  ENGINE                  │  │
│                                           │  - Event → Graph mapper  │  │
│                                           │  - Temporal windowing    │  │
│                                           │  - Feature extraction    │  │
│                                           └────────────┬─────────────┘  │
│                                                        │                │
│                    ┌───────────────────────┬────────────▼──────────┐    │
│                    │                       │                        │    │
│          ┌─────────▼────────┐   ┌─────────▼────────┐              │    │
│          │  Neo4j Graph DB  │   │  In-Memory Graph  │              │    │
│          │  (persistent)    │   │  (PyG Data)       │              │    │
│          └──────────────────┘   └─────────┬─────────┘              │    │
│                                           │                        │    │
│                              ┌────────────▼─────────────┐          │    │
│                              │  T-HetGAT DETECTION      │          │    │
│                              │  ENGINE                   │          │    │
│                              │  - Self-supervised embed  │          │    │
│                              │  - Anomaly scoring        │          │    │
│                              │  - Per-node/edge scores   │          │    │
│                              └────────────┬──────────────┘          │    │
│                                           │                        │    │
│                              ┌────────────▼──────────────┐          │    │
│                              │  DRL TRIAGE AGENT          │          │    │
│                              │  - DQN + PER              │          │    │
│                              │  - Actions: dismiss/       │          │    │
│                              │    investigate/escalate/   │          │    │
│                              │    correlate              │          │    │
│                              └────────────┬──────────────┘          │    │
│                                           │                        │    │
│                    ┌──────────────────────┬┴──────────────────┐     │    │
│                    │                      │                    │     │    │
│          ┌─────────▼────────┐  ┌─────────▼────────┐  ┌───────▼──┐ │    │
│          │  CAMPAIGN        │  │  ALERT STORE      │  │ FEDERATED│ │    │
│          │  RECONSTRUCTION  │  │  (PostgreSQL)     │  │ LAYER    │ │    │
│          │  - Louvain       │  │                    │  │ (Flower) │ │    │
│          │  - Temporal      │  │                    │  │          │ │    │
│          └─────────┬────────┘  └─────────┬─────────┘  └───────┬──┘ │    │
│                    │                      │                    │     │    │
│          ┌─────────▼──────────────────────▼────────────────────▼──┐ │    │
│          │              FastAPI BACKEND                            │ │    │
│          │  - REST API for dashboard                              │ │    │
│          │  - WebSocket for real-time alerts                      │ │    │
│          │  - Analyst feedback endpoint                           │ │    │
│          └─────────────────────┬──────────────────────────────────┘ │    │
│                                │                                    │    │
│          ┌─────────────────────▼──────────────────────────────────┐ │    │
│          │              Next.js SOC DASHBOARD                      │ │    │
│          │  - Real-time alert feed                                │ │    │
│          │  - Network graph visualization                         │ │    │
│          │  - Attack campaign timeline                            │ │    │
│          │  - Analyst triage interface                            │ │    │
│          └────────────────────────────────────────────────────────┘ │    │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Microservice Breakdown

For local development on RTX 3050, we use a **modular monolith** approach with Docker Compose — NOT full microservices. Each module is a separate Python package that CAN be extracted into a microservice later.

| Service | Port | Purpose |
|---|---|---|
| `kafka` (Redpanda) | 9092 | Message queue |
| `neo4j` | 7474, 7687 | Graph database |
| `postgres` | 5432 | Alert store, metadata, analyst feedback |
| `redis` | 6379 | Caching, real-time state |
| `api` | 8000 | FastAPI backend |
| `frontend` | 3000 | Next.js dashboard |
| `grafana` | 3001 | Monitoring dashboards |
| `prometheus` | 9090 | Metrics collection |

---

## 4. Data Flow Diagram

```
Raw Logs (syslog/NetFlow/CSV)
    │
    ▼
[Ingestion Parser] ── normalize ──▶ Unified Event Schema (JSON)
    │
    ▼
[Kafka: raw-events] ──▶ [Kafka: normalized-events]
    │
    ▼
[Graph Constructor] ── maps events to nodes/edges ──▶
    │
    ├──▶ [Neo4j] (persistent storage)
    └──▶ [PyG HeteroData] (in-memory for GNN)
            │
            ▼
      [T-HetGAT Model]
            │
            ├──▶ Node anomaly scores
            └──▶ Edge anomaly scores
                    │
                    ▼
            [DRL Triage Agent]
                    │
                    ├──▶ DISMISS  ──▶ Log & discard
                    ├──▶ INVESTIGATE ──▶ Queue for analyst
                    ├──▶ ESCALATE ──▶ Immediate alert
                    └──▶ CORRELATE ──▶ Campaign detection
                            │
                            ▼
                    [Campaign Reconstruction]
                            │
                            ▼
                    [PostgreSQL Alert Store]
                            │
                            ▼
                    [FastAPI] ──WebSocket──▶ [Next.js Dashboard]
```

---

## 5. Unified Event Schema

Every log/flow record is normalized to this schema before graph construction:

```json
{
    "event_id": "uuid-v4",
    "timestamp": "2026-03-15T10:30:00.000Z",
    "event_type": "network_flow | auth | dns | process | file",
    "source": {
        "ip": "192.168.1.10",
        "port": 54321,
        "hostname": "workstation-01",
        "user": "jsmith"
    },
    "destination": {
        "ip": "10.0.0.5",
        "port": 443,
        "hostname": "web-server-01",
        "service": "https"
    },
    "network": {
        "protocol": "TCP",
        "bytes_sent": 1024,
        "bytes_received": 4096,
        "duration_ms": 250,
        "packets_sent": 10,
        "packets_received": 15
    },
    "metadata": {
        "dataset_source": "CICIDS2017",
        "original_label": "BENIGN",
        "collector": "filebeat"
    }
}
```

---

## 6. Graph Schema

### Node Types

| Node Type | Properties | Example |
|---|---|---|
| `Host` | ip, hostname, os_type, is_internal | 192.168.1.10, workstation-01 |
| `User` | username, department, privilege_level | jsmith, IT, admin |
| `Service` | name, port, protocol | https, 443, TCP |
| `ExternalIP` | ip, geo_country, asn, reputation_score | 8.8.8.8, US, Google |
| `Domain` | fqdn, registered_date, reputation_score | google.com |

### Edge Types

| Edge Type | Source → Target | Temporal Properties |
|---|---|---|
| `CONNECTS_TO` | Host → Host | timestamp, bytes, duration, protocol |
| `AUTHENTICATES_AS` | Host → User | timestamp, auth_type, success |
| `QUERIES_DNS` | Host → Domain | timestamp, query_type |
| `TRANSFERS_DATA` | Host → Host | timestamp, bytes, protocol, port |
| `RUNS_SERVICE` | Host → Service | start_time, is_active |
| `RESOLVES_TO` | Domain → ExternalIP | timestamp, ttl |

---

## 7. Model Pipeline

```
Phase 2: Self-Supervised Pre-training
    ┌──────────────────────────────────────┐
    │  Normal Traffic Graph Snapshots       │
    │  (sliding windows, t1, t2, ... tn)   │
    └──────────────┬───────────────────────┘
                   │
                   ▼
    ┌──────────────────────────────────────┐
    │  Contrastive Learning (GraphCL)       │
    │  - Same node, adjacent normal windows │
    │    → embeddings should be SIMILAR      │
    │  - Node in attack window              │
    │    → embeddings should DIVERGE         │
    └──────────────┬───────────────────────┘
                   │
                   ▼
    ┌──────────────────────────────────────┐
    │  Pre-trained Encoder Weights          │
    │  (saved checkpoint)                   │
    └──────────────┬───────────────────────┘
                   │
Phase 3: Fine-tuning
                   │
                   ▼
    ┌──────────────────────────────────────┐
    │  T-HetGAT Detection Engine            │
    │  - Load pre-trained weights            │
    │  - Fine-tune on labeled attack data    │
    │  - Output: anomaly scores per node/edge│
    └──────────────┬───────────────────────┘
                   │
Phase 4: DRL Triage
                   │
                   ▼
    ┌──────────────────────────────────────┐
    │  DRL Triage Agent (DQN + PER)         │
    │  - State: T-HetGAT embeddings +       │
    │           alert metadata + history     │
    │  - Action: dismiss/investigate/        │
    │            escalate/correlate           │
    │  - Reward: analyst feedback +           │
    │            containment time +           │
    │            FP reduction                  │
    └──────────────────────────────────────┘
```

---

## 8. Security Considerations

| Concern | Mitigation |
|---|---|
| Network data contains PII | All data stays local; federated layer shares only gradients |
| Federated gradient leakage | Rényi Differential Privacy (Opacus), ε ≤ 8 |
| API security | JWT authentication, RBAC, rate limiting |
| Dashboard access | Role-based access (admin, analyst, viewer) |
| Model poisoning (federated) | Contribution scoring, Byzantine-robust aggregation |
| Data at rest | Encrypted volumes for Neo4j and PostgreSQL |
| Data in transit | TLS for all inter-service communication |

---

## 9. Communication Patterns

| From | To | Protocol | Pattern |
|---|---|---|---|
| Ingestion → Kafka | TCP | Async produce |
| Kafka → Graph Constructor | TCP | Async consume (consumer group) |
| Graph Constructor → Neo4j | Bolt | Batch write (Cypher) |
| Graph Constructor → PyG | In-process | Direct Python object |
| T-HetGAT → DRL Agent | In-process | Tensor passing |
| API → PostgreSQL | TCP | Async SQLAlchemy |
| API → Neo4j | Bolt | Async read queries |
| API → Redis | TCP | Cache reads/writes |
| Frontend → API | HTTP/WS | REST + WebSocket |
| Federated → Aggregator | gRPC/HTTP | Flower protocol |

---

## 10. Memory Budget (RTX 3050 — 6GB VRAM)

| Component | Estimated VRAM | Notes |
|---|---|---|
| T-HetGAT (training) | ~3.5 GB | With FP16, mini-batch sampling |
| T-HetGAT (inference) | ~1.5 GB | Smaller batch size |
| DRL Agent | ~0.5 GB | Lightweight DQN |
| PyG graph data | ~1.0 GB | Sampled subgraphs, not full graph |
| **Total (training)** | **~4.0 GB** | Leaves ~2GB headroom |
| **Total (inference)** | **~3.0 GB** | Leaves ~3GB for OS/display |

Strategies to stay within budget:
- **Gradient checkpointing** for T-HetGAT training
- **Neighborhood sampling** (NeighborLoader) — never load full graph to GPU
- **FP16 mixed precision** via `torch.cuda.amp`
- **Graph mini-batching** — process subgraphs, not full graph
- **Periodic GPU cache clearing** via `torch.cuda.empty_cache()`
