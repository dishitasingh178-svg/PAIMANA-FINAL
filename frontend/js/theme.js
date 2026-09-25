function initThemeToggle() {
  const toggleBtn = document.getElementById('theme-toggle');
  if (!toggleBtn) return;

  const darkIcon = document.getElementById('theme-dark-icon');
  const lightIcon = document.getElementById('theme-light-icon');

  function updateIcons() {
    const isDark = document.documentElement.classList.contains('dark');
    if (darkIcon && lightIcon) {
      if (isDark) {
        darkIcon.classList.add('hidden');
        lightIcon.classList.remove('hidden');
      } else {
        darkIcon.classList.remove('hidden');
        lightIcon.classList.add('hidden');
      }
    }
  }

  // Initial call to set correct icon
  updateIcons();

  toggleBtn.addEventListener('click', () => {
    if (document.documentElement.classList.contains('dark')) {
      document.documentElement.classList.remove('dark');
      localStorage.setItem('theme', 'light');
    } else {
      document.documentElement.classList.add('dark');
      localStorage.setItem('theme', 'dark');
    }
    updateIcons();
    
    // Dispatch event so Chart.js and Leaflet can update if they are on the page
    window.dispatchEvent(new Event('themeChanged'));
  });
}

document.addEventListener('DOMContentLoaded', () => {
  initThemeToggle();
  if (window.lucide) lucide.createIcons();
});