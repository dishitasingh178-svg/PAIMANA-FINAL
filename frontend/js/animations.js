/* PAIMANA AI — shared micro-interactions (compatibility layer)
   ---------------------------------------------------------------
   Keeps the original PaimanaFX API used by existing pages, now built
   on the dependency-free helpers in js/ui.js (window.PM) and CSS, so
   pages no longer need the anime.js / Motion CDN bundles. Every helper
   degrades to an instant update if ui.js is missing or the user prefers
   reduced motion. */

const PaimanaFX = (() => {
  const pm = () => window.PM;

  // Staggered fade/rise-in for a list of elements (alert cards, KPI cards).
  function staggerIn(elements) {
    if (pm()) pm().stagger(elements, 45, 'pm-pop-in');
  }

  // Opacity-only stagger, safe for <tr> elements.
  function staggerFadeIn(elements) {
    if (pm()) pm().stagger(elements, 30, 'pm-fade-swap');
  }

  // Animate a number up to `target`; `format` optionally wraps the value.
  function countUp(el, target, options = {}) {
    if (!el) return;
    if (pm()) { pm().countUp(el, target, options); return; }
    const n = Number(target);
    el.textContent = Number.isNaN(n) ? target : (options.format ? options.format(n) : n.toLocaleString());
  }

  // Hover feedback is handled in CSS now; kept so existing calls don't break.
  function initHoverLift() {}

  return { staggerIn, staggerFadeIn, countUp, initHoverLift };
})();

window.PaimanaFX = PaimanaFX;
