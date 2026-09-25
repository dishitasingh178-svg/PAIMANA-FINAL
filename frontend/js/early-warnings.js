(() => {
  'use strict';
  const el = id => document.getElementById(id);
  const escape = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const fmt = value => value == null ? 'Unavailable' : Number(value).toLocaleString('en-IN', {maximumFractionDigits: 1});
  const money = value => value == null ? 'Financial exposure unavailable' : `₹${fmt(value)} Cr`;
  const delta = value => value == null ? 'Previous reporting period unavailable' : `${value > 0 ? '+' : ''}${fmt(value)} points`;
  const closed = a => ['RESOLVED', 'DISMISSED'].includes(a.status);
  function matchesFilter(alert) {
    const query = filters.find(f => f[0] === active)[2];
    return (query.status ? alert.status === query.status : !closed(alert))
      && (!query.alert_class || alert.alert_class === query.alert_class)
      && (query.min_priority == null || alert.priority_score >= query.min_priority);
  }
  const projectId = new URLSearchParams(location.search).get('project_id');
  const filters = [['active','All Active',{}], ['new','New',{status:'NEW'}], ['immediate','Immediate',{min_priority:80}],
    ['predictive','Predictive',{alert_class:'PREDICTIVE'}], ['deteriorating','Deteriorating',{alert_class:'DETERIORATION'}],
    ['observed','Observed Issues',{alert_class:'OBSERVED_ISSUE'}], ['acknowledged','Acknowledged',{status:'ACKNOWLEDGED'}],
    ['review','Under Review',{status:'UNDER_REVIEW'}], ['resolved','Resolved',{status:'RESOLVED'}], ['dismissed','Dismissed',{status:'DISMISSED'}]];
  let active = 'active', rows = [], request = 0, busy = false;
  const panel = 'bg-white dark:bg-[#121826] border border-slate-200 dark:border-[#1E293B] rounded-xl p-5';
  function section(title, content) { return `<section><h3 class="text-xs font-bold uppercase text-slate-500 mb-2">${title}</h3><p class="text-sm whitespace-pre-wrap">${escape(content)}</p></section>`; }
  function renderRows() {
    el('alerts-container').innerHTML = rows.length ? rows.map(a => {
      const color = {CRITICAL:'text-red-500', ELEVATED:'text-orange-500', WATCH:'text-amber-500'}[a.severity] || 'text-slate-500';
      return `<article class="${panel}" data-alert-id="${escape(a.alert_id)}">
        <div class="flex flex-wrap justify-between gap-3 mb-3"><div><p class="text-xs font-bold ${color}">Severity: ${escape(a.severity)} · ${escape(a.alert_class_label)}</p>
        <a class="text-lg font-bold hover:underline" href="project-details.html?id=${encodeURIComponent(a.project_id)}">${escape(a.project_name)}</a>
        <p class="text-xs text-slate-500">${escape(a.sector)} · ${escape(a.status)}</p>
        <p class="text-xs text-slate-500">Alert #${escape(a.alert_id)} · ${escape(a.alert_type.replaceAll('_', ' '))}</p></div>
        <div class="text-right"><strong class="text-2xl">${fmt(a.priority_score)}</strong><p class="text-xs">Priority · ${escape(a.priority_label)}</p></div></div>
        <div class="flex flex-wrap gap-x-5 gap-y-1 text-sm mb-4"><span>Model risk: ${fmt(a.risk_score)} / 100 · ${escape(a.risk_tier)}</span><span>${delta(a.risk_delta)}</span><span>${money(a.financial_exposure_crore)}</span></div>
        <p class="text-xs text-slate-500 mb-4">Triggered: ${escape(a.triggered_at ? new Date(a.triggered_at).toLocaleDateString() : 'Unavailable')} · Alert report: ${escape(a.alert_report_month || 'Unavailable')} · Latest update: ${escape(a.report_month || 'Unavailable')} · Model report: ${escape(a.prediction_report_month || 'Unavailable')}</p>
        <div class="grid md:grid-cols-2 gap-4">${section('What changed', a.what_changed)}${section('Why it was flagged', a.why_flagged)}</div>
        <details class="my-4" open><summary class="text-xs font-bold cursor-pointer">EVIDENCE · latest available data</summary>
        <p class="text-xs text-slate-500 my-2">The recorded trigger above may be from an earlier report. Evidence below is dated independently.</p>
        <div class="grid sm:grid-cols-2 xl:grid-cols-3 gap-2">${a.evidence.map(e => `<div class="bg-slate-100 dark:bg-slate-800/50 rounded-lg p-3 text-xs"><p class="font-semibold">${escape(e.label)}</p><p class="mt-1">${e.previous != null ? escape(e.previous) + ' → ' : ''}${escape(e.current)} ${escape(e.unit || '')}</p>${e.change != null ? `<p>Change: ${e.change > 0 ? '+' : ''}${fmt(e.change)} ${escape(e.unit || '')}</p>` : ''}<p class="text-slate-500">${escape(e.previous_report_month ? e.previous_report_month + ' → ' : '')}${escape(e.current_report_month || '')}</p></div>`).join('')}</div></details>
        <div class="grid md:grid-cols-2 gap-4">${section('Potential consequence', a.potential_consequence)}${section('Recommended investigation', a.recommended_investigation)}</div>
        <p class="text-xs mt-4"><strong>Data confidence: ${escape(a.data_confidence)}</strong> · ${escape(a.data_confidence_reasons.join(' '))}</p>
        ${a.review_note ? section('Review note', a.review_note) : ''}
        <div class="mt-4 border-t border-slate-200 dark:border-slate-700 pt-4"><label class="text-xs block" for="note-${escape(a.alert_id)}">${closed(a) ? 'Review note' : 'Optional review note'}</label>
        <textarea id="note-${escape(a.alert_id)}" maxlength="5000" rows="2" class="w-full mt-1 mb-2 p-2 rounded border border-slate-300 dark:border-slate-700 bg-transparent text-sm">${escape(a.review_note || '')}</textarea>
        <div class="flex flex-wrap gap-2">${(closed(a) ? [['NEW','Reopen']] : [['ACKNOWLEDGED','Acknowledge'],['UNDER_REVIEW','Under Review'],['DISMISSED','Dismiss'],['RESOLVED','Resolve']]).map(([s,label]) => `<button data-status="${s}" ${s === a.status ? 'disabled' : ''} class="px-3 py-2 rounded-lg border border-slate-300 dark:border-slate-700 text-xs disabled:opacity-40">${label}</button>`).join('')}</div></div>
      </article>`;
    }).join('') : `<div class="${panel}">${active === 'active' ? 'No active warnings require attention.' : 'No warnings match this filter.'}</div>`;
  }
  async function loadRows(append = false) {
    const token = ++request;
    const query = {...filters.find(f => f[0] === active)[2], limit:50, offset:append ? rows.length : 0, ...(projectId ? {project_id:projectId} : {})};
    el('load-more-warnings').hidden = true;
    if (!append) el('alerts-container').textContent = 'Loading warnings...';
    try {
      const data = await API.getAlerts(query);
      if (token !== request) return;
      rows = (append ? rows.concat(data) : data).filter(matchesFilter);
      renderRows();
      el('load-more-warnings').hidden = data.length < 50;
    } catch (error) {
      if (token !== request) return;
      el('warning-feedback').textContent = `Unable to load warnings: ${error.message}. Use Refresh to retry.`;
      if (!append) el('alerts-container').textContent = 'Warnings are unavailable.';
    }
  }
  async function loadOverview() {
    const [summary, projects] = await Promise.allSettled([API.getAlertSummary(), API.getPriorityAlerts(5)]);
    el('warning-summary').innerHTML = summary.status === 'fulfilled' ? [['new','New alerts'],['immediate','Immediate priority projects'],['under_review','Under Review'],['resolved','Resolved']].map(([key,label]) => `<div class="${panel}"><p class="text-xs text-slate-500">${label}</p><p class="text-2xl font-bold">${fmt(summary.value[key])}</p></div>`).join('') : 'Summary unavailable. Use Refresh to retry.';
    el('priority-projects').innerHTML = projects.status === 'fulfilled' ? projects.value.map(p => `<a href="project-details.html?id=${encodeURIComponent(p.project_id)}" class="block rounded-lg border border-slate-200 dark:border-slate-700 p-4 hover:border-orange-500"><div class="flex gap-4"><div class="min-w-20"><strong class="text-2xl">${fmt(p.priority_score)}</strong><p class="text-xs font-semibold">${escape(p.priority_label)}</p></div><div class="min-w-0"><h3 class="font-semibold">${escape(p.project_name)}</h3><p class="text-xs text-slate-500">${escape(p.sector)} · ${escape(p.status)} · ${p.active_alert_count} active warnings</p><p class="text-sm my-1">Risk ${fmt(p.risk_score)} / 100 · ${delta(p.risk_delta)} · ${money(p.financial_exposure_crore)}</p><p class="text-xs">${escape(p.attention_reason)}</p></div></div></a>`).join('') || 'No active warnings require attention.' : 'Priority projects unavailable. Use Refresh to retry.';
  }
  async function refresh() { el('warning-feedback').textContent = ''; await Promise.all([loadRows(), loadOverview()]); }
  el('alert-filters').innerHTML = filters.map(([key,label]) => `<button class="px-3 py-2 border rounded-lg" data-filter="${key}" aria-pressed="${key === active}">${label}</button>`).join('');
  function highlight() {
    el('alert-filters').querySelectorAll('button').forEach(b => { b.setAttribute('aria-pressed', String(b.dataset.filter === active)); b.classList.toggle('bg-orange-500', b.dataset.filter === active); b.classList.toggle('text-white', b.dataset.filter === active); });
    const help = {
      active: 'All Active includes New, Acknowledged and Under Review. Acknowledging starts review; Resolve or Dismiss closes an alert. Use New for warnings awaiting their first action.',
      new: 'Warnings awaiting their first action. Acknowledge, Under Review, Resolve or Dismiss removes an alert from this view.',
      acknowledged: 'Acknowledged warnings remain open until resolved or dismissed.',
      review: 'Warnings currently under review remain open until resolved or dismissed.',
      resolved: 'Resolved warnings are excluded from All Active and project priority rankings.',
      dismissed: 'Dismissed warnings are excluded from All Active and project priority rankings.'
    };
    el('warning-filter-help').textContent = help[active] || 'Matching open warnings, including Acknowledged and Under Review. Resolved and Dismissed warnings are excluded.';
  }
  highlight();
  if (projectId) {
    const notice = document.createElement('p');
    notice.className = 'text-sm';
    notice.innerHTML = `Warnings filtered to project ${escape(projectId)}. <a class="text-orange-500 underline" href="early-warnings.html">Show all projects</a>`;
    el('alert-filters').before(notice);
  }
  el('alert-filters').addEventListener('click', e => { const b = e.target.closest('[data-filter]'); if (!b || busy) return; active = b.dataset.filter; highlight(); loadRows(); });
  el('refresh-warnings').addEventListener('click', () => { if (!busy) refresh(); });
  el('load-more-warnings').addEventListener('click', () => { if (!busy) loadRows(true); });
  el('alerts-container').addEventListener('click', async e => {
    const button = e.target.closest('[data-status]');
    if (!button || busy) return;
    const card = button.closest('[data-alert-id]'), id = card.dataset.alertId;
    busy = true;
    ++request; // A pre-action list response must not overwrite the updated status.
    card.querySelectorAll('button').forEach(b => b.disabled = true);
    try {
      const updated = await API.updateAlertStatus(id, button.dataset.status, el(`note-${id}`).value);
      rows = rows.map(a => String(a.alert_id) === id ? updated : a).filter(matchesFilter);
      renderRows();
      el('warning-feedback').textContent = `Alert #${id} updated to ${updated.status}. ${closed(updated)
        ? 'It is no longer active. Its project may remain listed if other open warnings exist.'
        : updated.status === 'NEW' ? 'It is awaiting action.'
        : 'It has left New and remains open in All Active until resolved or dismissed.'}`;
      await Promise.all([loadRows(), loadOverview()]);
    } catch (error) { el('warning-feedback').textContent = `Update failed: ${error.message}. Your note is retained; retry the action.`; card.querySelectorAll('button').forEach(b => b.disabled = false); }
    finally { busy = false; }
  });
  refresh();
})();
