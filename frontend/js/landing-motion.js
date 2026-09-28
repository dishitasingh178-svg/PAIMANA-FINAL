// Public landing only: native scrolling, reversible section depth, no scroll interception.
  (() => {
    'use strict';
    const scroller = window;
    const report = document.querySelector('main#main');
    if (!report || !document.getElementById('hero-title')) return;
    const sections = Array.from(report.querySelectorAll(':scope > .story'), anchor => ({
      anchor, surface: anchor.firstElementChild, top: 0, height: 0
    }));
    const reduced = matchMedia('(prefers-reduced-motion: reduce)');
    const narrow = matchMedia('(max-width: 767px)');
    let frame = 0, dirty = true, mounted = false, viewport = 1, viewportWidth = 1;

    function reset() {
      sections.forEach(({ surface }) => {
        surface.style.removeProperty('transform');
        surface.style.removeProperty('opacity');
        surface.style.removeProperty('will-change');
      });
    }
    function schedule() {
      if (mounted && !reduced.matches && !frame) frame = requestAnimationFrame(render);
    }
    function invalidate() { dirty = true; schedule(); }
    function render() {
      frame = 0;
      if (!mounted || reduced.matches) return;
      const scroll = window.scrollY;
      if (dirty) {
        // Batched reads only on size/content changes, never on ordinary scroll.
        const rootTop = 0;
        viewport = Math.max(1, window.innerHeight);
        viewportWidth = window.innerWidth;
        sections.forEach(section => {
          const rect = section.anchor.getBoundingClientRect();
          section.top = rect.top - rootTop + scroll;
          section.height = rect.height;
        });
        dirty = false;
      }
      const mobile = narrow.matches;
      const tablet = !mobile && viewportWidth < 1024;
      sections.forEach(({ top, height, surface }) => {
        const center = top + height / 2 - scroll - viewport / 2;
        // Tall sections stay settled while their central reading area is visible.
        const plateau = Math.max(0, (height - viewport * 0.6) / 2);
        const progress = Math.min(1, Math.max(0, Math.abs(center) - plateau) / (viewport * 0.65));
        const depth = progress * progress * (3 - 2 * progress);
        const direction = Math.sign(center);
        const y = direction * depth * (mobile ? 10 : tablet ? 18 : 28);
        const z = -depth * (mobile ? 0 : tablet ? 16 : 30);
        const tilt = direction * depth * (mobile ? 0 : tablet ? 0.8 : 1.5);
        const scale = 1 - depth * (mobile ? 0.006 : tablet ? 0.012 : 0.02);
        surface.style.transform = `perspective(1200px) translate3d(0, ${y.toFixed(2)}px, ${z.toFixed(2)}px) rotateX(${tilt.toFixed(2)}deg) scale(${scale.toFixed(4)})`;
        surface.style.opacity = (1 - depth * (mobile ? 0.04 : 0.10)).toFixed(3);
        surface.style.willChange = top < scroll + viewport + 120 && top + height > scroll - 120 ? 'transform, opacity' : 'auto';
      });
    }
    function motionChanged() {
      scroller.removeEventListener('scroll', schedule);
      if (frame) cancelAnimationFrame(frame);
      frame = 0;
      reset();
      if (!reduced.matches) {
        scroller.addEventListener('scroll', schedule, { passive: true });
        invalidate();
      }
    }
    const resize = new ResizeObserver(invalidate);
    function start() {
      if (mounted) return;
      mounted = true;
      // Observe content dimensions, not transformed surfaces.
      resize.observe(report);
      sections.forEach(({ anchor }) => resize.observe(anchor));
      window.addEventListener('resize', invalidate, { passive: true });
      document.addEventListener('pm:content', invalidate);
      reduced.addEventListener('change', motionChanged);
      motionChanged();
    }
    function stop() {
      mounted = false;
      scroller.removeEventListener('scroll', schedule);
      window.removeEventListener('resize', invalidate);
      document.removeEventListener('pm:content', invalidate);
      reduced.removeEventListener('change', motionChanged);
      resize.disconnect();
      if (frame) cancelAnimationFrame(frame);
      frame = 0;
      reset();
    }
    window.addEventListener('pagehide', stop);
    window.addEventListener('pageshow', start);
    document.fonts?.ready.then(invalidate);
    start();
  })();
