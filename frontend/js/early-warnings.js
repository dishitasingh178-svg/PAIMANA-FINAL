(() => {
  'use strict';
  if (window.__warningCenterInitialized) return;
  window.__warningCenterInitialized = true;
  const U = window.WarningUI, P = window.PM, el = id => document.getElementById(id);
  const {escape:esc, fmt, humanize} = U;
  const params = new URLSearchParams(location.search), projectId = params.get('project_id');

  // Server-side queues (query params sent to /alerts/workspace — unchanged)
  const filters = [
    ['new','New',{status:'NEW'}], ['immediate','Immediate',{priority:'IMMEDIATE'}],
    ['predictive','Predictive',{classification:'PREDICTIVE'}], ['deteriorating','Deteriorating',{classification:'DETERIORATION'}],
    ['observed','Observed Issues',{classification:'OBSERVED_ISSUE'}], ['acknowledged','Acknowledged',{status:'ACKNOWLEDGED'}],
    ['review','Under Review',{status:'UNDER_REVIEW'}], ['resolved','Resolved',{status:'RESOLVED'}], ['dismissed','Dismissed',{status:'DISMISSED'}]
  ];
  const groups = [['Open', ['new','immediate','predictive','deteriorating','observed']], ['In review', ['acknowledged','review']], ['Closed', ['resolved','dismissed']]];
  let active = 'new', rows = [], refreshFlight = null, mutating = false, loadedOnce = false, lastSummary = null;
  const refine = {severity:'', sector:'', days:''};
  const expanded = new Set(projectId ? [projectId] : []);
  const EVIDENCE_ON_CARD = 3;

  const icon = (name, cls = 'w-4 h-4') => P ? P.icon(name, cls) : '';
  const badge = (sev, score, showScore = false) => P ? P.tierBadge(sev, score, {showScore}) : esc(sev);
  const tierOf = (sev, score) => P ? P.tier(sev, score) : 'UNKNOWN';
  const motion = () => Boolean(P && !P.reducedMotion());
  const title = s => U.safeText(s, '').toLowerCase().replace(/\b\w/g, c => c.toUpperCase()).replace(/\b(And|Of)\b/g, m => m.toLowerCase());
  const money = value => value == null ? '—' : `₹${fmt(value)} Cr`;
  const signed = value => value == null ? '—' : `${value > 0 ? '+' : value < 0 ? '−' : ''}${fmt(Math.abs(value))}`;
  const delta = value => value == null ? 'Previous period unavailable.' : `${signed(value)} points`;
  const month = ym => U.monthLabel(ym) || '—';
  const when = iso => {
    const d = new Date(U.safeText(iso, ''));
    if (!Number.isFinite(d.getTime())) return {rel:'—', abs:'Time unavailable'};
    const s = (Date.now() - d.getTime()) / 1000;
    const rel = s < 60 ? 'just now' : s < 3600 ? `${Math.round(s / 60)} min ago` : s < 86400 ? `${Math.round(s / 3600)} h ago`
      : s < 86400 * 45 ? `${Math.round(s / 86400)} d ago` : d.toLocaleDateString('en-IN', {day:'numeric', month:'short', year:'numeric'});
    return {rel, abs:d.toLocaleString('en-IN', {dateStyle:'medium', timeStyle:'short'})};
  };
  const section = (heading, text) => `<section><h4 class="d-h">${heading}</h4><p class="d-p">${esc(U.safeText(text))}</p></section>`;
  const wfPill = status => `<span class="wf" data-wf="${esc(status)}">${esc(U.statusLabels[status] || humanize(status))}</span>`;
  const domId = value => U.safeText(value, '').replace(/[^A-Za-z0-9_-]/g, '_') || Math.random().toString(36).slice(2);

  function matches(item) {
    const query = filters.find(f => f[0] === active)[2];
    return (query.status ? item.workflow_status === query.status : !U.closed(item))
      && (!query.classification || item.dominant_classification === query.classification)
      && (!query.priority || item.priority_label === query.priority);
  }
  // Client-side refinements over the cases already loaded
  function refined(item) {
    if (refine.severity && tierOf(item.severity) !== refine.severity) return false;
    if (refine.sector && item.sector !== refine.sector) return false;
    if (refine.days) {
      const t = new Date(item.triggered_at).getTime();
      if (!Number.isFinite(t) || Date.now() - t > Number(refine.days) * 86400000) return false;
    }
    return true;
  }
  const refining = () => Boolean(refine.severity || refine.sector || refine.days);

  function normalizeList(data) {
    if (!Array.isArray(data)) throw new Error('The server returned an invalid case list. Verify the deployed API version.');
    const seen = new Set();
    return data.map(U.normalize).filter(item => {
      if (!item) return false;
      if (!item.project_id) return true;
      if (seen.has(item.project_id)) return false;
      seen.add(item.project_id); return true;
    });
  }

  // ------------------------------------------------------------------
  // Evidence (always visible on the card)
  // ------------------------------------------------------------------
  // Model comparison from the case's own fields: previous -> current composite score.
  function modelLine(item) {
    if (item.risk_delta == null && item.previous_risk_score == null) return '';
    const from = item.previous_risk_score, to = item.risk_score;
    const pm = U.monthLabel(item.previous_prediction_report_month), cm = U.monthLabel(item.prediction_report_month || item.report_month);
    const scores = from != null && to != null
      ? `<span class="ev-prev">${esc(fmt(from))}</span><span class="ev-arr" aria-label="to">→</span><b>${esc(fmt(to))}</b>`
      : to != null ? `<b>${esc(fmt(to))}</b>` : '';
    return `<p class="model"><span class="model-k">Model comparison</span>
      <span class="model-v pm-num">Composite risk ${scores}${item.risk_delta != null ? ` <span class="ev-c">(${esc(signed(item.risk_delta))} pts)</span>` : ''}</span>
      ${pm || cm ? `<span class="ev-m">${esc(pm && cm && pm !== cm ? `${pm} → ${cm}` : cm || pm)}</span>` : ''}</p>`;
  }
  function evRow(e) {
    const cur = U.evidenceValue(e.current, e.unit);
    const same = e.previous != null && String(e.previous) === String(e.current);
    const prev = e.previous != null && !same ? U.evidenceValue(e.previous, e.unit) : '';
    const chg = e.series ? '' : U.evidenceChange(e.change, e.unit) || (same ? 'no change' : '');
    const months = U.evidenceMonths(e);
    return `<div class="ev-row">
      <span class="ev-l">${esc(e.label)}${e.series ? ` <span class="ev-tag">${esc(fmt(e.series))} reports</span>` : ''}</span>
      <span class="ev-v pm-num">${prev ? `<span class="ev-prev">${esc(prev)}</span><span class="ev-arr" aria-label="to">→</span>` : ''}<b>${esc(cur)}</b>${chg ? ` <span class="ev-c">(${esc(chg)})</span>` : ''}</span>
      <span class="ev-m">${esc(months)}</span></div>`;
  }
  function evidenceHTML(item, did) {
    const hasModel = item.risk_delta != null || item.previous_risk_score != null;
    const {top, rest, total} = U.pickEvidence(item.evidence, item.dominant_alert_type || item.alert_type, {limit:EVIDENCE_ON_CARD, exclude: hasModel ? ['Composite risk'] : []});
    const head = `<p class="ev-head">${icon('chart-line', 'w-3.5 h-3.5')}<span>Evidence · latest available data</span>${total ? `<span class="ev-n">${esc(fmt(total))} metric${total === 1 ? '' : 's'}</span>` : ''}</p>`;
    if (!total) return `<section class="ev" aria-label="Evidence">${head}${modelLine(item)}<p class="ev-none">No evidence metrics recorded for this case.</p></section>`;
    return `<section class="ev" aria-label="Evidence, latest available data">${head}${modelLine(item)}
      <div class="ev-rows">${top.map(evRow).join('')}</div>
      ${rest.length ? `<div class="ev-rows ev-rest" id="ev-${did}" hidden>${rest.map(evRow).join('')}</div>
        <button type="button" class="ev-more" data-ev-more aria-expanded="false" aria-controls="ev-${did}"><span data-label>+${esc(fmt(rest.length))} more metric${rest.length === 1 ? '' : 's'}</span>${icon('chevron-right', 'w-3.5 h-3.5')}</button>` : ''}
    </section>`;
  }

  // ------------------------------------------------------------------
  // Case cards
  // ------------------------------------------------------------------
  function detailHTML(item) {
    const closed = U.closed(item);
    const riskMonth = item.prediction_report_month || item.report_month;
    const issue = U.splitMonth(item.what_changed);
    return `
      <div class="facts">
        <div><p class="pm-kpi-label">Model risk</p><div class="v">${badge(item.risk_tier, item.risk_score, true)}</div><p class="s">Composite, report ${esc(month(riskMonth))}</p></div>
        <div><p class="pm-kpi-label">Change vs previous</p><p class="v">${esc(delta(item.risk_delta))}</p><p class="s">${item.previous_risk_score != null ? `from ${esc(fmt(item.previous_risk_score))}${item.previous_prediction_report_month ? ` · ${esc(month(item.previous_prediction_report_month))}` : ''}` : 'No earlier prediction'}</p></div>
        <div><p class="pm-kpi-label">Financial exposure</p><p class="v">${esc(money(item.financial_exposure_crore))}</p><p class="s">Latest anticipated cost</p></div>
        <div><p class="pm-kpi-label">Data confidence</p><p class="v">${esc(humanize(item.data_confidence))}</p><p class="s">${esc(item.data_confidence_reasons.join(' ') || '—')}</p></div>
      </div>
      <div class="d-grid">${section('What changed', issue.text || item.what_changed)}${section('Why flagged', item.why_flagged)}
        ${section('Potential consequence', item.potential_consequence)}${section('Recommended investigation', item.recommended_investigation)}</div>
      <section class="mt-5">
        <h4 class="d-h">Contributing signals (${esc(fmt(item.signal_count))})</h4>
        <div class="sigs">${item.underlying_signals.map(s => {
          const sm = U.splitMonth(s.what_changed);
          return `<div class="sig"><div class="pt-0.5">${badge(s.severity)}</div><div class="min-w-0"><p style="color:var(--pm-text);font-weight:600">${esc(U.typeLabel(s.alert_type))}${sm.month ? ` <span class="pm-updated">· report ${esc(month(sm.month))}</span>` : ''}</p><p class="mt-0.5" style="color:var(--pm-text-2)">${esc(sm.text || s.what_changed)}</p></div></div>`;
        }).join('') || '<p class="d-p">Signal details unavailable.</p>'}</div>
      </section>
      <div class="act-panel">
        <label class="block text-[12px] font-semibold" style="color:var(--pm-muted)">Optional officer note
          <textarea maxlength="5000" rows="2" class="note mt-1.5 mb-3">${esc(item.review_note)}</textarea></label>
        <div class="flex flex-wrap items-center gap-2">
          ${(closed ? [['NEW','Reopen']] : [['ACKNOWLEDGED','Acknowledge'],['UNDER_REVIEW','Under Review'],['DISMISSED','Dismiss'],['RESOLVED','Resolve']]).map(([status, label]) =>
            `<button type="button" data-status="${status}" ${!item.project_id || status === item.workflow_status ? 'disabled' : ''} class="pm-btn pm-btn-sm ${status === 'RESOLVED' ? 'pm-btn-primary' : ''}">${label}</button>`).join('')}
          <span class="pm-updated" style="white-space:normal">Moves the whole case and its open signals.</span>
        </div>
      </div>`;
  }

  function caseHTML(item) {
    const closed = U.closed(item);
    const open = expanded.has(item.project_id);
    const issue = U.splitMonth(item.what_changed);
    const hasModel = item.risk_delta != null || item.previous_risk_score != null;
    // The model comparison sentence is shown as its own line inside Evidence; the headline keeps the problem.
    const text = issue.text || item.what_changed;
    const headline = hasModel ? text.split(/\s*Latest model comparison:/)[0] || text : text;
    const reportMonth = issue.month || (item.report_month !== 'Unavailable' ? item.report_month : '');
    const t = when(item.triggered_at);
    const others = item.alert_classifications.filter(c => c !== item.dominant_classification).map(c => U.classLabels[c]);
    const did = `case-${esc(domId(item.project_id))}`;
    const href = `project-details.html?id=${encodeURIComponent(item.project_id)}`;
    return `<article class="case ${open ? 'is-open' : ''}" data-project-id="${esc(item.project_id)}" data-tier="${tierOf(item.severity)}" data-closed="${closed}" aria-labelledby="${did}-name">
      <div class="case-main">
        <div class="case-top">
          <div class="case-flags">${badge(item.severity)}${wfPill(item.workflow_status)}
            ${item.has_new_evidence === true ? `<span class="flag">${icon('sparkles', 'w-3 h-3')}New evidence since review</span>` : ''}</div>
          <p class="prio-tag" title="Warning priority score (0–100)"><span class="pm-num">${esc(fmt(item.priority_score))}</span><span class="prio-tag-l" data-p="${esc(item.priority_label)}">${esc(humanize(item.priority_label).toLowerCase())} priority</span></p>
        </div>
        <h3 class="case-h"><a id="${did}-name" class="case-name" href="${href}">${esc(item.project_name)}</a></h3>
        <p class="case-meta">${esc([title(item.sector), title(item.state), item.project_id].filter(v => v && v !== 'Unavailable').join(' · '))}</p>
        <p class="case-issue">${reportMonth ? `<span class="rm" title="Report month of the triggering data">${esc(month(reportMonth))}</span>` : ''}<span>${esc(headline)}</span></p>
        ${evidenceHTML(item, did)}
        ${item.review_note ? `<p class="case-note"><span><b>Officer Note:</b> ${esc(item.review_note)}</span><span class="pm-updated">Updated ${esc(U.date(item.status_updated_at))}</span></p>` : ''}
        <div class="case-foot">
          <p class="case-why"><span class="case-time"><time datetime="${esc(item.triggered_at)}" title="Raised ${esc(t.abs)}">Raised ${esc(t.rel)}</time></span>
            <span>Trigger <b>${esc(U.classLabels[item.dominant_classification])}</b> · ${esc(U.typeLabel(item.dominant_alert_type || item.alert_type))}</span>
            <span>${esc(fmt(item.signal_count))} contributing signal${item.signal_count === 1 ? '' : 's'}</span>
            ${others.length ? `<span>Other signals: ${esc(others.join(', '))}</span>` : ''}</p>
          <div class="case-acts">
            <a class="pm-btn pm-btn-ghost pm-btn-sm" href="${href}">Open project</a>
            <button type="button" class="pm-btn pm-btn-sm toggle" data-toggle aria-expanded="${open}" aria-controls="${did}">${icon('chevron-right', 'w-3.5 h-3.5')}<span data-label>${open ? 'Hide review' : 'Review case'}</span></button>
          </div>
        </div>
      </div>
      <div class="case-detail" id="${did}" ${open ? '' : 'hidden'}>${open ? detailHTML(item) : ''}</div>
    </article>`;
  }

  function renderRows() {
    const box = el('alerts-container');
    const visible = rows.filter(refined);
    const queue = filters.find(f => f[0] === active)[1];
    el('queue-count').textContent = rows.length ? (refining() ? `Showing ${visible.length} of ${rows.length} loaded cases` : `${rows.length} case${rows.length === 1 ? '' : 's'} loaded`) : '';
    el('f-clear').hidden = !refining();
    if (!rows.length) {
      box.innerHTML = P ? P.stateHTML({kind:'empty', title:`No cases in the ${queue} queue`, message: projectId ? 'This project has no case in this queue. Try another queue, or view all projects.' : 'Nothing needs attention here right now.'}) : 'No warnings in this queue.';
      return;
    }
    if (!visible.length) {
      box.innerHTML = `${P ? P.stateHTML({kind:'empty', title:'No loaded cases match these refinements', message:'Clear the severity, sector or time refinement, or load more cases.'}) : 'No matches.'}<div class="flex justify-center -mt-2"><button type="button" class="pm-btn pm-btn-sm" data-clear-refine>Clear refinements</button></div>`;
      return;
    }
    box.innerHTML = visible.map(caseHTML).join('');
  }

  function toggleCase(card) {
    const id = card.dataset.projectId, item = rows.find(r => r.project_id === id);
    if (!item) return;
    const btn = card.querySelector('[data-toggle]'), detail = card.querySelector('.case-detail');
    const open = btn.getAttribute('aria-expanded') !== 'true';
    if (open) { expanded.add(id); if (!detail.childElementCount) detail.innerHTML = detailHTML(item); } else expanded.delete(id);  // collapsing keeps a typed note
    detail.hidden = !open;
    card.classList.toggle('is-open', open);
    btn.setAttribute('aria-expanded', String(open));
    btn.querySelector('[data-label]').textContent = open ? 'Hide review' : 'Review case';
    if (open && motion()) { detail.classList.remove('reveal-in'); void detail.offsetWidth; detail.classList.add('reveal-in'); }
  }
  function toggleEvidence(btn) {
    if (typeof btn.getAttribute !== 'function') return;
    const panel = document.getElementById(btn.getAttribute('aria-controls'));
    if (!panel) return;
    const open = btn.getAttribute('aria-expanded') !== 'true';
    panel.hidden = !open;
    btn.setAttribute('aria-expanded', String(open));
    const n = panel.children.length;
    btn.querySelector('[data-label]').textContent = open ? 'Show fewer metrics' : `+${fmt(n)} more metric${n === 1 ? '' : 's'}`;
    if (open && motion()) P.stagger(panel.children, 22, 'pm-fade-swap');
  }

  function syncSectorOptions() {
    const sel = el('f-sector');
    const sectors = [...new Set(rows.map(r => r.sector).filter(s => s && s !== 'Unavailable'))].sort();
    if (refine.sector && !sectors.includes(refine.sector)) sectors.unshift(refine.sector);
    sel.innerHTML = `<option value="">All sectors${sectors.length ? ` (${sectors.length})` : ''}</option>` + sectors.map(s => `<option value="${esc(s)}" ${s === refine.sector ? 'selected' : ''}>${esc(title(s))}</option>`).join('');
  }

  // ------------------------------------------------------------------
  // Summary + priority
  // ------------------------------------------------------------------
  const SUMMARY = [['new','New','new','Awaiting triage'],['immediate','Immediate','immediate','Priority label Immediate'],
    ['acknowledged','Acknowledged','acknowledged','Seen by an officer'],['under_review','Under review','review','Being investigated'],
    ['resolved','Resolved','resolved','Closed · addressed'],['dismissed','Dismissed','dismissed','Closed · not actionable']];
  function renderSummary(data) {
    lastSummary = data;
    el('warning-summary').innerHTML = SUMMARY.map(([key, label, filter, foot]) => `<button type="button" class="sum-cell" data-filter="${filter}" aria-pressed="${filter === active}" title="${esc(foot)}" aria-label="${esc(label)}: ${esc(fmt(data?.[key]))}. ${esc(foot)}. Show this queue.">
      <span class="sum-l">${label}</span><p class="sum-v" data-count="${key}">${fmt(data?.[key])}</p></button>`).join('');
    const parts = [];
    if (data?.total_cases != null) parts.push(`${fmt(data.total_cases)} cases`);
    if (data?.raw_alert_count != null) parts.push(`${fmt(data.raw_alert_count)} raw signals`);
    if (data?.total_projects != null) parts.push(`${fmt(data.total_projects)} projects monitored`);
    el('summary-foot').textContent = parts.join(' · ');
    if (P) el('warning-summary').querySelectorAll('[data-count]').forEach(n => { const v = U.safeNumber(data?.[n.dataset.count]); if (v != null) P.countUp(n, v); });
  }
  function renderPriority(data) {
    const list = normalizeList(data).filter(c => !U.closed(c));
    el('priority-projects').innerHTML = list.map((c, i) => {
      const raw = U.safeText(c.attention_reason, '');
      const rm = /\[(\d{4}-\d{2})\]/.exec(raw);
      const text = raw.replace(/^\s*\d+ contributing signals?\.\s*/i, '').replace(/\[\d{4}-\d{2}\]\s*/g, '');
      const reason = {month: rm ? rm[1] : null, text: c.risk_delta != null ? text.split(/\s*Latest model comparison:/)[0] || text : text};
      return `<li><a href="project-details.html?id=${encodeURIComponent(c.project_id)}" class="prio" aria-label="${esc(c.project_name)}, priority ${esc(fmt(c.priority_score))}. Open project.">
        <span class="prio-rank pm-num">${i + 1}</span>
        <span class="prio-body">
          <span class="prio-name">${esc(c.project_name)}</span>
          <span class="prio-meta">${badge(null, c.risk_score, true)}${c.risk_delta != null ? `<span class="pm-num">${esc(signed(c.risk_delta))} pts</span>` : ''}<span>${esc(title(c.sector))}</span></span>
          <span class="prio-reason">${esc(reason.text || c.attention_reason)}</span>
          <span class="prio-foot">${esc(U.statusLabels[c.workflow_status] || humanize(c.workflow_status))} · ${fmt(c.active_signal_count)} open signals · ${money(c.financial_exposure_crore)}${reason.month ? ` · report ${esc(month(reason.month))}` : ''}</span>
        </span>
        <span class="prio-score"><b class="pm-num">${fmt(c.priority_score)}</b><span data-p="${esc(c.priority_label)}">${esc(humanize(c.priority_label).toLowerCase())}</span></span></a></li>`;
    }).join('') || `<li>${P ? P.stateHTML({kind:'empty', title:'No projects currently require immediate attention', inline:true}) : 'No projects currently require immediate attention.'}</li>`;
    if (P) P.stagger(el('priority-projects').children, 50, 'pm-fade-swap');
  }

  // ------------------------------------------------------------------
  // Loading states
  // ------------------------------------------------------------------
  const skelRow = w => `<div class="ev-row"><div class="pm-skel pm-skel-line" style="width:${w}%;margin:3px 0"></div><div class="pm-skel pm-skel-line" style="width:90px;margin:3px 0"></div><div class="pm-skel pm-skel-line ev-m" style="width:60px;margin:3px 0"></div></div>`;
  const skelCases = () => Array.from({length:3}, () => `<div class="case case-skel" aria-hidden="true"><div class="case-main">
    <div class="case-top"><div class="flex gap-2"><div class="pm-skel" style="width:84px;height:22px"></div><div class="pm-skel" style="width:52px;height:22px;border-radius:99px"></div></div><div class="pm-skel" style="width:92px;height:22px"></div></div>
    <div class="pm-skel pm-skel-line" style="width:46%;height:14px;margin-top:12px"></div><div class="pm-skel pm-skel-line" style="width:24%"></div>
    <div class="pm-skel pm-skel-line" style="width:78%;margin-top:12px"></div>
    <div class="ev"><div class="pm-skel pm-skel-line" style="width:32%;margin:0 0 8px"></div>${skelRow(40)}${skelRow(34)}${skelRow(46)}</div>
    <div class="case-foot"><div class="pm-skel pm-skel-line" style="width:90px"></div><div class="pm-skel" style="width:190px;height:30px"></div></div>
  </div></div>`).join('');
  function showSkeletons() {
    if (!P) { el('alerts-container').textContent = 'Loading warnings...'; return; }
    el('alerts-container').innerHTML = skelCases();
    if (!loadedOnce) {
      el('warning-summary').innerHTML = SUMMARY.map(() => `<div class="sum-cell"><div class="pm-skel pm-skel-line" style="width:64%;margin:2px 0 8px"></div><div class="pm-skel" style="height:20px;width:44%"></div></div>`).join('');
      el('priority-projects').innerHTML = Array.from({length:5}, () => `<li class="prio prio-skel" aria-hidden="true"><div class="pm-skel" style="width:18px;height:18px;border-radius:5px"></div><div><div class="pm-skel pm-skel-line" style="width:80%;margin-top:0"></div><div class="pm-skel pm-skel-line" style="width:50%"></div><div class="pm-skel pm-skel-line" style="width:92%"></div></div><div class="pm-skel" style="width:34px;height:20px"></div></li>`).join('');
    }
  }
  function showError(message) {
    if (!P) {  // no design-system helpers: plain text only (never inject the message as HTML)
      el('alerts-container').textContent = `Unable to load cases. ${message}`;
      if (!loadedOnce) { el('warning-summary').textContent = 'Counts unavailable.'; el('priority-projects').textContent = 'Priority projects unavailable.'; }
      return;
    }
    el('alerts-container').innerHTML = P.stateHTML({kind:'error', title:'Unable to load cases', message});
    if (!loadedOnce) {
      el('warning-summary').innerHTML = `<div class="sum-err">${P.stateHTML({kind:'error', title:'Counts unavailable', message, inline:true})}</div>`;
      el('priority-projects').innerHTML = `<li>${P.stateHTML({kind:'error', title:'Priority projects unavailable', message, inline:true})}</li>`;
    }
    if (typeof document.querySelectorAll === 'function') {
      document.querySelectorAll('[data-pm-retry]').forEach(b => b.addEventListener('click', () => { if (!mutating) refresh(); }, {once:true}));
    }
  }
  function setFeedback(text, kind = 'info') {
    const f = el('warning-feedback');
    if (f.dataset) f.dataset.kind = kind;
    f.textContent = text;
  }

  function controls(disabled) {
    const btn = el('refresh-warnings');
    btn.disabled = disabled;
    if (btn.classList) btn.classList.toggle('spin', disabled);
    // Browsers update the label span; DOMs without querySelector get the label on the button itself.
    const label = typeof btn.querySelector === 'function' ? btn.querySelector('[data-label]') : null;
    (label || btn).textContent = disabled ? 'Refreshing…' : 'Refresh';
    el('load-more-warnings').disabled = disabled;
    el('alert-filters').querySelectorAll('button').forEach(b => b.disabled = disabled);
    el('warning-summary').querySelectorAll('button').forEach(b => b.disabled = disabled);
  }
  // quiet: keep the current list on screen (after a status change) instead of flashing skeletons.
  function refresh(append = false, {quiet = false} = {}) {
    if (refreshFlight) return refreshFlight;
    controls(true);
    setFeedback('');
    const query = {...filters.find(f => f[0] === active)[2], limit:50, offset:append ? rows.length : 0, ...(projectId ? {project_id:projectId} : {})};
    el('alerts-container').setAttribute('aria-busy','true');
    if (!append && !quiet) showSkeletons();
    const before = append ? rows.length : 0;
    refreshFlight = (async () => {
      try {
        const data = await API.getWarningWorkspace(query);
        if (!data || !data.summary || !Array.isArray(data.priority)) throw new Error('Invalid warning workspace response.');
        const list = normalizeList(data.cases).filter(matches);
        rows = append ? normalizeList(rows.concat(list)) : list;
        loadedOnce = true;
        syncSectorOptions();
        renderRows(); renderSummary(data.summary); renderPriority(data.priority);
        el('load-more-warnings').hidden = data.has_more !== true;
        if (P) P.markUpdated(el('updated'));
        if (P && !quiet) P.stagger(Array.from(el('alerts-container').children).slice(before), 40, 'pm-pop-in');
        if (projectId && !append) { const open = el('alerts-container').querySelector('.case.is-open'); if (open) open.scrollIntoView({block:'nearest'}); }
      } catch (error) {
        if (!append) rows = [];
        el('load-more-warnings').hidden = true;
        const base = U.safeText(error?.message);
        const message = /retry/i.test(base) ? base : `${base} Retry, or use Refresh.`;
        showError(message);
        setFeedback(message, 'error');
      }
    })().finally(() => { refreshFlight = null; controls(false); el('alerts-container').setAttribute('aria-busy','false'); });
    return refreshFlight;
  }

  function highlight() {
    // Optional DOM API: absent in lightweight DOMs (e.g. the Node test harness); real browsers always have it.
    if (typeof document.querySelectorAll === 'function') {
      document.querySelectorAll('[data-filter]').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.filter === active)));
    }
    el('warning-filter-help').textContent = filters.find(f => f[0] === active)[2].status
      ? 'One case per project. Actions move the entire case and its open signals into the selected workflow state.'
      : 'Open cases grouped by their primary reason. Other contributing signals remain inside each case.';
  }
  function selectFilter(key) {
    if (refreshFlight || mutating || !filters.some(f => f[0] === key)) return;
    active = key; highlight(); setFeedback(''); refresh();
  }

  // Status change feedback: the card folds out of the queue before the list re-renders.
  function leave(card) {
    if (!card.classList || !card.style || !motion()) return Promise.resolve();
    card.style.height = `${card.offsetHeight}px`;
    void card.offsetHeight;
    card.classList.add('is-leaving');
    return new Promise(resolve => setTimeout(resolve, 320));
  }

  // ------------------------------------------------------------------
  // Wiring
  // ------------------------------------------------------------------
  const byKey = Object.fromEntries(filters.map(f => [f[0], f]));
  el('alert-filters').innerHTML = groups.map(([label, keys]) => `<div class="chip-group" role="group" aria-label="${label} queues"><span class="chip-group-label">${label}</span>${keys.map(k => `<button type="button" class="pm-chip" data-filter="${k}" aria-pressed="false">${esc(byKey[k][1])}</button>`).join('')}</div>`).join('');
  highlight();
  el('alert-filters').addEventListener('click', event => { const b = event.target.closest('[data-filter]'); if (b) selectFilter(b.dataset.filter); });
  el('warning-summary').addEventListener('click', event => { const b = event.target.closest('[data-filter]'); if (b) selectFilter(b.dataset.filter); });
  el('refresh-warnings').addEventListener('click', () => { if (!mutating) { setFeedback(''); refresh(); } });
  el('load-more-warnings').addEventListener('click', () => { if (!mutating) refresh(true); });

  const onRefine = () => {
    refine.severity = el('f-severity').value; refine.sector = el('f-sector').value; refine.days = el('f-time').value;
    renderRows();
    if (P) P.stagger(el('alerts-container').children, 25, 'pm-fade-swap');
  };
  ['f-severity', 'f-sector', 'f-time'].forEach(id => el(id).addEventListener('change', onRefine));
  const clearRefine = () => { el('f-severity').value = ''; el('f-sector').value = ''; el('f-time').value = ''; onRefine(); };
  el('f-clear').addEventListener('click', clearRefine);

  if (projectId) {
    const s = el('scope');
    s.hidden = false;
    s.innerHTML = `${icon('eye')}<span>Showing warning cases for project <strong class="pm-mono" style="color:var(--pm-text)">${esc(projectId)}</strong> only. Counts above cover the whole portfolio.</span>
      <a class="pm-btn pm-btn-sm ml-auto" href="project-details.html?id=${encodeURIComponent(projectId)}">Open project</a>
      <a class="pm-btn pm-btn-ghost pm-btn-sm" href="early-warnings.html">View all projects</a>`;
  }

  el('alerts-container').addEventListener('click', async event => {
    const control = event.target.closest('[data-status], [data-toggle], [data-clear-refine], [data-ev-more]');
    if (!control) return;
    const data = control.dataset || {};
    if ('clearRefine' in data) { clearRefine(); return; }
    if ('toggle' in data) { toggleCase(control.closest('[data-project-id]')); return; }
    if ('evMore' in data) { toggleEvidence(control); return; }
    const button = control;
    if (!data.status || mutating || refreshFlight) return;
    const card = button.closest('[data-project-id]'), id = card.dataset.projectId;
    if (!id) return;
    mutating = true; controls(true); card.querySelectorAll('button').forEach(b => b.disabled = true);
    try {
      const updated = U.normalize(await API.updateProjectAlertStatus(id, button.dataset.status, card.querySelector('textarea').value));
      if (!updated) throw new Error('Invalid case update response.');
      if (!matches(updated)) await leave(card);
      rows = rows.map(c => c.project_id === id ? updated : c).filter(matches); renderRows();
      setFeedback(`${updated.project_name} moved to ${U.statusLabels[updated.workflow_status] || humanize(updated.workflow_status)}. Officer note saved.`, 'success');
      if (P) P.toast(`Case moved to ${U.statusLabels[updated.workflow_status] || humanize(updated.workflow_status)}.`, 'success', 2600);
      const note = el('warning-feedback').textContent;
      await refresh(false, {quiet:true});
      setFeedback(note, 'success');
    } catch (error) {
      if (card.classList) { card.classList.remove('is-leaving'); if (card.style) card.style.height = ''; }
      setFeedback(`Update failed: ${U.safeText(error?.message)}. Your note is retained; retry.`, 'error');
      card.querySelectorAll('button').forEach(b => b.disabled = false);
    } finally { mutating = false; controls(false); }
  });

  // No background polling: the workspace is a ~1 MB, multi-second query. Refresh is manual.
  if (P) P.hydrateIcons();
  refresh();
})();
