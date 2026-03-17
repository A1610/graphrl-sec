-- ============================================================
-- GraphRL-Sec — PostgreSQL Initialization
-- Runs once on first container startup
-- ============================================================

-- Enable useful extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";  -- fuzzy text search

-- ============================================================
-- Alerts table — anomaly alerts from detection pipeline
-- ============================================================
CREATE TABLE IF NOT EXISTS alerts (
    id            UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    node_id       TEXT NOT NULL,
    node_type     TEXT NOT NULL,
    anomaly_score FLOAT NOT NULL CHECK (anomaly_score >= 0 AND anomaly_score <= 1),
    status        TEXT NOT NULL DEFAULT 'pending'
                  CHECK (status IN ('pending', 'investigating', 'escalated', 'dismissed', 'resolved')),
    severity      TEXT NOT NULL DEFAULT 'medium'
                  CHECK (severity IN ('low', 'medium', 'high', 'critical')),
    raw_features  JSONB,
    graph_context JSONB
);

CREATE INDEX idx_alerts_created_at   ON alerts (created_at DESC);
CREATE INDEX idx_alerts_status       ON alerts (status);
CREATE INDEX idx_alerts_severity     ON alerts (severity);
CREATE INDEX idx_alerts_node_id      ON alerts (node_id);

-- ============================================================
-- Triage actions table — DRL agent decisions
-- ============================================================
CREATE TABLE IF NOT EXISTS triage_actions (
    id           UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    alert_id     UUID NOT NULL REFERENCES alerts(id) ON DELETE CASCADE,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    action       TEXT NOT NULL
                 CHECK (action IN ('dismiss', 'investigate', 'escalate', 'correlate')),
    confidence   FLOAT NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
    agent_source TEXT NOT NULL DEFAULT 'drl'
                 CHECK (agent_source IN ('drl', 'analyst', 'rule')),
    analyst_id   TEXT,
    notes        TEXT
);

CREATE INDEX idx_triage_alert_id    ON triage_actions (alert_id);
CREATE INDEX idx_triage_created_at  ON triage_actions (created_at DESC);

-- ============================================================
-- Attack campaigns table — correlated alert clusters
-- ============================================================
CREATE TABLE IF NOT EXISTS campaigns (
    id             UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    name           TEXT,
    tactic         TEXT,           -- MITRE ATT&CK tactic
    technique      TEXT,           -- MITRE ATT&CK technique
    alert_count    INT NOT NULL DEFAULT 0,
    status         TEXT NOT NULL DEFAULT 'active'
                   CHECK (status IN ('active', 'contained', 'resolved')),
    metadata       JSONB
);

CREATE TABLE IF NOT EXISTS campaign_alerts (
    campaign_id  UUID NOT NULL REFERENCES campaigns(id) ON DELETE CASCADE,
    alert_id     UUID NOT NULL REFERENCES alerts(id) ON DELETE CASCADE,
    PRIMARY KEY (campaign_id, alert_id)
);

-- ============================================================
-- Graph snapshots table — metadata for serialized PyG graphs
-- ============================================================
CREATE TABLE IF NOT EXISTS graph_snapshots (
    id           UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    window_start TIMESTAMPTZ NOT NULL,
    window_end   TIMESTAMPTZ NOT NULL,
    node_count   INT NOT NULL,
    edge_count   INT NOT NULL,
    file_path    TEXT NOT NULL,     -- path in data/graphs/
    checksum     TEXT NOT NULL      -- SHA-256 for integrity
);

CREATE INDEX idx_snapshots_window ON graph_snapshots (window_start, window_end);

-- ============================================================
-- Auto-update updated_at trigger
-- ============================================================
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER alerts_updated_at
    BEFORE UPDATE ON alerts
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER campaigns_updated_at
    BEFORE UPDATE ON campaigns
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();
