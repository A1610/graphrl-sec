# 20 — Module: FastAPI Backend API

## Phase 6, Module 6.1

---

## 1. What We Are Building

A production-grade FastAPI backend that exposes all GraphRL-Sec capabilities via REST APIs and WebSocket connections. This is the bridge between the AI/ML backend and the SOC Dashboard frontend.

**In Simple Terms:** The API is the "waiter" — the frontend asks for alerts, graphs, campaigns, and the API fetches them from all the backend services and serves them up in a clean format.

---

## 2. Why We Are Building It

- Frontend needs data in JSON format via HTTP
- Real-time alerts need WebSocket push
- Analyst feedback needs to reach the DRL agent
- Graph queries need to reach Neo4j
- All interactions need authentication and logging

---

## 3. How It Works

### API Architecture

```
Next.js Frontend
    │
    ├── REST ──▶ /api/v1/alerts        (CRUD alerts)
    ├── REST ──▶ /api/v1/campaigns     (campaign data)
    ├── REST ──▶ /api/v1/graph         (graph queries)
    ├── REST ──▶ /api/v1/triage        (triage decisions)
    ├── REST ──▶ /api/v1/metrics       (system metrics)
    ├── REST ──▶ /api/v1/auth          (authentication)
    │
    └── WebSocket ──▶ /ws/alerts       (real-time alert stream)
```

---

## 4. Implementation Plan

### Task 4.1: Project Structure & App Factory

```python
# src/api/main.py
```
- FastAPI app with proper middleware (CORS, logging, error handling)
- Lifespan management (startup: connect DB, load models; shutdown: cleanup)
- Health check endpoint: `GET /health`
- Prometheus metrics endpoint: `GET /metrics`

### Task 4.2: Database Models (SQLAlchemy)

```python
# src/api/models/
```
- `Alert`: id, timestamp, source_ip, dest_ip, anomaly_score, triage_decision, campaign_id
- `Campaign`: id, start_time, end_time, severity, attack_type, description
- `TriageDecision`: id, alert_id, action, confidence, analyst_feedback, created_at
- `User`: id, username, role (admin/analyst/viewer), hashed_password

### Task 4.3: API Routes

```python
# src/api/routes/
├── alerts.py      # GET /alerts, GET /alerts/{id}, POST /alerts/feedback
├── campaigns.py   # GET /campaigns, GET /campaigns/{id}/timeline
├── graph.py       # GET /graph/neighborhood/{ip}, GET /graph/stats
├── triage.py      # POST /triage/decide, GET /triage/history
├── metrics.py     # GET /metrics/detection, GET /metrics/triage
└── auth.py        # POST /auth/login, POST /auth/register
```

### Task 4.4: WebSocket for Real-Time Alerts

```python
# src/api/ws/alerts.py
```
- WebSocket endpoint at `/ws/alerts`
- Pushes new alerts as they're generated
- Pushes triage decisions in real-time
- Connection management (multiple analyst clients)

### Task 4.5: Authentication & Authorization

```python
# src/api/auth/
```
- JWT-based authentication
- Role-based access control (RBAC)
- Password hashing with bcrypt
- Token refresh mechanism

### Task 4.6: Service Layer

```python
# src/api/services/
```
- `AlertService`: manages alert CRUD + pagination
- `GraphService`: wraps Neo4j queries
- `TriageService`: calls DRL inference + stores decisions
- `CampaignService`: retrieves campaign data
- `MetricsService`: computes dashboard metrics

---

## 5. Folder Structure

```
src/api/
├── __init__.py
├── main.py                 # FastAPI app factory
├── config.py               # API configuration
├── dependencies.py         # Dependency injection
├── middleware.py            # CORS, logging, error handling
│
├── models/                 # SQLAlchemy ORM models
│   ├── __init__.py
│   ├── alert.py
│   ├── campaign.py
│   ├── triage.py
│   └── user.py
│
├── schemas/                # Pydantic request/response schemas
│   ├── __init__.py
│   ├── alert.py
│   ├── campaign.py
│   ├── triage.py
│   └── auth.py
│
├── routes/                 # API route handlers
│   ├── __init__.py
│   ├── alerts.py
│   ├── campaigns.py
│   ├── graph.py
│   ├── triage.py
│   ├── metrics.py
│   └── auth.py
│
├── services/               # Business logic
│   ├── __init__.py
│   ├── alert_service.py
│   ├── graph_service.py
│   ├── triage_service.py
│   ├── campaign_service.py
│   └── metrics_service.py
│
├── auth/                   # Authentication
│   ├── __init__.py
│   ├── jwt.py
│   └── rbac.py
│
└── ws/                     # WebSocket handlers
    ├── __init__.py
    └── alerts.py
```

