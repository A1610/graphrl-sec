# ============================================================
# GraphRL-Sec — Makefile
# ============================================================
.PHONY: help setup start stop restart status test test-unit test-integration \
        lint format typecheck clean logs neo4j-shell redis-cli psql

VENV       := venv
PYTHON     := $(VENV)/Scripts/python
PIP        := $(VENV)/Scripts/pip
PYTEST     := $(VENV)/Scripts/pytest
RUFF       := $(VENV)/Scripts/ruff
MYPY       := $(VENV)/Scripts/mypy

# Default target
help:
	@echo ""
	@echo "  GraphRL-Sec Development Commands"
	@echo "  ================================="
	@echo ""
	@echo "  Setup:"
	@echo "    make setup          Create venv + install all dependencies"
	@echo ""
	@echo "  Services (Docker):"
	@echo "    make start          Start all Docker services"
	@echo "    make stop           Stop all Docker services (data preserved)"
	@echo "    make restart        Restart all services"
	@echo "    make status         Show service health status"
	@echo "    make logs           Tail logs from all services"
	@echo ""
	@echo "  Development:"
	@echo "    make test           Run full test suite with coverage"
	@echo "    make test-unit      Run only unit tests (no Docker needed)"
	@echo "    make test-int       Run integration tests (Docker required)"
	@echo "    make lint           Check code style (ruff)"
	@echo "    make format         Auto-format code (ruff format)"
	@echo "    make typecheck      Run mypy type checker"
	@echo ""
	@echo "  DB Shells:"
	@echo "    make neo4j-shell    Open Neo4j Cypher shell"
	@echo "    make redis-cli      Open Redis CLI"
	@echo "    make psql           Open PostgreSQL shell"
	@echo ""
	@echo "  Cleanup:"
	@echo "    make clean          Remove caches and temp files"
	@echo "    make clean-all      Remove caches + Docker volumes (DESTRUCTIVE)"
	@echo ""

# ----------------------------------------------------------
# Setup
# ----------------------------------------------------------
setup:
	python3.10 -m venv $(VENV)
	$(PIP) install --upgrade pip
	$(PIP) install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
	$(PIP) install torch-scatter torch-sparse torch-cluster -f https://data.pyg.org/whl/torch-2.5.1+cu121.html
	$(PIP) install -r requirements.txt
	cp -n .env.example .env || true
	@echo ""
	@echo "Setup complete. Run 'make start' to launch Docker services."

# ----------------------------------------------------------
# Docker Services
# ----------------------------------------------------------
start:
	docker compose up -d
	@echo ""
	@echo "  Services starting — wait ~30s for full health"
	@echo "  Neo4j:           http://localhost:7474"
	@echo "  Redpanda Console: http://localhost:8080"
	@echo "  Grafana:         http://localhost:3001"
	@echo "  Prometheus:      http://localhost:9090"
	@echo "  API (when running): http://localhost:8000/docs"

stop:
	docker compose stop
	@echo "Services stopped (data preserved in volumes)"

restart:
	docker compose restart

status:
	docker compose ps

logs:
	docker compose logs -f --tail=50

# ----------------------------------------------------------
# Testing
# ----------------------------------------------------------
test:
	$(PYTEST) tests/ -v --cov=src --cov-report=term-missing --cov-report=html

test-unit:
	$(PYTEST) tests/unit/ -v -m unit

test-int:
	$(PYTEST) tests/integration/ -v -m integration

# ----------------------------------------------------------
# Code Quality
# ----------------------------------------------------------
lint:
	$(RUFF) check src/ tests/

format:
	$(RUFF) format src/ tests/

typecheck:
	$(MYPY) src/

check: lint typecheck
	@echo "All checks passed."

# ----------------------------------------------------------
# DB Shells
# ----------------------------------------------------------
neo4j-shell:
	docker exec -it graphrl-neo4j cypher-shell -u neo4j -p graphrlsec123

redis-cli:
	docker exec -it graphrl-redis redis-cli -a graphrlsec123

psql:
	docker exec -it graphrl-postgres psql -U graphrl -d graphrl_sec

# ----------------------------------------------------------
# Cleanup
# ----------------------------------------------------------
clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	rm -rf .pytest_cache .mypy_cache .ruff_cache htmlcov .coverage 2>/dev/null || true
	@echo "Caches cleaned."

clean-all: clean
	@echo "WARNING: This will delete all Docker volumes (Neo4j data, Postgres data, etc.)"
	@read -p "Are you sure? [y/N] " confirm && [ "$$confirm" = "y" ]
	docker compose down -v
	@echo "All volumes removed."
