/* =====================================================================
   PAIMANA landing page: scroll motion (progressive enhancement)

   - Loads GSAP core + ScrollTrigger (free core plugin) + Lenis from pinned
     jsDelivr URLs with SRI. Scripts are injected by this deferred file so a
     slow CDN never blocks parsing, first paint, DOMContentLoaded (theme toggle,
     role handling) or the live data requests the page has already started.
   - Nothing is hidden by CSS. Initial states are set here with gsap.set only
     after the libraries have loaded, inside gsap.matchMedia contexts so all of
     it reverts cleanly (reduced motion toggled, breakpoint changes).
   - One scroll system: Lenis drives window scroll, ScrollTrigger reads it.
   - Entrance reveals ([data-animate]) are NOT done here: js/scroll-animations.js
     owns them (dependency-free). This file only adds what that system doesn't:
     smooth scrolling, the pinned pipeline, parallax, bar growth, the weights wipe.
   - prefers-reduced-motion: no Lenis (native scroll), no pins, no parallax,
     no scrub. Content is shown in its final state.
   ===================================================================== */
(() => {
  'use strict';

  const LIBS = [
    { src: 'https://cdn.jsdelivr.net/npm/gsap@3.15.0/dist/gsap.min.js',
      sri: 'sha384-XmJ9SoHtVOHoQUcKvFAzVXwdkKo1Ie3bhmSoIAkcdsHGaIrVJIkmozyq0FJeb/Ly' },
    { src: 'https://cdn.jsdelivr.net/npm/gsap@3.15.0/dist/ScrollTrigger.min.js',
      sri: 'sha384-wl5TeDVvOWt30Pbf8aSo2ZrzsOjddu3avOBvHe+p+OhJt9gP6w9YXmDkN5DK2/dF' },
    { src: 'https://cdn.jsdelivr.net/npm/lenis@1.3.26/dist/lenis.min.js',
      sri: 'sha384-jqpi9VmOdhyLoLURgjCn7EpnG9BbnHW57ibIZoeaIU+erWDH3k8fQQg0xH2ySjnw' }
  ];

  const load = ({ src, sri }) => new Promise((resolve, reject) => {
    const s = document.createElement('script');
    s.src = src; s.async = false; // keep execution order (gsap before ScrollTrigger)
    s.integrity = sri; s.crossOrigin = 'anonymous';
    s.onload = resolve; s.onerror = () => reject(new Error(`Could not load ${src}`));
    document.head.appendChild(s);
  });

  Promise.allSettled(LIBS.map(load)).then(() => {
    if (!window.gsap || !window.ScrollTrigger) {
      console.info('[PAIMANA] motion libraries unavailable; using native scrolling.');
      return;
    }
    try { init(); } catch (err) { console.warn('[PAIMANA] motion disabled:', err); }
  });

  function init() {
    const { gsap, ScrollTrigger } = window;
    gsap.registerPlugin(ScrollTrigger);
    const $ = (id) => document.getElementById(id);
    const EASE = 'power3.out';

    let lenis = null;
    let pinST = null;        // pipeline pin (desktop only)
    let motionCtx = null;    // gsap context for reveals, so dynamic content joins it

    const mm = gsap.matchMedia();

    /* Entrance reveals live in js/scroll-animations.js (no second engine here). */

    // Bars inside newly rendered content (state list): grow from the left once in view.
    function bindBars(scope) {
      const bars = [...(scope || document).querySelectorAll('[data-bar]')].filter(el => !el.dataset.rv);
      if (!bars.length) return;
      bars.forEach(el => { el.dataset.rv = '1'; });
      gsap.set(bars, { scaleX: 0 });
      ScrollTrigger.create({
        trigger: bars[0].closest('ol') || bars[0],
        start: 'top 85%',
        once: true,
        onEnter: () => gsap.to(bars, { scaleX: 1, duration: 0.9, ease: 'power2.out', stagger: 0.05 })
      });
    }

    // Weight bar: a clip-path wipe, once.
    function bindWeights() {
      const w = $('weights');
      if (!w) return;
      gsap.fromTo(w, { clipPath: 'inset(0 100% 0 0)' }, {
        clipPath: 'inset(0 0% 0 0)', duration: 1.1, ease: 'power2.inOut',
        scrollTrigger: { trigger: w, start: 'top 85%', once: true }
      });
    }

    /* ---------------- Lenis: one scroll system ---------------- */
    function startLenis() {
      if (!window.Lenis) return null;
      const l = new window.Lenis({ autoRaf: false, lerp: 0.11, smoothWheel: true, syncTouch: false, stopInertiaOnNavigate: true });
      l.on('scroll', ScrollTrigger.update);
      const tick = (t) => l.raf(t * 1000);
      gsap.ticker.add(tick);
      gsap.ticker.lagSmoothing(0);
      l._pmTick = tick;
      return l;
    }
    function stopLenis(l) {
      if (!l) return;
      gsap.ticker.remove(l._pmTick);
      gsap.ticker.lagSmoothing(500, 33);
      l.destroy();
    }

    // In-page anchors through Lenis, keeping the hash in the URL and history.
    const targetY = (el) => {
      if (el.id === 'platform' && pinST) return pinST.start; // land at the start of the pinned sequence
      return el;
    };
    function focusTarget(el) {
      if (!el.matches('a, button, input, select, textarea, [tabindex]')) el.setAttribute('tabindex', '-1');
      el.focus({ preventScroll: true });
    }
    function scrollToEl(el, { immediate = false, focus = true } = {}) {
      if (!lenis) return;
      const t = targetY(el);
      lenis.scrollTo(t, {
        // element targets: Lenis already honours html { scroll-padding-top } (= top bar height)
        offset: 0,
        immediate, force: true, duration: immediate ? 0 : 1.1,
        easing: (x) => 1 - Math.pow(1 - x, 4),
        onComplete: () => { if (focus) focusTarget(el); }
      });
    }
    const hashTarget = (hash) => {
      const id = decodeURIComponent((hash || '').slice(1));
      return id ? document.getElementById(id) : null;
    };
    function onClick(e) {
      if (!lenis || e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
      const a = e.target.closest && e.target.closest('a[href^="#"]');
      if (!a) return;
      const el = hashTarget(a.getAttribute('href'));
      if (!el) return;
      e.preventDefault();
      if (location.hash !== a.getAttribute('href')) history.pushState(null, '', a.getAttribute('href'));
      scrollToEl(el);
    }
    function onPop() {
      if (!lenis) return;
      const el = hashTarget(location.hash);
      if (el) scrollToEl(el, { focus: false });
      else lenis.scrollTo(0, { force: true, duration: 1 });
    }
    function onMenu(e) {
      if (!lenis) return;
      if (e.detail && e.detail.open) lenis.stop(); else lenis.start();
    }

    /* ---------------- Pipeline ---------------- */
    const pipe = $('pipe');
    const stages = pipe ? [...pipe.querySelectorAll('.stage')] : [];
    const fills = stages.map(s => s.querySelector('.stage-link > i')).filter(Boolean);
    const status = $('pipe-status');
    const setActive = (idx) => {
      stages.forEach((s, j) => s.classList.toggle('is-on', j <= idx));
      if (status) {
        const t = stages[idx]?.querySelector('.stage-title')?.textContent || '';
        status.textContent = `Stage ${idx + 1} of ${stages.length} · ${t}`;
      }
    };
    const takeOverPipe = () => { pipe.classList.remove('is-in'); pipe.classList.add('js-pipe'); };
    const releasePipe = () => {
      pipe.classList.remove('js-pipe'); pipe.classList.add('is-in');
      stages.forEach(s => s.classList.remove('is-on'));
      if (status) status.textContent = '';
    };

    /* ================= Motion allowed ================= */
    mm.add('(prefers-reduced-motion: no-preference)', (ctx) => {
      motionCtx = ctx;
      document.documentElement.classList.add('js-motion');
      lenis = startLenis();
      if (lenis) { try { history.scrollRestoration = 'manual'; } catch (e) {} }

      bindBars(document);
      bindWeights();

      document.addEventListener('click', onClick);
      addEventListener('popstate', onPop);
      document.addEventListener('pm:menu', onMenu);

      // A hash on first load: re-land precisely once pins and spacing exist.
      if (location.hash && hashTarget(location.hash)) {
        requestAnimationFrame(() => { ScrollTrigger.refresh(); scrollToEl(hashTarget(location.hash), { immediate: true, focus: false }); });
      }

      return () => {
        document.removeEventListener('click', onClick);
        removeEventListener('popstate', onPop);
        document.removeEventListener('pm:menu', onMenu);
        stopLenis(lenis); lenis = null;
        try { history.scrollRestoration = 'auto'; } catch (e) {}
        document.documentElement.classList.remove('js-motion');
        document.querySelectorAll('[data-rv]').forEach(el => { delete el.dataset.rv; });
        motionCtx = null;
      };
    });

    /* Desktop: pin the pipeline briefly while its stages light in sequence (scrubbed),
       and a small parallax on the hero's live panel. */
    mm.add('(prefers-reduced-motion: no-preference) and (min-width: 1024px) and (min-height: 760px)', () => {
      if (!pipe || stages.length < 2) return;
      takeOverPipe();
      gsap.set(stages.slice(1), { opacity: 0.4 });
      gsap.set(fills, { scaleX: 0, transformOrigin: 'left center' });
      setActive(0);

      const segs = stages.length - 1;
      const tl = gsap.timeline({
        defaults: { ease: 'none' },
        scrollTrigger: {
          trigger: '#platform',
          start: () => `top ${($('topbar')?.offsetHeight || 64)}px`,
          end: () => `+=${Math.round(window.innerHeight * 0.85)}`,
          pin: true,
          scrub: 0.5,
          anticipatePin: 1,
          invalidateOnRefresh: true
        },
        // follow the scrubbed timeline (not raw scroll) so the highlight matches what is drawn
        onUpdate() { setActive(Math.min(segs, Math.floor(this.progress() * segs + 0.25))); }
      });
      for (let i = 0; i < segs; i++) {
        tl.to(fills[i], { scaleX: 1, duration: 1 })
          .to(stages[i + 1], { opacity: 1, duration: 0.35 }, '-=0.3');
      }
      pinST = tl.scrollTrigger;

      const panel = $('live-panel');
      if (panel) {
        gsap.to(panel, {
          y: -24, ease: 'none',
          scrollTrigger: { trigger: '.hero', start: 'top top', end: 'bottom top', scrub: true }
        });
      }

      return () => { pinST = null; releasePipe(); };
    });

    /* Smaller screens: no pin. Each stage lights as it reaches the reading line. */
    mm.add('(prefers-reduced-motion: no-preference) and (max-width: 1023.98px), (prefers-reduced-motion: no-preference) and (max-height: 759.98px)', () => {
      if (!pipe || !stages.length) return;
      takeOverPipe();
      const vertical = !window.matchMedia('(min-width: 1024px)').matches;
      gsap.set(stages.slice(1), { opacity: 0.4 });
      gsap.set(fills, vertical ? { scaleY: 0, transformOrigin: 'center top' } : { scaleX: 0, transformOrigin: 'left center' });
      setActive(0);
      stages.forEach((s, i) => {
        if (!i) return;
        ScrollTrigger.create({
          trigger: s, start: 'top 78%', once: true,
          onEnter: () => {
            gsap.to(fills[i - 1], vertical ? { scaleY: 1, duration: 0.45, ease: 'power1.inOut' } : { scaleX: 1, duration: 0.45, ease: 'power1.inOut' });
            gsap.to(s, { opacity: 1, duration: 0.5, delay: 0.25, ease: EASE, onStart: () => setActive(Math.max(i, currentMax())) });
          }
        });
      });
      return () => releasePipe();
    });
    const currentMax = () => stages.reduce((m, s, j) => (s.classList.contains('is-on') ? j : m), 0);

    /* ================= Reduced motion ================= */
    mm.add('(prefers-reduced-motion: reduce)', () => {
      if (pipe) pipe.classList.add('is-in');
    });

    /* ---------------- New real content from the page script ---------------- */
    let refreshTimer = 0;
    document.addEventListener('pm:content', (e) => {
      const root = e.detail && e.detail.root;
      if (motionCtx && root) motionCtx.add(() => bindBars(root));
      clearTimeout(refreshTimer);
      refreshTimer = setTimeout(() => ScrollTrigger.refresh(), 120);
    });
    if (document.fonts && document.fonts.ready) document.fonts.ready.then(() => ScrollTrigger.refresh());
    addEventListener('load', () => ScrollTrigger.refresh());
  }
})();
