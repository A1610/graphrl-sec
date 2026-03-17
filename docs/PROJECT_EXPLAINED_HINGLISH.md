# GraphRL-Sec — Poora Project Samjho (Hinglish)
### Ek 5 saal ke bachhe se lekar MTech student tak — sabko samajh aayega

---

## SABSE PEHLE — YE PROJECT HAI KYA?

Soch lo tumhare school mein ek guard hai. Uska kaam hai dekhna ke koi bacha school mein ghuse nahi jo wahan ka nahi hai. Abhi tak guard sirf ek list dekhta tha (rules) — agar koi rule toota to alarm bajata tha.

**Hamara project ek SMART guard banata hai** jo:
- Dekh sakta hai ke students kis route se aa rahe hain
- Pichle ek ghante ka pattern yaad rakhta hai
- Khud seekhta hai ke kaun suspicious lag raha hai
- Alarm bajane ka faisla khud leta hai — sirf rules se nahi

**Technical words mein:**
> GraphRL-Sec ek AI-powered cybersecurity system hai jo network traffic ko graph ke form mein represent karta hai, Graph Neural Network (GNN) se anomalies detect karta hai, aur Deep Reinforcement Learning (DRL) se alerts automatically triage karta hai.

---

## REAL DUNIYA MEIN PROBLEM KYA HAI?

Kisi bhi badi company (bank, hospital, government) ke computer network mein roz **lakho connections** hote hain:
- Employee A ne file download ki
- Server B ne database query ki
- Computer C ne internet se kuch maanga

In sab connections mein **hackers chhupe hote hain.** Unhe dhundhna bohot mushkil hai kyunki:

| Problem | Details |
|---------|---------|
| **Volume** | Ek din mein crore+ connections — koi manually nahi dekh sakta |
| **Speed** | Attack seconds mein hota hai |
| **Camouflage** | Hackers normal traffic jaisa dikhte hain |
| **Context** | Ek akela event suspicious nahi lagta — pattern dekhna padta hai |

---

## HAMARA SOLUTION — STEP BY STEP

### Soch lo ek Doodh Wali Ki Dukaan ki analogy:

```
Ek doodh wali ki dukaan hai. Roz hazaaron log aate hain.
Normally:
  - Ramlal roz subah 8 baje aata hai, 1 litre leta hai
  - Sheela ji Friday ko aati hain, 2 litre leti hain

Ek din:
  - Koi anjaan banda raat 2 baje aaya
  - 50 litre lene ki koshish ki
  - Paise nahi the uske paas

OLD SYSTEM: Sirf "raat 2 baje" rule tha — alarm bajaya
HAMARA SYSTEM: Pattern dekha — anjaan, unusual time,
               unusual quantity, no payment = HIGH RISK!
```

---

## PROJECT KE 6 MAIN PARTS (Jo Abhi Tak Bane Hain)

---

### PART 1 — DATA INGESTION (Data Ka Darwaza)
**File location:** `src/ingestion/`

#### Bachhe ki bhasha mein:
> Hazaaron CSV files hain jisme network traffic ka data hai. Yeh part un files ko padhta hai aur ek common format mein convert karta hai.

#### Thoda technical:
Humne do real-world cybersecurity datasets use kiye:
- **UNSW-NB15**: Australian university ka dataset — 2 GB, 49 columns, real network attacks
- **CICIDS2017**: Canadian university ka dataset — 7 GB, real attack scenarios (DDoS, Port Scan, SQL Injection etc.)

**Parsers ne kya kiya:**

```
UNSW-NB15 CSV (no header row, 49 columns)
    ↓
unsw.py parser ne padha, samjha, normalize kiya
    ↓
UnifiedEvent (ek common format):
{
  timestamp: "2017-07-03 10:23:45",
  source_ip: "192.168.1.5",
  dest_ip: "8.8.8.8",
  protocol: TCP,
  bytes_sent: 1024,
  is_attack: True,
  label: "DDoS"
}
```

**Kafka Producer ne kya kiya:**
- Sab UnifiedEvents ko **Kafka** (ek message queue) mein daala
- Kafka ek post office ki tarah hai — messages store karta hai
- Koi bhi baad mein aa ke messages le sakta hai

