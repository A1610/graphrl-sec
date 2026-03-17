# 06 — Module: Neo4j Graph Database & Kafka Integration

## Phase 1, Module 1.3

---

## 1. What We Are Building

Two integration modules:
1. **Neo4j integration** — persistent graph storage with Cypher queries for visualization and historical analysis
2. **Kafka streaming pipeline** — real-time event streaming from ingestion to graph construction

**In Simple Terms:** We're connecting the plumbing — making data flow from log files through a message queue into a graph database, so everything is stored and queryable.

---

## 2. Why We Are Building It

- **Neo4j:** The SOC dashboard needs to query the graph for visualization. Historical graph snapshots enable attack timeline reconstruction. Graph queries power the campaign detection module.
- **Kafka:** Decouples ingestion from processing. Enables replay of events. Production systems need message queues for reliability.

---

## 3. How It Works

### Neo4j Integration
```
PyG HeteroData ──▶ [Neo4j Writer] ──▶ Neo4j Graph DB
                                           │
                                           ▼
                   [Neo4j Reader] ◀── Cypher Queries (from API)
```

### Kafka Pipeline
```
[Ingestion CLI] ──produce──▶ [Kafka: normalized-events]
                                       │
                                       ▼ consume
                             [Graph Constructor Consumer]
                                       │
                                       ▼
                             [Graph Construction Engine]
```

---

## 4. Implementation Plan

### Task 4.1: Neo4j Schema & Constraints

```cypher
// Create constraints (run once at setup)
CREATE CONSTRAINT host_ip IF NOT EXISTS FOR (h:Host) REQUIRE h.ip IS UNIQUE;
CREATE CONSTRAINT user_name IF NOT EXISTS FOR (u:User) REQUIRE u.username IS UNIQUE;
CREATE CONSTRAINT service_name IF NOT EXISTS FOR (s:Service) REQUIRE s.name IS UNIQUE;
CREATE CONSTRAINT extip_ip IF NOT EXISTS FOR (e:ExternalIP) REQUIRE e.ip IS UNIQUE;
CREATE CONSTRAINT domain_fqdn IF NOT EXISTS FOR (d:Domain) REQUIRE d.fqdn IS UNIQUE;

// Create indexes for performance
CREATE INDEX host_hostname IF NOT EXISTS FOR (h:Host) ON (h.hostname);
CREATE INDEX edge_timestamp IF NOT EXISTS FOR ()-[r:CONNECTS_TO]-() ON (r.timestamp);
```

### Task 4.2: Neo4j Async Writer

```python
# src/graph/neo4j_writer.py
```
- Async batch writes using neo4j Python driver
- MERGE (upsert) for nodes
- CREATE for edges (edges are always new — temporal)
- Batch size: 1000 nodes/edges per transaction
- Connection pool management

### Task 4.3: Neo4j Query Service

```python
# src/graph/neo4j_queries.py
```
- `get_neighborhood(ip, hops=2)` — subgraph around a host
- `get_time_window(start, end)` — all edges in time range
- `get_top_communicators(limit=20)` — most active hosts
- `get_anomalous_paths(score_threshold)` — paths with high anomaly scores
- `get_graph_stats()` — node/edge counts by type

### Task 4.4: Kafka Consumer for Graph Construction

```python
# src/ingestion/consumer.py
```
- Consumes from `normalized-events` topic
- Deserializes JSON → UnifiedEvent
- Batches events (configurable batch size + timeout)
- Passes batch to graph constructor
- Commits offsets only after successful processing

### Task 4.5: Kafka Topics Setup Script

```python
# scripts/setup_kafka.py
```
- Creates required topics: `normalized-events`, `anomaly-scores`, `triage-decisions`
- Configurable partitions and replication

---

## 5. Folder Structure

```
src/graph/
├── ...existing files...
├── neo4j_writer.py         # Batch write to Neo4j
├── neo4j_queries.py        # Query service
└── neo4j_schema.py         # Schema setup (constraints, indexes)

src/ingestion/
├── ...existing files...
├── consumer.py             # Kafka consumer
└── topics.py               # Topic management

scripts/
├── setup_kafka.py          # Create Kafka topics
└── setup_neo4j.py          # Create Neo4j constraints
```

---

## 6. Expected Output

### Neo4j Browser Query:
```cypher
MATCH (h:Host)-[r:CONNECTS_TO]->(h2:Host)
WHERE r.timestamp > datetime('2017-07-07T14:00:00Z')
RETURN h, r, h2 LIMIT 100
```
→ Visual graph in Neo4j Browser at http://localhost:7474

### Kafka Consumer Logs:
```
[INFO] Consumer started on topic: normalized-events
[INFO] Received batch: 500 events
[INFO] Graph updated: +12 nodes, +487 edges
[INFO] Neo4j write: 499 relationships in 0.3s
```

---

## 7. Testing Strategy

1. **Neo4j Writer Test:** Write 100 nodes → query back → verify all exist
2. **Idempotency Test:** Write same node twice → verify only 1 exists (MERGE)
3. **Kafka Round-Trip:** Produce 100 events → consume → verify all received
4. **Integration:** Ingest CSV → Kafka → Consumer → Neo4j → Query → verify

---

## 8. Definition of Done

- [ ] Neo4j schema created (constraints + indexes)
- [ ] Neo4j writer handles batch writes without errors
- [ ] Neo4j queries return correct subgraphs
- [ ] Kafka consumer processes events and updates graph
- [ ] End-to-end: CSV → Kafka → Graph → Neo4j works
- [ ] All tests pass
