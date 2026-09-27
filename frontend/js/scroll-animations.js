/* =====================================================================
   PAIMANA scroll-triggered entrance animations (dependency-free)

   Generic: any page opts in by
     1. linking css/scroll-animations.css,
     2. adding `pm-anim` to <html> in <head> (enables the CSS start state),
     3. marking elements with data-animate / data-animate="stagger" /
        data-animate-load / class="animate-in" (see the CSS file),
     4. optionally placing <div class="pm-scroll-progress" data-scroll-progress aria-hidden="true">.
   Content rendered later is picked up via the existing `pm:content` event
   (detail.root) or PMScrollAnimations.scan(root).

   - IntersectionObserver (threshold .15, rootMargin 0 0 -10% 0); each element
     animates once and is then unobserved.
   - Elements already in view at start-up (e.g. index.html#platform, restored
     scroll) are revealed immediately; data-animate-load elements ~100 ms after load.
   - Reduced motion: nothing is hidden or animated (CSS) and everything is marked
     revealed; also when the preference changes while the page is open.
   - Focusing something inside an unrevealed element reveals it.
   - Independent of the theme (only html.dark changes on toggle).
   ===================================================================== */
(() => {
  'use strict';
  if (window.PMScrollAnimations) return;

  const root = document.documentElement;
  const TARGETS = '[data-animate], .animate-in';
  const IO_OPTIONS = { threshold: 0.15, rootMargin: '0px 0px -10% 0px' };
  const LOAD_DELAY_MS = 100;
  const MAX_STAGGER_STEPS = 8;              // keeps long groups from waiting too long
  const reduced = window.matchMedia('(prefers-reduced-motion: reduce)');
  const tracked = new WeakSet();
  let io = null;

  const isStagger = (el) => el.getAttribute('data-animate') === 'stagger';
  const ms = (value) => {
    const n = parseFloat(value);
    return Number.isFinite(n) ? (String(value).trim().endsWith('ms') ? n : n * 1000) : 0;
  };

  // Drop the entrance transition once it has run so elements keep their own transitions.
  function settle(el, children) {
    if (reduced.matches) { el.classList.add('pm-anim-done'); return; }
    const cs = getComputedStyle(el);
    const total = ms(cs.getPropertyValue('--pm-anim-delay')) + ms(cs.getPropertyValue('--pm-anim-duration') || '520ms')
      + children * ms(cs.getPropertyValue('--pm-anim-stagger') || '80ms');
    setTimeout(() => el.classList.add('pm-anim-done'), total + 60);
  }

  function reveal(el) {
    if (!el || el.classList.contains('visible')) return;
    if (io) io.unobserve(el);
    let steps = 0;
    if (isStagger(el)) {
      // Index only children that are actually displayed (hidden role-specific items don't leave gaps).
      for (const child of el.children) {
        if (child.getClientRects().length === 0) continue;
        child.style.setProperty('--pm-i', String(Math.min(steps, MAX_STAGGER_STEPS)));
        steps += 1;
      }
    }
    el.classList.add('visible');
    settle(el, Math.max(0, Math.min(steps, MAX_STAGGER_STEPS + 1) - 1));
  }

  function inView(rect) {
    const h = window.innerHeight || root.clientHeight;
    return rect.bottom > 0 && rect.top < h * 0.9 && (rect.width > 0 || rect.height > 0);
  }

  // Register elements under `scope`; reveal what is already visible, observe the rest.
  function scan(scope) {
    const base = scope && scope.querySelectorAll ? scope : document;
    const found = [...base.querySelectorAll(TARGETS)];
    if (base !== document && base.matches && base.matches(TARGETS)) found.unshift(base);
    const fresh = found.filter(el => !tracked.has(el));
    if (!fresh.length) return;
    fresh.forEach(el => tracked.add(el));

    if (reduced.matches || !('IntersectionObserver' in window)) { fresh.forEach(reveal); return; }

    const onLoad = [], now = [], later = [];
    // One batch of layout reads, then writes.
    const rects = fresh.map(el => el.getBoundingClientRect());
    fresh.forEach((el, i) => {
      if (el.hasAttribute('data-animate-load')) onLoad.push(el);
      else if (inView(rects[i])) now.push(el);
      else later.push(el);
    });
    now.forEach(reveal);
    if (onLoad.length) setTimeout(() => onLoad.forEach(reveal), LOAD_DELAY_MS);
    if (later.length) {
      io = io || new IntersectionObserver((entries) => {
        entries.forEach(entry => { if (entry.isIntersecting) reveal(entry.target); });
      }, IO_OPTIONS);
      later.forEach(el => io.observe(el));
    }
  }

  function revealAll() {
    document.querySelectorAll(TARGETS).forEach(el => { tracked.add(el); reveal(el); });
    if (io) { io.disconnect(); io = null; }
  }

  // Keyboard users must never land on something still transparent.
  document.addEventListener('focusin', (e) => {
    const el = e.target && e.target.closest ? e.target.closest(TARGETS) : null;
    if (el && !el.classList.contains('visible')) reveal(el);
  });

  // Switching to reduced motion while the page is open: show everything now.
  const onMotionChange = (e) => { if (e.matches) revealAll(); };
  if (reduced.addEventListener) reduced.addEventListener('change', onMotionChange);
  else if (reduced.addListener) reduced.addListener(onMotionChange);

  // Content the page renders later (landing page script already dispatches this).
  document.addEventListener('pm:content', (e) => scan(e.detail && e.detail.root));

  /* ---------------- Scroll progress ---------------- */
  function initProgress() {
    const bar = document.querySelector('[data-scroll-progress]');
    if (!bar) return;
    let queued = false;
    const update = () => {
      queued = false;
      const doc = document.scrollingElement || root;
      const max = doc.scrollHeight - window.innerHeight;
      const top = window.scrollY || doc.scrollTop || 0;
      const p = max > 0 ? Math.min(1, Math.max(0, top / max)) : 0;
      bar.style.transform = `scaleX(${p})`;
    };
    const schedule = () => { if (!queued) { queued = true; requestAnimationFrame(update); } };
    window.addEventListener('scroll', schedule, { passive: true });
    window.addEventListener('resize', schedule, { passive: true });
    // Page height changes as live data arrives; keep the ratio honest without polling.
    if ('ResizeObserver' in window) new ResizeObserver(schedule).observe(document.body);
    update();
  }

  window.PMScrollAnimations = { scan, reveal, revealAll };
  scan(document);
  initProgress();
})();
