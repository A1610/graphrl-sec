# 05 — Module: Graph Construction Engine

## Phase 1, Module 1.2

---

## 1. What We Are Building

A graph construction engine that converts normalized network events into a temporal heterogeneous graph. This graph has different types of nodes (hosts, users, services, IPs, domains) and different types of edges (connects-to, authenticates-as, queries-dns, etc.), each with temporal features.

**In Simple Terms:** We're building the "brain" that turns flat log data into a rich, connected network picture — like drawing a map of who talked to whom, when, and how.

---

## 2. Why We Are Building It

The core thesis of GraphRL-Sec is that **cyber attacks have graph structure** — lateral movement, multi-stage campaigns, distributed infrastructure. Without modeling the network as a graph, you can only see individual events, not the connections between them. This module creates the graph that T-HetGAT will analyze.

---

## 3. How It Works

```
List[UnifiedEvent]
    │
    ▼
[Node Extractor] ──▶ Creates/updates Host, User, Service, IP, Domain nodes
    │
    ▼
[Edge Constructor] ──▶ Creates temporal edges with features
    │
    ▼
[Temporal Windowing] ──▶ Slices graph into time windows
    │
    ├──▶ [Neo4j Writer] ── persistent storage
    └──▶ [PyG HeteroData] ── in-memory for GNN
```

### Internal Logic

1. **Node Extractor**: For each event, extract entities:
   - Source IP → Host node (create if not exists)
   - Destination IP → Host node or ExternalIP node
   - User field → User node
   - Service/port → Service node
   - DNS domain → Domain node

2. **Edge Constructor**: Map event types to edges:
   - `network_flow` → `CONNECTS_TO` edge (Host → Host)
   - `auth` event → `AUTHENTICATES_AS` edge (Host → User)
   - `dns` event → `QUERIES_DNS` edge (Host → Domain)

3. **Feature Engineering**: Each edge carries:
   - Timestamp (float, seconds since epoch)
   - Duration (ms)
   - Bytes transferred (sent + received)
   - Protocol (one-hot encoded)
   - Port number (normalized)

4. **Temporal Windowing**: Configurable sliding window (default 1 hour):
   - Window size: 1 hour
   - Slide step: 15 minutes
   - Creates overlapping snapshots for temporal analysis

5. **PyG Conversion**: Convert to `torch_geometric.data.HeteroData`:
   - Node features → tensors
   - Edge indices → COO format
   - Edge features → tensors
   - Enables GPU-accelerated GNN processing

---

## 4. Implementation Plan

### Task 4.1: Node Registry

```python
# src/graph/node_registry.py
```
- Maintains a mapping of entity → node_id
- Thread-safe (for future streaming support)
- Supports node type classification (internal IP → Host, external IP → ExternalIP)
- Configurable internal IP ranges (10.x, 172.16.x, 192.168.x)

### Task 4.2: Edge Constructor

```python
# src/graph/edge_constructor.py
```
- Maps UnifiedEvent → (source_node, edge_type, target_node, features)
- Feature extraction for each edge type
- Handles bidirectional edges (A connects to B = B receives from A)

### Task 4.3: Temporal Graph Manager

```python
# src/graph/temporal.py
```
- Manages sliding window of events
- Creates graph snapshots at configurable intervals
- Handles window expiry (remove edges older than window)
- Maintains global graph and per-window subgraphs

### Task 4.4: PyG Converter

```python
# src/graph/pyg_converter.py
```
- Converts internal graph representation to `HeteroData`
- Handles heterogeneous node/edge types
- Proper tensor creation for node features, edge indices, edge features
- Memory-efficient conversion (stays within 6GB budget)

### Task 4.5: Neo4j Writer

```python
# src/graph/neo4j_writer.py
```
- Batch writes nodes and edges to Neo4j
- Uses MERGE (upsert) to avoid duplicates
- Cypher query templates for each node/edge type
- Connection pooling

### Task 4.6: Graph Statistics & Validation

```python
# src/graph/stats.py
```
- Log graph statistics: node counts by type, edge counts by type
- Validate graph integrity: no orphan edges, valid node references
- Memory usage tracking

---

## 5. Folder Structure

```
src/graph/
├── __init__.py
├── node_registry.py        # Entity → node_id mapping
├── edge_constructor.py     # Event → edge mapping
├── temporal.py             # Temporal windowing manager
├── pyg_converter.py        # Convert to PyG HeteroData
├── neo4j_writer.py         # Persistent Neo4j storage
├── stats.py                # Graph statistics & validation
├── feature_engineering.py  # Node & edge feature extraction
└── config.py               # Graph construction config
```

---

## 6. Dependencies Required

