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
git clone https://github.com/YOUR_USERNAME/graphrl-sec.git
cd graphrl-sec
```

> `YOUR_USERNAME` ki jagah apna GitHub username dalo.

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

Docker Desktop open hona chahiye (Step 1 se). Phir:

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
> Complete hone par `data\graphs\` me ~17,000+ `.pt` files hongi.

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
> Username: `neo4j` | Password: `graphrlsec123`
> Query run karo: `MATCH (n) RETURN count(n)` → ~124,000 dikhna chahiye

---

## Step 9 — Pre-Training (Self-Supervised GNN)

Jab `data\graphs\` me `.pt` files aa jayein (Step 8 complete ho), tab:

```powershell
venv\Scripts\activate
python -m src.models.pretrain.trainer
```

Ye GPU pe chalega (RTX 3050). Output kuch aisa dikhega:
```
pretrain_start    device=cuda  graphs_dir=data\graphs
snapshots_loaded  count=17657
data_split        train_pairs=15891  val_pairs=1765
epoch=1  train_loss=6.97  val_loss=6.97  gpu_mb=813
epoch=2  train_loss=5.84  val_loss=5.91  best=True
...
early_stopping    epoch=22  patience=10
pretrain_complete best_val_loss=4.21  elapsed_s=11520
```

Training automatically ruk jayegi jab loss plateau pe aaye (patience=10 epochs).

| Setting | Value |
|---------|-------|
| GPU VRAM used | ~813 MB |
| Time per epoch | ~9 minutes |
| Expected total | ~2–4 hours |
| Best model saved | `models\pretrain\checkpoint_best.pt` |

> **Agar pehle se trained checkpoint hai** (Google Drive / USB se copy kiya):
> `models\pretrain\` folder me `checkpoint_best.pt` rakh do aur seedha Step 10 pe jao.
>
> **CPU pe bhi chal sakta hai** (bahut slow — ~10x):
> `.env` file me `DEVICE=cpu` set karo.

---

## Step 10 — Project Chalao (Sab ek saath)

4 alag terminals open karo:

### Terminal 1 — FastAPI Backend:
```powershell
cd D:\graphrl-sec
venv\Scripts\activate
python -m src.api.run
```
Backend chal raha hoga: http://localhost:8000

### Terminal 2 — Next.js Frontend:
```powershell
cd D:\graphrl-sec\frontend
npm run dev
```
Dashboard khulega: http://localhost:3000

### Terminal 3 — (Optional) Training chal rahi hai to monitor karo:
```powershell
cd D:\graphrl-sec
venv\Scripts\activate
python -m src.models.pretrain.trainer
```

### Terminal 4 — (Optional) Neo4j import agar abhi chal rahi hai:
```powershell
cd D:\graphrl-sec
venv\Scripts\activate
python scripts\neo4j_import.py
```

---

## Dashboard Pages

| Page | URL | Description |
|------|-----|-------------|
| Dashboard | http://localhost:3000 | KPIs, charts, recent alerts |
| Alerts | http://localhost:3000/alerts | Alert list with severity filter |
| Network Graph | http://localhost:3000/graph | Interactive vis-network graph |
| Analytics | http://localhost:3000/analytics | Stats, top communicators |
| Neo4j Browser | http://localhost:7474 | Direct graph database browser |
| API Docs | http://localhost:8000/docs | FastAPI Swagger UI |
| Grafana | http://localhost:3001 | System monitoring |

---

## Common Errors aur Fixes

### "Neo4j unreachable"
Docker chal raha hai? Check karo: `docker ps`
Agar nahi: `docker-compose up -d`

### "No .pt snapshot files found"
Step 8 abhi complete nahi hua. `data\graphs\` me files check karo.

### "CUDA not available"
NVIDIA drivers update karo ya CUDA toolkit install karo.
Training CPU pe bhi chalegi (bahut slow hogi): `.env` me `DEVICE=cpu` set karo.

### "Module not found"
Venv active hai? Terminal me `(venv)` dikhna chahiye.
Agar nahi: `venv\Scripts\activate`

### Frontend "Cannot connect to API"
Backend Terminal 1 me chal rahi hai? `python -m src.api.run` check karo.

### Docker port already in use
```powershell
docker-compose down
docker-compose up -d
```

---

## Project Structure (Reference)

```
graphrl-sec/
├── src/
│   ├── ingestion/          # CSV parsers, Kafka producer/consumer
│   ├── graph/              # Neo4j writer, PyG converter, temporal windows
│   ├── models/
│   │   ├── pretrain/       # HeteroGraphEncoder, NT-Xent, trainer
│   │   ├── thetgat/        # T-HetGAT anomaly detection (Module 09+)
│   │   └── drl/            # Deep RL agent (Module 10+)
│   └── api/                # FastAPI backend
├── frontend/               # Next.js SOC dashboard
├── scripts/                # Utility scripts (neo4j_import.py etc.)
├── tests/                  # Unit + integration tests
├── docs/                   # Module documentation
├── data/                   # (gitignored) raw CSVs, .pt snapshots
├── models/                 # (gitignored) trained checkpoints
├── docker-compose.yml      # All infrastructure services
├── requirements.txt        # Python dependencies
└── .env.example            # Environment template
```

---

## Saved Checkpoints Transfer karna (Optional)

Agar current system se trained checkpoint lena hai:

**Current system pe (copy karo):**
```powershell
# Google Drive ya USB pe copy karo
copy models\pretrain\checkpoint_best.pt <destination>
```

**Fresh system pe (paste karo):**
```powershell
mkdir models\pretrain
copy <source>\checkpoint_best.pt models\pretrain\
```

---

*GraphRL-Sec — Adaptive Cybersecurity Threat Intelligence using GNN + Deep RL*
