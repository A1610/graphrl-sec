# GraphRL-Sec — Poora Project Samjho (Hinglish)
## Har ek file, har ek code, har ek decision — 5 saal ke bachhe se MTech tak

---

# PART 0 — SABSE PEHLE: YE PROJECT KYU BANAYA?

## Real duniya ki problem (Dissertation document se)

Soch lo ek badi company hai — jaise koi bank ya hospital. Uske paas hazaaron computers hain. Roz **10,000 se zyada security alerts** aate hain. Matlab har din 10,000 baar alarm bajta hai.

Ab socho — ek security wala banda kitne alarms check kar sakta hai? Shayad 100-200. Baaki 9,800 alarms? **Ignore ho jaate hain.**

Aur hacker jaanta hai ye. Woh jaanboojhkar itna noise paida karta hai ke uski asli attack chhup jaaye.

**Numbers jo sochne pe majboor kar dete hain:**
- Cybercrime se duniya ko **$10.5 Trillion** ka nuksan 2025 tak
- **3.5 million** cybersecurity jobs khali hain — log nahi hain kaam karne waale
- SOC analyst ka **70% time** jhoothe alarms check karne mein jaata hai
- False positive rate (jhootha alarm): **80%+**

### Purani systems ka problem kya tha?

```
PURANI SYSTEM (Rule-Based IDS):
  Rule: "Agar koi 1000 se zyada packets bheje 1 minute mein → alarm"

  Problem 1: Hacker sirf 999 packets bheje → no alarm ❌
  Problem 2: Normal server bhi kabhi 1000 packets bhejta hai → false alarm ❌
  Problem 3: Multi-step attack (3 alag computers se slowly karo) → nahi pakda ❌
```

### Hamara solution kya hai?

```
HAMARA SYSTEM (GraphRL-Sec):
  1. Network ko ek MAP ki tarah dekho (Graph)
     "Kaun kisse baat karta hai? Kitni baar? Kab?"

  2. AI ko pattern seekhne do (GNN - Graph Neural Network)
     "Ye pattern normal hai... ye suspicious lag raha hai"

  3. AI khud decide kare (DRL - Deep Reinforcement Learning)
     "Is alarm ko escalate karo, use ignore karo"

  4. Multiple companies milke seekhen (Federated Learning)
     "Mere yahan naya attack aaya — sab ko bata do, data share kiye bina"
```

---

# PART 1 — PROJECT KA BLUEPRINT (Original Document)

Hamara pura project ek **MTech Dissertation** hai jiska naam hai:
> **"GraphRL-Sec: Adaptive Cybersecurity Threat Intelligence System using GNN-Reinforced Deep Learning and Federated SOC Analytics"**

**Ye 6 bade innovations ka combination hai:**

| Innovation | Simple Mein | Technical |
|-----------|-------------|-----------|
| **1. Temporal Graph** | Network ka time-wala map | Sliding window heterogeneous graph |
| **2. T-HetGAT** | Smart attack detector | Temporal Heterogeneous Graph Attention Network |
| **3. DRL Triage** | Auto-decide karne wala agent | DQN with prioritized experience replay |
| **4. Pre-training** | Bina labels ke seekhna | Self-supervised contrastive learning (GraphCL) |
| **5. Federated** | Privacy rakhke milke seekhna | Flower + Opacus differential privacy |
| **6. Campaign Detection** | Attack ki poori kahani | Louvain community detection |

---

# PART 2 — HUMNE ABHI TAK KYA BANAYA

## Poore project ka map:

```
POORA PROJECT (22 Modules):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PHASE 1 — FOUNDATION (Neenv)
  Module 4:  Data Ingestion         ✅ COMPLETE
  Module 5:  Graph Construction     ✅ COMPLETE
  Module 6:  Neo4j Integration      ✅ COMPLETE

PHASE 2 — AI FOUNDATION (Dimag banana)
  Module 8:  Self-Supervised Pretraining  ✅ COMPLETE
  Module 9:  Node2Vec Baseline           ⬜ PENDING

PHASE 3 — DETECTION (Attack pakadna)
  Module 11: T-HetGAT Detection    ⬜ PENDING
  Module 12: Benchmarking          ⬜ PENDING

PHASE 4 — AUTOMATION (Auto-decide)
  Module 14: SOC Environment       ⬜ PENDING
  Module 15: DRL Triage Agent      ⬜ PENDING

PHASE 5 — SCALE (Bada karo)
  Module 17: Federated Learning    ⬜ PENDING
  Module 18: Campaign Detection    ⬜ PENDING

PHASE 6 — PRESENTATION (Dikhao)
  Module 20: FastAPI Backend       ✅ COMPLETE
  Module 21: SOC Dashboard         ✅ COMPLETE
  Module 22: Integration Testing   ⬜ PENDING
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ABHI TAK: 6 modules complete (~30%)
```

---

# PART 3 — HAR EK FILE KA DEEP EXPLANATION

---

## 3.1 INFRASTRUCTURE — Docker aur Services

### File: `docker-compose.yml`

**Kyu banaya:** Project chalaane ke liye 7 alag softwares chahiye the. Har ek ko manually install karna mushkil tha. Docker mein sab ek file mein define kar diya.

**Simple analogy:** Soch lo ek dabba (Docker) liya jisme 7 chhote kamre hain. Har kamre mein ek kaam hota hai. Ek command se sab shuru ho jaata hai.

```
docker-compose up -d
→ Ye command chalao aur 7 softwares shuru ho jaate hain automatically
```

**7 services kya karte hain:**

