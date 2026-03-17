# GraphRL-Sec — Complete Project Explanation (English)
### Every file, every code decision, every bug — explained so a 5-year-old can understand

---

# PART 0 — WHY DOES THIS PROJECT EXIST?

## The Real-World Problem (From the Dissertation Proposal)

Imagine a huge company — a bank, a hospital, a government agency. It has thousands of computers. Every single day, **10,000+ security alerts** fire.

Now think: how many alerts can one security analyst actually check? Maybe 100–200. The remaining 9,800? **They get ignored.**

And hackers know this. They deliberately generate so much noise that their real attack drowns in it.

**Numbers that should shock you:**
- Cybercrime will cost the world **$10.5 Trillion** annually by 2025
- **3.5 million** cybersecurity jobs are unfilled — there simply aren't enough people
- SOC analysts spend **70% of their time** chasing false alarms
- False positive rate in traditional systems: **80%+**

### What was wrong with old systems?

```
OLD SYSTEM (Rule-Based IDS):
  Rule: "If someone sends more than 1000 packets in 1 minute → alarm"

  Problem 1: Hacker sends 999 packets → no alarm ❌
  Problem 2: Normal server also sometimes sends 1000 packets → false alarm ❌
  Problem 3: Multi-step attack (spread across 3 machines, done slowly) → never caught ❌
```

Old systems look at **individual events** in isolation. But attacks are **patterns** — sequences across multiple machines over time.

### Our solution:

```
GRAPHRL-SEC APPROACH:
  1. Think of the network as a MAP (Graph)
     "Who talks to whom? How often? When? With what volume?"

  2. Let AI learn what normal looks like (GNN — Graph Neural Network)
     "This pattern is normal... this one looks suspicious"

  3. Let AI make decisions autonomously (DRL — Deep Reinforcement Learning)
     "Escalate this alert, dismiss that one"

  4. Multiple organisations learn together (Federated Learning)
     "A new attack appeared here — tell everyone, without sharing the raw data"
```

---

# PART 1 — THE PROJECT BLUEPRINT (From Original Dissertation Document)

Our full project is an **MTech Dissertation** titled:
> **"GraphRL-Sec: Adaptive Cybersecurity Threat Intelligence System using GNN-Reinforced Deep Learning and Federated SOC Analytics"**

**Six core innovations:**

| Innovation | Simple Terms | Technical Terms |
|------------|-------------|-----------------|
| **1. Temporal Graph** | A time-aware map of the network | Sliding window heterogeneous graph |
| **2. T-HetGAT** | A smart attack detector | Temporal Heterogeneous Graph Attention Network |
| **3. DRL Triage** | An AI that decides which alerts matter | DQN with prioritized experience replay |
| **4. Self-Supervised Pre-training** | Learning patterns WITHOUT attack labels | GraphCL contrastive learning |
| **5. Federated Learning** | Multiple orgs learning together, privately | Flower + Opacus differential privacy |
| **6. Campaign Detection** | Finding the full story of an attack | Louvain community detection |

---

# PART 2 — WHAT WE'VE BUILT SO FAR

## Full project roadmap:

```
FULL PROJECT (22 Modules):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PHASE 1 — FOUNDATION
  Module 4:  Data Ingestion         ✅ COMPLETE
  Module 5:  Graph Construction     ✅ COMPLETE
  Module 6:  Neo4j Integration      ✅ COMPLETE

PHASE 2 — AI FOUNDATION
  Module 8:  Self-Supervised Pre-training  ✅ COMPLETE
  Module 9:  Node2Vec Baseline             ⬜ PENDING

PHASE 3 — DETECTION
  Module 11: T-HetGAT Detection    ⬜ PENDING
  Module 12: Benchmarking          ⬜ PENDING

PHASE 4 — AUTOMATION
  Module 14: SOC Environment       ⬜ PENDING
  Module 15: DRL Triage Agent      ⬜ PENDING

PHASE 5 — SCALE
  Module 17: Federated Learning    ⬜ PENDING
  Module 18: Campaign Detection    ⬜ PENDING

PHASE 6 — PRESENTATION
  Module 20: FastAPI Backend       ✅ COMPLETE
  Module 21: SOC Dashboard         ✅ COMPLETE
  Module 22: Integration Testing   ⬜ PENDING
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CURRENT STATUS: 6 modules complete (~30%)
```

---

# PART 3 — EVERY FILE EXPLAINED IN DEPTH

---

## 3.1 INFRASTRUCTURE — `docker-compose.yml`

**Why we created this file:** The project needs 7 different software services to run. Installing and configuring each one manually would take days and be error-prone. Docker lets us define all 7 in one file and start everything with a single command.

**Simple analogy:** Think of Docker Compose as a blueprint for a building with 7 rooms. Each room has a specific job. One command (`docker-compose up`) constructs all 7 rooms at once.

```
docker-compose up -d
→ Run this one command and all 7 services start automatically
```

**The 7 services and why each one exists:**

```
┌─────────────────────────────────────────────────────────────────┐
│ SERVICE 1: REDPANDA (Kafka-compatible)                          │
│ Port: 9092                                                      │
│                                                                 │
│ What it is: A message queue — like a post office for data       │
│                                                                 │
│ Why we need it: Our CSV files have 5+ million rows. We can't   │
│ load all 5M rows into RAM at once. Kafka acts as a buffer:     │
│ the producer reads rows at its own pace, the consumer          │
│ processes them at its own pace. Neither blocks the other.      │
│                                                                 │
│ Real analogy: Amazon's warehouse. A package arrives → stored   │
│ → the delivery driver picks it up when ready.                  │
│                                                                 │
│ Why Redpanda instead of real Kafka: Redpanda is fully Kafka-   │
│ compatible but runs as a single binary (no JVM, no ZooKeeper). │
│ Much simpler to run locally.                                    │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│ SERVICE 2: NEO4J                                                │
│ Ports: 7474 (web browser), 7687 (code connection)              │
│                                                                 │
│ What it is: A graph database                                    │
│                                                                 │
│ Why not PostgreSQL for this: Normal databases think in rows.   │
│ Our data IS a graph — "who is connected to whom". Neo4j is     │
│ designed specifically for graphs. Multi-hop traversal like      │
│ "find all paths within 3 hops of this suspicious IP" takes     │
│ milliseconds in Neo4j vs seconds in SQL.                       │
│                                                                 │
│ Real analogy: Facebook's friend network. "A → friends with B"  │
│ "B → friends with C" → "Is A connected to C in 2 steps?"      │
│ Neo4j answers this instantly. SQL would struggle.              │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│ SERVICE 3: POSTGRESQL                                           │
│ Port: 5432                                                      │
│                                                                 │
│ What it is: Traditional relational database (rows + columns)   │
│                                                                 │
│ Why we need it: Alerts, analyst feedback, user accounts —      │
│ this is simple tabular data. A normal database is the right    │
│ tool for this. Not everything needs to be a graph.             │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│ SERVICE 4: REDIS                                                │
│ Port: 6379                                                      │
│                                                                 │
│ What it is: An in-memory key-value store                        │
│                                                                 │
│ Why we need it: Neo4j queries take 200–500ms. If the           │
│ dashboard makes 10 API calls per second, that's 5 seconds of   │
│ Neo4j queries per second — it would overload. Redis caches     │
│ results for 60 seconds. Next request → served from Redis       │
│ in <1ms instead of 500ms. 500× speedup.                       │
│                                                                 │
│ Real analogy: A calculator's display. The last answer stays    │
│ on screen — you don't have to recalculate every time.          │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│ SERVICE 5: PROMETHEUS                                           │
│ Port: 9090                                                      │
│                                                                 │
│ What it is: A metrics collection system                         │
│                                                                 │
│ Why we need it: To know if the system is healthy. How much     │
│ CPU? How much memory? How fast are API responses? Prometheus   │
│ collects these numbers every 15 seconds.                       │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│ SERVICE 6: GRAFANA                                              │
│ Port: 3001                                                      │
│                                                                 │
│ What it is: A monitoring dashboard                              │
│                                                                 │
│ Why we need it: Turns Prometheus numbers into beautiful         │
│ graphs. Think of it as a health report card for the system.    │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│ SERVICE 7: REDPANDA CONSOLE                                     │
│ Port: 8080                                                      │
│                                                                 │
│ What it is: A web UI for browsing Kafka topics                  │
│                                                                 │
│ Why we need it: During development, we needed to visually      │
│ confirm that events were being published to Kafka correctly.   │
│ Open browser → see messages flowing in real time.              │
└─────────────────────────────────────────────────────────────────┘
```

---

## 3.2 DATA INGESTION — `src/ingestion/`

**Why this folder exists:** The original dissertation specified two datasets — UNSW-NB15 and CICIDS2017. Both are CSV files. Before we can do any graph work, we need to: (1) read the CSVs, (2) clean and validate each row, (3) convert to a unified format, (4) stream through Kafka. This folder does all four.

---

### File: `src/ingestion/schemas.py`

**Why we created this:** UNSW-NB15 and CICIDS2017 have completely different column structures. Without a unified schema, every downstream component would need to know "is this UNSW data or CICIDS data?" — making code messy and fragile.

**Simple analogy:** Two countries measure things differently — India uses litres, America uses gallons. Create a universal unit — millilitres — and convert everything to it. Then the rest of the code only ever sees millilitres.

**The `UnifiedEvent` dataclass:**
```python
@dataclass
class UnifiedEvent:
    timestamp:      datetime        # When did this happen?
    event_type:     EventType       # What type? (NETWORK_FLOW, AUTH, DNS...)
    source:         SourceInfo      # Who sent it? (IP + port)
    destination:    DestinationInfo # Who received it? (IP + port)
    network:        NetworkInfo     # How? (protocol, bytes, packets, duration)
    metadata:       EventMetadata   # Was it an attack? What type?
    dataset_source: DatasetSource   # CICIDS2017 or UNSW_NB15
```

