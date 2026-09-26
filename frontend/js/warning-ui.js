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
  const validClass = value => typeof value === 'string' && Object.hasOwn(classLabels, value);
  const classify = value => typeof value === 'string' && Object.hasOwn(classes, value) ? classes[value] : 'OBSERVED_ISSUE';
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
    item.alert_class = validClass(value.alert_class) ? value.alert_class : classify(item.alert_type);
    item.alert_class_label = classLabels[item.alert_class];
    item.dominant_classification = validClass(value.dominant_classification) ? value.dominant_classification : item.alert_class;
    item.workflow_status = item.status = status(value);
    item.review_note = safeText(value.review_note, '');
    item.status_updated_at = safeText(value.status_updated_at, '');
    item.severity = safeText(value.highest_severity || value.severity || value.highest_alert_severity);
    for (const key of ['priority_score','risk_score','risk_delta','previous_risk_score','financial_exposure_crore','active_signal_count','signal_count']) item[key] = safeNumber(value[key]);
    item.data_confidence_reasons = safeArray(value.data_confidence_reasons).map(v => safeText(v, '')).filter(Boolean);
    item.evidence = safeArray(value.evidence).filter(record).map(e => ({...e, label:safeText(e.label), current:safeText(e.current,'—'), previous:e.previous == null ? null : safeText(e.previous,'—'), change:safeNumber(e.change)}));
    item.underlying_signals = safeArray(value.underlying_signals).filter(record).map(s => ({...s, alert_type:safeText(s.alert_type || s.trigger_reason), severity:safeText(s.severity), what_changed:safeText(s.what_changed || s.issue_summary || s.message), alert_class:validClass(s.alert_class) ? s.alert_class : classify(s.alert_type)}));
    item.alert_classifications = [...new Set(safeArray(value.contributing_classifications || value.alert_classifications).filter(validClass).concat(item.underlying_signals.map(s => s.alert_class)))];
    if (!item.alert_classifications.length) item.alert_classifications = [item.alert_class];
    return item;
  }
  const fmt = value => safeNumber(value) == null ? '—' : Number(value).toLocaleString('en-IN',{maximumFractionDigits:1});
  const date = value => {
    const text = safeText(value,'');
    const d = new Date(text);
    return text && Number.isFinite(d.getTime()) ? d.toLocaleString() : 'Unavailable';
  };
  // Presentation helpers (additive; existing exports above are unchanged).
  const typeLabels = {ML_RISK_WARNING:'ML risk warning', RISK_DETERIORATION:'Risk deterioration', EXPENDITURE_ACCELERATION:'Expenditure acceleration', EXPENDITURE_PROGRESS_GAP:'Spend ahead of progress', MILESTONE_STAGNATION:'Milestone stagnation', COST_ESCALATION:'Cost escalation', SCHEDULE_SLIPPAGE:'Schedule slippage'};
  const typeLabel = value => {
    const key = safeText(value, '').toUpperCase();
    if (Object.hasOwn(typeLabels, key)) return typeLabels[key];
    const text = humanize(value).toLowerCase();
    return text.charAt(0).toUpperCase() + text.slice(1);
  };
  // "[2022-05] ML risk warning: ..." -> {month:'2022-05', text:'ML risk warning: ...'}
  const splitMonth = value => {
    const text = safeText(value, '');
    const m = /^\s*\[(\d{4}-\d{2})\]\s*/.exec(text);
    return m ? {month:m[1], text:text.slice(m[0].length)} : {month:null, text};
  };
  const statusLabels = {NEW:'New', ACKNOWLEDGED:'Acknowledged', UNDER_REVIEW:'Under review', RESOLVED:'Resolved', DISMISSED:'Dismissed'};

  // ---- Evidence presentation (additive). Formats only what the API sent; never fills gaps. ----
  const MONTHS = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
  // "2022-05" -> "May 2022"; "2022-06-01" -> "1 Jun 2022"; anything else is returned as text.
  const monthLabel = value => {
    const text = safeText(value, '');
    const m = /^(\d{4})-(\d{2})(?:-(\d{2}))?$/.exec(text);
    if (!m || Number(m[2]) < 1 || Number(m[2]) > 12) return text;
    return `${m[3] ? `${Number(m[3])} ` : ''}${MONTHS[Number(m[2]) - 1]} ${m[1]}`;
  };
  const unitText = unit => safeText(unit, '').trim();
  // Value with its unit: crore -> "₹4,825.6 Cr", % -> "60.7%", points -> "78.1 pts".
  const evidenceValue = (value, unit) => {
    const n = safeNumber(value), u = unitText(unit).toLowerCase();
    if (n == null) {
      const text = safeText(value, '—');
      return /^\d{4}-\d{2}(-\d{2})?$/.test(text) ? monthLabel(text) : (u && text !== '—' ? `${text} ${unitText(unit)}` : text);
    }
    const f = fmt(n);
    if (u === 'crore') return `₹${f} Cr`;
    if (u === '%') return `${f}%`;
    if (u === 'points') return `${f} pts`;
    if (u === 'percentage points') return `${f} pp`;
    if (u === 'months') return `${f} mo`;
    return u ? `${f} ${unitText(unit)}` : f;
  };
  // Signed change in the metric's unit; 0 -> "no change"; null -> '' (nothing to show).
  const evidenceChange = (change, unit) => {
    const n = safeNumber(change);
    if (n == null) return '';
    if (n === 0) return 'no change';
    return `${n > 0 ? '+' : '−'}${evidenceValue(Math.abs(n), unit)}`;
  };
  // Metric months: "Apr 2022 → May 2022", or just the current month.
  const evidenceMonths = e => {
    const cur = monthLabel(e && e.current_report_month), prev = monthLabel(e && e.previous_report_month);
    return prev && cur && prev !== cur ? `${prev} → ${cur}` : cur || prev || '';
  };
  // Collapses repeated history labels (one reading per month) into a single series row.
  function evidenceRows(evidence) {
    const rows = [], series = {};
    for (const e of safeArray(evidence)) {
      if (!record(e)) continue;
      const label = safeText(e.label);
      const isPoint = e.previous == null && /history$/i.test(label);
      if (isPoint && series[label]) { series[label].points.push(e); continue; }
      const row = {...e, label, points: isPoint ? [e] : null};
      if (isPoint) series[label] = row;
      rows.push(row);
    }
    return rows.map(r => {
      if (!r.points || r.points.length < 2) return {...r, points: null};
      const pts = r.points.slice().sort((a, b) => safeText(a.current_report_month, '').localeCompare(safeText(b.current_report_month, '')));
      const first = pts[0], last = pts[pts.length - 1];
      return {...r, series: pts.length, previous: first.current, current: last.current, change: null,
        previous_report_month: first.current_report_month, current_report_month: last.current_report_month, points: null};
    });
  }
  // Metrics most relevant to each trigger type, shown first on the card.
  const evidenceFocus = {
    ML_RISK_WARNING: ['Cost risk model','Schedule risk model','Lifecycle risk model','Anticipated cost'],
    RISK_DETERIORATION: ['Cost risk model','Schedule risk model','Lifecycle risk model','Anticipated cost'],
    COST_ESCALATION: ['Anticipated cost','Original approved cost','Revised cost','Rule cost baseline (revised, anticipated, original)'],
    SCHEDULE_SLIPPAGE: ['Original delay','Revised delay','Anticipated Commissioning Date','Revised Commissioning Date'],
    EXPENDITURE_ACCELERATION: ['Cumulative expenditure','Expenditure history','Anticipated cost'],
    EXPENDITURE_PROGRESS_GAP: ['Expenditure minus milestone progress','Cumulative expenditure','Milestones achieved'],
    MILESTONE_STAGNATION: ['Milestones achieved','Milestone history','Cumulative expenditure']
  };
  // -> {top: rows to show on the card, rest: remaining rows, total}
  function pickEvidence(evidence, alertType, {limit = 4, exclude = []} = {}) {
    const rows = evidenceRows(evidence);
    const key = safeText(alertType, '').toUpperCase();
    const focus = Object.hasOwn(evidenceFocus, key) ? evidenceFocus[key] : [];
    const rank = r => {
      const f = focus.indexOf(r.label);
      if (f >= 0) return f;
      if (exclude.includes(r.label)) return 1000;
      const ch = safeNumber(r.change);
      return ch != null && ch !== 0 ? 100 : 200;
    };
    const ordered = rows.map((r, i) => ({r, i, k: rank(r)})).sort((a, b) => a.k - b.k || a.i - b.i).map(x => x.r);
    return {top: ordered.slice(0, limit), rest: ordered.slice(limit), total: rows.length};
  }

  const api = {safeText,safeNumber,safeArray,humanize,escape,normalize,fmt,date,classLabels,closed:item => ['RESOLVED','DISMISSED'].includes(item.workflow_status),
    typeLabels, typeLabel, splitMonth, statusLabels,
    monthLabel, evidenceValue, evidenceChange, evidenceMonths, evidenceRows, pickEvidence};
  if (typeof module !== 'undefined') module.exports = api;
  else window.WarningUI = api;
})();
