-- Additive migration. No alert rows are removed.
ALTER TABLE alerts ADD COLUMN IF NOT EXISTS status VARCHAR(20);
ALTER TABLE alerts ADD COLUMN IF NOT EXISTS status_updated_at TIMESTAMP WITH TIME ZONE;
ALTER TABLE alerts ADD COLUMN IF NOT EXISTS acknowledged_at TIMESTAMP WITH TIME ZONE;
ALTER TABLE alerts ADD COLUMN IF NOT EXISTS resolved_at TIMESTAMP WITH TIME ZONE;
ALTER TABLE alerts ADD COLUMN IF NOT EXISTS dismissed_at TIMESTAMP WITH TIME ZONE;
ALTER TABLE alerts ADD COLUMN IF NOT EXISTS review_note TEXT;
UPDATE alerts SET status = CASE WHEN is_resolved IS TRUE THEN 'RESOLVED' ELSE 'NEW' END WHERE status IS NULL OR (is_resolved IS TRUE AND status <> 'RESOLVED');
UPDATE alerts SET is_resolved = (status = 'RESOLVED') WHERE is_resolved IS DISTINCT FROM (status = 'RESOLVED');
UPDATE alerts SET status_updated_at = COALESCE(triggered_at, CURRENT_TIMESTAMP) WHERE status_updated_at IS NULL;
ALTER TABLE alerts ALTER COLUMN status SET DEFAULT 'NEW';
ALTER TABLE alerts ALTER COLUMN status SET NOT NULL;
CREATE INDEX IF NOT EXISTS idx_alerts_project_type ON alerts(project_id, alert_type);