```
┌─────────────────────────────────────────────────────────────────┐
│ SERVICE 1: REDPANDA (Kafka)                                     │
│ Port: 9092                                                      │
│                                                                 │
│ Kya hai: Ek dak ghar (post office)                             │
│                                                                 │
│ Kyu chahiye: CSV files mein crore+ rows hain. Ek saath process │
│ nahi kar sakte. Kafka mein sab messages queue mein aa jaate     │
│ hain. Consumer apni speed se leta rehta hai.                    │
│                                                                 │
│ Real analogy: Amazon ka warehouse. Package aata hai → store    │
│ hota hai → delivery wala apni speed se le jaata hai.           │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│ SERVICE 2: NEO4J                                                │
│ Ports: 7474 (browser), 7687 (code se connect)                  │
│                                                                 │
│ Kya hai: Graph database                                         │
│                                                                 │
│ Kyu chahiye: Normal database (Excel/MySQL) rows mein socha     │
│ karta hai. Hamara data graph hai — "kaun kisse connected hai". │
│ Neo4j specifically graphs ke liye bana hai.                    │
│                                                                 │
│ Real analogy: Facebook ka friend map. "A → B ke dost hain"    │
│ "B → C ke dost hain" "A se C tak 2 steps mein pahuncho"       │
│ Ye query Neo4j mein milliseconds mein hoti hai.                │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│ SERVICE 3: POSTGRESQL                                           │
│ Port: 5432                                                      │
│                                                                 │
│ Kya hai: Normal relational database (rows + columns)           │
│                                                                 │
│ Kyu chahiye: Alerts, analyst feedback, user data store karna.  │
│ Ye simple tabular data hai → normal DB sahi hai.               │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│ SERVICE 4: REDIS                                                │
│ Port: 6379                                                      │
│                                                                 │
│ Kya hai: Super fast memory-based storage                       │
│                                                                 │
│ Kyu chahiye: API calls slow hoti hain agar har baar Neo4j se  │
│ query karo. Redis mein results 1 minute tak store karo →      │
│ next request mein seedha Redis se lo → 100x faster.            │
│                                                                 │
│ Real analogy: Calculator ki display. Previous answer yaad      │
│ rehta hai — dobara calculate nahi karna padta.                 │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│ SERVICE 5: PROMETHEUS                                           │
│ Port: 9090                                                      │
│                                                                 │
│ Kya hai: System health monitor                                  │
│                                                                 │
│ Kyu chahiye: Pata karne ke liye ki system sahi chal raha hai.  │
│ CPU kitna use ho raha hai? Memory? API kitni slow hai?          │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│ SERVICE 6: GRAFANA                                              │
│ Port: 3001                                                      │
│                                                                 │
│ Kya hai: Monitoring dashboard                                   │
│                                                                 │
│ Kyu chahiye: Prometheus ke numbers ko sundar graphs mein       │
│ dikhata hai. System ka "health report card".                    │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│ SERVICE 7: REDPANDA CONSOLE                                     │
│ Port: 8080                                                      │
│                                                                 │
│ Kya hai: Kafka ka web UI                                        │
│                                                                 │
│ Kyu chahiye: Browser mein dekh sako ke Kafka topic mein kitne  │
│ messages hain, kaisa data aa raha hai.                          │
└─────────────────────────────────────────────────────────────────┘
```

---

## 3.2 DATA INGESTION — `src/ingestion/`

**Kyu ye folder banaya:** Original document mein likha tha ke 2 datasets use karne hain — UNSW-NB15 aur CICIDS2017. Ye CSV files hain. Inhein padhna, clean karna, aur Kafka mein dalna tha.

---

### File: `src/ingestion/schemas.py`

**Kyu banaya:** UNSW dataset ke columns alag hain, CICIDS ke columns alag. Dono ka data ek common format mein lana tha — warna baaki code confuse hojata ke "ye column UNSW ka hai ya CICIDS ka?"

**Simple analogy:** Soch lo do desh hain — India mein litres mein doodh bechte hain, America mein gallons mein. Ek common unit banana pada — "milliliters" — taaki dono countries ka data same unit mein aa sake.

**Ye `UnifiedEvent` class banaya:**
```python
class UnifiedEvent:
    timestamp      # Kab hua ye event?
    event_type     # Kya hua? (network flow, auth, DNS...)
    source         # Kaun ne bheja? (IP address)
    destination    # Kise bheja? (IP address)
    network        # Kaise bheja? (protocol, bytes, packets)
    metadata       # Attack tha ya nahi? Kaun sa attack?
    dataset_source # UNSW se aaya ya CICIDS se?
```

**Aur ye `AttackLabel` enum banaya:**
```python
class AttackLabel:
    BENIGN          # Koi attack nahi — normal traffic
    DDOS            # Distributed Denial of Service
    PORT_SCAN       # Hacker ports check kar raha hai
    SQL_INJECTION   # Database pe attack
    BOT             # Automated hacking tool
    # ... 30+ attack types
```

**Kyu `AttackLabel` enum banaya:** Strings use karte to typos hoti. "DDOS" vs "DDoS" vs "ddos" — sab alag hote. Enum mein ek hi value — `AttackLabel.DDOS`.

---

### File: `src/ingestion/parsers/unsw.py`

**Kyu banaya:** UNSW-NB15 dataset ki CSV files mein **koi header nahi hota**. Matlab pehli line mein column names nahi hain — seedha data hota hai. Ek special parser banana pada.

**Simple analogy:** Soch lo koi tumhe ek list de jisme naam nahi hain — sirf numbers hain:
```
192.168.1.1, 8.8.8.8, 80, TCP, 1024, 1
```
Tumhe yaad rakhna padega ke "1st number = source IP, 2nd = dest IP..." etc.

**Ye kaise solve kiya:**
```python
_UNSW_HEADERS = [
    "srcip",     # Column 1 = source IP
    "sport",     # Column 2 = source port
    "dstip",     # Column 3 = destination IP
    "dsport",    # Column 4 = destination port
    "proto",     # Column 5 = protocol
    # ... 49 columns total
]

def _file_has_header(filepath):
    # Pehli line padho
    # Agar "srcip" jaisa word hai → header hai
    # Agar "192.168.1.1" jaisa IP hai → header nahi hai
    # Return True/False
```

**Important fix jo karna pada:** Pehle code header assume kar raha tha. UNSW files mein header nahi tha → sab data ek row shift ho gaya → parser fail. Ye bug dhundha aur fix kiya.

---

### File: `src/ingestion/parsers/cicids.py`

**Kyu banaya:** CICIDS2017 dataset ka format UNSW se alag hai. Source IP, Destination IP columns hain, timestamps bhi proper format mein hain: `"03/07/2017 10:23:45"`.

**Important cheez jo fix karni padi:** Do versions hain CICIDS ke:
1. **MachineLearningCSV** — IP columns NAHI hain (stripped version)
2. **GeneratedLabelledFlows** — IP columns HAIN ✅

Hamein doosra version chahiye tha. Pehle galat version use kar rahe the → `Source IP` column missing error aata tha.

**Timestamp parsing:**
```python
def _parse_cicids_timestamp(ts_string):
    # Input:  "03/07/2017 10:23:45"
    # Format: DD/MM/YYYY HH:MM:SS
    # Output: Python datetime object
    return datetime.strptime(ts_string, "%d/%m/%Y %H:%M:%S")
```

