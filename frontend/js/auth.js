/* PAIMANA AI — shared role + mobile navigation helpers
   ---------------------------------------------------------------
   This demo has no backend authentication, so "role" is a light
   client-side concept set on the login screen and stored in
   localStorage. It drives two things:
     1. Hiding admin-only nav items (e.g. "Add Project") for a
        "Project User" session.
     2. The mobile slide-in sidebar drawer (shared across pages).
   Load this AFTER theme.js on every internal page. */

const PAIMANA_ROLE_KEY = 'paimana_role';

function getRole() {
  const stored = localStorage.getItem(PAIMANA_ROLE_KEY);
  return stored === 'user' ? 'user' : 'admin'; // default: admin
}

function setRole(role) {
  localStorage.setItem(PAIMANA_ROLE_KEY, role === 'user' ? 'user' : 'admin');
}

function isAdmin() {
  return getRole() === 'admin';
}

// Hide admin-only elements and sync any role-labelled text on the page.
function applyRoleToPage() {
  const admin = isAdmin();

  document.querySelectorAll('[data-role="admin"]').forEach((el) => {
    el.classList.toggle('hidden', !admin);
  });

  document.querySelectorAll('[data-role-label]').forEach((el) => {
    el.textContent = admin ? 'Administrator' : 'Project User';
  });

  document.querySelectorAll('[data-role-greeting]').forEach((el) => {
    el.textContent = admin ? 'Good morning, Administrator.' : 'Good morning.';
  });
}

// Call at the top of any page that must stay Administrator-only
// (e.g. Add Project) so a Project User session bounces to the dashboard.
function guardAdminOnlyPage() {
  if (!isAdmin()) {
    window.location.replace('dashboard.html');
  }
}

// Mobile sidebar: off-canvas drawer under the lg breakpoint, shared markup:
//   <button id="sidebar-toggle"> in the header
//   <aside id="sidebar">          the nav drawer
//   <div id="sidebar-overlay">    backdrop, closes drawer on click
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

  // If the window is resized up into the desktop layout, reset drawer state
  window.addEventListener('resize', () => {
    if (window.innerWidth >= 1024) closeSidebar();
  });
}

window.PaimanaAuth = { getRole, setRole, isAdmin, applyRoleToPage, guardAdminOnlyPage };

document.addEventListener('DOMContentLoaded', () => {
  applyRoleToPage();
  initMobileSidebar();
});
