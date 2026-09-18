/* PAIMANA AI — shared micro-interactions
   ---------------------------------------------------------------
   Built on two CDN libraries, no bundler/React needed:
     - anime.js (window.anime)  -> number count-ups
     - Motion / motion.dev (window.Motion) -> fades, stagger, hover
   Every helper checks the library exists first, so a page still
   works if a CDN script is slow, blocked, or missing. */

const PaimanaFX = (() => {

  // Staggered fade/rise-in for a list of elements (alert cards, KPI cards).
  function staggerIn(elements) {
    const items = Array.from(elements || []).filter(Boolean);
    if (!window.Motion || !items.length) return;
    window.Motion.animate(
      items,
      { opacity: [0, 1], y: [10, 0] },
      { duration: 0.3, delay: window.Motion.stagger(0.05) }
    );
  }

  // Opacity-only stagger, safe for <tr> elements (transforms don't apply to table rows).
  function staggerFadeIn(elements) {
    const items = Array.from(elements || []).filter(Boolean);
    if (!window.Motion || !items.length) return;
    window.Motion.animate(
      items,
      { opacity: [0, 1] },
      { duration: 0.3, delay: window.Motion.stagger(0.04) }
    );
  }

  // Animate a number from 0 (or its current text) up to `target`.
  // `format` optionally wraps the rounded value (e.g. for currency/suffixes).
  function countUp(el, target, { decimals = 0, duration = 900, format } = {}) {
    if (!el) return;
    const targetNum = Number(target);
    if (Number.isNaN(targetNum)) { el.textContent = target; return; }

    if (!window.anime) { el.textContent = format ? format(targetNum) : targetNum.toLocaleString(); return; }

    const obj = { val: 0 };
    window.anime({
      targets: obj,
      val: targetNum,
      round: decimals === 0 ? 1 : false,
      easing: 'easeOutExpo',
      duration,
      update: () => {
        const v = decimals === 0 ? Math.round(obj.val) : Number(obj.val.toFixed(decimals));
        el.textContent = format ? format(v) : v.toLocaleString();
      }
    });
  }

  // Subtle hover lift for elements marked data-hover-lift (nav links, buttons, cards).
  function initHoverLift() {
    if (!window.Motion) return;
    document.querySelectorAll('[data-hover-lift]').forEach((el) => {
      el.addEventListener('mouseenter', () => window.Motion.animate(el, { scale: 1.02 }, { duration: 0.15 }));
      el.addEventListener('mouseleave', () => window.Motion.animate(el, { scale: 1 }, { duration: 0.15 }));
    });
  }

  document.addEventListener('DOMContentLoaded', () => {
    initHoverLift();
  });

  return { staggerIn, staggerFadeIn, countUp, initHoverLift };
})();

window.PaimanaFX = PaimanaFX;
