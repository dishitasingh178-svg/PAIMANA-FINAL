document.addEventListener('DOMContentLoaded', async () => {
  const container = document.getElementById('project-warnings');
  const id = new URLSearchParams(location.search).get('id');
  if (!id) { container.textContent = 'Select a project to view warnings.'; return; }
  document.getElementById('project-warning-link').href = `early-warnings.html?project_id=${encodeURIComponent(id)}`;
  try {
    const alerts = await API.getAlerts({project_id:id, limit:5});
    container.replaceChildren();
    if (!alerts.length) container.textContent = 'No active warnings require attention.';
    for (const alert of alerts) {
      const row = document.createElement('div');
      row.className = 'border-b border-slate-200 dark:border-slate-700 pb-2';
      const title = document.createElement('strong');
      title.textContent = `Priority ${alert.priority_score} (${alert.priority_label}) · ${alert.severity} · ${alert.alert_type} · ${alert.status}`;
      const reason = document.createElement('p');
      reason.textContent = alert.what_changed;
      row.append(title, reason);
      container.append(row);
    }
  } catch (_) { container.textContent = 'Unable to load early warnings. Open the Early Warning Center to retry.'; }
});
