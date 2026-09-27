/*
 * Tailwind build for the PAIMANA frontend (replaces the Play CDN runtime compiler,
 * which blocked rendering for ~1 s on every page).
 * Same options the pages previously passed to the CDN as `tailwind.config`.
 *
 * After adding or changing Tailwind classes in frontend/*.html or frontend/js/*.js,
 * regenerate the stylesheet (run from the repository root):
 *   npx tailwindcss@3.4.17 -c frontend/tailwind.config.js -i frontend/css/tailwind.input.css -o frontend/css/tailwind.css --minify
 */
module.exports = {
  darkMode: 'class',
  content: ['./frontend/*.html', './frontend/js/*.js'],
  theme: {
    extend: {
      fontFamily: {
        sans: ['"IBM Plex Sans"', 'system-ui', 'sans-serif'],
        mono: ['"IBM Plex Mono"', 'ui-monospace', 'monospace'],
      },
    },
  },
};