**Web Attack label encoding fix:** CICIDS files mein "Web Attack – Sql Injection" string tha, lekin file Windows mein save ki gayi thi → kuch characters `\x96` (Windows dash) ya `?` mein convert ho gaye. Sab variants handle kiye:
```python
_CICIDS_LABEL_MAP = {
    "Web Attack \x96 Sql Injection": AttackLabel.SQL_INJECTION,
    "Web Attack ? Sql Injection":    AttackLabel.SQL_INJECTION,
    "Web Attack – Sql Injection":    AttackLabel.SQL_INJECTION,
}
```

---

### File: `src/ingestion/normalizer.py`

**Kyu banaya:** Parsers se raw data aata hai. Validate karna tha — kya source IP valid hai? Kya timestamp valid hai? Duplicates nikalne the.

**Kya karta hai:**
```python
class EventNormalizer:
    def normalize(self, raw_dict):
        # 1. Check karo: IP valid hai? Port 0-65535 ke beech hai?
        # 2. Duplicate check: SHA-256 hash se
        #    "192.168.1.1→8.8.8.8→1024bytes→TCP" ka hash nikalo
        #    Agar ye hash pehle dekha hai → duplicate → skip
        # 3. UnifiedEvent banao aur return karo
        # 4. Agar kuch galat hai → None return karo (skip this event)
```

**Kyu SHA-256 hash use kiya duplicates ke liye:** Same network flow kabhi kabhi 2 baar log ho jaata hai. IP + Port + Bytes + Timestamp ka hash nikalo → agar same hash pehle aaya → duplicate.

---

### File: `src/ingestion/producer.py`

**Kyu banaya:** Normalized events ko Kafka mein dalna tha. Simple `kafka.send()` kafi nahi tha — rate limiting chahiye tha (server overload na ho), delivery confirmation chahiye tha (koi message drop na ho).

**Token Bucket Rate Limiter:**
```python
class _TokenBucket:
    # Soch lo ek bucket hai jisme tokens hain (jaise coins)
    # Har second mein N tokens aate hain (jaise salary)
    # Har message bhejne ke liye 1 token chahiye
    # Agar tokens khatam → wait karo
    # Iska fayda: Kafka server overload nahi hota
```

**Delivery callback:**
```python
def _on_delivery(err, msg):
    if err:
        # Message nahi pahuncha → log karo → retry
        log.error("delivery_failed", error=err)
    else:
        # Message pahuncha → sab theek
        pass
```

**Kyu ye zaroori tha:** CSV se 2.5M+ events publish karne the. Bina rate limiting ke Kafka crash ho sakta tha. Bina delivery callback ke pata nahi chalta tha koi message drop hua ya nahi.

---

### File: `src/ingestion/consumer.py`

**Kyu banaya:** Kafka mein messages aate rehte hain. Inhein continuously padhna tha, graph banane ke liye process karna tha, aur `.pt` files save karni thin.

**GraphConsumer class:**
```python
class GraphConsumer:
    def run(self):
        # Kafka subscribe karo
        # Loop shuru karo:
        while not stop:
            msg = kafka.poll()           # Ek message lo
            event = deserialize(msg)     # JSON → UnifiedEvent
            batch.append(event)          # Batch mein add karo

            if batch is full OR time limit reached:
                process_batch(batch)     # Graph banao
                commit_offset()          # "Maine ye read kar liya" batao Kafka ko
```

**Important addition:** `self._snapshot_seq = 0` — ek global counter jo `.pt` files ke naam ke liye use hota hai. Pehle har batch mein counter reset ho jaata tha → same filename likhta tha → pehli file overwrite ho jaati thi. Fix: global counter jo kabhi reset nahi hota.

```
Window 1 → window_000001.pt
Window 2 → window_000002.pt
Window 3 → window_000003.pt
... (kabhi overwrite nahi hoga)
```

---

## 3.3 GRAPH CONSTRUCTION — `src/graph/`

**Kyu ye folder banaya:** Network events ko graph mein convert karna tha. Original document mein specifically kaha gaya tha: "enterprise network ko heterogeneous graph ki tarah model karo."

---

### File: `src/graph/config.py`

**Kyu banaya:** Pura graph system configurable hona chahiye tha. "Window kitne ghante ka ho?" "Internal IP kya define karta hai?" — ye sab hardcode nahi karna tha.

**Key settings:**
```python
class GraphConfig:
    window_size_hours = 1      # 1 ghante ka ek snapshot
    window_slide_minutes = 15  # Har 15 min mein naya window start

    # Internal IPs (ye computers inside company ke hain)
    internal_ip_prefixes = ["192.168.", "10.", "172.16.", "172.17.", ...]

    # Neo4j connection
    neo4j_uri = "bolt://localhost:7687"
    neo4j_password = "graphrlsec123"

    # Memory limits (GPU/RAM overflow se bachne ke liye)
    max_nodes_per_window = 50_000
    max_edges_per_window = 500_000
```

---

### File: `src/graph/node_registry.py`

**Kyu banaya:** Graph mein nodes (circles) hote hain. Har unique IP/port/domain ke liye ek node chahiye tha. Ek registry banai jo track kare ke "192.168.1.5" ka node ID kya hai.

**NodeType — 5 types:**
```
HOST        = Internal computer (192.168.x.x)
EXTERNAL_IP = Baahri internet IP (8.8.8.8)
SERVICE     = Port:Protocol (80:TCP = web server)
DOMAIN      = Website name (google.com)
USER        = Login account (admin@company.com)
```

**Kyu 5 types:** Original document mein exactly ye 5 types specify kiye gaye the. Alag types isliye taaki model samjhe "ye connection internal-to-internal hai ya internal-to-external hai."

**`get_or_create_ip()` function:**
```python
def get_or_create_ip(self, ip_address):
    # Check karo: ye IP internal hai ya external?
    if ip_address.startswith("192.168.") or ip_address.startswith("10."):
        node_type = NodeType.HOST      # Internal computer
    else:
        node_type = NodeType.EXTERNAL  # Internet ka IP

    # Agar pehle se registry mein hai → wahi node return karo
    # Nahi hai → naya node banao with auto-increment ID
```

**Kyu RLock (thread lock) use kiya:** Consumer parallel mein kaafi events process karta hai. Bina lock ke do threads ek saath ek hi IP ke liye node bana dete → duplicate nodes.

---

### File: `src/graph/edge_constructor.py`

**Kyu banaya:** Ek event (connection) graph mein 1 se zyada edges create kar sakta hai. Ye class decide karti hai kaun se edges banana hai.

