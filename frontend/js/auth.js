/* PAIMANA AI — shared role + mobile navigation helpers */

const PAIMANA_ROLE_KEY = 'paimana_role';

function getRole() {
  const stored = localStorage.getItem(PAIMANA_ROLE_KEY);
  // FIX: Default to 'user' so public visitors don't see admin buttons
  return stored === 'admin' ? 'admin' : 'user'; 
}

function setRole(role) {
  localStorage.setItem(PAIMANA_ROLE_KEY, role === 'admin' ? 'admin' : 'user');
}

function isAdmin() {
  return getRole() === 'admin';
}

function applyRoleToPage() {
  const admin = isAdmin();

  // 1. Elements meant ONLY for admins (Add Project link, Logout buttons)
  document.querySelectorAll('[data-role="admin"]').forEach((el) => {
    if (admin) {
        el.classList.remove('hidden');
        el.style.display = 'flex'; // Force flex to maintain icon alignment
    } else {
        el.classList.add('hidden');
        el.style.display = 'none';
    }
  });

  // 2. Elements meant ONLY for public/users (Login buttons)
  document.querySelectorAll('[data-role="user"]').forEach((el) => {
    if (!admin) {
        el.classList.remove('hidden');
        el.style.display = 'flex';
    } else {
        el.classList.add('hidden');
        el.style.display = 'none';
    }
  });

  document.querySelectorAll('[data-role-label]').forEach((el) => {
    el.textContent = admin ? 'Administrator' : 'Project User';
  });

  document.querySelectorAll('[data-role-greeting]').forEach((el) => {
    el.textContent = admin ? 'Good morning, Administrator.' : 'Good morning, User.';
  });
}

function guardAdminOnlyPage() {
  if (!isAdmin()) {
    window.location.replace('dashboard.html');
  }
}

// Mobile sidebar drawer logic
function initMobileSidebar() {
  const sidebar = document.getElementById('sidebar');
  const toggle = document.getElementById('sidebar-toggle');
  const overlay = document.getElementById('sidebar-overlay');
  if (!sidebar || !toggle || !overlay) return;

  function openSidebar() {
    sidebar.classList.remove('-translate-x-full');
    overlay.classList.remove('hidden');
  }
  function closeSidebar() {
    sidebar.classList.add('-translate-x-full');
    overlay.classList.add('hidden');
  }

  toggle.addEventListener('click', () => {
    const isOpen = !sidebar.classList.contains('-translate-x-full');
    if (isOpen) closeSidebar(); else openSidebar();
  });
  overlay.addEventListener('click', closeSidebar);

  window.addEventListener('resize', () => {
    if (window.innerWidth >= 1024) closeSidebar();
  });
}

window.PaimanaAuth = { getRole, setRole, isAdmin, applyRoleToPage, guardAdminOnlyPage };

document.addEventListener('DOMContentLoaded', () => {
  applyRoleToPage();
  initMobileSidebar();
});
