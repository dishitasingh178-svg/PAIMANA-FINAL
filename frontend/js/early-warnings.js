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

  const icon = (name, cls = 'w-4 h-4') => P ? P.icon(name, cls) : '';
  const badge = (sev, score, showScore = false) => P ? P.tierBadge(sev, score, {showScore}) : esc(sev);
  const tierOf = (sev, score) => P ? P.tier(sev, score) : 'UNKNOWN';
  const title = s => U.safeText(s, '').toLowerCase().replace(/\b\w/g, c => c.toUpperCase()).replace(/\b(And|Of)\b/g, m => m.toLowerCase());
  const money = value => value == null ? '—' : `₹${fmt(value)} Cr`;
  const delta = value => value == null ? 'Previous period unavailable.' : `${value > 0 ? '+' : ''}${fmt(value)} points`;
  const month = ym => P && ym ? P.fmt.month(ym) : U.safeText(ym, '—');
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
  // Case cards
  // ------------------------------------------------------------------
  function detailHTML(item) {
    const closed = U.closed(item);
    const riskMonth = item.prediction_report_month || item.report_month;
    return `
      <div class="facts">
        <div><p class="pm-kpi-label">Model risk</p><div class="v">${badge(item.risk_tier, item.risk_score, true)}</div><p class="s">Composite, report ${esc(month(riskMonth))}</p></div>
        <div><p class="pm-kpi-label">Change vs previous</p><p class="v">${esc(delta(item.risk_delta))}</p><p class="s">${item.previous_risk_score != null ? `from ${esc(fmt(item.previous_risk_score))}${item.previous_prediction_report_month ? ` · ${esc(month(item.previous_prediction_report_month))}` : ''}` : 'No earlier prediction'}</p></div>
        <div><p class="pm-kpi-label">Financial exposure</p><p class="v">${esc(money(item.financial_exposure_crore))}</p><p class="s">Latest anticipated cost</p></div>
        <div><p class="pm-kpi-label">Data confidence</p><p class="v">${esc(humanize(item.data_confidence))}</p><p class="s">${esc(item.data_confidence_reasons.join(' ') || '—')}</p></div>
      </div>
      <div class="d-grid">${section('What changed', item.what_changed)}${section('Why flagged', item.why_flagged)}
        ${section('Potential consequence', item.potential_consequence)}${section('Recommended investigation', item.recommended_investigation)}</div>
      <div class="d-grid mt-5">
        <section>
          <h4 class="d-h">Contributing signals (${esc(fmt(item.signal_count))})</h4>
          <div>${item.underlying_signals.map(s => {
            const sm = U.splitMonth(s.what_changed);
            return `<div class="sig"><div class="pt-0.5">${badge(s.severity)}</div><div><p style="color:var(--pm-text);font-weight:600">${esc(U.typeLabel(s.alert_type))}${sm.month ? ` <span class="pm-updated">· report ${esc(month(sm.month))}</span>` : ''}</p><p class="mt-0.5" style="color:var(--pm-text-2)">${esc(sm.text || s.what_changed)}</p></div></div>`;
          }).join('') || '<p class="d-p">Signal details unavailable.</p>'}</div>
        </section>
        <section>
          <details class="more"><summary>${icon('chevron-right')}Evidence · latest available data (${item.evidence.length})</summary>
            <p class="pm-updated mt-2">Each metric is dated independently of the recorded trigger.</p>
            <div class="ev">${item.evidence.map(e => `<div><p style="color:var(--pm-text);font-weight:600">${esc(e.label)}</p><p class="pm-num mt-1" style="color:var(--pm-text-2)">${e.previous != null ? esc(e.previous) + ' → ' : ''}${esc(e.current)} ${esc(e.unit)}</p>${e.change != null ? `<p class="pm-num" style="color:var(--pm-muted)">Change: ${e.change > 0 ? '+' : ''}${fmt(e.change)}</p>` : ''}<p class="pm-updated mt-1">${esc(e.previous_report_month)} ${e.previous_report_month ? '→' : ''} ${esc(e.current_report_month)}</p></div>`).join('') || '<p class="d-p">Evidence unavailable.</p>'}</div>
          </details>
        </section>
      </div>
      <div class="mt-5 pt-4" style="border-top:1px solid var(--pm-line)">
        <label class="block text-[12px] font-semibold" style="color:var(--pm-muted)">Optional officer note
          <textarea maxlength="5000" rows="2" class="note mt-1.5 mb-3">${esc(item.review_note)}</textarea></label>
        <div class="flex flex-wrap items-center gap-2">
          ${(closed ? [['NEW','Reopen']] : [['ACKNOWLEDGED','Acknowledge'],['UNDER_REVIEW','Under Review'],['DISMISSED','Dismiss'],['RESOLVED','Resolve']]).map(([status, label]) =>
            `<button type="button" data-status="${status}" ${!item.project_id || status === item.workflow_status ? 'disabled' : ''} class="pm-btn pm-btn-sm ${status === 'RESOLVED' ? 'pm-btn-primary' : ''}">${label}</button>`).join('')}
          <span class="pm-updated">Moves the whole case and its open signals.</span>
          <a class="pm-btn pm-btn-ghost pm-btn-sm ml-auto" href="project-details.html?id=${encodeURIComponent(item.project_id)}">Open project ${icon('arrow-right', 'w-3.5 h-3.5')}</a>
        </div>
      </div>`;
  }

  function caseHTML(item) {
    const closed = U.closed(item);
    const open = expanded.has(item.project_id);
    const issue = U.splitMonth(item.what_changed);
    const t = when(item.triggered_at);
    const others = item.alert_classifications.filter(c => c !== item.dominant_classification).map(c => U.classLabels[c]);
    const did = `case-${esc(item.project_id || Math.random().toString(36).slice(2))}`;
    return `<article class="case ${open ? 'is-open' : ''}" data-project-id="${esc(item.project_id)}" data-tier="${tierOf(item.severity)}" data-closed="${closed}">
      <div class="case-main">
        <div class="min-w-0">
          <div class="flex flex-wrap items-center gap-2 mb-2">${badge(item.severity)}${wfPill(item.workflow_status)}
            ${item.has_new_evidence === true ? `<span class="pm-tier" data-tier="ELEVATED">${icon('sparkles')}New evidence since review</span>` : ''}</div>
          <a class="case-name" href="project-details.html?id=${encodeURIComponent(item.project_id)}">${esc(item.project_name)}</a>
          <p class="case-meta">${esc([title(item.sector), title(item.state), item.project_id].filter(v => v && v !== 'Unavailable').join(' · '))}</p>
          <p class="case-issue">${esc(issue.text || item.what_changed)}</p>
          <p class="case-why"><span>Trigger <b>${esc(U.classLabels[item.dominant_classification])}</b> · ${esc(U.typeLabel(item.dominant_alert_type || item.alert_type))}</span>
            <span>${esc(fmt(item.signal_count))} contributing signal${item.signal_count === 1 ? '' : 's'}</span>
            ${issue.month || item.report_month ? `<span>Report ${esc(month(issue.month || item.report_month))}</span>` : ''}
            ${others.length ? `<span>Other signals: ${esc(others.join(', '))}</span>` : ''}</p>
          ${item.review_note ? `<p class="case-why"><span><b>Officer Note:</b> ${esc(item.review_note)}</span><span>Updated ${esc(U.date(item.status_updated_at))}</span></p>` : ''}
        </div>
        <div class="case-side">
          <div><p class="score" title="Warning priority score (0–100)">${esc(fmt(item.priority_score))}</p><p class="score-lbl" data-p="${esc(item.priority_label)}">Priority · ${esc(humanize(item.priority_label).toLowerCase())}</p></div>
          <p class="case-time"><time datetime="${esc(item.triggered_at)}" title="Raised ${esc(t.abs)}">Raised ${esc(t.rel)}</time></p>
          <button type="button" class="pm-btn pm-btn-sm toggle" data-toggle aria-expanded="${open}" aria-controls="${did}">${icon('chevron-right', 'w-3.5 h-3.5')}${open ? 'Hide case' : 'Review case'}</button>
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
    btn.lastChild.textContent = open ? 'Hide case' : 'Review case';
    if (open && P && !P.reducedMotion()) { detail.classList.remove('pm-fade-swap'); void detail.offsetWidth; detail.classList.add('pm-fade-swap'); }
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
  const SUMMARY = [['new','New','new','Awaiting triage'],['immediate','Immediate priority','immediate','Priority label Immediate'],
    ['acknowledged','Acknowledged','acknowledged','Seen by an officer'],['under_review','Under review','review','Being investigated'],
    ['resolved','Resolved','resolved','Closed · addressed'],['dismissed','Dismissed','dismissed','Closed · not actionable']];
  function renderSummary(data) {
    lastSummary = data;
    el('warning-summary').innerHTML = SUMMARY.map(([key, label, filter, foot]) => `<button type="button" class="sum-cell" data-filter="${filter}" aria-pressed="${filter === active}" aria-label="${esc(label)}: ${esc(fmt(data?.[key]))}. Show this queue.">
      <p class="pm-kpi-label">${label}</p><p class="pm-kpi-value mt-1.5" data-count="${key}">${fmt(data?.[key])}</p><p class="pm-updated mt-1" style="white-space:normal">${foot}</p></button>`).join('');
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
      const reason = {month: rm ? rm[1] : null, text: raw.replace(/^\s*\d+ contributing signals?\.\s*/i, '').replace(/\[\d{4}-\d{2}\]\s*/g, '')};
      return `<a href="project-details.html?id=${encodeURIComponent(c.project_id)}" class="prio" aria-label="${esc(c.project_name)}, priority ${esc(fmt(c.priority_score))}. Open project.">
        <div><p class="score">${fmt(c.priority_score)}</p><p class="score-lbl" data-p="${esc(c.priority_label)}">${esc(humanize(c.priority_label).toLowerCase())}</p></div>
        <div class="min-w-0">
          <p class="text-[13.5px] font-semibold sm:truncate" style="color:var(--pm-text)"><span class="pm-updated mr-1.5">#${i + 1}</span>${esc(c.project_name)}</p>
          <p class="pm-updated mt-0.5" style="white-space:normal">${esc(title(c.sector))} · ${esc(U.statusLabels[c.workflow_status] || humanize(c.workflow_status))} · ${fmt(c.active_signal_count)} open signals · risk ${fmt(c.risk_score)}/100 · ${delta(c.risk_delta)} · ${money(c.financial_exposure_crore)}</p>
          <p class="prio-reason">${esc(reason.text || c.attention_reason)}${reason.month ? ` <span class="pm-updated">· report ${esc(month(reason.month))}</span>` : ''}</p>
        </div>
        <span class="go">${icon('arrow-right')}</span></a>`;
    }).join('') || (P ? P.stateHTML({kind:'empty', title:'No projects currently require immediate attention', inline:true}) : 'No projects currently require immediate attention.');
    if (P) P.stagger(el('priority-projects').children, 50, 'pm-fade-swap');
  }

  // ------------------------------------------------------------------
  // Loading states
  // ------------------------------------------------------------------
  const skelCases = () => Array.from({length:4}, () => `<div class="case case-skel" aria-hidden="true" style="padding:18px 20px"><div class="flex gap-2 mb-3"><div class="pm-skel" style="width:78px;height:22px"></div><div class="pm-skel" style="width:60px;height:22px;border-radius:99px"></div></div><div class="pm-skel pm-skel-line" style="width:48%;height:13px"></div><div class="pm-skel pm-skel-line" style="width:30%"></div><div class="pm-skel pm-skel-line" style="width:86%;margin-top:14px"></div><div class="pm-skel pm-skel-line" style="width:40%"></div></div>`).join('');
  function showSkeletons() {
    if (!P) { el('alerts-container').textContent = 'Loading warnings...'; return; }
    el('alerts-container').innerHTML = skelCases();
    if (!loadedOnce) {
      el('warning-summary').innerHTML = SUMMARY.map(() => `<div class="sum-cell"><div class="pm-skel pm-skel-line" style="width:60%"></div><div class="pm-skel" style="height:24px;width:45%;margin-top:10px"></div><div class="pm-skel pm-skel-line" style="width:70%"></div></div>`).join('');
      el('priority-projects').innerHTML = P.skeleton.rows(5);
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
      el('warning-summary').innerHTML = `<div class="col-span-full">${P.stateHTML({kind:'error', title:'Counts unavailable', message, inline:true})}</div>`;
      el('priority-projects').innerHTML = P.stateHTML({kind:'error', title:'Priority projects unavailable', message, inline:true});
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
  function refresh(append = false) {
    if (refreshFlight) return refreshFlight;
    controls(true);
    setFeedback('');
    const query = {...filters.find(f => f[0] === active)[2], limit:50, offset:append ? rows.length : 0, ...(projectId ? {project_id:projectId} : {})};
    el('alerts-container').setAttribute('aria-busy','true');
    if (!append) showSkeletons();
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
        if (!append && P) P.stagger(el('alerts-container').children, 35, 'pm-pop-in');
        if (projectId && !append) { const open = el('alerts-container').querySelector('.case.is-open'); if (open) open.scrollIntoView({block:'nearest'}); }
      } catch (error) {
        if (!append) rows = [];
        el('load-more-warnings').hidden = true;
        const message = `${U.safeText(error?.message)} Retry, or use Refresh.`;
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
    const control = event.target.closest('[data-status], [data-toggle], [data-clear-refine]');
    if (!control) return;
    const data = control.dataset || {};
    if ('clearRefine' in data) { clearRefine(); return; }
    if ('toggle' in data) { toggleCase(control.closest('[data-project-id]')); return; }
    const button = control;
    if (!data.status || mutating || refreshFlight) return;
    const card = button.closest('[data-project-id]'), id = card.dataset.projectId;
    if (!id) return;
    mutating = true; controls(true); card.querySelectorAll('button').forEach(b => b.disabled = true);
    try {
      const updated = U.normalize(await API.updateProjectAlertStatus(id, button.dataset.status, card.querySelector('textarea').value));
      if (!updated) throw new Error('Invalid case update response.');
      rows = rows.map(c => c.project_id === id ? updated : c).filter(matches); renderRows();
      setFeedback(`${updated.project_name} moved to ${U.statusLabels[updated.workflow_status] || humanize(updated.workflow_status)}. Officer note saved.`, 'success');
      if (P) P.toast(`Case moved to ${U.statusLabels[updated.workflow_status] || humanize(updated.workflow_status)}.`, 'success', 2600);
      const note = el('warning-feedback').textContent;
      await refresh();
      setFeedback(note, 'success');
    } catch (error) {
      setFeedback(`Update failed: ${U.safeText(error?.message)}. Your note is retained; retry.`, 'error');
      card.querySelectorAll('button').forEach(b => b.disabled = false);
    } finally { mutating = false; controls(false); }
  });

  // No background polling: the workspace is a ~1 MB, multi-second query. Refresh is manual.
  if (P) P.hydrateIcons();
  refresh();
})();