**The `AttackLabel` enum — why enum instead of plain strings:**
```python
class AttackLabel(str, Enum):
    BENIGN       = "benign"
    DDOS         = "ddos"
    PORT_SCAN    = "port_scan"
    SQL_INJECTION = "sql_injection"
    BOT          = "bot"
    # ... 30+ attack types

# Why enum: If we used plain strings, a typo "DDoS" vs "ddos" vs "DDOS"
# would be treated as 3 different attack types. With an enum, there is
# exactly one canonical value: AttackLabel.DDOS. The Python type checker
# catches any spelling mistakes at write-time, not runtime.
```

---

### File: `src/ingestion/parsers/unsw.py`

**Why we created this:** UNSW-NB15 CSV files have **no header row**. The first line is raw data, not column names. A special parser was needed that knows the column order by memory.

**Simple analogy:** Someone hands you a list with no labels:
```
192.168.1.1, 8.8.8.8, 80, TCP, 1024, 1
```
You have to memorise: "1st = source IP, 2nd = dest IP, 3rd = port..."

**How we solved it:**
```python
_UNSW_HEADERS = [
    "srcip",     # Column 1  = source IP address
    "sport",     # Column 2  = source port
    "dstip",     # Column 3  = destination IP
    "dsport",    # Column 4  = destination port
    "proto",     # Column 5  = protocol (TCP/UDP/etc)
    # ... 49 columns total, hardcoded in order
]

def _file_has_header(filepath: Path) -> bool:
    # Read the first line
    # If it contains "srcip" (a column name) → has header, skip it
    # If it contains "192.168." (an IP address) → no header, read from line 1
```

**Bug we fixed:** The initial code assumed every file had a header. The UNSW files don't. Result: the entire data was shifted by one column — every value was assigned to the wrong field. Fixed by adding the `_file_has_header()` detection.

---

### File: `src/ingestion/parsers/cicids.py`

**Why we created this:** CICIDS2017 has a completely different format from UNSW. Its timestamps, column names, and label encodings are all different. A separate parser keeps concerns separated.

**Critical version decision:**
```
CICIDS2017 has two releases:
  1. MachineLearningCSV      → Source IP and Dest IP columns STRIPPED ❌
  2. GeneratedLabelledFlows  → Source IP and Dest IP PRESERVED ✅

We need the second version. Without source/destination IPs
we cannot build a graph — we don't know who talked to whom.
```

**Timestamp parsing — why we had to be explicit:**
```python
def _parse_cicids_timestamp(ts_string: str) -> datetime:
    # CICIDS uses DD/MM/YYYY HH:MM:SS format
    # Input:  "03/07/2017 10:23:45"
    # Output: datetime(2017, 7, 3, 10, 23, 45)

    # Why not use dateutil.parse() (auto-detection)?
    # "03/07/2017" could be interpreted as March 7 OR July 3.
    # We hardcode the format to eliminate ambiguity.
    return datetime.strptime(ts_string, "%d/%m/%Y %H:%M:%S")
```

**Windows encoding bug we fixed:**
```python
# CICIDS files were created on Windows.
# The em-dash character (–) in "Web Attack – Sql Injection"
# got corrupted on different machines to different byte sequences.

_CICIDS_LABEL_MAP = {
    "Web Attack \x96 Sql Injection": AttackLabel.SQL_INJECTION,  # Windows-1252
    "Web Attack ? Sql Injection":    AttackLabel.SQL_INJECTION,  # Corruption
    "Web Attack \u2013 Sql Injection": AttackLabel.SQL_INJECTION, # Unicode
    "Web Attack – Sql Injection":    AttackLabel.SQL_INJECTION,  # UTF-8
}
# All four variants map to the same canonical label.
```

---

### File: `src/ingestion/normalizer.py`

**Why we created this:** Even after parsing, raw data can be invalid. IPs can be malformed, timestamps can be null, ports can be out of range. We also needed to deduplicate — the same network flow sometimes appears in multiple CSV files.

**What the normalizer does:**
```python
class EventNormalizer:
    def normalize(self, raw_event: dict) -> UnifiedEvent | None:
        # 1. Validate source IP — is it a real IPv4 address?
        # 2. Validate destination IP
        # 3. Check port is within 0–65535
        # 4. Check timestamp is not None and is reasonable
        # 5. Deduplicate using SHA-256 fingerprint:
        #    fingerprint = sha256(src_ip + dst_ip + bytes + timestamp)
        #    If we've seen this fingerprint → return None (skip)
        # 6. Build and return UnifiedEvent
        # If anything is invalid → return None (skip this event)
```

**Why SHA-256 for deduplication:**
```
The same network flow can appear in overlapping CSV export windows.
To deduplicate without storing every event in memory:

fingerprint = SHA-256( src_ip + "→" + dst_ip + ":" + bytes + "@" + timestamp )

This is a 256-bit hash. The probability of two different events
producing the same hash is astronomically small (2^-256).
We store the hash (32 bytes) instead of the full event (hundreds of bytes).
Memory stays bounded while deduplication is near-perfect.
```

---

### File: `src/ingestion/producer.py`

**Why we created this:** We needed to stream 5+ million events into Kafka. A naive implementation would blast the broker at maximum speed — potentially crashing it. We needed controlled, reliable delivery with confirmation.

**Token Bucket Rate Limiter:**
```python
class _TokenBucket:
    # Think of a bucket that holds coins (tokens).
    # Every second, N new coins are added (the "rate").
    # To send one message, you spend one coin.
    # If the bucket is empty → wait until a coin appears.
    # This caps the message rate regardless of CSV reading speed.

    def __init__(self, rate: float, capacity: float):
        self._tokens    = capacity   # Start full
        self._rate      = rate       # Tokens per second
        self._last_time = time.monotonic()

    def acquire(self):
        now = time.monotonic()
        elapsed = now - self._last_time
        self._tokens = min(self._capacity, self._tokens + elapsed * self._rate)
        self._last_time = now
        if self._tokens >= 1.0:
            self._tokens -= 1.0
            return True
        return False  # Caller should wait and retry
```

**Delivery confirmation callback:**
```python
def _on_delivery(err: KafkaError | None, msg: Message):
    if err is not None:
        # Message failed to reach Kafka → log for debugging
        log.error("delivery_failed", topic=msg.topic(), error=str(err))
    # On success: nothing to do. The at-least-once guarantee
    # means we commit offsets only after confirmed delivery.
```

---

### File: `src/ingestion/consumer.py`

**Why we created this:** After events flow through Kafka, we need something that reads them continuously, builds temporal graph windows from them, and saves `.pt` snapshot files.

**GraphConsumer class flow:**
```python
class GraphConsumer:
    def run(self):
        self._consumer.subscribe(["normalized-events"])

        while not self._stop_event.is_set():
            msg = self._consumer.poll(timeout=1.0)   # Get next message
            event = deserialize(msg.value())          # JSON → UnifiedEvent
            self._window_engine.push(event)           # Add to sliding window

            # When a window closes (time boundary passed):
            for result in self._window_engine.flush():
                snapshot = self._converter.convert(result)  # → HeteroData
                path = snapshot_dir / f"window_{self._seq:06d}.pt"
                torch.save(snapshot, path)
                self._seq += 1

            # After batch: commit offset to Kafka
            # ("I've processed everything up to message #X")
            self._consumer.commit(asynchronous=False)
```

**Critical bug we fixed — the snapshot counter:**
```python
# BUG: self._snapshot_seq was reset to 0 in each batch loop
# Result: window_000001.pt was overwritten every batch!
# Only the last batch's first window survived.

# FIX: Make _snapshot_seq an instance variable, never reset:
self._snapshot_seq: int = 0  # Set once in __init__, never touched again

# Now:
#   window_000001.pt → first window ever
#   window_000002.pt → second window ever
#   ...
#   window_017657.pt → last window ever
# None are ever overwritten. ✓
```

---

## 3.3 GRAPH CONSTRUCTION — `src/graph/`

**Why this folder exists:** The dissertation explicitly specified that the system must "model enterprise networks as heterogeneous temporal graphs." This folder translates the stream of network events (from Kafka) into PyTorch Geometric `HeteroData` objects — the format that GNNs consume.

---

### File: `src/graph/config.py`

**Why we created this:** All graph construction parameters need to be configurable without touching code. The window size, internal IP ranges, Neo4j connection details, memory limits — all in one place.

```python
class GraphConfig(BaseSettings):
    window_size_hours    : float = 1.0    # Each snapshot = 1 hour of traffic
    window_slide_minutes : int   = 15     # New window every 15 minutes
                                           # → 75% overlap between consecutive windows

    # Which IPs count as "internal" (inside the company)?
    internal_ip_prefixes : list[str] = [
        "192.168.", "10.", "172.16.", "172.17.", "172.18.",
        "172.19.", "172.20.", "172.21.", "172.22.", "172.23.",
        "172.24.", "172.25.", "172.26.", "172.27.", "172.28.",
        "172.29.", "172.30.", "172.31."
    ]  # RFC 1918 private address ranges

    # Safety caps — prevent OOM errors on 16GB RAM
    max_nodes_per_window : int = 50_000
    max_edges_per_window : int = 500_000

    # Neo4j connection
    neo4j_uri      : str = "bolt://localhost:7687"
    neo4j_password : str = "graphrlsec123"
```

---

### File: `src/graph/node_registry.py`

**Why we created this:** Within one time window, the same IP might appear hundreds of times. We don't want to create a new node for each appearance. The registry maintains a mapping from "IP address string" → "integer node ID". Each unique entity gets exactly one ID.

