-- Migration: Add telemetry tables with indexes and constraints
-- Created: 2025-01-23
-- Purpose: Track build execution metrics, phase performance, and system health

-- ============================================================================
-- Table: build_runs
-- Purpose: Track overall build execution attempts
-- ============================================================================
CREATE TABLE IF NOT EXISTS build_runs (
    run_id TEXT PRIMARY KEY,
    started_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP,
    status TEXT NOT NULL CHECK(status IN ('running', 'completed', 'failed', 'cancelled')),
    total_phases INTEGER DEFAULT 0,
    completed_phases INTEGER DEFAULT 0,
    failed_phases INTEGER DEFAULT 0,
    total_tokens_used INTEGER DEFAULT 0,
    total_cost_usd REAL DEFAULT 0.0,
    git_commit_hash TEXT,
    branch_name TEXT,
    trigger_type TEXT CHECK(trigger_type IN ('manual', 'scheduled', 'webhook', 'retry')),
    metadata_json TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_build_runs_status ON build_runs(status);
CREATE INDEX IF NOT EXISTS ix_build_runs_started_at ON build_runs(started_at DESC);
CREATE INDEX IF NOT EXISTS ix_build_runs_branch ON build_runs(branch_name);
CREATE INDEX IF NOT EXISTS ix_build_runs_trigger ON build_runs(trigger_type);

-- ============================================================================
-- Table: phase_executions
-- Purpose: Track individual phase execution within builds
-- ============================================================================
CREATE TABLE IF NOT EXISTS phase_executions (
    execution_id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    phase_id TEXT NOT NULL,
    phase_name TEXT NOT NULL,
    category TEXT NOT NULL,
    complexity TEXT CHECK(complexity IN ('low', 'medium', 'high', 'critical')),
    started_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP,
    status TEXT NOT NULL CHECK(status IN ('pending', 'running', 'completed', 'failed', 'skipped', 'cancelled')),
    exit_code INTEGER,
    tokens_estimated INTEGER,
    tokens_used INTEGER,
    cost_usd REAL DEFAULT 0.0,
    truncation_detected BOOLEAN DEFAULT 0,
    truncation_percentage REAL,
    retry_count INTEGER DEFAULT 0,
    error_message TEXT,
    error_type TEXT,
    output_size_bytes INTEGER,
    execution_time_ms INTEGER,
    metadata_json TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (run_id) REFERENCES build_runs(run_id) ON DELETE CASCADE,
    FOREIGN KEY (phase_id) REFERENCES phases(phase_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS ix_phase_executions_run_id ON phase_executions(run_id);
CREATE INDEX IF NOT EXISTS ix_phase_executions_phase_id ON phase_executions(phase_id);
CREATE INDEX IF NOT EXISTS ix_phase_executions_status ON phase_executions(status);
CREATE INDEX IF NOT EXISTS ix_phase_executions_started_at ON phase_executions(started_at DESC);
CREATE INDEX IF NOT EXISTS ix_phase_executions_category ON phase_executions(category);
CREATE INDEX IF NOT EXISTS ix_phase_executions_complexity ON phase_executions(complexity);
CREATE INDEX IF NOT EXISTS ix_phase_executions_truncation ON phase_executions(truncation_detected) WHERE truncation_detected = 1;
CREATE INDEX IF NOT EXISTS ix_phase_executions_run_phase ON phase_executions(run_id, phase_id);

-- ============================================================================
-- Table: token_usage_metrics
-- Purpose: Detailed token usage tracking per phase execution
-- ============================================================================
CREATE TABLE IF NOT EXISTS token_usage_metrics (
    metric_id INTEGER PRIMARY KEY AUTOINCREMENT,
    execution_id INTEGER NOT NULL,
    run_id TEXT NOT NULL,
    phase_id TEXT NOT NULL,
    timestamp TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    prompt_tokens INTEGER NOT NULL DEFAULT 0,
    completion_tokens INTEGER NOT NULL DEFAULT 0,
    total_tokens INTEGER NOT NULL DEFAULT 0,
    estimated_tokens INTEGER,
    estimation_accuracy_pct REAL,
    model_name TEXT NOT NULL,
    temperature REAL,
    max_tokens INTEGER,
    cost_per_1k_prompt REAL,
    cost_per_1k_completion REAL,
    total_cost_usd REAL,
    response_time_ms INTEGER,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (execution_id) REFERENCES phase_executions(execution_id) ON DELETE CASCADE,
    FOREIGN KEY (run_id) REFERENCES build_runs(run_id) ON DELETE CASCADE,
    FOREIGN KEY (phase_id) REFERENCES phases(phase_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS ix_token_usage_execution_id ON token_usage_metrics(execution_id);
CREATE INDEX IF NOT EXISTS ix_token_usage_run_id ON token_usage_metrics(run_id);
CREATE INDEX IF NOT EXISTS ix_token_usage_phase_id ON token_usage_metrics(phase_id);
CREATE INDEX IF NOT EXISTS ix_token_usage_timestamp ON token_usage_metrics(timestamp DESC);
CREATE INDEX IF NOT EXISTS ix_token_usage_model ON token_usage_metrics(model_name);

-- ============================================================================
-- Table: truncation_events
-- Purpose: Track output truncation incidents for analysis
-- ============================================================================
CREATE TABLE IF NOT EXISTS truncation_events (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    execution_id INTEGER NOT NULL,
    run_id TEXT NOT NULL,
    phase_id TEXT NOT NULL,
    detected_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    truncation_type TEXT CHECK(truncation_type IN ('hard_limit', 'incomplete_json', 'partial_file', 'mid_operation')),
    severity TEXT CHECK(severity IN ('minor', 'moderate', 'severe', 'critical')),
    estimated_loss_pct REAL,
    tokens_used INTEGER,
    tokens_limit INTEGER,
    output_size_bytes INTEGER,
    expected_operations INTEGER,
    completed_operations INTEGER,
    recovery_attempted BOOLEAN DEFAULT 0,
    recovery_successful BOOLEAN DEFAULT 0,
    impact_description TEXT,
    metadata_json TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (execution_id) REFERENCES phase_executions(execution_id) ON DELETE CASCADE,
    FOREIGN KEY (run_id) REFERENCES build_runs(run_id) ON DELETE CASCADE,
    FOREIGN KEY (phase_id) REFERENCES phases(phase_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS ix_truncation_events_execution_id ON truncation_events(execution_id);
CREATE INDEX IF NOT EXISTS ix_truncation_events_run_id ON truncation_events(run_id);
CREATE INDEX IF NOT EXISTS ix_truncation_events_phase_id ON truncation_events(phase_id);
CREATE INDEX IF NOT EXISTS ix_truncation_events_detected_at ON truncation_events(detected_at DESC);
CREATE INDEX IF NOT EXISTS ix_truncation_events_type ON truncation_events(truncation_type);
CREATE INDEX IF NOT EXISTS ix_truncation_events_severity ON truncation_events(severity);

-- ============================================================================
-- Table: performance_metrics
-- Purpose: System-level performance tracking
-- ============================================================================
CREATE TABLE IF NOT EXISTS performance_metrics (
    metric_id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    execution_id INTEGER,
    timestamp TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    metric_type TEXT NOT NULL CHECK(metric_type IN ('cpu_usage', 'memory_usage', 'disk_io', 'network_io', 'api_latency', 'queue_depth')),
    metric_value REAL NOT NULL,
    metric_unit TEXT NOT NULL,
    context TEXT,
    metadata_json TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (run_id) REFERENCES build_runs(run_id) ON DELETE CASCADE,
    FOREIGN KEY (execution_id) REFERENCES phase_executions(execution_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS ix_performance_metrics_run_id ON performance_metrics(run_id);
CREATE INDEX IF NOT EXISTS ix_performance_metrics_execution_id ON performance_metrics(execution_id);
CREATE INDEX IF NOT EXISTS ix_performance_metrics_timestamp ON performance_metrics(timestamp DESC);
CREATE INDEX IF NOT EXISTS ix_performance_metrics_type ON performance_metrics(metric_type);
CREATE INDEX IF NOT EXISTS ix_performance_metrics_run_type ON performance_metrics(run_id, metric_type);

-- ============================================================================
-- Table: error_logs
-- Purpose: Centralized error tracking and categorization
-- ============================================================================
CREATE TABLE IF NOT EXISTS error_logs (
    error_id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    execution_id INTEGER,
    phase_id TEXT,
    timestamp TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    error_type TEXT NOT NULL,
    error_category TEXT CHECK(error_category IN ('validation', 'execution', 'api', 'filesystem', 'database', 'network', 'timeout', 'resource', 'unknown')),
    severity TEXT NOT NULL CHECK(severity IN ('debug', 'info', 'warning', 'error', 'critical')),
    error_message TEXT NOT NULL,
    stack_trace TEXT,
    context_json TEXT,
    resolution_status TEXT DEFAULT 'unresolved' CHECK(resolution_status IN ('unresolved', 'investigating', 'resolved', 'wont_fix')),
    resolution_notes TEXT,
    resolved_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (run_id) REFERENCES build_runs(run_id) ON DELETE CASCADE,
    FOREIGN KEY (execution_id) REFERENCES phase_executions(execution_id) ON DELETE CASCADE,
    FOREIGN KEY (phase_id) REFERENCES phases(phase_id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS ix_error_logs_run_id ON error_logs(run_id);
CREATE INDEX IF NOT EXISTS ix_error_logs_execution_id ON error_logs(execution_id);
CREATE INDEX IF NOT EXISTS ix_error_logs_phase_id ON error_logs(phase_id);
CREATE INDEX IF NOT EXISTS ix_error_logs_timestamp ON error_logs(timestamp DESC);
CREATE INDEX IF NOT EXISTS ix_error_logs_type ON error_logs(error_type);
CREATE INDEX IF NOT EXISTS ix_error_logs_category ON error_logs(error_category);
CREATE INDEX IF NOT EXISTS ix_error_logs_severity ON error_logs(severity);
CREATE INDEX IF NOT EXISTS ix_error_logs_resolution ON error_logs(resolution_status);

-- ============================================================================
-- Table: audit_trail
-- Purpose: Track all significant system events and changes
-- ============================================================================
CREATE TABLE IF NOT EXISTS audit_trail (
    audit_id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT,
    execution_id INTEGER,
    timestamp TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    event_type TEXT NOT NULL,
    event_category TEXT CHECK(event_category IN ('build', 'phase', 'config', 'user', 'system', 'security')),
    actor TEXT,
    action TEXT NOT NULL,
    resource_type TEXT,
    resource_id TEXT,
    old_value TEXT,
    new_value TEXT,
    metadata_json TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (run_id) REFERENCES build_runs(run_id) ON DELETE SET NULL,
    FOREIGN KEY (execution_id) REFERENCES phase_executions(execution_id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS ix_audit_trail_run_id ON audit_trail(run_id);
CREATE INDEX IF NOT EXISTS ix_audit_trail_execution_id ON audit_trail(execution_id);
CREATE INDEX IF NOT EXISTS ix_audit_trail_timestamp ON audit_trail(timestamp DESC);
CREATE INDEX IF NOT EXISTS ix_audit_trail_event_type ON audit_trail(event_type);
CREATE INDEX IF NOT EXISTS ix_audit_trail_category ON audit_trail(event_category);
CREATE INDEX IF NOT EXISTS ix_audit_trail_actor ON audit_trail(actor);
CREATE INDEX IF NOT EXISTS ix_audit_trail_resource ON audit_trail(resource_type, resource_id);

-- ============================================================================
-- Triggers: Automatic timestamp updates
-- ============================================================================
CREATE TRIGGER IF NOT EXISTS update_build_runs_timestamp
AFTER UPDATE ON build_runs
FOR EACH ROW
BEGIN
    UPDATE build_runs SET updated_at = CURRENT_TIMESTAMP WHERE run_id = NEW.run_id;
END;

CREATE TRIGGER IF NOT EXISTS update_phase_executions_timestamp
AFTER UPDATE ON phase_executions
FOR EACH ROW
BEGIN
    UPDATE phase_executions SET updated_at = CURRENT_TIMESTAMP WHERE execution_id = NEW.execution_id;
END;

-- ============================================================================
-- Views: Analytical queries for common telemetry patterns
-- ============================================================================

-- View: Recent build summary
CREATE VIEW IF NOT EXISTS v_recent_builds AS
SELECT 
    br.run_id,
    br.started_at,
    br.completed_at,
    br.status,
    br.total_phases,
    br.completed_phases,
    br.failed_phases,
    br.total_tokens_used,
    br.total_cost_usd,
    br.branch_name,
    ROUND((JULIANDAY(br.completed_at) - JULIANDAY(br.started_at)) * 86400000) as duration_ms,
    ROUND(CAST(br.completed_phases AS REAL) / NULLIF(br.total_phases, 0) * 100, 2) as completion_pct
FROM build_runs br
ORDER BY br.started_at DESC
LIMIT 100;

-- View: Phase performance summary
CREATE VIEW IF NOT EXISTS v_phase_performance AS
SELECT 
    pe.phase_id,
    pe.phase_name,
    pe.category,
    pe.complexity,
    COUNT(*) as execution_count,
    SUM(CASE WHEN pe.status = 'completed' THEN 1 ELSE 0 END) as success_count,
    SUM(CASE WHEN pe.status = 'failed' THEN 1 ELSE 0 END) as failure_count,
    ROUND(AVG(pe.execution_time_ms), 2) as avg_execution_ms,
    ROUND(AVG(pe.tokens_used), 2) as avg_tokens,
    ROUND(AVG(pe.cost_usd), 4) as avg_cost_usd,
    SUM(CASE WHEN pe.truncation_detected = 1 THEN 1 ELSE 0 END) as truncation_count,
    ROUND(SUM(CASE WHEN pe.truncation_detected = 1 THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 2) as truncation_rate_pct
FROM phase_executions pe
GROUP BY pe.phase_id, pe.phase_name, pe.category, pe.complexity;

-- View: Token usage trends
CREATE VIEW IF NOT EXISTS v_token_usage_trends AS
SELECT 
    DATE(tum.timestamp) as usage_date,
    tum.model_name,
    COUNT(*) as request_count,
    SUM(tum.prompt_tokens) as total_prompt_tokens,
    SUM(tum.completion_tokens) as total_completion_tokens,
    SUM(tum.total_tokens) as total_tokens,
    ROUND(AVG(tum.total_tokens), 2) as avg_tokens_per_request,
    ROUND(SUM(tum.total_cost_usd), 4) as total_cost_usd,
    ROUND(AVG(tum.response_time_ms), 2) as avg_response_ms
FROM token_usage_metrics tum
GROUP BY DATE(tum.timestamp), tum.model_name
ORDER BY usage_date DESC, tum.model_name;

-- View: Truncation analysis
CREATE VIEW IF NOT EXISTS v_truncation_analysis AS
SELECT 
    te.phase_id,
    p.phase_name,
    te.truncation_type,
    te.severity,
    COUNT(*) as event_count,
    ROUND(AVG(te.estimated_loss_pct), 2) as avg_loss_pct,
    ROUND(AVG(te.tokens_used), 2) as avg_tokens_used,
    SUM(CASE WHEN te.recovery_successful = 1 THEN 1 ELSE 0 END) as successful_recoveries,
    ROUND(SUM(CASE WHEN te.recovery_successful = 1 THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 2) as recovery_rate_pct
FROM truncation_events te
LEFT JOIN phases p ON te.phase_id = p.phase_id
GROUP BY te.phase_id, p.phase_name, te.truncation_type, te.severity
ORDER BY event_count DESC;

-- View: Error summary
CREATE VIEW IF NOT EXISTS v_error_summary AS
SELECT 
    el.error_category,
    el.error_type,
    el.severity,
    COUNT(*) as occurrence_count,
    COUNT(DISTINCT el.run_id) as affected_runs,
    COUNT(DISTINCT el.phase_id) as affected_phases,
    MAX(el.timestamp) as last_occurrence,
    SUM(CASE WHEN el.resolution_status = 'resolved' THEN 1 ELSE 0 END) as resolved_count,
    ROUND(SUM(CASE WHEN el.resolution_status = 'resolved' THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 2) as resolution_rate_pct
FROM error_logs el
GROUP BY el.error_category, el.error_type, el.severity
ORDER BY occurrence_count DESC;

-- ============================================================================
-- Initial data validation
-- ============================================================================

-- Verify foreign key constraints are enabled
PRAGMA foreign_keys = ON;

-- Verify indexes were created
SELECT name, tbl_name FROM sqlite_master WHERE type = 'index' AND name LIKE 'ix_%' ORDER BY tbl_name, name;

-- Migration complete