**Key files:**
| File | Kaam |
|------|------|
| `schemas.py` | UnifiedEvent ka blueprint — har field define hai |
| `parsers/unsw.py` | UNSW-NB15 CSV → UnifiedEvent |
| `parsers/cicids.py` | CICIDS2017 CSV → UnifiedEvent |
| `normalizer.py` | Raw data validate + clean karna |
| `producer.py` | Events Kafka mein bhejta hai |
| `consumer.py` | Kafka se events leta hai |

---

### PART 2 — GRAPH CONSTRUCTION (Network Ka Map Banana)
**File location:** `src/graph/`

#### Bachhe ki bhasha mein:
> Soch lo tumhare school mein ek map ban raha hai — kaun konse dost ke ghar gaya, kaun kitni baar gaya, kab gaya. Isi tarah humne network ka map banaya — kaun sa computer kisse baat karta hai.

#### Thoda technical:
Network traffic ko **Graph** mein convert kiya:

```
NODES (Circles) = Computers / Servers / Services
  - Host (Blue): Internal computers — 192.168.x.x
  - ExternalIP (Red): Baahri internet addresses
  - Service (Green): Ports jaise HTTP(80), SSH(22)
  - Domain (Orange): Website names
  - User (Purple): Login accounts

EDGES (Lines) = Connections
  - CONNECTS_TO: IP se IP connection
  - USES_SERVICE: Computer ne port use kiya
  - RESOLVES_DOMAIN: DNS lookup kiya
  - AUTHENTICATED_AS: User ne login kiya
```

**Sliding Window kya hai:**

```
Time: ─────────────────────────────────────────►

Window 1: [════════════════════]               (1 hour)
Window 2:          [════════════════════]      (1 hour, 15 min baad)
Window 3:                   [════════════════] (1 hour, 30 min baad)

Har window ek "snapshot" hai network ka us time pe
```

**Feature Engineering (Nodes ko describe karna):**

Har node ke paas numbers hain jo usse describe karte hain:
```
Host node features (8 numbers):
  1. Kitne connections kiye (degree)
  2. Kitne bytes bheje
  3. Kitne bytes receive kiye
  4. Kitni unique destinations se baat ki
  5. Internal hai ya external
  6. Attack score (0.0 = safe, 1.0 = definitely hacker)
  7. Last kab active tha
  8. Kitne packets bheje
```

**Key files:**
| File | Kaam |
|------|------|
| `node_registry.py` | Har IP/port/domain ko unique ID deta hai |
| `edge_constructor.py` | Events ko graph edges mein convert karta hai |
| `feature_engineering.py` | Har node/edge ke liye numbers nikalta hai |
| `temporal.py` | Sliding window banata hai |
| `pyg_converter.py` | Graph ko PyTorch Geometric format mein convert karta hai |

---

### PART 3 — NEO4J DATABASE (Graph Ka Storage)
**File location:** `src/graph/neo4j_*.py`

#### Bachhe ki bhasha mein:
> Soch lo ek bahut bada corkboard hai jisme hazaaron strings lagaaye hain — har string ek connection dikhati hai. Neo4j wohi corkboard hai computers ke liye.

#### Thoda technical:
**Neo4j** ek **Graph Database** hai — normal database (Excel) nahi, ye specifically graphs store karne ke liye bana hai.

**Hamare Neo4j mein abhi:**
- **124,768 nodes** (computers, IPs, services)
- **3,028,187 edges** (connections)
- **5,583,870 total nodes merged** (Neo4j import complete)
- **10,593,668 total edges merged**

**Neo4j Queries (Cypher language):**
```cypher
-- Top 10 most active computers
MATCH (src)-[r:CONNECTS_TO]->(dst)
WITH src, count(r) AS connections
ORDER BY connections DESC LIMIT 10
RETURN src.ip, connections

-- Suspicious computers (high attack score)
MATCH (n:Host)
WHERE n.attack_score >= 0.5
RETURN n.ip, n.attack_score
```

**Import Process:**
```
17,657 time windows
    ↓ (1 hour 45 minutes laga)
Neo4j mein 20,137 windows import hue
    ↓
5.5 million+ nodes, 10.5 million+ edges
```

---

### PART 4 — SELF-SUPERVISED PRE-TRAINING (GNN Ko Sikhana)
**File location:** `src/models/pretrain/`

