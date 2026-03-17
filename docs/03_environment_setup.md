# 03 — Environment Setup

## Complete Development Environment Setup

---

## 1. What We Are Doing

Setting up an isolated, reproducible development environment for GraphRL-Sec. This includes Python virtual environment, CUDA/GPU setup, Docker services, and project scaffolding.

## 2. Why This Is Important

- **Isolation:** No global dependency pollution
- **Reproducibility:** Anyone can recreate this environment
- **GPU Optimization:** RTX 3050 (6GB) needs specific PyTorch + CUDA versions
- **Service Dependencies:** Neo4j, Kafka, PostgreSQL, Redis all run in Docker

---

## 3. Prerequisites

Before starting, ensure you have:

```
- Python 3.10 or 3.11 (NOT 3.12 — PyTorch Geometric compatibility)
- NVIDIA GPU Driver ≥ 525 (for CUDA 12.x)
- Docker Desktop or Docker Engine + Docker Compose v2
- Node.js 18+ and npm/pnpm
- Git
- 50GB+ free disk space
```

### Verify Prerequisites

```bash
# Python version
python3 --version  # Should be 3.10.x or 3.11.x

# NVIDIA driver
nvidia-smi  # Should show driver version and GPU info

# Docker
docker --version
docker compose version

# Node.js
node --version  # Should be 18+
npm --version

# Git
git --version
```

---

## 4. Step-by-Step Setup

### Step 4.1: Create Project Directory

```bash
mkdir graphrl-sec
cd graphrl-sec
git init
```

### Step 4.2: Create Python Virtual Environment

```bash
# Create virtual environment
python3.11 -m venv venv

# Activate it
# Linux/macOS:
source venv/bin/activate
# Windows:
# .\venv\Scripts\activate

# Verify you're in the venv
which python  # Should show /path/to/graphrl-sec/venv/bin/python
pip --version  # Should show venv path
```

### Step 4.3: Install PyTorch with CUDA

```bash
# PyTorch with CUDA 12.1 (optimized for RTX 3050)
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121

# Verify GPU access
python -c "import torch; print(f'CUDA available: {torch.cuda.is_available()}'); print(f'GPU: {torch.cuda.get_device_name(0)}'); print(f'VRAM: {torch.cuda.get_device_properties(0).total_mem / 1e9:.1f} GB')"
```

Expected output:
```
CUDA available: True
GPU: NVIDIA GeForce RTX 3050
VRAM: 6.0 GB
```

### Step 4.4: Install PyTorch Geometric

```bash
# PyTorch Geometric (must match PyTorch + CUDA versions)
pip install torch-geometric

# PyG extensions (sparse operations)
pip install pyg-lib torch-scatter torch-sparse torch-cluster torch-spline-conv -f https://data.pyg.org/whl/torch-2.3.0+cu121.html
```

**Note:** If the PyG extensions URL fails, check https://data.pyg.org/whl/ for your exact PyTorch version.

### Step 4.5: Install All Python Dependencies

Create `requirements.txt`:

```
# Core ML
torch>=2.3.0
torch-geometric>=2.5.0
numpy>=1.24,<2.0
pandas>=2.0
scikit-learn>=1.3

# Graph
neo4j>=5.0
networkx>=3.1

# RL
stable-baselines3>=2.2
gymnasium>=0.29

# Federated Learning
flwr>=1.7
opacus>=1.4

# API
fastapi>=0.110
uvicorn[standard]>=0.27
sqlalchemy[asyncio]>=2.0
asyncpg>=0.29
pydantic>=2.5
python-jose[cryptography]>=3.3
passlib[bcrypt]>=1.7
python-multipart>=0.0.6

# Message Queue
confluent-kafka>=2.3
# Alternative: aiokafka>=0.10

# Caching
redis>=5.0
aioredis>=2.0

# Data Processing
pyarrow>=15.0
polars>=0.20

# Monitoring
prometheus-client>=0.20
structlog>=24.1

# Utilities
pyyaml>=6.0
python-dotenv>=1.0
rich>=13.0
click>=8.1
tqdm>=4.66
httpx>=0.27

# Testing
pytest>=8.0
pytest-asyncio>=0.23
pytest-cov>=4.1
hypothesis>=6.92
locust>=2.20

# Type checking
mypy>=1.8
pydantic>=2.5

# Code quality
ruff>=0.2
black>=24.1
```