**5 node types — why these 5:**
```
HOST        → RFC 1918 internal IPs (192.168.x.x, 10.x.x.x)
              "Company-owned computers"

EXTERNAL_IP → Public internet IPs (8.8.8.8, 185.220.x.x)
              "The outside world"

SERVICE     → Port:Protocol pairs (80:TCP, 443:TCP, 22:TCP)
              "What service is being accessed" (HTTP, HTTPS, SSH)

DOMAIN      → DNS hostnames (google.com, suspicious-domain.xyz)
              "Named destinations" — separate from IPs for DNS analysis

USER        → Authentication accounts (admin@corp, user123)
              "Who logged in from where"

Why exactly 5: The dissertation specified these as the minimum
set that captures internal-vs-external relationships, service
access patterns, DNS-based C2 detection, and lateral movement.
```

**Thread safety — why `RLock`:**
```python
class NodeRegistry:
    def __init__(self):
        self._lock = threading.RLock()  # Reentrant lock
        self._nodes: dict[str, int] = {}

    def get_or_create_ip(self, ip: str) -> tuple[int, NodeType]:
        with self._lock:
            # Why lock: The consumer can process multiple events
            # concurrently. Without a lock, two threads could
            # simultaneously check "does 192.168.1.5 exist?" →
            # both see "no" → both create a node → duplicate!
            # RLock (reentrant) allows the same thread to acquire
            # the lock multiple times without deadlocking.
            key = f"ip:{ip}"
            if key not in self._nodes:
                self._nodes[key] = len(self._nodes)
            return self._nodes[key], self._classify_ip(ip)
```

---

### File: `src/graph/edge_constructor.py`

**Why we created this:** One network event can produce 1–4 edges in the graph depending on what type of event it is. This file encapsulates that logic cleanly.

**How 4 edge types are derived from one event:**
```
Event: 192.168.1.5 connects to 8.8.8.8 on port 80 via TCP

From this single event, these edges are created:

1. CONNECTS_TO:   192.168.1.5 (Host) → 8.8.8.8 (ExternalIP)
   "An IP-to-IP network connection"

2. USES_SERVICE:  192.168.1.5 (Host) → Service(80:TCP)
   "This computer accessed the HTTP service"

3. (If DNS query) RESOLVES_DOMAIN:    IP → Domain
   "This computer queried this DNS name"
   Note: UNSW/CICIDS don't carry DNS data, so this edge type
   produces 0 edges — this is expected, not an error.

4. (If auth event) AUTHENTICATED_AS: IP → User
   "Someone logged in from this machine"
   Note: Same — UNSW/CICIDS don't carry auth data.
```

**12-dimensional edge feature vector — what each number means:**
```python
edge_features = [
    timestamp_normalized,     # When: normalized to [0, 1] within window
    duration_normalized,      # How long: connection duration (normalized)
    bytes_sent_normalized,    # Data sent: how many bytes (normalized)
    bytes_recv_normalized,    # Data received: how many bytes (normalized)
    packets_sent,             # Packet count sent
    packets_recv,             # Packet count received
    proto_tcp,                # 1.0 if TCP protocol, else 0.0
    proto_udp,                # 1.0 if UDP protocol, else 0.0
    proto_icmp,               # 1.0 if ICMP (ping), else 0.0
    proto_other,              # 1.0 if any other protocol
    port_norm,                # Destination port / 65535 → [0, 1]
    is_attack,                # 1.0 if labelled as attack, else 0.0
]
```

---

### File: `src/graph/feature_engineering.py`

**Why we created this:** Neural networks only understand numbers. Every node needs to be represented as a vector of numbers. This file computes those feature vectors from raw statistics.

**Host/ExternalIP node — 8 features and why each one:**
```python
host_features = [
    degree_norm,         # Number of connections (normalized 0–1)
                         # High degree = very active = possibly scanning
    bytes_sent_norm,     # Total bytes sent (normalized)
                         # High = possibly data exfiltration
    bytes_recv_norm,     # Total bytes received (normalized)
                         # High = possibly downloading malware/tools
    packets_sent_norm,   # Packet count sent
    unique_dsts_norm,    # How many unique destinations? (normalized)
                         # Very high = port scan signature
    is_internal,         # 1.0 = inside company, 0.0 = internet
                         # Internal compromise is more dangerous
    attack_score,        # Fraction of events from this node that were attacks
                         # attack_score = attack_events / total_events
                         # 0.0 = all benign, 1.0 = all attacks
    last_seen_norm,      # When was this node last active? (normalized)
]
```

**`attack_score` — why this is the most important feature:**
```
Imagine a computer made 100 connections in this window.
40 of those connections were labelled as attacks.
attack_score = 40 / 100 = 0.4

This tells the model: "40% of this node's activity was malicious."
The model learns that nodes with high attack_score cluster
together in the embedding space — forming the "anomalous region."
```

**Service node — 4 features:**
```python
service_features = [
    port_norm,          # port / 65535 → [0, 1]
    is_well_known,      # 1.0 if port < 1024 (HTTP=80, SSH=22, DNS=53...)
    is_registered,      # 1.0 if 1024 ≤ port < 49152
    protocol_enc,       # 0=TCP, 1=UDP, 2=ICMP, 3=other (normalised)
]
```

---

### File: `src/graph/temporal.py`

**Why we created this:** Network traffic is continuous — packets arrive at any time. To build discrete graph snapshots, we need to bucket this continuous stream into overlapping time windows.

**Sliding window illustrated:**
```
Window size: 1 hour | Slide: 15 minutes

12:00 ─────────────────────────── 13:00    ← Window 1
      12:15 ─────────────────────────── 13:15  ← Window 2
            12:30 ─────────────────────────── 13:30  ← Window 3
                  12:45 ─────────────────────────── 13:45  ← Window 4

Overlap: 45 minutes (75%)

Why overlap: If an attack starts at 12:50 and ends at 13:10,
  Window 1 only captures half of it — the signature may be incomplete.
  Window 2 captures the full 20-minute attack pattern.
  The model gets the chance to see complete attack subgraphs.
```

**Why 1-hour windows, not the dissertation's suggested 24-72 hours:**
The dissertation suggested 24–72 hour windows for real production data.
With academic datasets (limited time range), 1-hour windows produce
more distinct snapshots (17,657 vs ~100) — more training data.

**`SlidingWindowEngine` logic:**
```python
class SlidingWindowEngine:
    def push(self, event: UnifiedEvent):
        # Add event to all currently open windows
        for window in self._active_windows:
            if window.start <= event.timestamp < window.end:
                window.add_event(event)

        # Open a new window if it's time
        if event.timestamp >= self._next_window_start:
            self._open_new_window(event.timestamp)

    def flush(self) -> list[WindowResult]:
        # Return and close windows whose end time has passed
        closed = [w for w in self._active_windows if w.is_closed]
        self._active_windows = [w for w in self._active_windows if not w.is_closed]
        return closed
```

---

### File: `src/graph/pyg_converter.py`

**Why we created this:** Our `WindowResult` is a Python object with dictionaries and lists. The GNN model needs `torch_geometric.data.HeteroData` — a PyTorch tensor-based format. This file bridges the gap.

**The conversion:**
```python
def convert(self, result: WindowResult) -> HeteroData:
    data = HeteroData()

    # Node features — each node type gets its own tensor
    data['Host'].x         = torch.FloatTensor(host_features)        # shape: (N_hosts, 8)
    data['ExternalIP'].x   = torch.FloatTensor(ext_ip_features)      # shape: (N_ext, 8)
    data['Service'].x      = torch.FloatTensor(service_features)     # shape: (N_svc, 4)
    data['Domain'].x       = torch.FloatTensor(domain_features)      # shape: (N_dom, 1)
    data['User'].x         = torch.FloatTensor(user_features)        # shape: (N_usr, 1)

    # Edge connectivity — which nodes are connected
    # edge_index = tensor of shape (2, num_edges)
    # edge_index[0] = source node indices
    # edge_index[1] = destination node indices
    data[('Host', 'CONNECTS_TO', 'ExternalIP')].edge_index = host_to_ext_edges
    data[('Host', 'USES_SERVICE', 'Service')].edge_index   = host_to_svc_edges
    # etc.

    # Metadata for Neo4j import
    data.window_id = result.window.window_id
    data.start_ts  = result.window.start.isoformat()
    data.end_ts    = result.window.end.isoformat()

    return data
    # → saved as data/graphs/window_000001.pt via torch.save()
```

**Why `.pt` format:** PyTorch's native binary format. `torch.save()` and `torch.load()` in 1 line each. Fast I/O. Preserves all tensor types and metadata. Much faster than JSON or CSV for training.

---

### File: `src/graph/neo4j_writer.py`

**Why we created this:** The `.pt` files give us a local ML-ready format. But for the SOC dashboard to query the graph interactively, we need the data in Neo4j. This file writes each `WindowResult` to Neo4j using MERGE operations.

**Why MERGE (not INSERT):**
```cypher
-- INSERT approach (WRONG for us):
CREATE (h:Host {entity_key: $key, ip: $ip})
-- Problem: If this host appeared in window 1 AND window 2,
-- we'd get 2 duplicate Host nodes.

-- MERGE approach (our way):
MERGE (h:Host {entity_key: $key})
SET h += {ip: $ip, attack_score: $score, window_id: $wid}
-- MERGE = "create if not exists, update if exists"
-- 100% idempotent — safe to replay from Kafka
-- Result: exactly 1 Host node per unique IP, ever.
```