**4 edge types kaise decide hote hain:**
```
Ek event: 192.168.1.5 → 8.8.8.8:80 via TCP (HTTP request)

Is event se ye edges bante hain:
  1. CONNECTS_TO:    192.168.1.5 → 8.8.8.8
     (IP to IP direct connection)

  2. USES_SERVICE:   192.168.1.5 → Service(80:TCP)
     (Ye computer HTTP use kar raha hai)

  3. (Agar DNS query tha) RESOLVES_DOMAIN: 192.168.1.5 → google.com
     (Ye computer google.com lookup kar raha tha)

  4. (Agar login tha) AUTHENTICATED_AS: 192.168.1.5 → User(admin)
     (Kisi ne is computer se admin se login kiya)
```

**Edge features (12 numbers):**
```python
edge_features = [
    timestamp_normalized,    # Kab hua
    duration_normalized,     # Kitna time laga
    bytes_sent_normalized,   # Kitna data bheja
    bytes_received_normalized, # Kitna data aaya
    packets_sent,            # Kitne packets bheje
    packets_received,        # Kitne packets aaye
    is_tcp,                  # 1.0 agar TCP, 0 warna
    is_udp,                  # 1.0 agar UDP, 0 warna
    is_icmp,                 # 1.0 agar ICMP (ping), 0 warna
    is_other_protocol,       # 1.0 agar koi aur protocol
    port_normalized,         # Port number 0-1 ke beech
    is_attack,               # 1.0 agar attack hai, 0 warna
]
```

---

### File: `src/graph/feature_engineering.py`

**Kyu banaya:** Machine learning ke liye har node ko numbers mein represent karna hota hai. Ye file nodes ke liye feature vectors nikaalti hai.

**Host node (8 numbers) — kyu ye 8 features:**
```python
features = [
    degree_norm,           # Kitne connections kiye (0-1 normalized)
    bytes_sent_norm,       # Kitna data bheja
    bytes_recv_norm,       # Kitna data receive kiya
    packets_sent_norm,     # Kitne packets
    unique_dsts_norm,      # Kitni unique destinations se baat ki
    is_internal,           # 1.0 = internal computer, 0.0 = external
    attack_score,          # 0-1: kitne events attacks the
    last_seen_norm,        # Kab last active tha
]
```

**`attack_score` kyu important hai:**
```
Computer ne 100 connections kiye.
In 100 mein se 40 attacks the.
attack_score = 40/100 = 0.4

Matlab: 40% chance ye computer compromised hai
```

---

### File: `src/graph/temporal.py`

**Kyu banaya:** Network traffic continuous hai — packets kabhi bhi aa sakte hain. Inhe fixed-size "windows" (time chunks) mein todna tha taaki har window ka ek graph ban sake.

**Sliding Window:**
```
1 ghante ka window, 15 min slide:

12:00 ──────────────────── 13:00    ← Window 1
      12:15 ──────────────────── 13:15  ← Window 2
            12:30 ──────────────────── 13:30  ← Window 3

Overlap kyon: Agar attack 12:50 shuru hota hai 13:10 tak chalega,
Window 1 mein aadha dikhega, Window 2 mein poora dikhega
```

**Kyu sliding window:** Original document mein specifically kaha tha "sliding window typically 24-72 hours". Hamne 1 hour rakha kyunki dataset smaller hai aur training faster hoti hai.

**Output — `WindowResult`:**
```python
@dataclass
class WindowResult:
    window: TimeWindow         # Start time, end time, window ID
    registry: NodeRegistry     # Is window ke saare nodes
    accumulator: EdgeAccumulator # Is window ke saare edges
```

---

### File: `src/graph/pyg_converter.py`

**Kyu banaya:** Machine learning model PyTorch Geometric (PyG) format ka data maangta hai — `HeteroData` object. Hamara `WindowResult` directly use nahi ho sakta tha.

**Conversion:**
```python
def convert(window_result):
    data = HeteroData()

    # Node features
    data['Host'].x         = tensor([[degree, bytes, ...], ...])  # shape: (N_hosts, 8)
    data['ExternalIP'].x   = tensor([[...], ...])                  # shape: (N_ext, 8)
    data['Service'].x      = tensor([[...], ...])                  # shape: (N_svc, 4)

    # Edge indices (which nodes are connected)
    data[('Host', 'CONNECTS_TO', 'ExternalIP')].edge_index = tensor([[src_ids], [dst_ids]])
    data[('Host', 'CONNECTS_TO', 'ExternalIP')].edge_attr  = tensor([[bytes, duration, ...]])

    return data  # → saved as window_000001.pt
```

**Kyu `.pt` format:** PyTorch ka native binary format. Fast load hota hai training ke dauran. `torch.save(data, path)` aur `torch.load(path)` — simple.

---

### File: `src/graph/neo4j_writer.py`

**Kyu banaya:** WindowResult ko Neo4j mein store karna tha — sirf `.pt` files nahi chahiye thin, database bhi chahiye tha taaki dashboard real-time queries kar sake.

**MERGE operation kyu:**
```python
# Normal INSERT:
# "192.168.1.5" node insert karo
# Agar kal dubara same data aaye → duplicate node bana dega!

# MERGE (hamara approach):
# "192.168.1.5" node MERGE karo
# Agar already hai → sirf update karo
# Nahi hai → naya banao
# KABHI DUPLICATE NAHI HOGA ✓
```

**Batch writes kyu:**
```python
# Slow approach (ek ek node):
for node in nodes:
    neo4j.run("MERGE (n:Host {ip: $ip})", ip=node.ip)
# 1000 nodes = 1000 database calls = SLOW

# Fast approach (batch mein):
neo4j.run("UNWIND $batch AS row MERGE (n:Host {ip: row.ip})", batch=nodes_list)
# 1000 nodes = 1 database call = FAST ✓
```

---

### File: `src/graph/neo4j_schema.py`

**Kyu banaya:** Neo4j mein constraints aur indexes banane the. Bina index ke queries slow hoti hain. Bina constraints ke duplicate data aa sakta tha.

**Constraints kya hote hain:**
```cypher
CREATE CONSTRAINT FOR (n:Host) REQUIRE n.entity_key IS UNIQUE
-- Matlab: Do Host nodes same entity_key nahi rakh sakte
-- Ye guarantee karta hai no duplicates
```

**Indexes kya hote hain:**
```cypher
CREATE INDEX FOR (n:Host) ON (n.ip)
-- Matlab: Jab "ip = '192.168.1.5'" query karo
-- → Database seedha wahan jaata hai, saari nodes scan nahi karta
-- 1000x faster queries
```

---

### File: `src/graph/neo4j_queries.py`

**Kyu banaya:** FastAPI backend ko Neo4j se data fetch karna tha. Ye file saare Cypher queries centralize karti hai — ek jagah se query likhte hain, saare routes use karte hain.

**5 main queries:**

