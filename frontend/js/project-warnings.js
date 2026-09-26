/* Early-warning case for one project (project-details.html).
   Data: GET /alerts/cases?project_id=<id>&include_closed=true (API.getAlertCases)
   Link: early-warnings.html?project_id=<id>
   Needs js/api.js, js/ui.js (PM) and js/warning-ui.js (WarningUI). */
document.addEventListener('DOMContentLoaded', () => {
  'use strict';
  const container = document.getElementById('project-warnings');
  const link = document.getElementById('project-warning-link');
  const countEl = document.getElementById('project-warnings-count');
  const U = window.WarningUI;
  if (!container || !U || !window.PM) return;
  const { esc, icon, tierBadge, stateHTML, skeleton, fmt } = PM;

  const id = (new URLSearchParams(location.search).get('id') || '').trim();
  if (!id) {
    container.innerHTML = stateHTML({ kind: 'empty', title: 'No project selected', message: 'Open a project from the portfolio to see its warning case.' });
    return;
  }
  if (link) link.href = `early-warnings.html?project_id=${encodeURIComponent(id)}`;

  const STATUS = {
    NEW: 'New', ACKNOWLEDGED: 'Acknowledged', UNDER_REVIEW: 'Under review', RESOLVED: 'Resolved', DISMISSED: 'Dismissed'
  };
  const stripMonth = (s) => String(s || '').replace(/^\[\d{4}-\d{2}\]\s*/, '');
  const known = (s) => s && s !== 'Unavailable';

  function signalHTML(s) {
    return `<li class="pw-signal">
      ${tierBadge(s.severity, null, { showScore: false })}
      <div class="min-w-0">
        <p class="pw-signal-type">${esc(U.humanize(s.alert_type).toLowerCase().replace(/^\w/, c => c.toUpperCase()))}</p>
        <p class="pw-signal-text">${esc(stripMonth(s.what_changed))}</p>
      </div>
    </li>`;
  }

  function caseHTML(c) {
    const closed = U.closed(c);
    const signals = c.underlying_signals || [];
    const month = c.alert_report_month || c.report_month;
    const rows = [
      known(c.why_flagged) ? ['Why flagged', c.why_flagged] : null,
      known(c.potential_consequence) ? ['Potential consequence', c.potential_consequence] : null,
      known(c.recommended_investigation) ? ['Recommended investigation', c.recommended_investigation] : null
    ].filter(Boolean);
    return `<article class="pw-case ${closed ? 'is-closed' : ''}">
      <div class="pw-case-head">
        <div class="flex flex-wrap items-center gap-2">
          ${tierBadge(c.severity, null, { showScore: false })}
          <span class="pw-status" data-status="${esc(c.workflow_status)}">${esc(STATUS[c.workflow_status] || U.humanize(c.workflow_status))}</span>
          ${known(c.alert_class_label) ? `<span class="pw-kind">${esc(c.alert_class_label)}</span>` : ''}
        </div>
        <div class="pw-priority" title="Warning priority score (0–100)">
          <span class="pw-priority-val">${esc(U.fmt(c.priority_score))}</span>
          <span class="pw-priority-lbl">${esc(known(c.priority_label) ? U.humanize(c.priority_label).toLowerCase() : 'priority')}</span>
        </div>
      </div>
      <p class="pw-what">${esc(stripMonth(c.what_changed))}</p>
      <p class="pw-meta">${[
        month ? `Signal from report ${esc(fmt.month(month))}` : '',
        c.triggered_at ? `raised ${esc(fmt.relative(c.triggered_at))}` : '',
        c.signal_count != null ? `${esc(U.fmt(c.signal_count))} contributing signal${c.signal_count === 1 ? '' : 's'}` : ''
      ].filter(Boolean).join(' · ')}</p>
      ${rows.length ? `<dl class="pw-dl">${rows.map(([k, v]) => `<div><dt>${esc(k)}</dt><dd>${esc(v)}</dd></div>`).join('')}</dl>` : ''}
      ${signals.length ? `<details class="pw-details" ${signals.length <= 2 ? 'open' : ''}>
          <summary>${icon('chevron-right', 'pw-chev')}Contributing signals <span class="pw-count">${signals.length}</span></summary>
          <ul class="pw-signals">${signals.map(signalHTML).join('')}</ul>
        </details>` : ''}
      ${known(c.data_confidence) ? `<p class="pw-confidence" data-level="${esc(String(c.data_confidence).toUpperCase())}">
          ${icon(String(c.data_confidence).toUpperCase() === 'HIGH' ? 'circle-check' : 'triangle-alert', 'w-3.5 h-3.5')}
          <span><strong>Data confidence: ${esc(U.humanize(c.data_confidence).toLowerCase())}.</strong> ${esc((c.data_confidence_reasons || []).join(' '))}</span></p>` : ''}
      ${c.review_note ? `<div class="pw-note"><p class="pw-note-k">Officer note</p><p>${esc(c.review_note)}</p>
          ${c.status_updated_at ? `<p class="pw-note-t">Updated ${esc(U.date(c.status_updated_at))}</p>` : ''}</div>` : ''}
    </article>`;
  }

  function load() {
    return PM.section(container, {
      loader: () => API.getAlertCases({ project_id: id, include_closed: true }),
      skeleton: `<div class="pw-case">${skeleton.lines(1)}${skeleton.lines(3)}</div>`,
      isEmpty: (data) => !U.safeArray(data).map(U.normalize).filter(Boolean).length,
      empty: { title: 'No warning case for this project', message: 'The early-warning engine has not raised any signals for this project, open or closed.' },
      errorTitle: 'Warning case unavailable',
      render: (data, el) => {
        const cases = U.safeArray(data).map(U.normalize).filter(Boolean)
          .sort((a, b) => Number(U.closed(a)) - Number(U.closed(b)) || (b.priority_score ?? 0) - (a.priority_score ?? 0));
        el.innerHTML = cases.map(caseHTML).join('');
        if (countEl) {
          const open = cases.filter(c => !U.closed(c)).length;
          countEl.textContent = `${open} open${cases.length > open ? ` · ${cases.length - open} closed` : ''}`;
          countEl.hidden = false;
        }
        PM.stagger(el.children, 60, 'pm-fade-swap');
      }
    }).then((data) => {
      if (countEl && data !== undefined && !U.safeArray(data).length) { countEl.textContent = 'None'; countEl.hidden = false; }
    });
  }

  // project-details.html calls this once the project itself has loaded, so an
  // unknown id never queries the (slow, ~3–8 s) case endpoint. Stand-alone
  // use (no page hook) starts immediately.
  let started = false;
  const start = () => { if (!started) { started = true; load(); } };
  container.innerHTML = `<div class="pw-case">${skeleton.lines(1)}${skeleton.lines(3)}</div>`;
  if (window.ProjectWarningsDeferred) window.ProjectWarnings = { start };
  else start();
});