**Why batch writes:**
```python
# Slow (1 database call per node):
for node in nodes:
    neo4j.run("MERGE (n:Host {ip: $ip})", ip=node.ip)
# 1000 nodes = 1000 round-trips = ~500ms

# Fast (1 database call for all nodes):
neo4j.run(
    "UNWIND $batch AS row MERGE (n:Host {ip: row.ip}) SET n += row",
    batch=nodes_as_list_of_dicts
)
# 1000 nodes = 1 round-trip = ~5ms → 100× faster ✓
```

---

### File: `src/graph/neo4j_schema.py`

**Why we created this:** Before importing any data, Neo4j needs constraints (to prevent duplicates) and indexes (to make queries fast). Running schema setup once, separately from data import, is cleaner.

**Constraints — what they do:**
```cypher
CREATE CONSTRAINT FOR (n:Host) REQUIRE n.entity_key IS UNIQUE
-- Enforces: no two Host nodes can have the same entity_key.
-- This is our duplicate prevention at the database level.
-- If a MERGE would create a duplicate, Neo4j throws a
-- ConstraintViolation instead of silently creating a duplicate.
```

**Indexes — why they matter:**
```cypher
CREATE INDEX FOR (n:Host) ON (n.ip)
-- Without index: To find Host with ip='192.168.1.5',
--   Neo4j scans ALL nodes → O(N) scan → slow with 124K nodes.
-- With index: Hash/B-tree lookup → O(log N) → instant.
-- 1000× speedup for the most common query type.
```

---

### File: `src/graph/neo4j_queries.py`

**Why we created this:** All Cypher queries used by the API are in one place. This makes it easy to tune queries, add EXPLAIN plans, and prevents SQL/Cypher injection by always using parameterised queries.

**5 main query functions:**
```python
# 1. Get the subgraph around a specific IP (N hops)
def get_neighborhood(self, ip: str, hops: int = 2):
    # "Show me everything connected to 192.168.1.5 within 2 steps"
    # Used by: Graph Explorer page (click a node)

# 2. Most active nodes
def get_top_communicators(self, limit: int = 20):
    # "Which IPs made the most outbound connections?"
    # Used by: Dashboard bar chart, Analytics page

# 3. Suspicious connections (high attack_score)
def get_anomalous_paths(self, threshold: float = 0.5, limit: int = 1000):
    # "Find connections where source or dest has attack_score ≥ 0.5"
    # Used by: Alerts page, Dashboard alerts table

# 4. Connections in a time range
def get_time_window_edges(self, min_window: int, max_window: int):
    # "Show connections that happened between window 100 and 200"
    # Used by: Graph Explorer time slider

# 5. Database statistics summary
def get_graph_stats(self):
    # "How many nodes of each type? How many edges of each type?"
    # Used by: Dashboard KPI cards, WebSocket streaming
```

**Why parameterised queries (security critical):**
```python
# DANGEROUS (Cypher injection possible):
query = f"MATCH (n:Host {{ip: '{user_input}'}}) RETURN n"
# If user_input = "'}) RETURN 1 //"  → query logic is hijacked!

# SAFE (our approach — always):
query  = "MATCH (n:Host {ip: $ip}) RETURN n"
params = {"ip": user_input}
session.run(query, params)
# Neo4j treats $ip as a literal string parameter, never as query syntax.
# Injection is structurally impossible. ✓
```

**Cypher bug we fixed:**
```cypher
-- BROKEN: ORDER BY after RETURN DISTINCT
MATCH (src)-[r:CONNECTS_TO]->(dst)
WHERE src.attack_score >= $threshold
RETURN DISTINCT src.entity_key AS src_key
ORDER BY src.attack_score DESC  -- ERROR: src not in scope after RETURN

-- FIXED: ORDER BY before RETURN using WITH
MATCH (src)-[r:CONNECTS_TO]->(dst)
WHERE src.attack_score >= $threshold OR dst.attack_score >= $threshold
WITH src, dst, r
ORDER BY src.attack_score DESC  -- ← ORDER BY while src is still in scope
RETURN DISTINCT
    src.entity_key AS src_key,
    dst.entity_key AS dst_key,
    type(r) AS rel_type,
    properties(r) AS props
LIMIT $limit
```

---

## 3.4 SELF-SUPERVISED PRE-TRAINING — `src/models/pretrain/`

**Why this folder exists:** Phase 2 of the dissertation is "Self-Supervised Pre-training." The key idea: we have 17,657 graph snapshots but only 20–30% have attack labels. Traditional supervised learning wastes the 70% unlabelled data. Self-supervised learning uses ALL of it — it creates its own training signal from the graph structure itself.

---

### File: `src/models/pretrain/config.py`

**Why we created this:** All training hyperparameters in one place, loadable from `.env` file. No hardcoding throughout the codebase.

```python
class PretrainConfig(BaseSettings):
    hidden_dim              : int   = 128    # GNN embedding size
    projection_dim          : int   = 64     # Contrastive loss projection size
    num_layers              : int   = 2      # Number of message-passing layers
    learning_rate           : float = 1e-3   # AdamW learning rate
    batch_size              : int   = 4      # Graphs per mini-batch

    # Why batch_size=4 specifically:
    # RTX 3050 = 4GB VRAM
    # One forward pass for one graph ≈ 200MB activations
    # 4 graphs × 200MB = 800MB + model weights (~100MB) = ~900MB total
    # That's safe under 4GB. batch_size=8 would cause OOM.

    num_epochs              : int   = 100    # Max epochs (early stopping will trigger first)
    early_stopping_patience : int   = 10     # Stop if no improvement for 10 epochs
    weight_decay            : float = 1e-5   # L2 regularisation
    grad_clip               : float = 1.0    # Clip gradients at L2 norm 1.0
    temperature             : float = 0.5    # NT-Xent temperature
    aug_feature_mask_ratio  : float = 0.20   # Mask 20% of node features
    aug_edge_drop_ratio     : float = 0.20   # Drop 20% of edges
    mixed_precision         : bool  = True   # FP16 AMP (halves VRAM usage)
    device                  : str   = "cuda" # GPU preferred
```

---

### File: `src/models/pretrain/encoder.py`

**Why we created this:** This is the project's AI brain — the `HeteroGraphEncoder`. It takes a heterogeneous graph as input and outputs a 128-dimensional embedding vector for every node. Nodes that behave similarly will have similar embedding vectors.

**Architecture — step by step:**

```
STEP 1: Input Projection (LazyLinear per node type)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Different node types have different feature sizes:
  Host:       8 features → need to project to 128
  ExternalIP: 8 features → need to project to 128
  Service:    4 features → need to project to 128

Why LazyLinear (not Linear):
  nn.Linear(8, 128)     → hardcodes input_dim=8 at definition time
  nn.LazyLinear(128)    → infers input_dim on first forward pass

  Benefit: If we add a new node type with 12 features tomorrow,
  we don't need to change the encoder code — LazyLinear adapts.

STEP 2: Message Passing — SAGEConv × 2 layers (via HeteroConv)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Simple analogy: Information spreading through a social network.
  Each person asks their friends "what do you know?"
  Combines their own knowledge with what friends shared.
  After Round 1: knows what immediate neighbours know.
  After Round 2: knows what 2-hop neighbours know.

Mathematically (GraphSAGE):
  h_v(new) = W · CONCAT( h_v,  MEAN(h_u for all u∈N(v)) )

Why SAGEConv (not GAT, not GCN):
  GCN:  normalises by degree — distorts features in dense graphs
  GAT:  attention weights — more parameters, more memory, slower
  SAGE: simple, inductive (works on new graphs), memory-efficient

Why HeteroConv wrapper:
  Our graph has 5 node types and 4 edge types.
  HeteroConv applies a separate SAGEConv for each edge type,
  then sums the resulting messages at each node.
  This is the standard approach for heterogeneous GNNs.

valid_edges filter — why it's essential:
  Some windows have no DNS queries → no Domain nodes →
  no RESOLVES_DOMAIN edges. If SAGEConv tries to aggregate
  messages over a non-existent edge type → "NoneType has no
  attribute 'dim'" runtime error.
  Fix: filter edge_types to only those present in the current graph.

STEP 3: BatchNorm1d + ReLU (per node type, per layer)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
BatchNorm: Normalise activations to mean=0, std=1 across the batch.
           Prevents gradient explosion/vanishing.
ReLU:      Set all negative values to 0. Adds non-linearity —
           without it, the whole network is just a linear transform.

STEP 4: Projection Head (2-layer MLP)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
128 → Linear → 128 → ReLU → Linear → 64 → L2-normalise

Why a separate projection head (key insight from SimCLR paper):
  The encoder (128-dim) is what we keep for downstream tasks.
  The projection head (64-dim) is used only during contrastive training.
  After training, we discard the projection head and use only the encoder.

  Why: The contrastive loss pushes the projection space to be
  invariant to augmentations. This invariance is useful for the
  contrastive loss objective but is NOT useful for anomaly detection
  (where we WANT to be sensitive to subtle differences).
  The encoder layer sits "before" this over-invariance kicks in.
  Removing the head at inference time recovers sensitivity.
```

---

### File: `src/models/pretrain/augmentation.py`

**Why we created this:** GraphCL (Graph Contrastive Learning) requires creating two "views" of the same graph — the same graph but slightly perturbed. The model is trained to produce similar embeddings for both views. This forces it to learn representations that are robust to noise.