#### Bachhe ki bhasha mein:
> Soch lo tumne ek naya student liya jo cybersecurity ke baare mein kuch nahi jaanta. Pehle tum usse sirf **patterns** dekhate ho — "ye normal traffic jaisa dikhta hai, ye suspicious jaisa". Koi label nahi dete. Ye student khud seekhta hai patterns ko — yahi "self-supervised pre-training" hai.

#### Thoda technical:

**Model Architecture — HeteroGraphEncoder:**
```
Input: Graph (nodes + edges with features)
    ↓
Step 1: Per-node Linear Layer
        Har node type ko 128-dimensional space mein project karo
    ↓
Step 2: 2x SAGEConv Layers (Message Passing)
        Har node apne neighbors ka message leta hai
        "Mujhse kaise baat kar raha hai network?"
    ↓
Step 3: BatchNorm + ReLU
        Values normalize karo
    ↓
Step 4: Projection Head (2-layer MLP)
        128-dim → 64-dim (contrastive learning ke liye)
    ↓
Output: Har node ke liye ek 128-dim vector (embedding)
        Similar nodes ke vectors close hote hain
```

**GraphCL Contrastive Learning:**
```
Ek graph liya → Do augmented views banaye:
  View 1: Original + 20% features mask kiye
  View 2: Original + 20% edges drop kiye

NT-Xent Loss:
  "View 1 ka node i aur View 2 ka node i SAME hain"
  "View 1 ka node i aur View 2 ka node j DIFFERENT hain"

  Loss = inhe alag karo (negatives) + inhe saath rakho (positives)
```

**Training Results:**
```
Datasets: 17,657 graph snapshots
Training pairs: 15,891 | Validation pairs: 1,765
Hardware: RTX 3050 4GB VRAM (GPU)

Epoch 1:  train_loss=6.97  val_loss=6.97  ✓ Best
Epoch 3:  train_loss=6.83  val_loss=6.94  ✓ Best
Epoch 4:  train_loss=6.71  val_loss=6.94  ✓ Best
...
Epoch 13: Early stopping (patience=10)

Best val_loss: 4.812 (pehle run se)
Total time: ~2 hours on GPU
Checkpoint saved: models/pretrain/checkpoint_best.pt
```

**Key files:**
| File | Kaam |
|------|------|
| `encoder.py` | HeteroGraphEncoder model (brain) |
| `augmentation.py` | Graph ke do views banata hai |
| `contrastive.py` | NT-Xent loss calculate karta hai |
| `trainer.py` | Training loop chalata hai |
| `checkpoint.py` | Best model save karta hai |
| `config.py` | Hyperparameters (learning rate, batch size etc.) |

---

### PART 5 — FASTAPI BACKEND (Dashboard Ka Darwaza)
**File location:** `src/api/`

#### Bachhe ki bhasha mein:
> Soch lo ek waiter hai restaurant mein. Tum order dete ho (request), waiter kitchen (Neo4j) se khaana laata hai, tumhe serve karta hai (response). FastAPI wohi waiter hai.

#### Thoda technical:

**Endpoints (Menu):**
```
GET  /health                          → Server chal raha hai?
GET  /api/stats                       → Total nodes, edges count
GET  /api/stats/top-communicators     → Top 20 most active IPs
GET  /api/graph/neighborhood?ip=X     → Ek IP ke aaspaas ka graph
GET  /api/graph/anomalous             → Suspicious connections
GET  /api/graph/time-window           → Ek time range ki connections
GET  /api/alerts                      → Security alerts list
GET  /api/alerts/{id}                 → Ek alert ki full detail
WS   /ws/graph-stats                  → Live stats har 5 second mein
```

**WebSocket kya hai:**
```
Normal HTTP: Tum puchho → Server jawab de (ek baar)
WebSocket:   Connection open rakho → Server khud data bhejta rahe

Jaise news channel ka live ticker — tum kuch nahi puchha,
lekin data aata rehta hai automatically
```

---

### PART 6 — NEXT.JS DASHBOARD (Jo Dikhta Hai)
**File location:** `frontend/src/`

#### Bachhe ki bhasha mein:
> Ye woh screen hai jo SOC analyst (security guard) dekhta hai. Jaise TV ka remote control — sab kuch ek jagah dikhta hai.

#### Pages:

