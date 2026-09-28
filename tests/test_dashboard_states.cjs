const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const html = fs.readFileSync(path.join(__dirname, '../frontend/dashboard.html'), 'utf8');
const geo = JSON.parse(fs.readFileSync(path.join(__dirname, '../frontend/data/india-states.json'), 'utf8'));
function runtime() {
  const elements = new Map();
  const $ = id => {
    if (!elements.has(id)) elements.set(id, {innerHTML:'', textContent:'', setAttribute(){}, querySelectorAll(){return [];}});
    return elements.get(id);
  };
  const context = {geo, console, num:Number, fmt:{int:String, crore:String, date:String},
    localStorage:{getItem:()=>null}, $, esc:s=>String(s).replace(/</g,'&lt;')};
  vm.createContext(context);
  const start=html.indexOf('    const norm =');
  const end=html.indexOf('    const metricMax');
  vm.runInContext(html.slice(start,end),context);
  vm.runInContext(`globalThis.aggregate=aggregateStates; globalThis.display=displayName;`,context);
  return {context,elements};
}
function row(state) {return {state,projects:1,ongoing:1,ongoing_latest_cost_crore:100,latest_cost_crore:100,high_risk:1,ongoing_high_risk:1,critical:0,risk_exposure_crore:50,ongoing_unscored:0};}
test('malformed source strings never become geographic states or joined labels',()=>{
  const {context}=runtime();
  const result=context.aggregate(geo,{data:[row('BIHAR'),row('bihar'),row('BIHAR 02/2008 7'),row('BIHAR 0/0'),row('UNRECOGNIZED')]});
  assert.equal(result.agg.get('BIHAR').projects,2);
  assert.equal(result.off.other.length,3);
  assert.equal(context.display(result.agg.get('BIHAR')),'Bihar');
  assert.equal(context.display({name:'Bihar',parts:Array(100).fill(row('BIHAR 02/2008 7'))}),'Bihar');
});
test('actual summary renderer stays concise and explicitly reports unmapped projects',()=>{
  const {context,elements}=runtime();
  context.summary={data:[row('BIHAR'),row('bihar'),row('BIHAR 02/2008 7')],ongoing_definition:'Reported dates.',as_of:'2026-09-28'};
  vm.runInContext(`summaryMeta=summary; stateMeta=aggregateStates(geo,summary); stateAgg=stateMeta.agg; metric='high';
    function stateLabel(a){return displayName(a);} function metricMax(){return 2;} function restyleStates(){} function wirePathA11y(){}`,context);
  const start=html.indexOf('    function renderMetricViews()');
  const end=html.indexOf('    const metricSelect',start);
  vm.runInContext(html.slice(start,end)+';renderMetricViews();',context);
  const text=elements.get('heat-sum').innerHTML;
  assert.match(text,/highest reported: <b>Bihar<\/b>/);
  assert.ok(text.length<200);
  assert.ok(!text.includes('02/2008'));
  assert.match(elements.get('state-foot').textContent,/unrecognised\/unmapped states: 1 projects/);
});
test('historical shared UT outline remains grouped without leaking raw labels',()=>{
 const {context}=runtime(); const result=context.aggregate(geo,{data:[row('LADAKH'),row('JAMMU & KASHMIR')]});
 assert.equal(result.agg.get('JAMMU AND KASHMIR').projects,2);
 assert.ok(context.display(result.agg.get('JAMMU AND KASHMIR')).length<80);
});