```python
class GraphAugmentor:
    def __call__(self, graph: HeteroData) -> HeteroData:
        augmented = graph.clone()  # Deep copy — don't modify original

        # AUGMENTATION 1: Feature Masking
        # Randomly zero out 20% of node feature values
        for node_type in graph.node_types:
            N, D = graph[node_type].x.shape
            mask = torch.rand(N, D, device=device) < self._feat_ratio  # 20%
            augmented[node_type].x[mask] = 0.0

        # AUGMENTATION 2: Edge Dropping
        # Randomly remove 20% of edges
        for edge_type in graph.edge_types:
            N_edges = graph[edge_type].edge_index.shape[1]
            keep_mask = torch.rand(N_edges, device=device) > self._edge_ratio
            augmented[edge_type].edge_index = graph[edge_type].edge_index[:, keep_mask]
            if hasattr(graph[edge_type], 'edge_attr'):
                augmented[edge_type].edge_attr = graph[edge_type].edge_attr[keep_mask]

        return augmented
```

**Why these two augmentations:**
- **Feature masking** simulates sensor noise — in real networks, log collectors miss data.
- **Edge dropping** simulates packet loss — real networks don't capture 100% of connections.

The model must learn to produce the same embedding for "noisy version" and "cleaner version" of the same graph window. This forces it to focus on structural patterns (which remain after noise) rather than memorising exact feature values.

---

### File: `src/models/pretrain/contrastive.py`

**Why we created this:** NT-Xent (Normalised Temperature-scaled Cross Entropy) is the loss function from the SimCLR paper. It mathematically defines "push positive pairs together, push negative pairs apart."

**NT-Xent loss — explained like you're 5:**
```
Imagine 6 photos are laid out:
  A1, A2 (two photos of person A)
  B1, B2 (two photos of person B)
  C1, C2 (two photos of person C)

The loss function says:
  "A1 and A2 MUST be close together (they're the same person)"
  "A1 and B1 MUST be far apart (they're different people)"

In graph terms:
  node_5(view1) and node_5(view2) → same node, must be close
  node_5(view1) and node_7(view2) → different nodes, must be far
```

**Mathematical implementation:**
```python
def _nt_xent(z1: Tensor, z2: Tensor, temperature: float = 0.5) -> Tensor:
    n = z1.shape[0]  # Number of nodes

    # Step 1: Stack all projections together
    z = torch.cat([z1, z2], dim=0)  # shape: (2N, 64)

    # Step 2: Compute all pairwise cosine similarities
    # (vectors are L2-normalised, so dot product = cosine similarity)
    sim = torch.mm(z, z.t()) / temperature  # shape: (2N, 2N)

    # Step 3: Mask out self-similarity (diagonal = 1.0 = always "similar")
    sim.fill_diagonal_(float('-inf'))

    # Step 4: Labels — the positive for node i in z1 is node i in z2
    # z1 has indices  0,  1, ..., N-1
    # z2 has indices  N, N+1, ..., 2N-1
    # So label[i] = i + N  (the corresponding node in z2)
    # And label[i+N] = i   (the corresponding node in z1)
    labels = torch.cat([torch.arange(n) + n, torch.arange(n)]).to(z.device)

    # Step 5: Cross-entropy
    # For each node, "which index has my positive pair?"
    # The loss is low when the model assigns high similarity to
    # the correct positive pair and low similarity to all negatives.
    return F.cross_entropy(sim, labels)
```

---

### File: `src/models/pretrain/trainer.py`

**Why we created this:** The training loop orchestrates everything — loading data, running epochs, computing loss, updating weights, saving checkpoints, and early stopping.

**Full training flow:**
```python
class Trainer:
    def train(self):
        # Load all 17,657 .pt snapshot files
        snapshots = sorted(graphs_dir.glob("window_*.pt"))
        train_set, val_set = train_val_split(snapshots, val_ratio=0.1)
        # Result: 15,891 train + 1,765 validation

        for epoch in range(1, num_epochs + 1):
            # Run one epoch of training
            train_loss = self._run_epoch(train_set, training=True)

            # Validate (no gradient computation)
            val_loss = self._run_epoch(val_set, training=False)

            # Update learning rate schedule
            scheduler.step()

            # Save checkpoint
            is_best = checkpoint_manager.save(epoch, val_loss)

            # Check early stopping
            if patience_counter >= 10:
                break  # No improvement for 10 epochs → stop
```

**Mini-batching — why it was necessary:**
```python
# BEFORE (slow — 1 graph at a time):
for graph_a, graph_b in pairs:          # 15,891 iterations
    view1 = augmentor(graph_a)
    proj1 = model.project(view1)        # GPU processes 1 graph
    # GPU utilisation: 10–20% (most time spent loading from disk)

# AFTER (fast — 4 graphs at a time):
for start in range(0, len(pairs), batch_size):   # 15,891/4 ≈ 3973 iterations
    mini = pairs[start : start + batch_size]     # 4 pairs

    views_a, views_b = [], []
    for graph, _ in mini:
        views_a.append(augmentor(graph))   # view1 of graph
        views_b.append(augmentor(graph))   # view2 of same graph (!)

    # Merge 4 separate HeteroData into one big batched HeteroData
    batch_a = Batch.from_data_list(views_a)
    batch_b = Batch.from_data_list(views_b)

    proj1 = model.project(batch_a)   # GPU processes 4 graphs at once
    # GPU utilisation: 60–80% → ~3–4× speedup
```

**The val_loss=0.0 bug — most critical bug in the project:**
```python
# WRONG (original code):
for graph_a, graph_b in pairs:
    view1 = augmentor(graph_a)   # Window 5000 (e.g. 45 Host nodes)
    view2 = augmentor(graph_b)   # Window 5001 (e.g. 52 Host nodes)
    # collect_node_projections checks: z1.shape[0] == z2.shape[0]?
    # 45 ≠ 52 → skip this pair → returns None
    # If all pairs in a batch are skipped:
    #   loss = sum([]) / 0 = 0.0 / 0 = 0.0

# CORRECT (GraphCL proper approach):
for graph_a, _ in pairs:
    view1 = augmentor(graph_a)   # View 1 of window 5000 → 45 Host nodes
    view2 = augmentor(graph_a)   # View 2 of window 5000 → 45 Host nodes (!)
    # Same source graph → same number of nodes per type → guaranteed match ✓
```

**Double optimizer.step() bug:**
```python
# WRONG (called twice — double gradient update):
train_loss = self._run_epoch(...)  # optimizer.step() called inside here
optimizer.step()                   # ← accidentally called again outside!
scheduler.step()

# Consequences: gradients applied twice per step → 2× learning rate
# effectively. Unstable training, loss spikes.

# CORRECT:
train_loss = self._run_epoch(...)  # optimizer.step() happens inside
scheduler.step()                   # ← only this outside. optimizer.step() removed. ✓
```

**Mixed Precision (FP16) — why it matters on a 4GB GPU:**
```python
# Without FP16 (FP32):
#   Each float32 number = 4 bytes
#   Model weights (128-dim, 2 layers): ~200MB
#   Activations for 4 graphs: ~800MB
#   Gradients: ~200MB
#   Total: ~1.2GB → fits

# With more graphs or larger model → quickly runs out of 4GB

# With FP16 (Mixed Precision):
#   Forward pass uses float16 (2 bytes per number → half the VRAM)
#   GradScaler keeps gradients in float32 (prevents underflow)
#   Net result: activations use half VRAM → can fit 2× the data

scaler   = GradScaler("cuda", enabled=use_amp)    # Updated API (not torch.cuda.amp)
with autocast("cuda", enabled=use_amp):            # Updated API
    proj1, proj2 = model.project(batch_a), model.project(batch_b)
    loss = contrastive_loss(proj1, proj2)

scaler.scale(loss).backward()     # Scale loss to prevent FP16 underflow
scaler.step(optimizer)            # Unscale gradients, then step
scaler.update()                   # Update scaler for next iteration
```

---

### File: `src/models/pretrain/checkpoint.py`

**Why we created this:** Training takes ~2 hours. If the machine crashes at epoch 11, we don't want to restart from epoch 1. Checkpoints save the model state after every epoch and separately track the best model ever seen.

```python
class CheckpointManager:
    def save(self, model, optimizer, scheduler, epoch, val_loss) -> bool:
        state = {
            "model_state":     model.state_dict(),
            "optimizer_state": optimizer.state_dict(),
            "scheduler_state": scheduler.state_dict(),
            "epoch":           epoch,
            "val_loss":        val_loss,
            "config":          self._cfg.model_dump(mode="json"),  # ← bug fix!
        }

        # Always save "latest" checkpoint (for resume)
        torch.save(state, self._dir / "checkpoint_latest.pt")

        # Also save "best" checkpoint if this is the lowest val_loss ever
        if val_loss < self._best_val_loss:
            shutil.copy(latest_path, self._dir / "checkpoint_best.pt")
            self._best_val_loss = val_loss
            return True   # is_best = True
        return False

# Bug we fixed: model_dump(mode="json")
# model_dump() returns Python Path objects in config (e.g. graphs_dir=PosixPath(...))
# torch.save() with weights_only=True cannot serialise Path objects.
# mode="json" converts all Path objects to strings before saving.
# Without this fix: "TypeError: Object of type PosixPath is not JSON serialisable"
```

---

## 3.5 FASTAPI BACKEND — `src/api/`

**Why this folder exists:** The SOC dashboard (Next.js, runs in the browser) cannot directly connect to Neo4j. Browsers don't have the Neo4j Bolt driver. We need an HTTP REST API layer between the browser and the database. FastAPI is that layer.

---

### File: `src/api/main.py`

**Why we created this:** The FastAPI application entry point. Everything is registered here — routes, middleware (CORS), lifespan (connection pool management).

