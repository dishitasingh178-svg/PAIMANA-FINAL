/* =====================================================================
   PAIMANA shared UI layer (window.PM)
   - App shell (one sidebar for every page, same destinations as before)
   - Section loader: skeleton -> real data | error + retry | empty
   - Risk tier badges (icon + text + colour), formatting, toasts,
     count-ups, reveal-on-scroll, chart theme values
   Nothing here produces data: every number shown comes from the API.
   ===================================================================== */
(() => {
  'use strict';

  const ICONS = {"arrow-right": "<path d=\"M5 12h14\" /> <path d=\"m12 5 7 7-7 7\" />", "arrow-up-right": "<path d=\"M7 7h10v10\" /> <path d=\"M7 17 17 7\" />", "bell": "<path d=\"M10.268 21a2 2 0 0 0 3.464 0\" /> <path d=\"M3.262 15.326A1 1 0 0 0 4 17h16a1 1 0 0 0 .74-1.673C19.41 13.956 18 12.499 18 8A6 6 0 0 0 6 8c0 4.499-1.411 5.956-2.738 7.326\" />", "bot": "<path d=\"M12 8V4H8\" /> <rect width=\"16\" height=\"12\" x=\"4\" y=\"8\" rx=\"2\" /> <path d=\"M2 14h2\" /> <path d=\"M20 14h2\" /> <path d=\"M15 13v2\" /> <path d=\"M9 13v2\" />", "chart-line": "<path d=\"M3 3v16a2 2 0 0 0 2 2h16\" /> <path d=\"m19 9-5 5-4-4-3 3\" />", "chevron-right": "<path d=\"m9 18 6-6-6-6\" />", "circle-check": "<circle cx=\"12\" cy=\"12\" r=\"10\" /> <path d=\"m16 9-5.5 5.5L8 12\" />", "circle-plus": "<circle cx=\"12\" cy=\"12\" r=\"10\" /> <path d=\"M8 12h8\" /> <path d=\"M12 8v8\" />", "eye": "<path d=\"M2.062 12.348a1 1 0 0 1 0-.696 10.75 10.75 0 0 1 19.876 0 1 1 0 0 1 0 .696 10.75 10.75 0 0 1-19.876 0\" /> <circle cx=\"12\" cy=\"12\" r=\"3\" />", "file-up": "<path d=\"M6 22a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h8a2.4 2.4 0 0 1 1.704.706l3.588 3.588A2.4 2.4 0 0 1 20 8v12a2 2 0 0 1-2 2z\" /> <path d=\"M14 2v5a1 1 0 0 0 1 1h5\" /> <path d=\"M12 12v6\" /> <path d=\"m15 15-3-3-3 3\" />", "folder-kanban": "<path d=\"M4 20h16a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.93a2 2 0 0 1-1.66-.9l-.82-1.2A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13c0 1.1.9 2 2 2Z\" /> <path d=\"M8 10v4\" /> <path d=\"M12 10v2\" /> <path d=\"M16 10v6\" />", "inbox": "<polyline points=\"22 12 16 12 14 15 10 15 8 12 2 12\" /> <path d=\"M5.45 5.11 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z\" />", "layout-dashboard": "<rect width=\"7\" height=\"9\" x=\"3\" y=\"3\" rx=\"1\" /> <rect width=\"7\" height=\"5\" x=\"14\" y=\"3\" rx=\"1\" /> <rect width=\"7\" height=\"9\" x=\"14\" y=\"12\" rx=\"1\" /> <rect width=\"7\" height=\"5\" x=\"3\" y=\"16\" rx=\"1\" />", "log-out": "<path d=\"m16 17 5-5-5-5\" /> <path d=\"M21 12H9\" /> <path d=\"M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4\" />", "map-pin": "<path d=\"M20 10c0 4.993-5.539 10.193-7.399 11.799a1 1 0 0 1-1.202 0C9.539 20.193 4 14.993 4 10a8 8 0 0 1 16 0\" /> <circle cx=\"12\" cy=\"10\" r=\"3\" />", "menu": "<path d=\"M4 5h16\" /> <path d=\"M4 12h16\" /> <path d=\"M4 19h16\" />", "moon": "<path d=\"M20.985 12.486a9 9 0 1 1-9.473-9.472c.405-.022.617.46.402.803a6 6 0 0 0 8.268 8.268c.344-.215.825-.004.803.401\" />", "octagon-alert": "<path d=\"M12 16h.01\" /> <path d=\"M12 8v4\" /> <path d=\"M15.312 2a2 2 0 0 1 1.414.586l4.688 4.688A2 2 0 0 1 22 8.688v6.624a2 2 0 0 1-.586 1.414l-4.688 4.688a2 2 0 0 1-1.414.586H8.688a2 2 0 0 1-1.414-.586l-4.688-4.688A2 2 0 0 1 2 15.312V8.688a2 2 0 0 1 .586-1.414l4.688-4.688A2 2 0 0 1 8.688 2z\" />", "refresh-cw": "<path d=\"M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8\" /> <path d=\"M21 3v5h-5\" /> <path d=\"M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16\" /> <path d=\"M8 16H3v5\" />", "search": "<path d=\"m21 21-4.34-4.34\" /> <circle cx=\"11\" cy=\"11\" r=\"8\" />", "shield-alert": "<path d=\"M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z\" /> <path d=\"M12 8v4\" /> <path d=\"M12 16h.01\" />", "sparkles": "<path d=\"M11.017 2.814a1 1 0 0 1 1.966 0l1.051 5.558a2 2 0 0 0 1.594 1.594l5.558 1.051a1 1 0 0 1 0 1.966l-5.558 1.051a2 2 0 0 0-1.594 1.594l-1.051 5.558a1 1 0 0 1-1.966 0l-1.051-5.558a2 2 0 0 0-1.594-1.594l-5.558-1.051a1 1 0 0 1 0-1.966l5.558-1.051a2 2 0 0 0 1.594-1.594z\" /> <path d=\"M20 2v4\" /> <path d=\"M22 4h-4\" /> <circle cx=\"4\" cy=\"20\" r=\"2\" />", "sun": "<circle cx=\"12\" cy=\"12\" r=\"4\" /> <path d=\"M12 2v2\" /> <path d=\"M12 20v2\" /> <path d=\"m4.93 4.93 1.41 1.41\" /> <path d=\"m17.66 17.66 1.41 1.41\" /> <path d=\"M2 12h2\" /> <path d=\"M20 12h2\" /> <path d=\"m6.34 17.66-1.41 1.41\" /> <path d=\"m19.07 4.93-1.41 1.41\" />", "triangle-alert": "<path d=\"m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3\" /> <path d=\"M12 9v4\" /> <path d=\"M12 17h.01\" />", "wifi-off": "<path d=\"M12 20h.01\" /> <path d=\"M8.5 16.429a5 5 0 0 1 7 0\" /> <path d=\"M5 12.859a10 10 0 0 1 5.17-2.69\" /> <path d=\"M19 12.859a10 10 0 0 0-2.007-1.523\" /> <path d=\"M2 8.82a15 15 0 0 1 4.177-2.643\" /> <path d=\"M22 8.82a15 15 0 0 0-11.288-3.764\" /> <path d=\"m2 2 20 20\" />", "x": "<path d=\"M18 6 6 18\" /> <path d=\"m6 6 12 12\" />"};
  const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');

  function icon(name, cls = '') {
    const body = ICONS[name];
    if (!body) return '';
    return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false" class="${cls}">${body}</svg>`;
  }

  // ------------------------------------------------------------------
  // Formatting
  // ------------------------------------------------------------------
  const esc = (value) => String(value ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const num = (value) => {
    if (value === null || value === undefined || value === '' || typeof value === 'boolean') return null;
    const n = Number(typeof value === 'string' ? value.replace(/[₹,\s]/g, '') : value);
    return Number.isFinite(n) ? n : null;
  };
  const inr = new Intl.NumberFormat('en-IN');
  const fmt = {
    int: (v) => num(v) === null ? '—' : inr.format(Math.round(num(v))),
    dec: (v, d = 1) => num(v) === null ? '—' : num(v).toLocaleString('en-IN', { minimumFractionDigits: d, maximumFractionDigits: d }),
    crore: (v, d = 1) => num(v) === null ? '—' : `₹${num(v).toLocaleString('en-IN', { maximumFractionDigits: d })} Cr`,
    lakhCrore: (v) => num(v) === null ? '—' : `₹${num(v).toFixed(2)}L Cr`,
    pct: (v, d = 0) => num(v) === null ? '—' : `${num(v).toFixed(d)}%`,
    date: (v) => {
      if (!v) return '—';
      const d = new Date(v);
      return Number.isFinite(d.getTime()) ? d.toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' }) : String(v);
    },
    month: (v) => {
      const m = /^(\d{4})-(\d{2})/.exec(String(v || ''));
      if (!m) return v ? String(v) : '—';
      return new Date(Number(m[1]), Number(m[2]) - 1, 1).toLocaleDateString('en-IN', { month: 'short', year: 'numeric' });
    },
    relative: (v) => {
      const d = v instanceof Date ? v : new Date(v);
      const s = (Date.now() - d.getTime()) / 1000;
      if (!Number.isFinite(s)) return '—';
      if (s < 45) return 'just now';
      if (s < 3600) return `${Math.round(s / 60)} min ago`;
      if (s < 86400) return `${Math.round(s / 3600)} h ago`;
      return fmt.date(d);
    }
  };

  // ------------------------------------------------------------------
  // Risk tiers — same thresholds as ml_package/predictor.py
  // (<25 LOW, <50 WATCH, <75 ELEVATED, else CRITICAL)
  // ------------------------------------------------------------------
  const TIERS = {
    LOW:      { label: 'Low',      icon: 'circle-check',  range: '0–25' },
    WATCH:    { label: 'Watch',    icon: 'eye',           range: '25–50' },
    ELEVATED: { label: 'Elevated', icon: 'triangle-alert', range: '50–75' },
    CRITICAL: { label: 'Critical', icon: 'octagon-alert', range: '75–100' },
    UNKNOWN:  { label: 'Unassessed', icon: 'circle-check', range: '' }
  };
  const TIER_ORDER = ['LOW', 'WATCH', 'ELEVATED', 'CRITICAL'];
  const TIER_ALIASES = { MEDIUM: 'WATCH', MODERATE: 'WATCH', HIGH: 'ELEVATED', SEVERE: 'CRITICAL', UNASSESSED: 'UNKNOWN' };

  function tierFromScore(score) {
    const s = num(score);
    if (s === null) return 'UNKNOWN';
    return s < 25 ? 'LOW' : s < 50 ? 'WATCH' : s < 75 ? 'ELEVATED' : 'CRITICAL';
  }
  // Prefer an explicit backend label; fall back to the score.
  function tier(label, score) {
    const t = String(label || '').trim().toUpperCase().replace(/\s+RISK$/, '');
    if (TIERS[t]) return t;
    if (TIER_ALIASES[t]) return TIER_ALIASES[t];
    return tierFromScore(score);
  }
  function tierBadge(label, score, { showScore = true } = {}) {
    const t = tier(label, score);
    const s = num(score);
    const scorePart = showScore && s !== null
      ? `<span class="pm-tier-sep">·</span><span class="pm-tier-score">${s.toFixed(1)}</span>` : '';
    return `<span class="pm-tier" data-tier="${t}">${icon(TIERS[t].icon)}${TIERS[t].label}${scorePart}</span>`;
  }
  function cssVar(name) { return getComputedStyle(document.documentElement).getPropertyValue(name).trim(); }
  // Fill colour for charts/pins/bars; text colours stay on the darker --pm-<tier> tokens.
  function tierColor(t) { return cssVar(`--pm-${String(t).toLowerCase()}-fill`) || cssVar('--pm-unknown-fill'); }

  // ------------------------------------------------------------------
  // States: skeleton / error / empty
  // ------------------------------------------------------------------
  const skeleton = {
    lines: (n = 3) => Array.from({ length: n }, (_, i) => `<div class="pm-skel pm-skel-line" style="width:${92 - (i % 3) * 18}%"></div>`).join(''),
    block: (h = 160, extra = '') => `<div class="pm-skel" style="height:${h}px;${extra}"></div>`,
    rows: (n = 4) => Array.from({ length: n }, () => `<div class="flex gap-3 items-start py-3"><div class="pm-skel" style="width:28px;height:28px;border-radius:8px;flex:none"></div><div class="flex-1"><div class="pm-skel pm-skel-line" style="width:70%;margin-top:2px"></div><div class="pm-skel pm-skel-line" style="width:45%"></div></div></div>`).join('')
  };

  function stateHTML({ kind = 'empty', title, message, retryLabel = 'Retry', inline = false } = {}) {
    const glyph = kind === 'error' ? 'wifi-off' : 'inbox';
    return `<div class="pm-state ${kind === 'error' ? 'is-error' : ''} ${inline ? 'pm-state-inline' : ''}" role="${kind === 'error' ? 'alert' : 'status'}">
      <div class="pm-state-icon">${icon(glyph)}</div>
      <div>${title ? `<p class="pm-state-title">${esc(title)}</p>` : ''}${message ? `<p class="pm-state-msg">${esc(message)}</p>` : ''}</div>
      ${kind === 'error' ? `<button type="button" class="pm-btn pm-btn-sm" data-pm-retry>${icon('refresh-cw', 'w-3.5 h-3.5')}${esc(retryLabel)}</button>` : ''}
    </div>`;
  }

  // Runs `loader()` for one independent section of a page.
  //   el:        container to fill
  //   loader:    async () => data           (real API call)
  //   render:    (data, el) => void          (called only with real data)
  //   skeleton:  html shown while loading
  //   isEmpty:   (data) => bool, empty:{title,message}
  //   errorTitle
  // A failure only affects this section; retry re-runs just this loader.
  async function section(el, { loader, render, skeleton: skel = skeleton.lines(3), isEmpty, empty = {}, errorTitle = 'Could not load this section', inline = false }) {
    if (!el) return;
    el.setAttribute('aria-busy', 'true');
    el.innerHTML = skel;
    try {
      const data = await loader();
      el.removeAttribute('aria-busy');
      if (isEmpty && isEmpty(data)) {
        el.innerHTML = stateHTML({ kind: 'empty', title: empty.title || 'Nothing to show yet', message: empty.message, inline });
        return data;
      }
      el.innerHTML = '';
      render(data, el);
      return data;
    } catch (err) {
      if (err && err.name === 'AbortError') return;
      el.removeAttribute('aria-busy');
      console.warn('[PAIMANA] section failed:', err);
      el.innerHTML = stateHTML({ kind: 'error', title: errorTitle, message: err?.message || 'Unexpected error.', inline });
      const btn = el.querySelector('[data-pm-retry]');
      if (btn) btn.addEventListener('click', () => section(el, { loader, render, skeleton: skel, isEmpty, empty, errorTitle, inline }), { once: true });
      return undefined;
    }
  }

  // ------------------------------------------------------------------
  // Motion helpers (all no-ops or instant under reduced motion)
  // ------------------------------------------------------------------
  function countUp(el, target, { decimals = 0, duration = 900, format } = {}) {
    if (!el) return;
    const end = num(target);
    const render = (v) => { el.textContent = format ? format(v) : v.toLocaleString('en-IN', { minimumFractionDigits: decimals, maximumFractionDigits: decimals }); };
    if (end === null) { el.textContent = '—'; return; }
    if (reducedMotion.matches || duration <= 0) { render(end); return; }
    const start = performance.now();
    const from = num(el.dataset.pmValue) ?? 0;
    const step = (now) => {
      const t = Math.min((now - start) / duration, 1);
      const eased = 1 - Math.pow(1 - t, 4);
      const v = from + (end - from) * eased;
      render(decimals ? Number(v.toFixed(decimals)) : Math.round(v));
      if (t < 1) requestAnimationFrame(step); else { render(end); el.dataset.pmValue = String(end); }
    };
    requestAnimationFrame(step);
  }

  let revealObserver = null;
  function reveal(root = document) {
    const items = root.querySelectorAll('.pm-reveal:not(.is-in)');
    if (!items.length) return;
    if (reducedMotion.matches || !('IntersectionObserver' in window)) { items.forEach(i => i.classList.add('is-in')); return; }
    revealObserver = revealObserver || new IntersectionObserver((entries) => {
      entries.forEach(e => { if (e.isIntersecting) { e.target.classList.add('is-in'); revealObserver.unobserve(e.target); } });
    }, { rootMargin: '0px 0px -6% 0px', threshold: 0.05 });
    items.forEach(i => revealObserver.observe(i));
  }
  function stagger(elements, step = 45, cls = 'pm-pop-in') {
    Array.from(elements || []).forEach((el, i) => {
      if (reducedMotion.matches) return;
      el.style.setProperty('--pm-delay', `${Math.min(i, 14) * step}ms`);
      el.classList.add(cls);
    });
  }

  // ------------------------------------------------------------------
  // Toasts + last-updated
  // ------------------------------------------------------------------
  function toast(message, kind = 'info', ms = 4200) {
    let host = document.querySelector('.pm-toasts');
    if (!host) { host = document.createElement('div'); host.className = 'pm-toasts'; host.setAttribute('aria-live', 'polite'); document.body.appendChild(host); }
    const t = document.createElement('div');
    t.className = 'pm-toast'; t.dataset.kind = kind; t.setAttribute('role', kind === 'error' ? 'alert' : 'status');
    t.innerHTML = `${icon(kind === 'error' ? 'triangle-alert' : kind === 'success' ? 'circle-check' : 'sparkles')}<span>${esc(message)}</span>`;
    host.appendChild(t);
    setTimeout(() => { t.classList.add('is-leaving'); setTimeout(() => t.remove(), 260); }, ms);
  }
  const updatedEls = new Set();
  function markUpdated(el, when = new Date()) {
    if (!el) return;
    el.dataset.pmUpdated = when.toISOString();
    el.textContent = `Updated ${fmt.relative(when)}`;
    el.title = when.toLocaleString();
    updatedEls.add(el);
  }
  setInterval(() => updatedEls.forEach(el => { if (el.isConnected) el.textContent = `Updated ${fmt.relative(el.dataset.pmUpdated)}`; }), 30000);

  // A lane runs heavy requests one at a time, in the order queued. The API is a
  // single worker process: parallel heavy queries contend and all finish late,
  // while queuing them lets the most important section render first.
  function lane() {
    let tail = Promise.resolve();
    return (task) => {
      const run = tail.then(task, task);
      tail = run.catch(() => {});
      return run;
    };
  }

  const debounce = (fn, ms = 300) => { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; };

  // ------------------------------------------------------------------
  // Chart.js theme values (read at draw time so theme toggles apply)
  // ------------------------------------------------------------------
  function chartTheme() {
    return {
      grid: cssVar('--pm-chart-grid'), tick: cssVar('--pm-chart-tick'), text: cssVar('--pm-text'),
      muted: cssVar('--pm-muted'), surface: cssVar('--pm-bg-elev'), line: cssVar('--pm-line-strong'),
      accent: cssVar('--pm-accent'), info: cssVar('--pm-info'),
      font: { family: '"IBM Plex Sans", system-ui, sans-serif', size: 11.5 }
    };
  }
  function chartTooltip() {
    const t = chartTheme();
    return {
      backgroundColor: t.surface, titleColor: t.text, bodyColor: t.muted, borderColor: t.line, borderWidth: 1,
      padding: 10, cornerRadius: 9, boxPadding: 4, usePointStyle: true,
      titleFont: { ...t.font, weight: '600', size: 12 }, bodyFont: { ...t.font, size: 12 }
    };
  }

  // ------------------------------------------------------------------
  // App shell: sidebar. Destinations match the original navigation.
  // ------------------------------------------------------------------
  const NAV = [
    { group: 'Monitor', items: [
      { href: 'dashboard.html', label: 'Overview', icon: 'layout-dashboard', key: 'dashboard' },
      { href: 'projects.html', label: 'Projects', icon: 'folder-kanban', key: 'projects', also: ['project-details'] },
      { href: 'early-warnings.html', label: 'Early Warnings', icon: 'bell', key: 'early-warnings' }
    ] },
    { group: 'Analyze', items: [
      { href: 'risk-analytics.html', label: 'Risk Analytics', icon: 'chart-line', key: 'risk-analytics' },
      { href: 'ai-assistant.html', label: 'AI Assistant', icon: 'bot', key: 'ai-assistant' }
    ] },
    { group: 'Ingest', admin: true, items: [
      { href: 'add-project.html', label: 'Add Project', icon: 'circle-plus', key: 'add-project', admin: true, id: 'admin-add-project' }
    ] }
  ];

  function renderShell() {
    const aside = document.getElementById('sidebar');
    if (!aside || !aside.hasAttribute('data-pm-shell') || aside.dataset.pmRendered) return;
    const page = (location.pathname.split('/').pop() || 'index.html').replace('.html', '');
    const groups = NAV.map(g => `
      <div class="pm-nav-group" ${g.admin ? 'data-role="admin" style="display:none"' : ''}>
        <p class="pm-nav-label">${g.group}</p>
        ${g.items.map(i => `<a href="${i.href}" class="pm-nav-link" ${i.id ? `id="${i.id}"` : ''} ${page === i.key || (i.also || []).includes(page) ? 'aria-current="page"' : ''}>${icon(i.icon)}<span>${i.label}</span></a>`).join('')}
      </div>`).join('');
    aside.classList.add('pm-sidebar');
    aside.setAttribute('aria-label', 'Primary');
    aside.innerHTML = `
      <div>
        <a href="index.html" class="pm-brand" aria-label="PAIMANA home">
          <span class="pm-brand-mark">${icon('shield-alert')}</span>
          <span class="pm-brand-name">PAIMANA<small>Infrastructure intelligence</small></span>
        </a>
        <nav class="mt-2">${groups}</nav>
      </div>
      <div class="pm-user">
        <span class="pm-avatar" aria-hidden="true">${icon('shield-alert', 'w-4 h-4')}</span>
        <div class="text-xs min-w-0">
          <p class="font-semibold" style="color:var(--pm-text)" data-role-label>Project User</p>
          <p style="color:var(--pm-faint)">Session role</p>
        </div>
        <a href="login.html" class="pm-btn pm-btn-ghost pm-btn-sm ml-auto" data-role="user" style="display:none">Log in</a>
      </div>`;
    aside.dataset.pmRendered = '1';
    syncSidebarInert(aside);
    // auth.js opens/closes the mobile drawer by toggling -translate-x-full;
    // while closed on small screens its links leave the tab order.
    new MutationObserver(() => syncSidebarInert(aside)).observe(aside, { attributes: true, attributeFilter: ['class'] });
    window.addEventListener('resize', () => syncSidebarInert(aside));
  }

  function syncSidebarInert(aside) {
    const hidden = window.innerWidth < 1024 && aside.classList.contains('-translate-x-full');
    aside.inert = hidden;
    if (hidden) aside.setAttribute('aria-hidden', 'true'); else aside.removeAttribute('aria-hidden');
  }

  // <span data-icon="name" class="w-4 h-4"> placeholders -> inline SVG (keeps the span, its id and classes)
  function hydrateIcons(root = document) {
    root.querySelectorAll('[data-icon]:not([data-icon-done])').forEach(el => {
      el.innerHTML = icon(el.dataset.icon, 'w-full h-full');
      el.classList.add('inline-block', 'shrink-0');
      el.setAttribute('aria-hidden', 'true');
      el.dataset.iconDone = '1';
    });
  }

  // Theme toggle icon state (theme.js owns the click handler)
  function syncThemeButton() {
    const btn = document.getElementById('theme-toggle');
    if (!btn) return;
    const dark = document.documentElement.classList.contains('dark');
    btn.setAttribute('aria-label', dark ? 'Switch to light theme' : 'Switch to dark theme');
    btn.setAttribute('title', dark ? 'Light theme' : 'Dark theme');
  }

  window.PM = {
    icon, esc, num, fmt, TIERS, TIER_ORDER, tier, tierFromScore, tierBadge, tierColor, cssVar,
    skeleton, stateHTML, section, lane, countUp, reveal, stagger, toast, markUpdated, debounce,
    chartTheme, chartTooltip, renderShell, syncThemeButton, hydrateIcons, reducedMotion: () => reducedMotion.matches
  };

  renderShell();
  document.addEventListener('DOMContentLoaded', () => { renderShell(); hydrateIcons(); syncThemeButton(); reveal(); });
  window.addEventListener('themeChanged', syncThemeButton);
})();
