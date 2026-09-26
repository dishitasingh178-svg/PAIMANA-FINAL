document.addEventListener('DOMContentLoaded', async () => {
  const container=document.getElementById('project-warnings'), U=window.WarningUI;
  const id=new URLSearchParams(location.search).get('id');
  if(!container)return;
  if(!id){container.textContent='Select a project to view warnings.';return;}
  document.getElementById('project-warning-link').href=`early-warnings.html?project_id=${encodeURIComponent(id)}`;
  try {
    const cases=U.safeArray(await API.getAlertCases({project_id:id,include_closed:true})).map(U.normalize).filter(Boolean);
    container.replaceChildren();
    if(!cases.length)container.textContent='No warnings in this queue.';
    for(const item of cases){
      const row=document.createElement('div'), title=document.createElement('strong'), reason=document.createElement('p');
      title.textContent=`Priority ${U.fmt(item.priority_score)} (${item.priority_label}) · ${item.severity} · ${U.humanize(item.workflow_status)}`;
      reason.textContent=item.what_changed;
      row.append(title,reason);
      if(item.review_note){const note=document.createElement('p');note.textContent=`Officer Note: ${item.review_note} · Updated: ${U.date(item.status_updated_at)}`;row.append(note);}
      container.append(row);
    }
  } catch(_){container.textContent='Unable to load the warning case. Open the Early Warning Center to retry.';}
});