**Lifespan context manager:**
```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── SERVER STARTING ──
    service = Neo4jQueryService()    # Create Neo4j connection pool
    set_query_service(service)       # Register globally for routes to use
    log.info("neo4j_connected")

    yield  # ← Server runs here (handles all requests)

    # ── SERVER SHUTTING DOWN ──
    clear_query_service()
    service.close()                  # Release connection pool gracefully
    log.info("neo4j_disconnected")

# Why this pattern: If we don't close the connection pool on shutdown,
# Neo4j holds the connections open indefinitely → memory leak → crash
# after prolonged use. The lifespan pattern guarantees cleanup.
```

**CORS middleware — why it's essential:**
```python
app.add_middleware(CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # Next.js dev server
    allow_methods=["GET", "OPTIONS"],
    allow_headers=["*"],
)

# Why: Browsers enforce the Same-Origin Policy.
# Frontend at localhost:3000 making a fetch() to localhost:8000
# is considered a "cross-origin" request.
# Without CORS headers, the browser blocks the response.
# This middleware adds "Access-Control-Allow-Origin: http://localhost:3000"
# to every response → browser allows it. ✓
```

**WebSocket for live stats:**
```python
@app.websocket("/ws/graph-stats")
async def ws_graph_stats(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            stats = service.get_graph_stats()
            await websocket.send_json(stats.model_dump())
            await asyncio.sleep(5)   # Push update every 5 seconds
    except WebSocketDisconnect:
        pass  # Client closed the tab — clean exit

# Why WebSocket vs polling:
#   Polling: Frontend makes GET /api/stats every 5 seconds
#            → 5 extra HTTP connections per minute per user
#            → server must handle, CORS headers each time
#   WebSocket: One connection opens, server pushes every 5 seconds
#            → less overhead, true real-time feel in the dashboard
```

---

### File: `src/api/dependencies.py`

**Why we created this:** FastAPI's dependency injection system. Instead of importing the Neo4j service directly in every route file, we register it once and inject it where needed.

```python
_query_service: Neo4jQueryService | None = None

def set_query_service(svc: Neo4jQueryService) -> None:
    global _query_service
    _query_service = svc

def get_query_service() -> Neo4jQueryService:
    if _query_service is None:
        raise HTTPException(status_code=503, detail="Database unavailable")
    return _query_service

# Type alias for route function signatures:
QueryServiceDep = Annotated[Neo4jQueryService, Depends(get_query_service)]

# Usage in a route:
@router.get("/api/stats")
def get_stats(service: QueryServiceDep):  # ← FastAPI auto-injects this
    return service.get_graph_stats()

# Benefits:
# 1. All routes share the same connection pool (not creating new connections)
# 2. If Neo4j is down: auto 503 error before route logic runs
# 3. Testing: inject a mock service without changing route code
```

---

### Files: `src/api/routes/stats.py`, `graph.py`, `alerts.py`

**Why three separate route files:** Separation of concerns. Stats, graph queries, and alerts are different domains. Each file has its own router prefix, its own Pydantic response models.

**`stats.py` — what it serves:**
```
GET /api/stats
→ GraphStatsResponse:
  {
    host_count: 45231,
    external_ip_count: 32541,
    service_count: 28901,
    domain_count: 1842,
    user_count: 16253,
    connects_to_count: 2891234,
    uses_service_count: 1547821,
    resolves_domain_count: 0,        ← expected: UNSW/CICIDS have no DNS
    authenticated_as_count: 0,       ← expected: no auth events
    total_node_count: 124768,
    total_edge_count: 3028187,
  }

GET /api/stats/top-communicators?limit=20
→ [{ entity_key, node_label, outbound_count, unique_destinations }, ...]
```

**`alerts.py` — the derivation logic:**
```python
# There is NO alerts table in the database.
# Alerts are derived on-the-fly from anomalous paths.

def _derive_alerts(
    edges: list[AnomalousPathRow],
    threshold: float = 0.3,
) -> list[AlertResponse]:
    alerts = []
    for edge in edges:
        score = max(edge.src_score, edge.dst_score)

        # Score → Severity mapping
        if score >= 0.8:   severity = "critical"
        elif score >= 0.6: severity = "high"
        elif score >= 0.4: severity = "medium"
        else:              severity = "low"

        # Stable, deterministic ID — same edge always gets same ID
        # (important for the /api/alerts/{id} lookup to work)
        raw = f"{edge.src_key}|{edge.dst_key}|{edge.window_id}"
        alert_id = hashlib.sha256(raw.encode()).hexdigest()[:16]

        alerts.append(AlertResponse(
            id=alert_id,
            src_ip=edge.src_key,
            dst_ip=edge.dst_key,
            attack_score=score,
            severity=severity,
            ...
        ))
    return alerts

# Why no alerts table: We don't have a continuous detection model yet
# (T-HetGAT is future work). Our current alerts are simply the
# anomalous graph edges. Deriving them on-the-fly avoids having to
# maintain a stale alerts table that would need re-importing whenever
# we change the threshold.
```

---

### File: `src/api/run.py`

**Why we created this:** Provides the `python -m src.api.run` entry point. Configures uvicorn with the right host, port, reload settings, and log level.

```python
if __name__ == "__main__":
    uvicorn.run(
        "src.api.main:app",
        host="0.0.0.0",          # Accept connections from all interfaces
        port=8000,
        reload=True,             # Auto-restart when code changes (dev mode)
        log_level="info",
    )

# Why uvicorn: ASGI server required for async FastAPI.
# Why reload=True: During development, saves having to restart manually.
# Production would use reload=False with multiple workers.
```

---

## 3.6 FRONTEND — `frontend/src/`

**Why this folder exists:** The dissertation specified a "React-based SOC Dashboard." Security analysts need a visual interface — tables, interactive graphs, charts, and real-time data. A raw API is not usable by a non-programmer SOC analyst.

---

### File: `frontend/src/app/layout.tsx`

**Why we created this:** The root layout wraps every page. Defines the shared structure: dark background, sidebar navigation, top header, and the TanStack Query provider (so all pages can use `useQuery`).

```typescript
export default function RootLayout({ children }: { children: React.ReactNode }) {
    return (
        <html lang="en">
            <body className="bg-[#0d1117] text-[#e6edf3]">
                {/* #0d1117 = GitHub dark background */}
                {/* #e6edf3 = GitHub dark text colour */}
                <Providers>
                    <div className="flex h-screen overflow-hidden">
                        <Sidebar />           {/* Left navigation */}
                        <div className="flex-1 flex flex-col overflow-hidden">
                            <Header />        {/* Top bar */}
                            <main className="flex-1 overflow-auto p-6">
                                {children}    {/* Current page content */}
                            </main>
                        </div>
                    </div>
                    <Toaster position="bottom-right" />  {/* Toast notifications */}
                </Providers>
            </body>
        </html>
    )
}

// Why dark theme: The dissertation explicitly stated
// "Dark theme — SOC analysts work in low-light environments
// for extended periods. Dark UI reduces eye strain."
```

---

### File: `frontend/src/app/page.tsx` (Main Dashboard)

**Why we created this:** The first thing an analyst sees when they open the dashboard. Quick summary: how big is the graph? How many anomalies? Which IPs are most active?

**Layout:**
```
┌─────────────────────────────────────────────────────────┐
│  KPI Cards (4 boxes):                                   │
│  [ 124,768 Nodes ] [ 3M+ Edges ] [ X Anomalous ] [ IP ]│
├────────────────────────────┬────────────────────────────┤
│  Node Type Distribution    │  Top Communicators         │
│  (Donut chart)             │  (Horizontal bar chart)    │
│  Host/ExternalIP/Service/  │  Top 10 IPs by             │
│  Domain/User breakdown     │  outbound connections      │
├────────────────────────────┴────────────────────────────┤
│  Recent Alerts Table                                    │
│  Score | Severity | Src IP | Dst IP | Protocol | Label  │
│  0.95  | CRITICAL | ...    | ...    | TCP      | DDoS   │
└─────────────────────────────────────────────────────────┘
```

**Data fetching with TanStack Query:**
```typescript
// Each query has independent caching, loading state, and error handling
const { data: stats,  isLoading: statsLoading  } = useGraphStats()
const { data: topIPs, isLoading: topIPsLoading } = useTopCommunicators(10)
const { data: alerts, isLoading: alertsLoading } = useAlerts({ limit: 20 })
const { stats: liveStats, connected }             = useGraphStream() // WebSocket

// Why TanStack Query (not useState + useEffect):
//   With useState: need to manually handle loading, errors, caching, refetching
//   With TanStack Query: declare what you want, it handles everything
//   staleTime=30000 means cached data is reused for 30 seconds
//   → dashboard loads instantly from cache on re-visit
```

---

### File: `frontend/src/components/graph/NetworkGraph.tsx`

**Why we created this:** Analysts need to visually explore the network graph. See which IPs are connected, spot clusters of malicious activity, click a suspicious IP to see its neighbourhood.

**Why vis-network (not D3):**
```
D3.js:
  + Maximum flexibility and customisation
  - Requires writing force simulation from scratch
  - Hundreds of lines of code for basic graph rendering
  - Steep learning curve

vis-network:
  + Built specifically for network/graph visualisation
  + Force-directed layout out of the box (just pass nodes + edges)
  + Built-in zoom, pan, drag, hover, click events
  + Handles 1000+ nodes efficiently
  - Less customisable than D3
  → Perfect for our use case. Analyst can drag nodes, zoom in, click IPs.
```

**Why dynamic import with SSR disabled:**
```typescript
// In page.tsx:
const NetworkGraph = dynamic(
    () => import('@/components/graph/NetworkGraph'),
    { ssr: false }    // ← critical
)

// Why: vis-network uses browser DOM APIs (document.getElementById, window)
// Next.js Server-Side Rendering runs in Node.js, which has NO browser DOM.
// Without ssr:false → "document is not defined" error on server render.
// ssr:false tells Next.js: "only render this component in the browser."
```

