# GraphRL-Sec — Complete Setup Guide

Ye guide tumhe step-by-step batayegi ke fresh system pe poora project kaise chalao.
Isko follow karo aur project exactly wahan se start hoga jahan tune chhoda tha.

---

## Prerequisites — Pehle ye install karo

### 1. Git
- Download: https://git-scm.com/download/win
- Install karo (default settings theek hain)
- Verify: `git --version`

### 2. Python 3.10
- Download: https://www.python.org/downloads/release/python-31011/
- **IMPORTANT**: Install karte waqt **"Add Python to PATH"** checkbox zaroor tick karo
- Verify: `python --version` → `Python 3.10.x` dikhna chahiye

### 3. Node.js (v20 LTS)
- Download: https://nodejs.org/en/download (LTS version)
- Install karo (default settings)
- Verify: `node --version` aur `npm --version`

### 4. Docker Desktop
- Download: https://www.docker.com/products/docker-desktop/
- Install karo aur system restart karo
- Docker Desktop open karo aur wait karo jab tak green (running) ho jaye
- Verify: `docker --version`

### 5. CUDA Toolkit (agar NVIDIA GPU hai)
- Download: https://developer.nvidia.com/cuda-downloads
- Apni GPU ke hisaab se version choose karo (RTX 3050 → CUDA 12.x)
- Verify: `nvidia-smi`

---

## Step 1 — GitHub se Project Clone karo

PowerShell ya Terminal kholo aur ye commands chalao:

```powershell
cd D:\
git clone https://github.com/A1610/graphrl-sec.git
cd graphrl-sec
```

---

## Step 2 — Environment File Banao

```powershell
copy .env.example .env
```

`.env` file ko Notepad me kholo aur check karo — default values theek hain, kuch change karne ki zarurat nahi.

---

## Step 3 — Python Virtual Environment Banao

```powershell
python -m venv venv
venv\Scripts\activate
```

Ab terminal me `(venv)` dikhna chahiye. Phir sari Python dependencies install karo:

```powershell
pip install -r requirements.txt
```

> Ye thoda time lega — ~5-10 minutes. PyTorch bada package hai.

---

## Step 4 — Frontend Dependencies Install karo

```powershell
cd frontend
npm install
cd ..
```

---

## Step 5 — Docker Services Start karo

Docker Desktop open hona chahiye. Phir:

```powershell
docker-compose up -d
```

Ye start karega:
- **Kafka (Redpanda)** — port 9092
- **Neo4j** — port 7474 (browser), 7687 (bolt)
- **PostgreSQL** — port 5432
- **Redis** — port 6379
- **Prometheus + Grafana** — ports 9090, 3001

Verify karo sab chal rahe hain:
```powershell
docker ps
```

Sab containers `Up` status me dikhne chahiye.

Neo4j ready hone me ~30 seconds lagte hain. Browser me check karo:
- Open: http://localhost:7474
- Username: `neo4j`
- Password: `graphrlsec123`

---

## Step 6 — Data Folders Banao

```powershell
mkdir data\raw\unsw
mkdir data\raw\cicids
mkdir data\graphs
mkdir models\pretrain
mkdir models\thetgat
```

---

## Step 7 — Datasets Download karo

### UNSW-NB15 Dataset
1. Jao: https://research.unsw.edu.au/projects/unsw-nb15-dataset
2. "UNSW-NB15 - CSV Files" download karo
3. Ye 4 files chahiye:
   - `UNSW-NB15_1.csv`
   - `UNSW-NB15_2.csv`
   - `UNSW-NB15_3.csv`
   - `UNSW-NB15_4.csv`