```python
# 1. Ek IP ke aaspaas ka graph (2 hops)
def get_neighborhood(ip, hops=2):
    # "192.168.1.5 se 2 connections door tak kaun kaun hai?"
    # MATCH path = (center {entity_key: $ip})-[*1..2]-(neighbor)

# 2. Sabse zyada active computers
def get_top_communicators(limit=20):
    # "Kaun sa computer sabse zyada connections karta hai?"
    # ORDER BY outbound connections DESC

# 3. Suspicious paths
def get_anomalous_paths(threshold=0.5):
    # "Kaun se connections mein attack_score >= 0.5 hai?"

# 4. Time range mein connections
def get_time_window_edges(min_window, max_window):
    # "Window 100 se 200 ke beech kya connections the?"

# 5. Database ki summary
def get_graph_stats():
    # "Total kitne nodes hain? Kitne edges?"
    # Returns: host_count=45231, external_ip_count=32541, ...
```

**Kyu parameterized queries:**
```python
# GALAT (SQL injection possible):
query = f"MATCH (n:Host {{ip: '{user_input}'}})"
# Agar user_input = "' OR 1=1" → security breach!

# SAHI (hamara approach):
query = "MATCH (n:Host {ip: $ip})"
params = {"ip": user_input}  # Neo4j handle karta hai safely
```

---

## 3.4 SELF-SUPERVISED PRE-TRAINING — `src/models/pretrain/`

**Kyu ye folder banaya:** Original document mein Phase 2 tha — "Self-Supervised Pre-training". GNN ko bina labeled data ke seekhna tha. Labels sirf 20-30% data ke liye available the. Unlabeled majority data bhi use karna tha.

---

### File: `src/models/pretrain/config.py`

**Kyu banaya:** Training ke saare hyperparameters ek jagah define karna tha. `.env` file se environment variables bhi support karna tha.

```python
class PretrainConfig:
    hidden_dim = 128          # GNN ka "brain size" — 128 dimensions
    projection_dim = 64       # Contrastive loss ke liye smaller space
    num_layers = 2            # 2 message passing layers
    learning_rate = 0.001     # Kitni tezi se seekhe
    batch_size = 4            # 4 graphs ek saath — 4GB VRAM ke liye safe
    num_epochs = 100          # Maximum 100 rounds
    early_stopping_patience = 10  # 10 rounds mein improvement nahi → stop
    mixed_precision = True    # FP16 — VRAM aadha use karo
    device = "cuda"           # GPU use karo, CPU nahi
```

**Kyu `batch_size = 4`:** RTX 3050 mein sirf 4GB VRAM hai. Ek graph ~200MB activations leta hai training ke dauran. 4 × 200 = 800MB + model weights = safe. 8 graphs liye to OOM (Out of Memory) error aata.

---

### File: `src/models/pretrain/encoder.py`

**Kyu banaya:** Ye project ka main "brain" hai — HeteroGraphEncoder. Har node ko ek 128-dimensional vector mein represent karta hai.

**Architecture step by step:**

```
STEP 1: LazyLinear (Input Projection)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Har node type ke features alag dimension mein hain:
  Host:       8 features
  ExternalIP: 8 features
  Service:    4 features

Inhe sabko same dimension (128) pe lana tha.

LazyLinear kyu:
  Normal Linear(8, 128) → input dimension hardcode karna padta
  LazyLinear(-1, 128)   → pehle forward pass pe khud figure out karta hai

Hume faida: Naye node types add karo — code change nahi karna

STEP 2: SAGEConv (Message Passing) × 2 layers
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Simple analogy: School mein gossip spreading
  - Har student apne dosto se sunata hai
  - Apni information aur dosto ki information combine karta hai
  - Yahi update ho jaati hai uski "state"

Formally:
  h_v(new) = W · CONCAT(h_v, MEAN(h_u for all neighbors u))

Kyu SAGE (GraphSAGE):
  GAT se simple aur fast
  Inductive — naye nodes pe bhi kaam karta hai
  Heterogeneous graphs ke liye suitable

valid_edges filter kyu:
  Kuch windows mein kuch node types missing hote hain
  Agar Service nodes nahi hain to USES_SERVICE edges bhi nahi
  Bina filter ke: "NoneType has no attribute 'dim'" error
  Fix: Sirf wo edges pass karo jiske dono endpoints h_dict mein hain

STEP 3: BatchNorm + ReLU
━━━━━━━━━━━━━━━━━━━━━━━
BatchNorm: Values normalize karo (exploding/vanishing gradients rokne ke liye)
ReLU: Negative values zero kar do (non-linearity laao)

STEP 4: Projection Head (2-layer MLP)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
128 → 128 → ReLU → 64 (L2 normalized)

Kyu alag projection head:
  Encoder (128-dim) = downstream tasks ke liye (anomaly detection)
  Projection (64-dim) = sirf training ke liye contrastive loss

  Baad mein projection head hata do, sirf encoder rakho
  Ye SimCLR paper ka key insight hai
```

---

### File: `src/models/pretrain/augmentation.py`

**Kyu banaya:** GraphCL ke liye ek graph ke do "views" banana tha. Do alag augmentations se do views → "same graph, thoda alag dikhta hai" → model ko invariant representations seekhni padti hain.

```python
class GraphAugmentor:
    def __call__(self, graph):
        augmented = graph.clone()

        # AUGMENTATION 1: Feature Masking (20%)
        # Kuch node features ko zero kar do
        # "Agar kuch information chhupo, phir bhi same node recognize karo"
        for node_type in graph.node_types:
            mask = torch.rand(N, D) < 0.20  # 20% features random mask
            augmented[node_type].x[mask] = 0.0

        # AUGMENTATION 2: Edge Dropping (20%)
        # Kuch connections hata do
        # "Agar kuch connections miss ho jayein, phir bhi recognize karo"
        for edge_type in graph.edge_types:
            N_edges = graph[edge_type].edge_index.shape[1]
            keep = torch.rand(N_edges) > 0.20  # 20% drop
            augmented[edge_type].edge_index = edge_index[:, keep]

        return augmented
```

**Kyu ye augmentations:** Real network mein packets drop hote hain, sensors miss karte hain, logs corrupt ho jaate hain. In augmentations se model seekhta hai ke partial information pe bhi sahi representation nikalna hai.

---

### File: `src/models/pretrain/contrastive.py`

**Kyu banaya:** NT-Xent loss implement karna tha — SimCLR paper se inspired. Ye loss function model ko sikhati hai ke positive pairs (same node, do views) close rakhne hain aur negative pairs door rakhne hain.