**Node colours and what they mean:**
```typescript
const NODE_COLORS: Record<string, string> = {
    Host:       '#58a6ff',   // Blue  — internal trusted computer
    ExternalIP: '#f85149',   // Red   — external internet IP (potentially hostile)
    Service:    '#3fb950',   // Green — port/service (HTTP, SSH, etc.)
    Domain:     '#d29922',   // Orange — DNS domain name
    User:       '#bc8cff',   // Purple — authenticated user account
}

// Colour logic: GitHub dark theme palette.
// Red for ExternalIP because external IPs are the primary attack vector.
// Blue for internal hosts — they are "inside" and generally trusted.
// Size = proportional to event_count (busier nodes are bigger circles).
```

---

### Files: `frontend/src/hooks/`

**Why these files exist:** Custom hooks separate API-fetching logic from UI rendering. Every component just calls `useAlerts()` or `useGraphStats()` — it doesn't know or care about fetch URLs, error states, or caching.

**`useGraphStats.ts`:**
```typescript
export function useGraphStats() {
    return useQuery({
        queryKey: ['graph-stats'],
        queryFn:  () => apiClient.get<GraphStatsResponse>('/api/stats').then(r => r.data),
        staleTime:       30_000,   // Cache valid for 30 seconds
        refetchInterval: 30_000,   // Auto-refetch every 30 seconds
    })
}
// Usage: const { data, isLoading, error } = useGraphStats()
// isLoading → show skeleton placeholder
// error     → show error state
// data      → render KPI cards
```

**`useGraphStream.ts` (WebSocket real-time hook):**
```typescript
export function useGraphStream() {
    const [stats, setStats]       = useState<GraphStatsResponse | null>(null)
    const [connected, setConnected] = useState(false)

    useEffect(() => {
        let ws: WebSocket
        let retryDelay = 1000  // Start with 1 second, doubles each attempt

        function connect() {
            ws = new WebSocket('ws://localhost:8000/ws/graph-stats')

            ws.onopen = () => {
                setConnected(true)
                retryDelay = 1000  // Reset backoff on success
            }

            ws.onmessage = (event) => {
                setStats(JSON.parse(event.data))  // Update UI with live data
            }

            ws.onclose = ws.onerror = () => {
                setConnected(false)
                // Exponential backoff: 1s → 2s → 4s → 8s → max 30s
                setTimeout(connect, Math.min(retryDelay, 30_000))
                retryDelay *= 2
            }
        }

        connect()
        return () => ws?.close()  // Cleanup when component unmounts
    }, [])

    return { stats, connected }
}
```

---

### File: `frontend/src/lib/api.ts`

**Why we created this:** All API calls go through a single Axios instance with the base URL pre-configured. If the backend port ever changes, we change it in one place.

```typescript
import axios from 'axios'

export const apiClient = axios.create({
    baseURL: process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000',
    timeout: 10_000,   // 10 second timeout — don't hang the UI
    headers: { 'Content-Type': 'application/json' },
})

// Response interceptor — global error handling
apiClient.interceptors.response.use(
    (response) => response,
    (error) => {
        console.error('API error:', error.message)
        return Promise.reject(error)
    }
)
```

---

### File: `scripts/neo4j_import.py`

**Why we created this:** During normal consumer operation, graph construction and Neo4j writing happen together — which slows both down. The Neo4j import script replays the Kafka topic from the beginning using a dedicated consumer group (`neo4j-import-v1`) and does ONLY Neo4j writes, without saving `.pt` files.

```python
# How it works:
# 1. Connect to Kafka topic "normalized-events"
# 2. Use consumer group "neo4j-import-v1"
#    (fresh group = read from the very beginning of the topic)
# 3. For each completed window:
#    writer.write_window(result)  # MERGE all nodes and edges into Neo4j
# 4. Print live progress table:
#    Windows written : 20,137
#    Nodes merged    : 5,583,870
#    Edges merged    : 10,593,668
#    Elapsed         : 6,313s (1h 45min)
```

**Why a dedicated script (not part of the consumer):**
- Training reads `.pt` files from disk — heavy I/O.
- Neo4j import writes to the database — heavy network I/O.
- Running both simultaneously halves the throughput of each.
- Solution: run consumer to create `.pt` files first, then run `neo4j_import.py` separately overnight.

---

# PART 4 — THE TRAINING STORY (ALL 6 RUNS)

Every bug we hit, every fix we made:

```
RUN 1 — Very first attempt:
  Error: "RuntimeError: LazyLinear: input has wrong number of dims"
  Root cause: nn.Linear(-1, 128) is not supported in PyTorch ≥ 2.0
              Linear requires explicit input_dim at construction.
  Fix: Changed nn.Linear(-1, 128) → nn.LazyLinear(128)
       LazyLinear infers the dimension on the first forward pass.

RUN 2 — Second attempt:
  Error: "TypeError: Object of type PosixPath is not JSON serialisable"
  Root cause: checkpoint.py called model_dump() without mode="json"
              → Config Path objects can't be serialised by torch.save()
  Fix: Changed model_dump() → model_dump(mode="json")
      (converts Path objects to strings before saving)

RUN 3 — Third attempt:
  Error: "AttributeError: 'NoneType' object has no attribute 'dim'"
  Root cause: Some windows have no Domain/User nodes (UNSW has no DNS/auth data)
              → RESOLVES_DOMAIN edge type has no nodes → SAGEConv gets None input
  Fix: Added valid_edges filter in encoder.py:
      edge_types = [e for e in graph.edge_types if both endpoints exist in h_dict]

RUN 4 — Training finally starts!
  Epoch 1:  val_loss = 4.977 ✓ New best
  Epoch 2:  val_loss = 4.918 ✓ New best
  Epoch 3:  val_loss = 4.812 ✓ New best   ← best of all time
  Epoch 4:  val_loss = 4.929   (no improvement)
  ...
  Epoch 13: Early stopping triggered (10 epochs without improvement)
  Final best: val_loss = 4.812  ✓

RUN 5 — After code changes, rerun:
  Problem: val_loss reported as 0.0000 every epoch
  Root cause: Augmenting graph_a AND graph_b (two different windows)
              window_a might have 45 Host nodes, window_b might have 52
              collect_node_projections: shape mismatch → returns None
              valid_pairs = 0 → loss = sum([]) / 0 = 0.0
              The model was silently learning nothing.
  Fix: Augment graph_a TWICE (proper GraphCL approach):
      view1 = augmentor(graph_a)   ← view 1 of same graph
      view2 = augmentor(graph_a)   ← view 2 of same graph (not graph_b!)
  Also found: checkpoint_best.pt from earlier had val_loss=0.0
              Any real val_loss (6.97) > 0.0 → "not best" → early stop at epoch 11
  Fix: Delete stale checkpoint files, restart fresh.

RUN 6 — After GraphCL fix + stale checkpoint cleared:
  Epoch 1:  val_loss = 6.971  (higher than run 4, starting fresh)
  Epoch 4:  val_loss = 6.940 ✓ New best
  ...training continues... (this is the current active training run)
```

## Training hardware and results:

```
Hardware:    NVIDIA RTX 3050 4GB (laptop GPU)
VRAM used:   813 MB / 4096 MB (20% of VRAM — safe headroom)
Time/epoch:  ~9 minutes (mini-batch=4, mixed precision FP16)

Dataset:
  Input snapshots:  17,657 .pt files
  Train set:        15,891 (90%)
  Validation set:    1,765 (10%)

Best result (Run 4):
  Best val_loss:  4.812
  Best epoch:     3
  Total epochs:   13 (early stopped)
  Total time:     ~2 hours

Output:  models/pretrain/checkpoint_best.pt
```

---

# PART 5 — WHAT'S DONE, WHAT'S NEXT

## Completed modules (✅):

| # | Module | What We Built | Actual Numbers |
|---|--------|--------------|----------------|
| M4 | Data Ingestion | UNSW + CICIDS parsers, Kafka pipeline | 9GB raw data → 250M+ events |
| M5 | Graph Construction | Sliding windows → PyG HeteroData snapshots | 17,657 `.pt` files |
| M6 | Neo4j Integration | Full graph database with real-time queries | 124K nodes, 3M+ edges |
| M8 | Self-Supervised Pre-training | GNN encoder via GraphCL contrastive learning | val_loss=4.812 |
| M20 | FastAPI Backend | REST API + WebSocket streaming | 8 endpoints |
| M21 | SOC Dashboard | 4-page interactive Next.js dashboard | Real Neo4j data |

## Pending modules (⬜):

| # | Module | What Needs Building | Difficulty |
|---|--------|--------------------|-|
| M9  | Node2Vec Baseline | Traditional graph embedding for comparison | Medium |
| M11 | T-HetGAT Detection | Temporal Heterogeneous GAT for anomaly scoring (core model) | Hard |
| M12 | Benchmarking | T-HetGAT vs baselines (AUROC, F1, FPR) | Medium |
| M14 | SOC Environment | Gymnasium RL environment for alert triage | Hard |
| M15 | DRL Triage Agent | DQN agent that learns optimal alert prioritisation | Very Hard |
| M17 | Federated Learning | Flower + Opacus for privacy-preserving multi-org training | Hard |
| M18 | Campaign Detection | Louvain community detection for multi-step attack chains | Medium |
| M22 | Integration Testing | End-to-end system tests | Medium |

## Progress bar:

```
Foundation (Data + Graph):      ████████████████████ 100% ✅
GNN Pre-training:               ████████████████████ 100% ✅
Backend + Dashboard:            ████████████░░░░░░░░  60% (functional, not final)
Anomaly Detection (T-HetGAT):   ░░░░░░░░░░░░░░░░░░░░   0% ← NEXT PHASE
DRL Triage Agent:               ░░░░░░░░░░░░░░░░░░░░   0%
Federated Learning:             ░░░░░░░░░░░░░░░░░░░░   0%
Campaign Detection:             ░░░░░░░░░░░░░░░░░░░░   0%

Overall: ██████░░░░░░░░░░░░░░  ~30%
```