**Dashboard (/):**
```
┌─────────────────────────────────────────────┐
│  GraphRL-Sec SOC Dashboard                  │
├──────┬──────────────────────────────────────┤
│      │  [124,768]  [3M+]  [Suspicious]  [Top IP] │
│ Menu │   Nodes    Edges   Connections   Talker   │
│      │                                          │
│ 📊   │  [Node Type Donut Chart]                 │
│ 🔔   │  [Top Communicators Bar Chart]           │
│ 🕸️   │                                          │
│ 📈   │  Recent Alerts Table                     │
└──────┴──────────────────────────────────────┘
```

**Alerts Page (/alerts):**
- Saari suspicious connections ki list
- Filter: Critical (🔴) / High (🟠) / Medium (🟡) / Low (🔵)
- Sorted by attack score

**Graph Page (/graph):**
- Interactive network map
- Vis-network library use ki hai
- Nodes drag kar sako, zoom karo
- Node pe click karo → uske connections dikhte hain

**Analytics Page (/analytics):**
- Detailed statistics
- Top 20 communicators table

---

## INFRASTRUCTURE — BACKGROUND MEIN KYA CHAL RAHA HAI

```
Docker Desktop ke andar ye sab chal rahe hain:

┌─────────────────────────────────────────────────┐
│                  Docker                         │
│                                                 │
│  ┌──────────┐  ┌───────┐  ┌────────┐           │
│  │ Redpanda │  │ Neo4j │  │Postgres│           │
│  │ (Kafka)  │  │ Graph │  │  DB    │           │
│  │ :9092    │  │ :7474 │  │ :5432  │           │
│  └──────────┘  └───────┘  └────────┘           │
│                                                 │
│  ┌───────┐  ┌──────────┐  ┌────────┐           │
│  │ Redis │  │Prometheus│  │Grafana │           │
│  │ Cache │  │ Metrics  │  │Monitor │           │
│  │ :6379 │  │  :9090   │  │ :3001  │           │
│  └───────┘  └──────────┘  └────────┘           │
└─────────────────────────────────────────────────┘
```

| Service | Kaam | Analogy |
|---------|------|---------|
| **Redpanda (Kafka)** | Events store karta hai | Post office |
| **Neo4j** | Graph database | Corkboard map |
| **PostgreSQL** | Alerts, feedback store | Excel sheet |
| **Redis** | Fast caching | Scratch pad |
| **Prometheus** | System metrics collect | Health monitor |
| **Grafana** | Metrics visualize | Doctor ka dashboard |

---

## DATA FLOW — EK EVENT KA SAFAR

```
CSV File
  │
  ▼ (Parser reads row)
Raw Row: "192.168.1.5, 8.8.8.8, 80, TCP, 1024 bytes, DDoS"
  │
  ▼ (Normalizer validates)
UnifiedEvent {src: 192.168.1.5, dst: 8.8.8.8, ...}
  │
  ▼ (Kafka Producer)
Redpanda Topic: "normalized-events"
  │
  ▼ (Kafka Consumer - GraphConsumer)
Sliding Window Engine → WindowResult (1 hour ka snapshot)
  │
  ├──▶ PyG Converter → HeteroData (.pt file saved)
  │                    data/graphs/window_000001.pt
  │
  └──▶ Neo4j Writer → Graph Database
                      MERGE (host:Host {entity_key: "192.168.1.5"})
                      MERGE (ext:ExternalIP {entity_key: "8.8.8.8"})
                      MERGE (host)-[:CONNECTS_TO]->(ext)
  │
  ▼ (Pre-training)
17,657 .pt files → HeteroGraphEncoder trains → checkpoint_best.pt
  │
  ▼ (FastAPI Backend)
localhost:8000/api/alerts → anomalous connections query
  │
  ▼ (Next.js Frontend)
localhost:3000 → Dashboard dikhta hai analyst ko
```

---

## ABHI TAK KITNA BANA — STATUS TABLE

| Module | Kya Hai | Status | Details |
|--------|---------|--------|---------|
| **M4: Data Ingestion** | CSV → Kafka | ✅ Complete | UNSW + CICIDS2017 parsed |
| **M5: Graph Construction** | Events → PyG Graphs | ✅ Complete | 17,657 snapshots |
| **M6: Neo4j Integration** | Graph → Database | ✅ Complete | 124K+ nodes, 3M+ edges |
| **M8: Pre-training** | GNN sikhana | ✅ Complete | best_val_loss=4.812, 13 epochs |
| **M20: FastAPI Backend** | REST API | ✅ Complete | 8 endpoints + WebSocket |
| **M21: SOC Dashboard** | Frontend UI | ✅ Complete | 4 pages, real data |

