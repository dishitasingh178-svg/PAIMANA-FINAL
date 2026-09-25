CREATE TABLE IF NOT EXISTS projects (
    project_id VARCHAR(50) PRIMARY KEY,
    project_name TEXT NOT NULL,
    sector VARCHAR(100),
    implementing_agency VARCHAR(100),
    state VARCHAR(100),
    date_of_approval DATE,
    original_cost_crore NUMERIC(14, 2),
    original_commissioning_date DATE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS project_updates (
    id BIGSERIAL PRIMARY KEY,
    project_id VARCHAR(50) NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
    report_month VARCHAR(7) NOT NULL,
    serial_no INT,
    revised_cost_crore NUMERIC(14, 2),
    anticipated_cost_crore NUMERIC(14, 2),
    cumulative_expenditure_crore NUMERIC(14, 2),
    revised_commissioning_date DATE,
    anticipated_commissioning_date DATE,
    delay_original_months NUMERIC(8, 2),
    delay_revised_months NUMERIC(8, 2),
    milestones_achieved INT,
    milestones_total INT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT unique_project_report UNIQUE (project_id, report_month)
);

CREATE TABLE IF NOT EXISTS predictions (
    prediction_id BIGSERIAL PRIMARY KEY,
    project_id VARCHAR(50) NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
    report_month VARCHAR(7) NOT NULL,
    cost_risk_probability NUMERIC(6, 4) NOT NULL,
    schedule_risk_probability NUMERIC(6, 4) NOT NULL,
    cox_risk NUMERIC(10, 4) NOT NULL,
    cox_risk_probability NUMERIC(6, 4) NOT NULL,
    composite_risk_score NUMERIC(5, 2) NOT NULL,
    risk_tier VARCHAR(20) NOT NULL,
    model_version VARCHAR(50) DEFAULT '1.0.0',
    generated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS alerts (
    alert_id BIGSERIAL PRIMARY KEY,
    project_id VARCHAR(50) NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
    alert_type VARCHAR(50) NOT NULL,
    severity VARCHAR(20) NOT NULL,
    message TEXT NOT NULL,
    is_resolved BOOLEAN DEFAULT FALSE,
    status VARCHAR(20) NOT NULL DEFAULT 'NEW',
    status_updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    acknowledged_at TIMESTAMP WITH TIME ZONE,
    resolved_at TIMESTAMP WITH TIME ZONE,
    dismissed_at TIMESTAMP WITH TIME ZONE,
    review_note TEXT,
    triggered_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_updates_proj_month ON project_updates(project_id, report_month);
CREATE INDEX IF NOT EXISTS idx_predictions_proj ON predictions(project_id);
CREATE INDEX IF NOT EXISTS idx_alerts_unresolved ON alerts(project_id) WHERE is_resolved = FALSE;