```bash
pip install -r requirements.txt
```

### Step 4.6: Create Project Directory Structure

```bash
mkdir -p src/{ingestion,graph,models/{thetgat,pretrain,drl,federated},campaign,api,utils,config}
mkdir -p tests/{unit,integration,fixtures}
mkdir -p data/{raw,processed,graphs}
mkdir -p models
mkdir -p notebooks
mkdir -p scripts
mkdir -p infra/{docker,monitoring}
mkdir -p frontend
mkdir -p docs

# Create __init__.py files
find src -type d -exec touch {}/__init__.py \;
find tests -type d -exec touch {}/__init__.py \;
```

### Step 4.7: Create Docker Compose for Services

Create `docker-compose.yml`:

```yaml
version: "3.9"

services:
  # Redpanda (lightweight Kafka replacement for local dev)
  redpanda:
    image: docker.redpanda.com/redpandadata/redpanda:v24.1.1
    container_name: graphrl-redpanda
    command:
      - redpanda start
      - --smp 1
      - --memory 512M
      - --overprovisioned
      - --kafka-addr PLAINTEXT://0.0.0.0:9092
      - --advertise-kafka-addr PLAINTEXT://localhost:9092
    ports:
      - "9092:9092"
      - "9644:9644"
    volumes:
      - redpanda_data:/var/lib/redpanda/data

  # Neo4j Graph Database
  neo4j:
    image: neo4j:5.17-community
    container_name: graphrl-neo4j
    ports:
      - "7474:7474"  # HTTP
      - "7687:7687"  # Bolt
    environment:
      - NEO4J_AUTH=neo4j/graphrlsec123
      - NEO4J_PLUGINS=["apoc"]
      - NEO4J_server_memory_heap_initial__size=512m
      - NEO4J_server_memory_heap_max__size=1G
    volumes:
      - neo4j_data:/data

  # PostgreSQL
  postgres:
    image: postgres:16-alpine
    container_name: graphrl-postgres
    ports:
      - "5432:5432"
    environment:
      - POSTGRES_DB=graphrl_sec
      - POSTGRES_USER=graphrl
      - POSTGRES_PASSWORD=graphrlsec123
    volumes:
      - postgres_data:/var/lib/postgresql/data

  # Redis
  redis:
    image: redis:7-alpine
    container_name: graphrl-redis
    ports:
      - "6379:6379"
    command: redis-server --maxmemory 256mb --maxmemory-policy allkeys-lru

  # Prometheus (monitoring)
  prometheus:
    image: prom/prometheus:v2.50.0
    container_name: graphrl-prometheus
    ports:
      - "9090:9090"
    volumes:
      - ./infra/monitoring/prometheus.yml:/etc/prometheus/prometheus.yml

  # Grafana (dashboards)
  grafana:
    image: grafana/grafana:10.3.1
    container_name: graphrl-grafana
    ports:
      - "3001:3000"
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=admin
    volumes:
      - grafana_data:/var/lib/grafana

volumes:
  redpanda_data:
  neo4j_data:
  postgres_data:
  grafana_data:
```

### Step 4.8: Create Configuration Files

Create `.env.example`:

```env
# Database
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=graphrl_sec
POSTGRES_USER=graphrl
POSTGRES_PASSWORD=graphrlsec123

# Neo4j
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=graphrlsec123

# Kafka
KAFKA_BOOTSTRAP_SERVERS=localhost:9092

# Redis
REDIS_URL=redis://localhost:6379

# API
API_HOST=0.0.0.0
API_PORT=8000
JWT_SECRET=change-this-in-production

# ML
DEVICE=cuda
VRAM_LIMIT_GB=6
MIXED_PRECISION=true

# Logging
LOG_LEVEL=INFO
```

```bash
cp .env.example .env
```

Create `.gitignore`:

```
# Python
venv/
__pycache__/
*.pyc
*.egg-info/
dist/
build/

# Environment
.env

# Data
data/raw/
data/processed/
data/graphs/

# Models
models/*.pt
models/*.pth

# IDE
.vscode/
.idea/

# Docker volumes
volumes/

# OS
.DS_Store
Thumbs.db

# Notebooks
.ipynb_checkpoints/

# Node
frontend/node_modules/
frontend/.next/
```

Create `pyproject.toml`:

```toml
[project]
name = "graphrl-sec"
version = "0.1.0"
description = "Adaptive Cybersecurity Threat Intelligence System using GNN-Reinforced Deep Learning"
requires-python = ">=3.10,<3.12"

[tool.ruff]
line-length = 100
target-version = "py311"

[tool.ruff.lint]
select = ["E", "F", "I", "N", "W", "UP"]

[tool.mypy]
python_version = "3.11"
strict = true
warn_return_any = true
warn_unused_configs = true

[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
```

Create `Makefile`:

```makefile
.PHONY: setup start stop test lint clean

setup:
	python3.11 -m venv venv
	. venv/bin/activate && pip install -r requirements.txt
	docker compose pull

start:
	docker compose up -d
	@echo "Services starting..."
	@echo "Neo4j:      http://localhost:7474"
	@echo "Redpanda:   localhost:9092"
	@echo "PostgreSQL: localhost:5432"
	@echo "Redis:      localhost:6379"
	@echo "Grafana:    http://localhost:3001"

stop:
	docker compose down

test:
	. venv/bin/activate && pytest tests/ -v --cov=src

lint:
	. venv/bin/activate && ruff check src/ tests/
	. venv/bin/activate && mypy src/

clean:
	docker compose down -v
	rm -rf __pycache__ .pytest_cache .mypy_cache
	find . -name "*.pyc" -delete
```

### Step 4.9: Start Docker Services

```bash
docker compose up -d

# Verify all services are running
docker compose ps

# Test Neo4j
python -c "
from neo4j import GraphDatabase
driver = GraphDatabase.driver('bolt://localhost:7687', auth=('neo4j', 'graphrlsec123'))
with driver.session() as session:
    result = session.run('RETURN 1 AS num')
    print(f'Neo4j connected: {result.single()[\"num\"]}')
driver.close()
"

# Test PostgreSQL
python -c "
import asyncio, asyncpg
async def test():
    conn = await asyncpg.connect('postgresql://graphrl:graphrlsec123@localhost:5432/graphrl_sec')
    val = await conn.fetchval('SELECT 1')
    print(f'PostgreSQL connected: {val}')
    await conn.close()
asyncio.run(test())
"

# Test Redis
python -c "
import redis
r = redis.Redis(host='localhost', port=6379)
r.set('test', 'graphrl-sec')
print(f'Redis connected: {r.get(\"test\").decode()}')
"
```

### Step 4.10: Setup Prometheus Monitoring

Create `infra/monitoring/prometheus.yml`:

```yaml
global:
  scrape_interval: 15s

scrape_configs:
  - job_name: "graphrl-api"
    static_configs:
      - targets: ["host.docker.internal:8000"]
    metrics_path: "/metrics"

  - job_name: "node-exporter"
    static_configs:
      - targets: ["host.docker.internal:9100"]
```

### Step 4.11: Setup Next.js Frontend

```bash
cd frontend
npx create-next-app@latest . --typescript --tailwind --eslint --app --src-dir
npm install d3 @types/d3 vis-network axios socket.io-client
cd ..
```

---

## 5. Verification Checklist

After completing all steps, run this verification:

```bash
# Activate venv
source venv/bin/activate

# 1. Python environment
python --version          # 3.11.x
pip list | grep torch     # torch, torch-geometric present

# 2. GPU
python -c "import torch; print(torch.cuda.is_available())"  # True

# 3. Docker services
docker compose ps         # All services running

# 4. Neo4j
curl -s http://localhost:7474 | head -1  # Should return HTML

# 5. Project structure
find src -name "__init__.py" | wc -l  # Should be ≥ 10

# 6. Frontend
cd frontend && npm run build && cd ..  # Should build without errors
```

---

## 6. Common Issues & Fixes

| Issue | Fix |
|---|---|
| `CUDA out of memory` during setup test | Close other GPU apps, reduce test batch size |
| `torch-geometric` install fails | Ensure exact PyTorch version match in URL |
| Neo4j won't start | Check Docker memory allocation (needs ≥ 2GB) |
| Port conflict | Change ports in docker-compose.yml |
| `pip install` fails on Windows | Use WSL2 for development |
| Redpanda OOM | Increase `--memory` flag to 1G |

---

## 7. Daily Development Workflow

```bash
# Morning startup
cd graphrl-sec
source venv/bin/activate
docker compose up -d

# Work on code...

# Run tests before committing
make test
make lint

# Evening shutdown
docker compose stop  # stop, not down (preserves data)
deactivate
```
