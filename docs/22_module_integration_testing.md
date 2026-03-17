# 22 — Module: End-to-End Integration & System Testing

## Phase 6, Module 6.3

---

## 1. What We Are Building

The final integration module that connects ALL components into a working end-to-end system. This includes Docker Compose orchestration, integration tests, system-level testing, and performance benchmarking.

**In Simple Terms:** We're connecting every piece we built — data ingestion, graph construction, T-HetGAT detection, DRL triage, campaign detection, API, and dashboard — into one cohesive system that works together.

---

## 2. Why We Are Building It

Individual modules are useless if they don't work together. This module ensures:
- Data flows correctly from ingestion to dashboard
- No interface mismatches between modules
- System meets performance targets under load
- Everything runs together on RTX 3050

---

## 3. How It Works

### Full System Pipeline

```
[1] CSV Dataset (CICIDS2017/UNSW-NB15)
     │
     ▼
[2] Ingestion CLI → Kafka Topic
     │
     ▼
[3] Kafka Consumer → Graph Constructor → Neo4j + PyG HeteroData
     │
     ▼
[4] T-HetGAT Model → Anomaly Scores (per node/edge)
     │
     ▼
[5] DRL Triage Agent → Triage Decisions (dismiss/investigate/escalate/correlate)
     │
     ▼
[6] Campaign Detection → Attack Campaigns (Louvain clustering)
     │
     ▼
[7] PostgreSQL → Alert Store + Campaign Store
     │
     ▼
[8] FastAPI Backend → REST API + WebSocket
     │
     ▼
[9] Next.js Dashboard → SOC Analyst Interface
```

---

## 4. Implementation Plan

### Task 4.1: Docker Compose Full Stack

```yaml
# docker-compose.prod.yml — adds API + frontend to base compose
```
- All services from docker-compose.yml (Kafka, Neo4j, Postgres, Redis)
- Plus: API service (FastAPI)
- Plus: Frontend service (Next.js)
- Plus: Model inference service
- Health checks on all services
- Proper startup ordering with `depends_on`

### Task 4.2: Pipeline Orchestrator

```python
# src/pipeline/orchestrator.py
```
- Orchestrates the full pipeline:
  1. Ingest data → Kafka
  2. Consume → build graph
  3. Run T-HetGAT inference
  4. Run DRL triage
  5. Run campaign detection
  6. Store results in PostgreSQL
  7. Notify API via internal event

### Task 4.3: Integration Tests

```python
# tests/integration/
├── test_ingestion_to_graph.py      # CSV → Kafka → Graph → Neo4j
├── test_graph_to_detection.py      # Graph → T-HetGAT → Anomaly scores
├── test_detection_to_triage.py     # Anomaly scores → DRL → Triage decisions
├── test_triage_to_campaign.py      # Triage → Campaign clustering
├── test_api_to_frontend.py         # API responses match frontend expectations
└── test_full_pipeline.py           # End-to-end: CSV → Dashboard
```

### Task 4.4: Performance Benchmarking

```python
# scripts/benchmark_system.py
```
- Measure end-to-end latency: first event → alert on dashboard
- Target: < 30 seconds
- Measure throughput: events/second the system can handle
- Measure GPU utilization during inference
- Measure memory usage of each component

### Task 4.5: Demo Script

```python
# scripts/demo.py
```
- One-click demo: loads sample data, runs full pipeline, opens dashboard
- Used for dissertation defense / demo presentations
- Generates realistic alert stream with mix of benign and attack traffic

---

## 5. System-Level Testing

### Smoke Test (run after every integration):
```bash
#!/bin/bash
# scripts/smoke_test.sh

echo "=== GraphRL-Sec Smoke Test ==="

# 1. Services running?
docker compose ps | grep -c "running"  # Should be 6+

# 2. API healthy?
curl -s http://localhost:8000/health | grep "ok"

# 3. Neo4j connected?
curl -s http://localhost:7474 | grep -c "neo4j"

# 4. Kafka topic exists?
# (use rpk or kafka CLI)

# 5. Frontend builds?
curl -s http://localhost:3000 | grep -c "GraphRL-Sec"

# 6. Can ingest sample data?
python -m src.ingestion.cli ingest --dataset unsw --path tests/fixtures/sample_unsw.csv --mode batch

# 7. Graph constructed?
python -c "from src.graph.neo4j_queries import get_graph_stats; print(get_graph_stats())"

# 8. API returns alerts?
curl -s http://localhost:8000/api/v1/alerts | python -m json.tool

echo "=== Smoke Test Complete ==="
```

### Load Test (locust):
```python
# tests/load/locustfile.py
from locust import HttpUser, task, between

class SOCAnalyst(HttpUser):
    wait_time = between(1, 5)

    @task(3)
    def get_alerts(self):
        self.client.get("/api/v1/alerts?limit=20")

    @task(1)
    def get_campaign(self):
        self.client.get("/api/v1/campaigns")

    @task(2)
    def get_graph_neighborhood(self):
        self.client.get("/api/v1/graph/neighborhood/192.168.10.50")
```

---

## 6. Definition of Done

- [ ] Full pipeline runs: CSV → Dashboard without manual intervention
- [ ] All integration tests pass
- [ ] End-to-end latency < 30 seconds
- [ ] System runs on RTX 3050 without OOM
- [ ] Smoke test passes
- [ ] Demo script works for presentation
- [ ] Docker Compose starts all services cleanly