4. Inhe dalo: `data\raw\unsw\`

### CICIDS 2017 Dataset
1. Jao: https://www.unb.ca/cic/datasets/ids-2017.html
2. "GeneratedLabelledFlows" download karo (ZIP file)
3. ZIP extract karo
4. Saari CSV files dalo: `data\raw\cicids\`

---

## Step 8 — Data Ingest karo (CSV → Kafka → .pt files + Neo4j)

Venv active honi chahiye. Ye commands ek-ek karke chalao:

### UNSW-NB15 ingest:
```powershell
venv\Scripts\activate
python -m src.ingestion.cli ingest --dataset unsw --path data\raw\unsw --mode batch
```

### CICIDS2017 ingest:
```powershell
python -m src.ingestion.cli ingest --dataset cicids --path data\raw\cicids --mode batch
```

### Kafka events ko graphs me convert karo (.pt files banao):
```powershell
python -m src.ingestion.cli consume --snapshot-dir data\graphs --neo4j
```

> Ye **lamba process** hai — ghanton lag sakte hain. Isko background me chalao ya raat ko chhod do.
> Complete hone par `data\graphs\` me ~17,657 `.pt` files hongi.

---

## Step 8b — Neo4j me Data Dalo (Graph Database Populate karo)

> **Ye step zaroori hai** — Neo4j sirf us machine pe accessible hota hai jahan Docker chal raha ho.
> Dusri machine pe clone karo to Neo4j empty hogi, dobara populate karna padega.

Step 8 complete hone ke baad (`.pt` files ban jayein), ek **naya terminal** kholo:

```powershell
cd D:\graphrl-sec
venv\Scripts\activate
python scripts\neo4j_import.py
```

Output kuch aisa dikhega:
```
Neo4j connected.
Press Ctrl+C to stop gracefully.

Windows written : 1,250
Nodes merged    : 45,000
Edges merged    : 120,000
Elapsed         : 300s
```

> Ye bhi **2-3 ghante** ka kaam hai. Raat ko chhod do.
> Complete hone par Neo4j me ~124,000+ nodes aur ~3,000,000+ edges honge.
>
> **Verify karo**: Browser kholo → http://localhost:7474
> Query run karo: `MATCH (n) RETURN count(n)` → ~124,000 dikhna chahiye

---

## Step 9 — GNN Pre-Training (Self-Supervised HeteroGraphEncoder)

Jab `data\graphs\` me `.pt` files aa jayein (Step 8 complete ho), tab:

```powershell
venv\Scripts\activate
python -m src.models.pretrain.runner
```

Ye GPU pe chalega. Output kuch aisa dikhega:
```
pretrain_start    device=cuda  graphs_dir=data\graphs
snapshots_loaded  count=17657
data_split        train_pairs=15891  val_pairs=1765
epoch=1  train_loss=6.97  val_loss=6.97  gpu_mb=813
epoch=2  train_loss=5.84  val_loss=5.91  best=True
...
early_stopping    epoch=22  patience=10
pretrain_complete best_val_loss=4.21
```

| Setting | Value |
|---------|-------|
| GPU VRAM used | ~813 MB |
| Time per epoch | ~9 minutes |
| Expected total | ~2–4 hours |
| Best model saved | `models\pretrain\checkpoint_best.pt` |

> **Shortcut**: Agar pehle se trained checkpoint hai (Google Drive / USB se copy kiya):
> `models\pretrain\checkpoint_best.pt` rakh do aur seedha Step 10 pe jao.

---

## Step 10 — T-HetGAT Training (Anomaly Detection Model)

> **Ye Step 9 ke baad karna hai** — `models\pretrain\checkpoint_best.pt` hona chahiye.

```powershell
venv\Scripts\activate
python -m src.models.thetgat.runner
```

Ye automatically karega:
1. `data\graphs\` me saare 17,657 window files discover karta hai
2. Stratified train/val/test split karta hai (80/10/10) — attack windows alag rakhta hai taaki har split me dono classes hon
3. Pretrained HeteroGraphEncoder load karta hai `models\pretrain\checkpoint_best.pt` se
4. **Phase A** (5 epochs): Encoder frozen, sirf T-HetGAT layers train hoti hain
5. **Phase B** (remaining epochs): Full end-to-end fine-tuning with early stopping
6. Best checkpoint save hoti hai `models\thetgat\thetgat_best.pt` pe
7. Test set pe evaluate karta hai aur metrics print karta hai

Output kuch aisa dikhega:
```
Model parameters: 2,847,233 total | 487,041 trainable (encoder frozen initially)

phase_A_start   freeze_epochs=5
epoch=0  train_loss=0.312  val_loss=0.289  val_auroc=0.7821
epoch=1  train_loss=0.241  val_loss=0.198  val_auroc=0.8934  best=True
...
phase_B_start   epoch=5
epoch=5  train_loss=0.089  val_loss=0.071  val_auroc=0.9812  best=True
...
early_stopping  epoch=23  best_auroc=0.9847

============================================================
  T-HetGAT Evaluation Results
============================================================
  Test windows : 1,766
  Attack       : 316  (17.9%)
  Normal       : 1,450