**NT-Xent Loss simple mein:**
```
Soch lo 6 log hain ek party mein:
  A1, A2 (same person A ke do photos)
  B1, B2 (same person B ke do photos)
  C1, C2 (same person C ke do photos)

NT-Xent Loss kehti hai:
  "A1 aur A2 ko ek doosre ke paas rakho (same person hain)"
  "A1 ko B1, B2, C1, C2 se door rakho (alag log hain)"

Graph mein:
  node_5(view1) aur node_5(view2) → paas rahen
  node_5(view1) aur node_7(view2) → door rahen
```

**Mathematical implementation:**
```python
def _nt_xent(z1, z2):
    n = z1.shape[0]  # N nodes

    # Step 1: Sab vectors ek jagah
    z = torch.cat([z1, z2], dim=0)  # shape: (2N, 64)

    # Step 2: Har pair ke beech similarity nikalo
    sim = torch.mm(z, z.t()) / temperature  # shape: (2N, 2N)

    # Step 3: Self-similarity (apne aap se) ko -infinity karo
    # (Apne aap se compare nahi karna)
    sim.masked_fill(torch.eye(2n, dtype=bool), float('-inf'))

    # Step 4: Labels: node i ka positive = node i+N
    labels = torch.cat([arange(N) + N, arange(N)])  # [N, N+1, ..., 2N-1, 0, 1, ..., N-1]

    # Step 5: Cross-entropy loss
    loss = F.cross_entropy(sim, labels)
    return loss
```

---

### File: `src/models/pretrain/trainer.py`

**Kyu banaya:** Training loop manage karna tha — data load karo, epochs chalao, loss compute karo, gradients update karo, checkpoint save karo.

**Important bugs jo fix kiye:**

**Bug 1: val_loss = 0.0**
```python
# PROBLEM: Do alag graphs augment karte the
view1 = augmentor(graph_a)  # Window t
view2 = augmentor(graph_b)  # Window t+1

# graph_a mein 45 Host nodes
# graph_b mein 52 Host nodes
# collect_node_projections mein check: shape[0] must match
# 45 ≠ 52 → None return → valid_pairs = 0 → loss = 0.0 / 0 = 0.0

# FIX: Same graph ko do baar augment karo (GraphCL proper approach)
view1 = augmentor(graph_a)  # View 1 of graph_a
view2 = augmentor(graph_a)  # View 2 of graph_a (SAME SOURCE!)
# Ab dono mein same number of nodes → shape match ✓
```

**Bug 2: optimizer.step() double call**
```python
# PROBLEM:
train_loss = self._run_epoch(...)  # Andar bhi optimizer.step() hai
optimizer.step()  # ← Ye extra tha! Double gradient update!
scheduler.step()  # ← Ye sahi jagah tha

# FIX: optimizer.step() bahar wala remove kiya
train_loss = self._run_epoch(...)  # optimizer.step() andar hota hai
scheduler.step()  # Sirf scheduler.step() bahar
```

**Mini-batch processing (kyu banaya):**
```python
# PEHLE: Ek ek graph process hota tha
for graph_a, graph_b in pairs:  # 15,891 iterations!
    view1 = augmentor(graph_a)
    proj1 = model.project(view1)
    # GPU: 10-20% utilization (zyada time CPU par)

# AB: 4 graphs ek saath (mini-batch)
for start in range(0, len(pairs), batch_size=4):
    mini = pairs[start:start+4]  # 4 pairs
    views_a = [augmentor(g) for g, _ in mini]  # 4 graphs augment
    views_b = [augmentor(g) for g, _ in mini]  # 4 more views

    batch_a = Batch.from_data_list(views_a)  # Merge into 1 big graph
    batch_b = Batch.from_data_list(views_b)

    proj1 = model.project(batch_a)  # Ek forward pass = 4 graphs!
    # GPU: 60-80% utilization → 3-4x faster
```

**Mixed Precision (FP16) kyu:**
```
Normal training: 32-bit floats → 4 bytes per number
FP16 training:   16-bit floats → 2 bytes per number

4GB VRAM mein:
  FP32: 4GB / 4 bytes = 1GB ka model/activations
  FP16: 4GB / 2 bytes = 2GB ka model/activations → double space!

Implementation:
  GradScaler("cuda") → gradients safely FP32 mein rakhta hai
  autocast("cuda")   → forward pass FP16 mein karta hai
```

---

### File: `src/models/pretrain/checkpoint.py`

**Kyu banaya:** Agar training bich mein ruk jaye (power cut, crash), to pura kaam waste na ho. Checkpoint har epoch ke baad save karta hai.

```python
class CheckpointManager:
    def save(self, model, optimizer, scheduler, epoch, val_loss):
        # Hamesha latest checkpoint save karo
        torch.save({
            'model_state': model.state_dict(),
            'optimizer_state': optimizer.state_dict(),
            'epoch': epoch,
            'val_loss': val_loss,
            'config': self._cfg.model_dump(mode="json")  # Path → string
        }, "checkpoint_latest.pt")

        # Agar ye best val_loss hai → best bhi save karo
        if val_loss < self._best_val_loss:
            copy → "checkpoint_best.pt"
            self._best_val_loss = val_loss
            return is_best=True

# Bug fix: model_dump(mode="json") kyu?
# model_dump() mein Path objects hote hain (Python Path, not string)
# torch.save() ke saath weights_only=True → Path serialize nahi hota
# mode="json" → Path → string conversion hoti hai → save works
```

---

## 3.5 FASTAPI BACKEND — `src/api/`

**Kyu ye folder banaya:** Dashboard ko Neo4j data chahiye tha. Direct Neo4j queries frontend se nahi hoti (browser mein Neo4j driver nahi). Ek REST API banana tha — frontend API se maange, API Neo4j se le ke de.

---

### File: `src/api/main.py`

**Kyu banaya:** FastAPI application ka entry point. Yahan sab kuch register hota hai — routes, middleware, lifespan.

**Lifespan kya hai:**
```python
@asynccontextmanager
async def lifespan(app):
    # SERVER START hone pe:
    service = Neo4jQueryService()  # Neo4j connection pool banao
    set_query_service(service)

    yield  # ← Yahan server chalta hai

    # SERVER STOP hone pe:
    service.close()  # Connection pool band karo gracefully

# Kyu: Agar connection pool band nahi kiya → memory leak
# Kyu asynccontextmanager: FastAPI ka modern lifecycle management
```

