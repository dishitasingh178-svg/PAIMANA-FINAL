(() => {
  'use strict';
  const U = window.WarningUI, el = id => document.getElementById(id);
  const {escape:esc, fmt, humanize} = U;
  const params = new URLSearchParams(location.search), projectId = params.get('project_id');
  const filters = [
    ['new','New',{status:'NEW'}], ['immediate','Immediate',{priority:'IMMEDIATE'}],
    ['predictive','Predictive',{classification:'PREDICTIVE'}], ['deteriorating','Deteriorating',{classification:'DETERIORATION'}],
    ['observed','Observed Issues',{classification:'OBSERVED_ISSUE'}], ['acknowledged','Acknowledged',{status:'ACKNOWLEDGED'}],
    ['review','Under Review',{status:'UNDER_REVIEW'}], ['resolved','Resolved',{status:'RESOLVED'}], ['dismissed','Dismissed',{status:'DISMISSED'}]
  ];
  let active = 'new', rows = [], refreshFlight = null, mutating = false;
  const panel = 'bg-white dark:bg-[#121826] border border-slate-200 dark:border-[#1E293B] rounded-xl p-5';
  const money = value => value == null ? '—' : `₹${fmt(value)} Cr`;
  const delta = value => value == null ? 'Previous period unavailable.' : `${value > 0 ? '+' : ''}${fmt(value)} points`;
  const section = (title, text) => `<section><h3 class="text-xs font-bold uppercase text-slate-500 mb-2">${title}</h3><p class="text-sm whitespace-pre-wrap">${esc(U.safeText(text))}</p></section>`;
  function matches(item) {
    const query = filters.find(f => f[0] === active)[2];
    return (query.status ? item.workflow_status === query.status : !U.closed(item))
      && (!query.classification || item.alert_classifications.includes(query.classification))
      && (!query.priority || item.priority_label === query.priority);
  }
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
  function renderRows() {
    el('alerts-container').innerHTML = rows.length ? rows.map(item => {
      const color = {CRITICAL:'text-red-500',ELEVATED:'text-orange-500',WATCH:'text-amber-500'}[item.severity] || 'text-slate-500';
      return `<article class="${panel}" data-project-id="${esc(item.project_id)}">
        <div class="flex flex-wrap justify-between gap-3 mb-3"><div><p class="text-xs font-bold ${color}">Highest severity: ${esc(item.severity)} · ${esc(item.alert_classifications.map(c => U.classLabels[c]).join(' · '))}</p>
        <a class="text-lg font-bold hover:underline" href="project-details.html?id=${encodeURIComponent(item.project_id)}">${esc(item.project_name)}</a>
        <p class="text-xs text-slate-500">${esc(item.sector)} · Case status: ${esc(humanize(item.workflow_status))} · ${fmt(item.signal_count)} contributing signals</p>
        ${item.has_new_evidence === true ? '<p class="text-orange-500 text-xs font-bold">New evidence / escalation since last review</p>' : ''}</div>
        <div class="text-right"><strong class="text-2xl">${fmt(item.priority_score)}</strong><p class="text-xs">Priority · ${esc(item.priority_label)}</p></div></div>
        <div class="flex flex-wrap gap-x-5 gap-y-1 text-sm mb-4"><span>Model risk: ${fmt(item.risk_score)} / 100 · ${esc(item.risk_tier)}</span><span>${delta(item.risk_delta)}</span><span>Exposure: ${money(item.financial_exposure_crore)}</span></div>
        <div class="grid md:grid-cols-2 gap-4">${section('What changed',item.what_changed)}${section('Why flagged',item.why_flagged)}</div>
        <details class="my-4"><summary class="text-xs font-bold cursor-pointer">CONTRIBUTING SIGNALS (${fmt(item.signal_count)})</summary>
        ${item.underlying_signals.map(s => `<div class="border-b border-slate-200 dark:border-slate-700 py-3 text-sm"><strong>${esc(humanize(s.alert_type))} · ${esc(s.severity)}</strong><p>${esc(s.what_changed)}</p></div>`).join('') || '<p class="text-sm">Signal details unavailable.</p>'}</details>
        <details class="my-4"><summary class="text-xs font-bold cursor-pointer">EVIDENCE · latest available data</summary><p class="text-xs text-slate-500 my-2">Each metric is dated independently of the recorded trigger.</p>
        <div class="grid sm:grid-cols-2 xl:grid-cols-3 gap-2">${item.evidence.map(e => `<div class="bg-slate-100 dark:bg-slate-800/50 rounded-lg p-3 text-xs"><strong>${esc(e.label)}</strong><p>${e.previous != null ? esc(e.previous)+' → ' : ''}${esc(e.current)} ${esc(e.unit)}</p>${e.change != null ? `<p>Change: ${e.change > 0 ? '+' : ''}${fmt(e.change)}</p>` : ''}<p>${esc(e.previous_report_month)} ${e.previous_report_month ? '→' : ''} ${esc(e.current_report_month)}</p></div>`).join('') || '<p class="text-sm">Evidence unavailable.</p>'}</div></details>
        <div class="grid md:grid-cols-2 gap-4">${section('Potential consequence',item.potential_consequence)}${section('Recommended investigation',item.recommended_investigation)}</div>
        <p class="text-xs mt-4">Data confidence: ${esc(item.data_confidence)} · ${esc(item.data_confidence_reasons.join(' '))}</p>
        ${item.review_note ? section('Officer Note',item.review_note) + `<p class="text-xs text-slate-500">Updated: ${esc(U.date(item.status_updated_at))}</p>` : ''}
        <div class="mt-4 border-t border-slate-200 dark:border-slate-700 pt-4"><label class="text-xs block">Optional officer note<textarea maxlength="5000" rows="2" class="w-full mt-1 mb-2 p-2 rounded border border-slate-300 dark:border-slate-700 bg-transparent text-sm">${esc(item.review_note)}</textarea></label>
        <div class="flex flex-wrap gap-2">${(U.closed(item) ? [['NEW','Reopen']] : [['ACKNOWLEDGED','Acknowledge'],['UNDER_REVIEW','Under Review'],['DISMISSED','Dismiss'],['RESOLVED','Resolve']]).map(([status,label]) => `<button data-status="${status}" ${!item.project_id || status === item.workflow_status ? 'disabled' : ''} class="px-3 py-2 rounded-lg border border-slate-300 dark:border-slate-700 text-xs disabled:opacity-40">${label}</button>`).join('')}</div></div></article>`;
    }).join('') : `<div class="${panel}">No warnings in this queue.</div>`;
  }
  function renderSummary(data) {
    el('warning-summary').innerHTML = [['new','New projects'],['immediate','Immediate Priority'],['acknowledged','Acknowledged'],['under_review','Under Review'],['resolved','Resolved'],['dismissed','Dismissed']].map(([key,label]) => `<div class="${panel}"><p class="text-xs text-slate-500">${label}</p><p class="text-2xl font-bold" data-count="${key}">${fmt(data?.[key])}</p></div>`).join('');
  }
  function renderPriority(data) {
    el('priority-projects').innerHTML = normalizeList(data).filter(c => !U.closed(c)).map(c => `<a href="project-details.html?id=${encodeURIComponent(c.project_id)}" class="block rounded-lg border border-slate-200 dark:border-slate-700 p-4 hover:border-orange-500"><div class="flex gap-4"><div><strong class="text-2xl">${fmt(c.priority_score)}</strong><p class="text-xs">${esc(c.priority_label)}</p></div><div><strong>${esc(c.project_name)}</strong><p class="text-xs text-slate-500">${esc(c.sector)} · ${esc(humanize(c.workflow_status))} · ${fmt(c.active_signal_count)} open signals</p><p class="text-sm">Risk ${fmt(c.risk_score)} / 100 · ${delta(c.risk_delta)} · ${money(c.financial_exposure_crore)}</p><p class="text-xs">${esc(c.attention_reason)}</p></div></div></a>`).join('') || 'No projects currently require immediate attention.';
  }
  function controls(disabled) {
    el('refresh-warnings').disabled = disabled;
    el('refresh-warnings').textContent = disabled ? 'Refreshing…' : 'Refresh';
    el('load-more-warnings').disabled = disabled;
    el('alert-filters').querySelectorAll('button').forEach(b => b.disabled = disabled);
  }
  function refresh(append = false) {
    if (refreshFlight) return refreshFlight;
    controls(true);
    const query = {...filters.find(f => f[0] === active)[2], limit:50, offset:append ? rows.length : 0, ...(projectId ? {project_id:projectId} : {})};
    el('alerts-container').setAttribute('aria-busy','true');
    refreshFlight = (async () => {
      const results = await Promise.allSettled([API.getAlertCases(query), API.getAlertSummary(), API.getPriorityAlerts(5)]);
      const failures = [];
      const [list, summary, priority] = results;
      try {
        if (list.status === 'rejected') throw list.reason;
        const data = normalizeList(list.value).filter(matches);
        rows = append ? normalizeList(rows.concat(data)) : data;
        renderRows();
        el('load-more-warnings').hidden = data.length < 50;
      } catch (error) { rows=[]; el('alerts-container').textContent='Unable to load cases. Click Refresh to retry.'; el('load-more-warnings').hidden=true; failures.push(U.safeText(error?.message)); }
      if (summary.status === 'fulfilled') renderSummary(summary.value);
      else { el('warning-summary').textContent='Counts unavailable.'; failures.push('Counts could not be refreshed.'); }
      try { if (priority.status === 'rejected') throw priority.reason; renderPriority(priority.value); }
      catch (_) { el('priority-projects').textContent='Priority projects unavailable.'; failures.push('Priority projects could not be refreshed.'); }
      if (failures.length) el('warning-feedback').textContent=failures.join(' ')+' Click Refresh to retry.';
    })().finally(() => { refreshFlight=null; controls(false); el('alerts-container').setAttribute('aria-busy','false'); });
    return refreshFlight;
  }
  function highlight() {
    el('alert-filters').querySelectorAll('button').forEach(b => {const selected=b.dataset.filter===active; b.setAttribute('aria-pressed',String(selected)); b.classList.toggle('bg-orange-500',selected); b.classList.toggle('text-white',selected);});
    el('warning-filter-help').textContent = filters.find(f => f[0]===active)[2].status
      ? 'One case per project. Actions move the entire case and its open signals into the selected workflow state.'
      : 'Filters across open project cases. Each case retains its single workflow status.';
  }
  el('alert-filters').innerHTML=filters.map(([key,label])=>`<button class="px-3 py-2 border rounded-lg" data-filter="${key}">${label}</button>`).join('');
  highlight();
  el('alert-filters').addEventListener('click',event=>{const b=event.target.closest('[data-filter]'); if(!b||refreshFlight||mutating)return; active=b.dataset.filter; highlight(); el('warning-feedback').textContent=''; refresh();});
  el('refresh-warnings').addEventListener('click',()=>{if(!mutating){el('warning-feedback').textContent='';refresh();}});
  el('load-more-warnings').addEventListener('click',()=>{if(!mutating)refresh(true);});
  el('alerts-container').addEventListener('click',async event=>{
    const button=event.target.closest('[data-status]');
    if(!button||mutating||refreshFlight)return;
    const card=button.closest('[data-project-id]'), id=card.dataset.projectId;
    if(!id)return;
    mutating=true; controls(true); card.querySelectorAll('button').forEach(b=>b.disabled=true);
    try {
      const updated=U.normalize(await API.updateProjectAlertStatus(id,button.dataset.status,card.querySelector('textarea').value));
      if(!updated)throw new Error('Invalid case update response.');
      rows=rows.map(c=>c.project_id===id?updated:c).filter(matches); renderRows();
      el('warning-feedback').textContent=`${updated.project_name} moved to ${humanize(updated.workflow_status)}. Officer note saved.`;
      await refresh();
    } catch(error) {el('warning-feedback').textContent=`Update failed: ${U.safeText(error?.message)}. Your note is retained; retry.`;card.querySelectorAll('button').forEach(b=>b.disabled=false);}
    finally {mutating=false;controls(false);}
  });
  refresh();
})();
