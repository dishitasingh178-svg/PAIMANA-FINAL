const {test}=require('node:test'), assert=require('node:assert/strict');
const fs=require('node:fs'), vm=require('node:vm'), path=require('node:path');
const U=require('../frontend/js/warning-ui.js');
const settle=()=>new Promise(r=>setImmediate(r));
function deferred(){let resolve,reject;const promise=new Promise((a,b)=>{resolve=a;reject=b;});return {promise,resolve,reject};}
function page(initial=[{project_id:'p1',project_name:'Project One',status:'NEW',alert_type:'ML_RISK_WARNING',priority_score:81,priority_label:'IMMEDIATE',signal_count:3}]){
  const elements=new Map(), calls={cases:0,summary:0,priority:0};
  let data=initial, override=null;
  function el(id){if(!elements.has(id))elements.set(id,{innerHTML:'',textContent:'',listeners:{},hidden:false,disabled:false,querySelectorAll:()=>[],setAttribute(){},addEventListener(k,v){this.listeners[k]=v;}});return elements.get(id);}
  const API={
    getAlertCases:query=>{calls.cases++;if(override)return override(query);return Promise.resolve(data.filter(c=>!query.status || c?.status===query.status || c?.status==null));},
    getAlertSummary:()=>{calls.summary++;const summary={};for(const s of ['NEW','ACKNOWLEDGED','UNDER_REVIEW','RESOLVED','DISMISSED'])summary[s.toLowerCase()]=data.filter(c=>c?.status===s).length;summary.immediate=0;return Promise.resolve(summary);},
    getPriorityAlerts:()=>{calls.priority++;return Promise.resolve(data.filter(c=>!['RESOLVED','DISMISSED'].includes(c?.status)));},
    updateProjectAlertStatus:(id,status,note)=>{data=data.map(c=>c?.project_id===id?{...c,status,workflow_status:status,review_note:note,status_updated_at:'2026-09-26T10:00:00Z'}:c);return Promise.resolve(data.find(c=>c.project_id===id));}
  };
  vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../frontend/js/early-warnings.js'),'utf8'),{window:{WarningUI:U},API,document:{getElementById:el},location:{search:''},URLSearchParams});
  return {el,calls,setList:f=>override=f,
    tab:name=>el('alert-filters').listeners.click({target:{closest:()=>({dataset:{filter:name}})}}),
    refresh:()=>el('refresh-warnings').listeners.click(),
    act:(status,note='Officer note')=>el('alerts-container').listeners.click({target:{closest:()=>({dataset:{status},closest:()=>({dataset:{projectId:'p1'},querySelectorAll:()=>[],querySelector:()=>({value:note})})})}})
  };
}

test('legacy missing fields and malformed records cannot crash rendering',async()=>{
  const p=page([null,{}, {project_id:'p1',project_name:'Legacy',alert_class:undefined,priority_label:null,evidence:null,review_note:undefined}, {project_id:'p2',evidence:[null,4,{}],alert_type:7,underlying_signals:[null,{}]}]);
  await settle();
  const html=p.el('alerts-container').innerHTML;
  assert.match(html,/Legacy/);assert.match(html,/data-project-id="p2"/);
  assert.doesNotMatch(html,/undefined|NaN|\[object Object\]/);
  assert.equal(U.normalize({is_resolved:true}).workflow_status,'RESOLVED');
  assert.equal(U.normalize({alert_type:'ML_RISK_WARNING'}).alert_class,'PREDICTIVE');
});

test('project action leaves New, updates counts, and note renders in target queue',async()=>{
  const p=page();await settle();
  await p.act('ACKNOWLEDGED','<script>Testing acknowledgement persistence.</script>');
  assert.doesNotMatch(p.el('alerts-container').innerHTML,/data-project-id="p1"/);
  assert.match(p.el('warning-summary').innerHTML,/data-count="new">0</);
  assert.match(p.el('warning-summary').innerHTML,/data-count="acknowledged">1</);
  p.tab('acknowledged');await settle();
  assert.match(p.el('alerts-container').innerHTML,/Officer Note/);
  assert.match(p.el('alerts-container').innerHTML,/&lt;script&gt;Testing acknowledgement persistence\.&lt;\/script&gt;/);
  for(const [state,tab] of [['UNDER_REVIEW','review'],['RESOLVED','resolved'],['NEW','new'],['DISMISSED','dismissed']]){
    await p.act(state,`Note ${state}`);
    assert.doesNotMatch(p.el('alerts-container').innerHTML,/data-project-id="p1"/);
    p.tab(tab);await settle();assert.match(p.el('alerts-container').innerHTML,new RegExp(`Note ${state}`));
  }
  assert.doesNotMatch(p.el('priority-projects').innerHTML,/Project One/);
});

test('Refresh refetches all panels, preserves queue and coalesces repeated clicks',async()=>{
  const p=page();await settle();await p.act('ACKNOWLEDGED');p.tab('acknowledged');await settle();
  const before={...p.calls}, pending=deferred();p.setList(()=>pending.promise);
  p.refresh();p.refresh();
  assert.equal(p.el('refresh-warnings').disabled,true);
  assert.equal(p.calls.cases,before.cases+1);assert.equal(p.calls.summary,before.summary+1);assert.equal(p.calls.priority,before.priority+1);
  pending.resolve([{project_id:'p1',project_name:'Fresh result',status:'ACKNOWLEDGED'}]);await settle();
  assert.equal(p.el('refresh-warnings').disabled,false);
  assert.match(p.el('alerts-container').innerHTML,/Fresh result/);
  assert.equal((p.el('alerts-container').innerHTML.match(/data-project-id="p1"/g)||[]).length,1);
});

test('API failure removes stale list and restores Refresh',async()=>{
  const p=page();await settle();p.setList(()=>Promise.reject(new Error('offline')));p.refresh();await settle();
  assert.match(p.el('alerts-container').textContent,/Unable to load cases/);
  assert.match(p.el('warning-feedback').textContent,/offline/);
  assert.equal(p.el('refresh-warnings').disabled,false);
});

test('normalization never invents missing numeric metrics',()=>{
  for(const value of [undefined,null,'',NaN,{},true])assert.equal(U.safeNumber(value),null);
  assert.equal(U.fmt(null),'—');assert.deepEqual(U.normalize({}).evidence,[]);
});