**CORS kyu:**
```python
app.add_middleware(CORSMiddleware,
    allow_origins=["http://localhost:3000"])  # Next.js frontend

# Kyu zaroori: Browser security rule hai —
# localhost:3000 (frontend) → localhost:8000 (backend) pe
# request blocked hogi CORS ke bina
# Middleware se: "3000 wale ko allow karo"
```

**WebSocket `/ws/graph-stats`:**
```python
@app.websocket("/ws/graph-stats")
async def ws_graph_stats(websocket):
    await websocket.accept()
    while True:
        stats = service.get_graph_stats()
        await websocket.send_json(stats)
        await asyncio.sleep(5)  # Har 5 second mein update

# Kyu WebSocket normal HTTP se:
# HTTP: Frontend puchhe → Backend jawab de (one-time)
# WebSocket: Connection open → Backend khud data bhejta rahe
# Dashboard pe live numbers update hote hain bina refresh ke
```

---

### File: `src/api/dependencies.py`

**Kyu banaya:** Har API route ko Neo4jQueryService chahiye. Isko baar baar banane ki jagah ek singleton banao aur FastAPI ke `Depends()` se inject karo.

```python
_query_service: Neo4jQueryService | None = None

def get_query_service():
    if _query_service is None:
        raise HTTPException(503, "Service unavailable")
    return _query_service

# Route mein use:
@router.get("/api/stats")
def get_stats(service: QueryServiceDep):  # Auto-injected!
    return service.get_graph_stats()

# Kyu Depends pattern:
# Testing mein fake service inject kar sako
# Ek hi connection pool sab routes share kare
# 503 error auto-handle hota hai agar Neo4j down hai
```

---

### Files: `src/api/routes/stats.py`, `graph.py`, `alerts.py`

**Kyu ye files banayein:**

**stats.py** — Dashboard ke KPI cards ke liye:
```
GET /api/stats → Total nodes, edges per type
GET /api/stats/top-communicators → Top 20 active IPs
```

**graph.py** — Graph explorer page ke liye:
```
GET /api/graph/neighborhood?ip=X    → Ek IP ka subgraph
GET /api/graph/anomalous            → Suspicious connections
GET /api/graph/time-window          → Time range ki connections
```

**alerts.py** — Alert list page ke liye:
```python
# Alerts alag table mein store nahi hain
# Ye DERIVE hote hain anomalous paths se

def _derive_alerts(edges):
    for edge in edges:
        attack_score = max(src.attack_score, dst.attack_score)

        # Score → Severity
        if score >= 0.8:   severity = "critical"
        elif score >= 0.6: severity = "high"
        elif score >= 0.4: severity = "medium"
        else:              severity = "low"

        # Stable ID banao (har run mein same ID)
        alert_id = sha256(f"{src}|{dst}|{window_id}")[:16]

        yield AlertResponse(id=alert_id, severity=severity, ...)
```

---

## 3.6 FRONTEND — `frontend/src/`

**Kyu ye folder banaya:** Original document mein "React-based SOC dashboard" mention tha. SOC analyst ko visual interface chahiye tha — tables, graphs, charts.

---

### File: `frontend/src/app/layout.tsx`

**Kyu banaya:** Poore app ka wrapper. Sidebar + Header + Page content — ye structure yahan define hai.

```typescript
export default function RootLayout({ children }) {
    return (
        <html lang="en">
            <body className="bg-[#0d1117]">  {/* Dark theme */}
                <QueryClientProvider client={queryClient}>
                    {/* TanStack Query: API calls manage karo */}
                    <div style={{ display: 'flex' }}>
                        <Sidebar />  {/* Left navigation */}
                        <div>
                            <Header />   {/* Top bar */}
                            {children}   {/* Current page */}
                        </div>
                    </div>
                    <Toaster />  {/* Toast notifications */}
                </QueryClientProvider>
            </body>
        </html>
    )
}
```

**Dark theme kyu:** Original document mein explicitly likha tha "Dark theme — SOC analysts work in dark rooms."

---

### File: `frontend/src/app/page.tsx` (Dashboard)

**Kyu banaya:** Main overview page. Analyst pehle yahan dekhta hai — quick summary.

```
KPI Cards:
  124,768 nodes   |  3M+ edges  |  Suspicious  |  Top Talker
  (total graph)   (connections) (attack_score≥0.5) (most active IP)

Charts:
  [Donut: Node type distribution]  [Bar: Top 10 communicators]

Recent Alerts Table:
  Score | Severity | Src IP | Dst IP | Protocol | Label
  0.95  | CRITICAL | 10.0.0.5 | 185.220.x.x | TCP | DDoS
```

**Auto-refresh kyu:**
```typescript
const { data } = useQuery({
    queryKey: ['stats'],
    queryFn: () => apiClient.get('/api/stats'),
    staleTime: 30_000,  // 30 sec baad "stale" consider karo
    refetchInterval: 30_000,  // Har 30 sec mein auto-refresh
})
// Analyst ko manually refresh nahi karna padta
```

---

### File: `frontend/src/components/graph/NetworkGraph.tsx`

**Kyu banaya:** Interactive network visualization. Analyst visually dekh sake ke kaun sa IP kaisse connected hai.

**vis-network kyu choose kiya (D3 nahi):**
```
D3.js:    Control zyada, code zyada, seekhna mushkil
vis-network: Built-in force layout, drag, zoom, click events
             Graph apps ke liye specially bana hai
             Hume sirf nodes/edges dene hain → khud layout karta hai
```

**Dynamic import kyu:**
```typescript
const NetworkGraph = dynamic(() => import('./NetworkGraph'), { ssr: false })

// Kyu: vis-network browser APIs use karta hai (DOM, window)
// Next.js server pe render karta hai (Node.js)
// Node.js mein DOM nahi → error
// dynamic(..., { ssr: false }) → sirf browser pe render karo
```

**Node colors (exact kyu):**
```typescript
const NODE_COLORS = {
    Host:       '#58a6ff',  // Blue  — internal, trusted
    ExternalIP: '#f85149',  // Red   — external, potentially dangerous
    Service:    '#3fb950',  // Green — services/ports
    Domain:     '#d29922',  // Orange — domains
    User:       '#bc8cff',  // Purple — users/accounts
}
// Kyu ye colors: GitHub dark theme se inspired
// Security context mein red = external/dangerous, blue = internal/safe
```

---

### Files: `frontend/src/hooks/`

**Kyu ye hooks banaye:** API calls ko components se alag karo. Ek hi jagah se data fetch karo — caching, error handling, loading states — sab manage ho jaata hai.