------------------------------------------------------------
  AUROC        : 0.9847  [BEATS baseline 0.9804]
  Avg Precision: 0.9123
  Best F1      : 0.8734  [BEATS baseline 0.4912]
  Threshold    : 0.42
  Precision    : 0.8901
  Recall       : 0.8576
------------------------------------------------------------
  Confusion Matrix (at best-F1 threshold):
    TP=271  FP=33
    FN=45   TN=1417
------------------------------------------------------------
  AUROC  improvement vs baseline: +0.0043
  F1     improvement vs baseline: +0.3822
============================================================
```

| Setting | Value |
|---------|-------|
| GPU VRAM used | ~1.2 GB |
| Expected training time | ~3–7 hours |
| Best model saved | `models\thetgat\thetgat_best.pt` |
| Latest checkpoint | `models\thetgat\thetgat_latest.pt` |
| Training history | `models\thetgat\thetgat_train_history.json` |
| Eval results | `models\thetgat\thetgat_eval_results.json` |

> **Shortcut**: Agar trained T-HetGAT checkpoint hai (USB/Drive se):
> `models\thetgat\thetgat_best.pt` rakh do — FastAPI backend is se load karega.

---

## Step 11 — Poora Project Chalao (Sab ek saath)

**3 alag terminals open karo:**

### Terminal 1 — FastAPI Backend:
```powershell
cd D:\graphrl-sec
venv\Scripts\activate
python -m src.api.run
```
Backend chal raha hoga: http://localhost:8000
API docs: http://localhost:8000/docs

### Terminal 2 — Next.js Frontend:
```powershell
cd D:\graphrl-sec\frontend
npm run dev
```
Dashboard khulega: http://localhost:3000

### Terminal 3 — Docker (agar band hai to):
```powershell
cd D:\graphrl-sec
docker-compose up -d
```

Teeno chal rahe hain? Browser me http://localhost:3000 kholo — dashboard live hai.

---

## Dashboard Pages

| Page | URL | Kya dikhta hai |
|------|-----|----------------|
| Dashboard | http://localhost:3000 | KPI cards, node/edge charts, recent alerts — main overview |
| Alerts | http://localhost:3000/alerts | Saare anomalous connections — filter by severity, paginated |
| Graph Explorer | http://localhost:3000/graph | Interactive force-directed network graph |
| Analytics | http://localhost:3000/analytics | Detailed stats + top 20 communicators table |
| Neo4j Browser | http://localhost:7474 | Direct graph database — Cypher queries |
| API Docs | http://localhost:8000/docs | FastAPI Swagger UI — sab endpoints |
| Grafana | http://localhost:3001 | System monitoring metrics |

### Dashboard Features (aaj add kiye):
- **Har card clickable** → bottom se slide-up drawer aata hai jo us metric ki full explanation deta hai
- **Page Info button** → har page ke header me top-right side pe `[ℹ Page Info]` button hai — click karo to us pure page ki in-depth explanation khulti hai
- **Live status** → Page Info ke baaju me `● Live` / `● Connecting` status dikhta hai

---

## Saved Checkpoints Transfer karna

Agar apni current machine se dusri machine pe le jaana hai:

### Current machine pe (export):
```powershell
# USB ya Google Drive pe copy karo
copy models\pretrain\checkpoint_best.pt <USB-drive-path>\
copy models\thetgat\thetgat_best.pt <USB-drive-path>\
```

### Nai machine pe (import):
```powershell
# Step 6 ke baad ye karo
mkdir models\pretrain
mkdir models\thetgat
copy <USB-drive-path>\checkpoint_best.pt models\pretrain\
copy <USB-drive-path>\thetgat_best.pt models\thetgat\
```

Checkpoints copy ke baad seedha **Step 11** pe jao — training dobara nahi karni padegi.

---

## Common Errors aur Fixes

### "Neo4j unreachable"
```powershell
docker ps          # check kar raha hai?
docker-compose up -d   # nahi chal raha to start karo
```

### "No window_*.pt files found"
Step 8 abhi complete nahi hua. `data\graphs\` me files check karo:
```powershell
dir data\graphs\*.pt | measure -line
```
~17,657 files honi chahiye.

### "Pretrained encoder checkpoint not found"
`models\pretrain\checkpoint_best.pt` exist karta hai? Step 9 pehle complete karo ya USB se copy karo.

### "CUDA not available"
```powershell
nvidia-smi    # GPU detect ho rahi hai?
```
Training CPU pe bhi chalegi (slow ~10x): `.env` me `DEVICE=cpu` set karo.

### "Module not found"
Venv active hai? Terminal me `(venv)` dikhna chahiye:
```powershell
venv\Scripts\activate
```

### Frontend "Cannot connect to API"
Terminal 1 me backend chal raha hai? `http://localhost:8000/docs` browser me kholo — agar nahi khulta to backend restart karo.