---

# PART 6 — END-TO-END DATA PIPELINE

```
┌───────────────────────────────────────────────────────┐
│                    DATA SOURCES                       │
│   UNSW-NB15 (2GB, ~2.5M rows)                        │
│   CICIDS2017 GeneratedLabelledFlows (7GB, ~2.8M rows) │
└──────────────────────┬────────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────────────┐
│                   INGESTION LAYER                            │
│   unsw.py parser ──┐                                         │
│                    ├── EventNormalizer (SHA-256 dedup)        │
│   cicids.py parser─┘        ↓                                │
│                    EventProducer (token bucket rate limit)    │
└──────────────────────────────┬───────────────────────────────┘
                               │
                               ▼
         ┌─────────────────────────────────────┐
         │   REDPANDA (KAFKA)                  │
         │   Topic: normalized-events          │
         │   ~250M events, at-least-once       │
         └──────────────────┬──────────────────┘
                            │
                   ┌────────┴────────┐
                   ▼                 ▼
     ┌──────────────────────┐  ┌─────────────────────────┐
     │  GRAPH CONSTRUCTION  │  │  NEO4J IMPORT SCRIPT     │
     │  GraphConsumer       │  │  neo4j_import.py         │
     │  SlidingWindowEngine │  │                          │
     │  NodeRegistry        │  │  Replays Kafka from     │
     │  EdgeConstructor     │  │  beginning, writes only  │
     │  FeatureEngineering  │  │  to Neo4j               │
     │  PyGConverter        │  │                          │
     │         ↓            │  │  20,137 windows         │
     │  17,657 .pt files    │  │  5.5M MERGE ops (nodes) │
     │  data/graphs/        │  │  10.5M MERGE ops (edges) │
     └──────────────────────┘  └──────────────┬───────────┘
                                              │
                                        NEO4J DB
                                        124K nodes
                                        3M+ edges
                                              │
                            ┌─────────────────┴──────────────┐
                            ▼                                ▼
             ┌──────────────────────┐          ┌────────────────────────┐
             │   PRE-TRAINING       │          │   FASTAPI BACKEND      │
             │                      │          │   src/api/             │
             │  17,657 .pt files    │          │                        │
             │  HeteroGraphEncoder  │          │  /api/stats            │
             │  GraphCL + NT-Xent   │          │  /api/graph/*          │
             │  FP16 + mini-batch   │          │  /api/alerts           │
             │  RTX 3050, 813MB     │          │  /ws/graph-stats       │
             │         ↓            │          │                        │
             │  checkpoint_best.pt  │          └────────────┬───────────┘
             │  val_loss = 4.812    │                        │
             └──────────────────────┘                        ▼
                                              ┌────────────────────────┐
                                              │   NEXT.JS DASHBOARD    │
                                              │   localhost:3000        │
                                              │                        │
                                              │  /          Dashboard  │
                                              │  /alerts    Alert list │
                                              │  /graph     vis-network│
                                              │  /analytics Stats      │
                                              └────────────────────────┘
```

---

# PART 7 — INFRASTRUCTURE DETAILS

## Docker Services Summary:

| Service | Image | Port | Purpose |
|---------|-------|------|---------|
| **redpanda** | v24.1.1 | 9092 | Kafka-compatible event streaming |
| **redpanda-console** | v2.5.2 | 8080 | Web UI to inspect Kafka topics |
| **neo4j** | 5.17-community | 7474 / 7687 | Graph database |
| **postgres** | 16-alpine | 5432 | Alert storage, analyst feedback |
| **redis** | 7-alpine | 6379 | API response caching |
| **prometheus** | v2.50.0 | 9090 | Metrics collection |
| **grafana** | 10.3.1 | 3001 | Monitoring dashboards |

## Memory limits (all within 16GB RAM system):
```
redpanda:   768 MB   neo4j:     1536 MB
postgres:   512 MB   redis:      384 MB
prometheus: 256 MB   grafana:    256 MB
Total Docker: ~3.7 GB
```

---

# PART 8 — KEY NUMBERS

| Metric | Value |
|--------|-------|
| Raw dataset size | ~9 GB |
| UNSW-NB15 records | ~2.5 million |
| CICIDS2017 records | ~2.8 million |
| Kafka events published | ~250 million+ |
| Graph time windows | 17,657 |
| Neo4j unique nodes | 124,768 |
| Neo4j unique edges | 3,028,187+ |
| Neo4j MERGE operations (nodes) | 5,583,870 |
| Neo4j MERGE operations (edges) | 10,593,668 |
| Neo4j import time | 1 hour 45 minutes |
| GNN hidden dimensions | 128 |
| GNN projection dimensions | 64 |
| GNN parameters (approx) | ~500,000 |
| GPU VRAM used during training | 813 MB / 4096 MB |
| Training time per epoch | ~9 minutes |
| Total training time | ~2 hours |
| Best training result | val_loss = 4.812 (epoch 3 of 13) |
| Python source files | 30+ |
| Frontend source files | 25+ |
| Total lines of code | ~43,000 |
| REST API endpoints | 8 |
| WebSocket endpoints | 1 |
| Docker services | 7 |
| Unit tests (passing) | 55 |

---

# PART 9 — TECHNOLOGY STACK

### Python Backend:
| Library | Version | Why We Use It |
|---------|---------|--------------|
| PyTorch | 2.5+ | GPU-accelerated tensor operations and neural networks |
| PyTorch Geometric | 2.5+ | Heterogeneous graph neural network layers (SAGEConv, HeteroConv) |
| FastAPI | 0.110+ | Async HTTP + WebSocket framework (fastest Python web framework) |
| Uvicorn | 0.27+ | ASGI server to run FastAPI |
| neo4j | 5.x | Official Neo4j Python driver (connection pooling) |
| confluent-kafka | 2.x | High-performance Kafka producer/consumer (C library bindings) |
| pydantic-settings | 2.x | `.env` file → typed Python config objects |
| structlog | latest | Structured JSON logging (key=value format, great for production) |
| polars | latest | Fast DataFrame operations (faster than pandas for large CSVs) |

### JavaScript Frontend:
| Library | Version | Why We Use It |
|---------|---------|--------------|
| Next.js | 16.x | React framework with App Router, SSR, file-based routing |
| React | 19.x | UI component library |
| TypeScript | 5.x | Type safety — catch bugs at write-time not runtime |
| TailwindCSS | 4.x | Utility-first CSS — no custom CSS files needed |
| vis-network | 10.x | Force-directed graph visualisation built for network graphs |
| Recharts | 3.x | SVG-based charts (donut, bar charts) |
| TanStack Query | 5.x | Server state management (caching, refetching, loading states) |
| Zustand | 5.x | Lightweight client state (selected node, filter values) |
| Axios | 1.x | HTTP client (cleaner API than native fetch) |
| framer-motion | 12.x | Smooth UI animations |

---

# PART 10 — FOR THE DISSERTATION PRESENTATION

## One-line description:
> "We built an AI-powered cybersecurity platform that models network traffic as a temporal heterogeneous graph, uses self-supervised contrastive learning to pre-train a GNN without needing attack labels, and provides a real-time SOC dashboard backed by a Neo4j graph database."

## Explain it like I'm 5:
> "We built a smart security guard. Instead of just checking a list of rules, it watches WHO talks to WHOM and WHEN. It learned what 'normal' looks like by studying thousands of hours of network traffic — without anyone telling it which events were attacks. Now it can spot the unusual ones."

## For a technical panel:
> "Temporal heterogeneous graph model: 5 node types (Host, ExternalIP, Service, Domain, User), 4 edge types, 1-hour sliding windows with 15-minute slide (75% overlap). GraphCL self-supervised pre-training on 17,657 PyG HeteroData snapshots. HeteroGraphEncoder: LazyLinear input projection + 2×HeteroConv(SAGEConv) + BatchNorm + ReLU + 2-layer projection head. NT-Xent loss with temperature=0.5. Trained on RTX 3050 4GB (813MB VRAM, FP16 AMP, batch=4). Best val_loss=4.812. Neo4j 5.17: 124,768 entities, 3M+ relationships. FastAPI async REST + WebSocket. Next.js 16 SOC dashboard with vis-network interactive graph."

## Why this beats traditional IDS:
| Traditional IDS | Our System |
|-----------------|-----------|
| Rule-based (if packet > X → alert) | Pattern-based (learned from graph structure) |
| Misses novel attacks | Can detect zero-days via structural anomaly |
| Looks at individual packets | Looks at multi-hop graph patterns |
| 80%+ false positive rate | Graph structure reduces false positives |
| No alert prioritisation | DRL agent (future) learns optimal triage |

## Innovation claims in dissertation:
1. **Temporal heterogeneous graph model** — captures the who/what/when of network behaviour in a graph structure that tabular ML completely misses.
2. **GraphCL on security data** — applying SimCLR-style contrastive learning (originally designed for images) to cybersecurity graphs. No labelled data needed for pre-training.
3. **DRL for SOC triage** — treating alert prioritisation as a Markov Decision Process with reward shaping based on analyst feedback (future module).
4. **Federated SOC** — enabling multiple organisations to share threat intelligence without sharing raw traffic data (future module, via Flower + Opacus differential privacy).

---

*Document updated: 17 March 2026 | GraphRL-Sec MTech Dissertation Project*
*Based on: Project_4_GraphRL_Sec.docx (original dissertation proposal)*
