# 24 — Development Workflow Guide

## How to Use This Documentation

---

## 1. The Golden Rule

**Follow the documents IN ORDER. Do not skip ahead.**

```
01 → 02 → 03 → 04 → 05 → 06 → 07 → 08 → ... → 23
```

Each document builds on the previous one. If you skip a module, later modules will fail.

---

## 2. Module-by-Module Workflow

For EVERY module, follow this exact process:

### Step 1: READ the documentation file completely
```bash
# Example: Starting Module 04 (Data Ingestion)
cat docs/04_module_data_ingestion.md
```
Read the entire file. Understand: What, Why, How.

### Step 2: CREATE the folder structure
```bash
# Create the exact folder structure specified in the doc
mkdir -p src/ingestion/parsers
touch src/ingestion/__init__.py
# ... etc
```

### Step 3: IMPLEMENT task by task
Each module doc has an "Implementation Plan" with numbered tasks (Task 4.1, 4.2, ...).
Implement them IN ORDER.

### Step 4: TEST the module
```bash
# Run unit tests for this module
pytest tests/unit/test_ingestion/ -v

# Run type checker
mypy src/ingestion/

# Run linter
ruff check src/ingestion/
```

### Step 5: VERIFY the "Definition of Done"
At the bottom of every module doc is a "Definition of Done" checklist.
Check every box before moving on.

### Step 6: COMMIT
```bash
git add -A
git commit -m "Complete Module 04: Data Ingestion Pipeline"
```

### Step 7: MOVE to next document
Only after ALL checks pass.

---

## 3. Phase Gate Process

After completing all modules in a phase, fill out the Phase Progress Report:

```
Phase 1: docs/07_phase1_progress_report.md
Phase 2: docs/10_phase2_progress_report.md
Phase 3: docs/13_phase3_progress_report.md
Phase 4: docs/16_phase4_progress_report.md
Phase 5: docs/19_phase5_progress_report.md
Phase 6: docs/23_final_progress_report.md
```

Fill in all metrics, check all boxes, document any known issues.

**DO NOT start the next phase until the progress report is complete.**

---

## 4. Daily Development Routine

```
Morning:
  1. cd graphrl-sec && source venv/bin/activate
  2. docker compose up -d
  3. git pull (if using remote)
  4. Open current module doc

During Development:
  5. Write code for current task
  6. Write tests alongside code
  7. Run tests frequently: pytest tests/ -v --last-failed
  8. Check types: mypy src/
  9. Check style: ruff check src/

End of Day:
  10. Run full test suite: make test
  11. Commit progress: git commit
  12. Update module checklist (what's done, what's remaining)
  13. docker compose stop
  14. deactivate
```

---

## 5. Document Index

### Foundation
| # | Document | Phase | Content |
|---|---|---|---|
| 01 | project_requirements.md | Pre | Full requirements, tech stack, constraints |
| 02 | system_architecture.md | Pre | Architecture, data flow, memory budget |
| 03 | environment_setup.md | Pre | Venv, Docker, CUDA, project scaffold |

### Phase 1: Data Pipeline + Graph (Week 1-4)
| # | Document | Module | Content |
|---|---|---|---|
| 04 | module_data_ingestion.md | 1.1 | Parsers, schema, Kafka producer |
| 05 | module_graph_construction.md | 1.2 | Node registry, edges, PyG conversion |
| 06 | module_neo4j_kafka_integration.md | 1.3 | Neo4j writer, Kafka consumer |
| 07 | phase1_progress_report.md | Gate | Validation & metrics |

### Phase 2: Self-Supervised Pre-training (Week 5-8)
| # | Document | Module | Content |
|---|---|---|---|
| 08 | module_self_supervised_pretraining.md | 2.1 | Contrastive learning, encoder |
| 09 | module_node2vec_baseline.md | 2.2 | Node2Vec, baseline anomaly detection |
| 10 | phase2_progress_report.md | Gate | Validation & metrics |

### Phase 3: T-HetGAT Detection (Week 9-13)
| # | Document | Module | Content |
|---|---|---|---|
| 11 | module_thetgat_detection.md | 3.1 | Core novel model |
| 12 | module_baselines_benchmarking.md | 3.2 | E-GraphSAGE, DOMINANT, RF, XGBoost |
| 13 | phase3_progress_report.md | Gate | Benchmark results |

### Phase 4: DRL Triage Agent (Week 14-17)
| # | Document | Module | Content |
|---|---|---|---|
| 14 | module_soc_environment.md | 4.1 | Gymnasium SOC simulator |
| 15 | module_drl_triage_agent.md | 4.2 | DQN + PER, training, inference |
| 16 | phase4_progress_report.md | Gate | Triage metrics |

### Phase 5: Federated + Campaign (Week 18-20)
| # | Document | Module | Content |
|---|---|---|---|
| 17 | module_federated_learning.md | 5.1 | Flower, Opacus, multi-org sim |
| 18 | module_campaign_detection.md | 5.2 | Louvain, temporal clustering |
| 19 | phase5_progress_report.md | Gate | Federated & campaign metrics |

### Phase 6: Integration + Dashboard (Week 21-22)
| # | Document | Module | Content |
|---|---|---|---|
| 20 | module_fastapi_backend.md | 6.1 | REST API, WebSocket, Auth |
| 21 | module_nextjs_dashboard.md | 6.2 | SOC dashboard, graph viz |
| 22 | module_integration_testing.md | 6.3 | Full pipeline, smoke test |
| 23 | final_progress_report.md | Gate | Final metrics, completion |
| 24 | development_workflow.md | Guide | This file — how to use docs |

---

## 6. When You're Stuck

1. **Re-read the current module doc** — the answer is usually there
2. **Check the architecture doc (02)** — understand how this module fits
3. **Run tests** — they'll tell you exactly what's broken
4. **Check edge cases** — every module doc lists them
5. **GPU issues?** Check memory budget in the module doc
6. **Dependency issues?** Re-read environment setup (03)

---

## 7. Key Reminders

- **Always activate venv** before any Python work
- **Always start Docker** before testing (Neo4j, Kafka, Postgres, Redis)
- **Never install packages globally** — always `pip install` inside venv
- **Test after every task**, not just at the end of the module
- **Commit frequently** — one commit per task is ideal
- **Fill in progress reports honestly** — they help you track what works
- **RTX 3050 = 6GB VRAM** — always check memory usage before scaling up
