/* Defensive normalization shared by both Early Warning surfaces. */
(() => {
  'use strict';
  const safeText = (value, fallback = 'Unavailable') =>
    (typeof value === 'string' && value.trim()) || (typeof value === 'number' && Number.isFinite(value) ? String(value) : fallback);
  const safeNumber = value => value == null || (typeof value === 'string' && value.trim() === '') || typeof value === 'boolean' || !['string','number'].includes(typeof value) || !Number.isFinite(Number(value)) ? null : Number(value);
  const safeArray = value => Array.isArray(value) ? value : [];
  const record = value => value && typeof value === 'object' && !Array.isArray(value);
  const humanize = value => safeText(value).replace(/_/g, ' ');
  const escape = value => safeText(value, '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const states = ['NEW','ACKNOWLEDGED','UNDER_REVIEW','RESOLVED','DISMISSED'];
  const classes = {ML_RISK_WARNING:'PREDICTIVE', RISK_DETERIORATION:'DETERIORATION', EXPENDITURE_ACCELERATION:'DETERIORATION', EXPENDITURE_PROGRESS_GAP:'DETERIORATION', MILESTONE_STAGNATION:'DETERIORATION', COST_ESCALATION:'OBSERVED_ISSUE', SCHEDULE_SLIPPAGE:'OBSERVED_ISSUE'};
  const classLabels = {PREDICTIVE:'Predictive Risk', DETERIORATION:'Deteriorating', OBSERVED_ISSUE:'Observed Issue'};
  const status = value => {
    const candidate = safeText(value.workflow_status || value.status, 'NEW').toUpperCase();
    return value.is_resolved === true ? 'RESOLVED' : states.includes(candidate) ? candidate : 'NEW';
  };
  function normalize(value) {
    if (!record(value)) return null;
    const item = {...value};
    for (const key of ['project_name','sector','state','implementing_agency','priority_label','risk_tier','what_changed','why_flagged','potential_consequence','recommended_investigation','attention_reason','data_confidence']) item[key] = safeText(value[key]);
    item.project_id = safeText(value.project_id, '');
    item.alert_type = safeText(value.alert_type || value.trigger_reason, 'UNKNOWN');
    item.alert_class = Object.hasOwn(classLabels, value.alert_class) ? value.alert_class : classes[item.alert_type] || 'OBSERVED_ISSUE';
    item.alert_class_label = classLabels[item.alert_class];
    item.workflow_status = item.status = status(value);
    item.review_note = safeText(value.review_note, '');
    item.status_updated_at = safeText(value.status_updated_at, '');
    item.severity = safeText(value.highest_severity || value.severity || value.highest_alert_severity);
    for (const key of ['priority_score','risk_score','risk_delta','previous_risk_score','financial_exposure_crore','active_signal_count','signal_count']) item[key] = safeNumber(value[key]);
    item.data_confidence_reasons = safeArray(value.data_confidence_reasons).map(v => safeText(v, '')).filter(Boolean);
    item.evidence = safeArray(value.evidence).filter(record).map(e => ({...e, label:safeText(e.label), current:safeText(e.current,'—'), previous:e.previous == null ? null : safeText(e.previous,'—'), change:safeNumber(e.change)}));
    item.underlying_signals = safeArray(value.underlying_signals).filter(record).map(s => ({...s, alert_type:safeText(s.alert_type || s.trigger_reason), severity:safeText(s.severity), what_changed:safeText(s.what_changed || s.issue_summary || s.message), alert_class:Object.hasOwn(classLabels, s.alert_class) ? s.alert_class : classes[s.alert_type] || 'OBSERVED_ISSUE'}));
    item.alert_classifications = [...new Set(safeArray(value.alert_classifications).filter(c => Object.hasOwn(classLabels, c)).concat(item.underlying_signals.map(s => s.alert_class)))];
    if (!item.alert_classifications.length) item.alert_classifications = [item.alert_class];
    return item;
  }
  const fmt = value => safeNumber(value) == null ? '—' : Number(value).toLocaleString('en-IN',{maximumFractionDigits:1});
  const date = value => {
    const text = safeText(value,'');
    const d = new Date(text);
    return text && Number.isFinite(d.getTime()) ? d.toLocaleString() : 'Unavailable';
  };
  const api = {safeText,safeNumber,safeArray,humanize,escape,normalize,fmt,date,classLabels,closed:item => ['RESOLVED','DISMISSED'].includes(item.workflow_status)};
  if (typeof module !== 'undefined') module.exports = api;
  else window.WarningUI = api;
})();