---

## 6. API Endpoints Reference

### Alerts

| Method | Path | Description | Auth |
|---|---|---|---|
| GET | `/api/v1/alerts` | List alerts (paginated, filterable) | analyst+ |
| GET | `/api/v1/alerts/{id}` | Get alert details with graph context | analyst+ |
| POST | `/api/v1/alerts/{id}/feedback` | Submit analyst feedback | analyst+ |
| GET | `/api/v1/alerts/stats` | Alert statistics (counts, rates) | viewer+ |

### Campaigns

| Method | Path | Description | Auth |
|---|---|---|---|
| GET | `/api/v1/campaigns` | List campaigns | analyst+ |
| GET | `/api/v1/campaigns/{id}` | Campaign details + involved hosts | analyst+ |
| GET | `/api/v1/campaigns/{id}/timeline` | Campaign event timeline | analyst+ |

### Graph

| Method | Path | Description | Auth |
|---|---|---|---|
| GET | `/api/v1/graph/neighborhood/{ip}` | Subgraph around IP (k-hop) | analyst+ |
| GET | `/api/v1/graph/stats` | Graph statistics | viewer+ |
| GET | `/api/v1/graph/anomalous` | Most anomalous subgraphs | analyst+ |

### Triage

| Method | Path | Description | Auth |
|---|---|---|---|
| POST | `/api/v1/triage/decide` | Get DRL agent decision for alert | system |
| GET | `/api/v1/triage/history` | Triage decision history | analyst+ |
| GET | `/api/v1/triage/performance` | Agent performance metrics | admin |

### Example Request/Response:

```bash
# Get alerts with high anomaly scores
GET /api/v1/alerts?min_score=0.8&limit=10&sort=-anomaly_score

Response:
{
    "total": 45,
    "page": 1,
    "limit": 10,
    "alerts": [
        {
            "id": "alert-001",
            "timestamp": "2026-03-15T14:30:00Z",
            "source_ip": "192.168.10.50",
            "dest_ip": "205.174.165.73",
            "anomaly_score": 0.97,
            "triage_decision": "ESCALATE",
            "triage_confidence": 0.94,
            "campaign_id": "campaign-001",
            "attack_type": "DDoS"
        }
    ]
}
```

```bash
# Get campaign timeline
GET /api/v1/campaigns/campaign-001/timeline

Response:
{
    "campaign_id": "campaign-001",
    "attack_type": "DDoS",
    "severity": "CRITICAL",
    "start_time": "2026-03-15T14:00:00Z",
    "end_time": "2026-03-15T14:47:00Z",
    "involved_hosts": ["192.168.10.50", "192.168.10.51"],
    "involved_external_ips": ["205.174.165.73"],
    "timeline": [
        {"time": "14:00:00", "event": "First anomalous connection detected", "severity": "medium"},
        {"time": "14:05:00", "event": "Traffic spike: 500 req/s from 205.174.165.73", "severity": "high"},
        {"time": "14:15:00", "event": "DDoS pattern confirmed, 12 source IPs", "severity": "critical"},
        {"time": "14:47:00", "event": "Attack subsided", "severity": "low"}
    ]
}
```

---

## 7. Testing Strategy

### Unit Tests:
```
tests/unit/test_api/
├── test_alert_routes.py
├── test_campaign_routes.py
├── test_graph_routes.py
├── test_triage_routes.py
├── test_auth.py
└── test_services.py
```

### Integration Tests:
```python
# Using FastAPI TestClient
from fastapi.testclient import TestClient
from src.api.main import app

client = TestClient(app)

def test_get_alerts():
    response = client.get("/api/v1/alerts", headers={"Authorization": "Bearer test_token"})
    assert response.status_code == 200
    assert "alerts" in response.json()
```

---

## 8. Definition of Done

- [ ] All REST endpoints respond correctly
- [ ] WebSocket pushes alerts in real-time
- [ ] JWT authentication works
- [ ] RBAC enforces role-based access
- [ ] Database models migrate correctly
- [ ] API docs available at `/docs` (Swagger UI)
- [ ] Error handling returns proper HTTP status codes
- [ ] All tests pass
- [ ] API runs on port 8000