```
torch-geometric>=2.5.0
networkx>=3.1
neo4j>=5.0
numpy>=1.24
```

---

## 7. Data Flow

```
UnifiedEvent
    │
    ▼
Node Registry:
    source.ip  ──▶  Host(id=0, ip="192.168.1.10")
    dest.ip    ──▶  Host(id=1, ip="10.0.0.5")
    │
    ▼
Edge Constructor:
    event_type="network_flow" ──▶ CONNECTS_TO(
        src=0, dst=1,
        features=[timestamp, duration, bytes, protocol_onehot, port_norm]
    )
    │
    ▼
Temporal Window (e.g., 14:00-15:00):
    Collects all edges within window ──▶ GraphSnapshot
    │
    ▼
PyG Converter:
    HeteroData(
        host = { x: tensor(N_hosts, F_host) },
        external_ip = { x: tensor(N_ext, F_ext) },
        (host, connects_to, host) = {
            edge_index: tensor(2, E),
            edge_attr: tensor(E, F_edge)
        },
        ...
    )
```

---

## 8. Expected Output

### Graph Statistics (after ingesting UNSW-NB15):
```
[INFO] Graph Snapshot [14:00-15:00]
[INFO] Nodes:
[INFO]   Host:       1,247
[INFO]   ExternalIP:   892
[INFO]   Service:       43
[INFO]   Domain:       156
[INFO] Edges:
[INFO]   CONNECTS_TO:    45,231
[INFO]   QUERIES_DNS:     3,456
[INFO]   RUNS_SERVICE:      127
[INFO] Memory: PyG HeteroData = 12.4 MB
[INFO] Neo4j: 2,338 nodes, 48,814 relationships written
```

### PyG HeteroData structure:
```python
HeteroData(
    host={ x=[1247, 8] },
    external_ip={ x=[892, 6] },
    service={ x=[43, 4] },
    (host, connects_to, host)={
        edge_index=[2, 45231],
        edge_attr=[45231, 12]
    },
    (host, queries_dns, domain)={
        edge_index=[2, 3456],
        edge_attr=[3456, 5]
    }
)
```

---

## 9. Edge Cases

| Edge Case | Handling |
|---|---|
| Same IP appears as source and destination | Allow self-loops, flag for analysis |
| Massive fan-out (one IP → 10K destinations) | Track degree, sample for GNN input |
| Window with no events | Skip window, log warning |
| Node features change across windows | Use latest features, store history |
| Memory overflow from large graphs | Enforce max nodes/edges per window, sample |
| Neo4j connection failure | Queue writes, retry with exponential backoff |

---

## 10. Testing Strategy

### Unit Tests
```
tests/unit/test_graph/
├── test_node_registry.py       # Node creation, deduplication
├── test_edge_constructor.py    # Event-to-edge mapping
├── test_temporal.py            # Window creation, sliding
├── test_pyg_converter.py       # HeteroData structure validation
└── test_feature_engineering.py # Feature extraction correctness
```

### Key test cases:
1. Node registry deduplicates IPs correctly
2. Internal vs external IP classification works
3. Edge features have correct dimensions
4. Temporal windows overlap correctly
5. PyG HeteroData has valid edge_index (no out-of-bounds)
6. Empty event list produces empty graph (no crash)

### Integration Test:
```python
def test_end_to_end_graph_construction():
    events = batch_ingest("tests/fixtures/sample_unsw.csv")
    graph = GraphConstructor().build(events, window_hours=1)
    assert isinstance(graph, HeteroData)
    assert graph['host'].x.shape[0] > 0
    assert graph['host', 'connects_to', 'host'].edge_index.shape[0] == 2
```

---

## 11. Memory Budget

For RTX 3050 (6GB), graph construction stays in CPU RAM. Only PyG tensors move to GPU during model training.

| Component | Memory | Location |
|---|---|---|
| Node Registry | ~50 MB | CPU RAM |
| Edge lists | ~200 MB | CPU RAM |
| PyG HeteroData (1 window) | ~50 MB | CPU RAM → GPU on demand |
| Neo4j connection | ~10 MB | CPU RAM |

---

## 12. Definition of Done

- [ ] Node registry correctly creates and deduplicates all node types
- [ ] Edge constructor maps all event types to correct edge types
- [ ] Temporal windowing produces correct overlapping snapshots
- [ ] PyG HeteroData has valid structure (no tensor shape mismatches)
- [ ] Neo4j writer persists graph correctly (verify via Neo4j Browser)
- [ ] Graph stats printed after each ingestion
- [ ] Integration test: CSV → UnifiedEvents → HeteroData works end-to-end
- [ ] All unit tests pass
- [ ] Memory usage stays under 2GB CPU RAM for UNSW-NB15