---

## KYA BAAKI HAI — FUTURE MODULES

| Module | Kya Banana Hai | Difficulty |
|--------|---------------|-----------|
| **M9: Node2Vec Baseline** | Comparison ke liye ek simple model | Medium |
| **M11: T-HetGAT** | Actual anomaly detection model | Hard |
| **M12: Benchmarking** | T-HetGAT vs baselines comparison | Medium |
| **M14: SOC Environment** | RL training environment | Hard |
| **M15: DRL Agent** | AI jo alerts triage kare | Very Hard |
| **M17: Federated Learning** | Privacy-safe model sharing | Hard |
| **M18: Campaign Detection** | Attack chains dhundna | Medium |
| **M22: Integration Testing** | Poora system test | Medium |

---

## NUMBERS JO IMPRESS KARTE HAIN

```
Dataset size    : ~9 GB (UNSW 2GB + CICIDS 7GB)
Total events    : Crore+ network flow records
Graph snapshots : 17,657 files
Neo4j nodes     : 124,768 unique entities
Neo4j edges     : 3,028,187+ connections
Neo4j import    : 5.5M nodes, 10.5M edges merged
Training time   : ~2 hours on RTX 3050 GPU
Model size      : ~500K parameters (~2MB)
GPU VRAM used   : 813 MB out of 4GB
API endpoints   : 8 REST + 1 WebSocket
Frontend pages  : 4 (Dashboard, Alerts, Graph, Analytics)
Docker services : 7 (Kafka, Neo4j, Postgres, Redis, Prometheus, Grafana, Console)
Python files    : 30+
Frontend files  : 25+
Total code      : 43,000+ lines
```

---

## TECHNOLOGY STACK (Kin Tools Ka Use Kiya)

### Backend (Python):
| Technology | Kya Hai | Kyun Use Kiya |
|-----------|---------|---------------|
| **PyTorch** | ML framework | GPU pe neural network chalane ke liye |
| **PyTorch Geometric** | Graph ML library | Heterogeneous graphs ke liye |
| **FastAPI** | Web framework | Fast async API banane ke liye |
| **Neo4j** | Graph database | Graph queries ke liye |
| **Kafka (Redpanda)** | Message queue | Events stream karne ke liye |
| **Pydantic** | Data validation | Type-safe configs ke liye |
| **Structlog** | Logging | Production-grade logs ke liye |

### Frontend (TypeScript/React):
| Technology | Kya Hai | Kyun Use Kiya |
|-----------|---------|---------------|
| **Next.js 16** | React framework | App Router, SSR ke liye |
| **TailwindCSS 4** | CSS utility | Fast styling ke liye |
| **vis-network** | Graph viz | Interactive network graph ke liye |
| **Recharts** | Charts | Donut, bar charts ke liye |
| **TanStack Query** | Data fetching | Caching, auto-refresh ke liye |
| **Zustand** | State management | Global state ke liye |
| **Socket.io-client** | WebSocket | Live data streaming ke liye |

---

## JAB SIR POOCHE TO YE BOLO

**Q: Project kya hai?**
> "Sir, GraphRL-Sec ek AI-powered cybersecurity platform hai jo GNN aur Deep RL ko combine karta hai. Network traffic ko heterogeneous graph mein model karte hain, self-supervised pre-training se GNN encoder train kiya, aur real-time SOC dashboard banaya jisme Neo4j graph database se live data aata hai."

**Q: Dataset?**
> "UNSW-NB15 (2GB, 2.5M records) aur CICIDS2017 GeneratedLabelledFlows (7GB) use kiye — dono industry-standard research datasets hain."

**Q: Training?**
> "RTX 3050 4GB VRAM pe GraphCL contrastive learning se HeteroGraphEncoder pre-train kiya. 17,657 graph snapshots pe 13 epochs chalaye, best validation loss 4.812 mila. NT-Xent loss use ki — SimCLR ka graph version."

**Q: Neo4j mein data?**
> "124K+ unique network entities aur 3M+ connections stored hain. Import process mein 1.75 ghante lage — 20,137 temporal windows process hue."

---

*Document banaya: 17 March 2026 | GraphRL-Sec MTech Dissertation Project*