### Docker port already in use
```powershell
docker-compose down
docker-compose up -d
```

### BatchNorm error during T-HetGAT training
Ye automatically handle hota hai — `encoder.eval()` training loop me call hota hai. Agar phir bhi error aaye to `.env` me `DEVICE=cpu` set karo.

---

## Project Structure (Reference)

```
graphrl-sec/
├── src/
│   ├── ingestion/          # CSV parsers, Kafka producer/consumer
│   ├── graph/              # Neo4j writer, PyG converter, temporal windows
│   ├── models/
│   │   ├── pretrain/       # HeteroGraphEncoder, NT-Xent loss, trainer
│   │   └── thetgat/        # T-HetGAT anomaly detection
│   │       ├── config.py         # Hyperparameters
│   │       ├── model.py          # THetGATModel + AnomalyScorer
│   │       ├── hetgat_layer.py   # TemporalGATConv + HeteroTemporalGATLayer
│   │       ├── temporal_encoder.py # TemporalEdgeEncoder (sinusoidal)
│   │       ├── losses.py         # FocalLoss (alpha=0.25, gamma=2.0)
│   │       ├── trainer.py        # THetGATTrainer (Phase A/B, early stopping)
│   │       ├── evaluate.py       # THetGATEvaluator (AUROC, F1, confusion matrix)
│   │       └── runner.py         # CLI entrypoint
│   └── api/                # FastAPI backend
├── frontend/               # Next.js SOC dashboard
│   └── src/
│       ├── app/            # 4 pages: Dashboard, Alerts, Graph, Analytics
│       ├── components/
│       │   ├── layout/
│       │   │   ├── Header.tsx    # Page Info button + Live status
│       │   │   ├── KPICard.tsx   # Clickable cards with onCardClick
│       │   │   └── Sidebar.tsx
│       │   ├── ui/
│       │   │   ├── InfoModal.tsx  # Page Info modal (scrollable, max-w-2xl)
│       │   │   └── InfoDrawer.tsx # Bottom-sheet drawer for card info
│       │   ├── alerts/     # AlertTable
│       │   ├── charts/     # SeverityDonut, TopCommunicators
│       │   └── graph/      # NetworkGraph (vis-network)
│       └── hooks/          # useGraphStream (WebSocket)
├── scripts/                # Utility scripts (neo4j_import.py etc.)
├── tests/                  # Unit + integration tests
├── docs/                   # Module documentation
├── data/                   # (gitignored) raw CSVs, .pt snapshots
├── models/                 # (gitignored) trained checkpoints
│   ├── pretrain/           # checkpoint_best.pt (GNN encoder)
│   └── thetgat/            # thetgat_best.pt, thetgat_latest.pt
├── docker-compose.yml      # All infrastructure services
├── requirements.txt        # Python dependencies
└── .env.example            # Environment template
```

---

## Quick Reference — Sab Commands ek jagah

```powershell
# 1. Clone
git clone https://github.com/A1610/graphrl-sec.git && cd graphrl-sec

# 2. Setup
copy .env.example .env
python -m venv venv && venv\Scripts\activate
pip install -r requirements.txt
cd frontend && npm install && cd ..

# 3. Infrastructure start
docker-compose up -d

# 4. Data ingest (ek baar, lamba process)
python -m src.ingestion.cli ingest --dataset unsw --path data\raw\unsw --mode batch
python -m src.ingestion.cli ingest --dataset cicids --path data\raw\cicids --mode batch
python -m src.ingestion.cli consume --snapshot-dir data\graphs --neo4j
python scripts\neo4j_import.py

# 5. Model training (ek baar, GPU pe)
python -m src.models.pretrain.runner       # Step 9 — GNN pre-training (~2-4 hrs)
python -m src.models.thetgat.runner        # Step 10 — T-HetGAT (~3-7 hrs)

# 6. Daily run (3 terminals)
python -m src.api.run                      # Terminal 1 — Backend
cd frontend && npm run dev                 # Terminal 2 — Frontend
docker-compose up -d                       # Terminal 3 — Docker (agar band ho)
```

---

*GraphRL-Sec — Adaptive Cybersecurity Threat Intelligence using GNN + Deep RL*