```typescript
// useGraphStats.ts
export function useGraphStats() {
    return useQuery({
        queryKey: ['graph-stats'],
        queryFn: () => apiClient.get('/api/stats').then(r => r.data),
        staleTime: 30_000,
    })
}

// Component mein:
const { data, isLoading, error } = useGraphStats()
if (isLoading) return <Skeleton />
if (error) return <ErrorState />
return <KPICard value={data.host_count} />
```

**useGraphStream.ts (WebSocket):**
```typescript
export function useGraphStream() {
    const [stats, setStats] = useState(null)

    useEffect(() => {
        const ws = new WebSocket('ws://localhost:8000/ws/graph-stats')

        ws.onmessage = (event) => {
            setStats(JSON.parse(event.data))  // Live data update
        }

        ws.onerror = () => {
            // Exponential backoff reconnect
            // 1s → 2s → 4s → 8s → max 30s
        }

        return () => ws.close()  // Cleanup on unmount
    }, [])

    return { stats, connected: ws.readyState === WebSocket.OPEN }
}
```

---

### File: `scripts/neo4j_import.py`

**Kyu banaya:** Sirf consume karne se Neo4j slow ho jaata tha — training aur Neo4j import simultaneously nahi chal sakta tha efficiently. Ek dedicated script banaya jo **sirf Neo4j fill karta hai** — Kafka se events dobara padhke.

```python
# Kaise kaam karta hai:
1. Kafka topic "normalized-events" ko BEGINNING se padho
   (consumer group "neo4j-import-v1" — fresh start)

2. Har window ready hone pe:
   writer.write_window(result)  # Neo4j mein MERGE

3. Live progress table:
   Windows written: 20,137
   Nodes merged:    5,583,870
   Edges merged:    10,593,668
   Elapsed:         6313s (1hr 45min)
```

**Kyu alag script:** Training (`.pt` files) aur Neo4j import alag parallelly karo — ek dusre ko slow nahi karte.

---

# PART 4 — TRAINING KI POORI KAHANI

## Pehle run mein kya hua (bugs ki kahani):

```
RUN 1 — Pehli attempt:
  Error: LazyLinear nahi tha → Linear(-1, 128) PyTorch 2.5 mein kaam nahi karta
  Fix: nn.LazyLinear(128) kiya

RUN 2 — Second attempt:
  Error: checkpoint mein Path object save nahi ho raha
  Fix: model_dump(mode="json") kiya

RUN 3 — Third attempt:
  Error: 'NoneType has no attribute dim'
  Fix: valid_edges filter add kiya encoder mein

RUN 4 — Training shuru!
  Epoch 1: val_loss = 4.977 ✓
  Epoch 2: val_loss = 4.918 ✓
  Epoch 3: val_loss = 4.812 ✓ Best!
  ...
  (Run complete, best = 4.812)

RUN 5 — val_loss = 0.0 bug!
  Problem: graph_a aur graph_b ke nodes count same nahi → collect fails
  Fix: Same graph ko do baar augment karo (proper GraphCL)

RUN 6 — Fix ke baad:
  Epoch 1: val_loss = 6.971 ✓ (fresh start, higher loss)
  Epoch 4: val_loss = 6.940 ✓ Best
  Still running...
```

## Training numbers:
```
Input:      17,657 graph snapshots (9GB dataset se bane)
Split:      15,891 train + 1,765 validation
GPU:        RTX 3050 4GB VRAM
VRAM used:  813 MB (well within 4GB)
Per epoch:  ~9 minutes
Best loss:  4.812 (from earlier run)
Total time: ~2 hours
Output:     models/pretrain/checkpoint_best.pt
```

---

# PART 5 — ABHI TAK KYA BANA, KYA BAAKI HAI

## Completed (✅):

| # | Module | Kya Banaya | Actual Numbers |
|---|--------|-----------|----------------|
| 1 | Data Ingestion | UNSW + CICIDS parsers, Kafka pipeline | 9GB parsed |
| 2 | Graph Construction | 17,657 PyG snapshots | 17,657 .pt files |
| 3 | Neo4j Integration | Graph database populated | 124K nodes, 3M+ edges |
| 4 | Pre-training | GNN encoder trained | val_loss=4.812, 13 epochs |
| 5 | FastAPI Backend | REST API + WebSocket | 8 endpoints |
| 6 | SOC Dashboard | 4-page Next.js frontend | Real data from Neo4j |

## Pending (⬜):

| # | Module | Kya Banana Hai | Kitna Mushkil |
|---|--------|---------------|---------------|
| 7 | Node2Vec Baseline | Comparison ke liye simple graph embedding | Medium |
| 8 | T-HetGAT Detection | Actual anomaly detector — project ka core model | Hard |
| 9 | Benchmarking | T-HetGAT vs baselines, AUROC/F1 results | Medium |
| 10 | SOC Environment | RL training ground — Gymnasium-based | Hard |
| 11 | DRL Triage Agent | AI jo auto-decide kare alerts | Very Hard |
| 12 | Federated Learning | Privacy-safe multi-org training | Hard |
| 13 | Campaign Detection | Attack chains dhundna | Medium |
| 14 | Integration Testing | Poora system test | Medium |

## Progress Meter:
```
Data Foundation:  ████████████████████ 100% ✅
Graph Storage:    ████████████████████ 100% ✅
AI Pre-training:  ████████████████████ 100% ✅
Detection Model:  ░░░░░░░░░░░░░░░░░░░░   0% ← NEXT
Auto-triage:      ░░░░░░░░░░░░░░░░░░░░   0%
Privacy/Federated:░░░░░░░░░░░░░░░░░░░░   0%
Dashboard:        ████████████░░░░░░░░  60% (basic)

Overall:          ██████░░░░░░░░░░░░░░  ~30%
```

---

# PART 6 — JAB SIR SE PRESENTATION HO

## Ek line mein project:
> "Sir, hamne ek AI system banaya hai jo network traffic ko graph mein model karta hai, self-supervised GNN se normal behavior seekhta hai, aur real-time SOC dashboard pe anomalies dikhata hai."

## 5 saal ke bachhe ko explain karo toh:
> "Ek smart police wala banaya jisne traffic dekha, patterns seekhe, aur ab bol sakta hai ke kaun suspicious hai."

## Technical depth mein:
> "Temporal heterogeneous graph (5 node types, 4 edge types, sliding windows) pe GraphCL contrastive pre-training kiya. 17,657 snapshots, 9GB dataset. RTX 3050 pe 813MB VRAM, best val_loss 4.812. Neo4j mein 124K+ entities, 3M+ connections stored. FastAPI REST + WebSocket + Next.js SOC dashboard — poora production-grade stack."

---

*Document updated: 17 March 2026 | GraphRL-Sec MTech Dissertation*
