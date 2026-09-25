const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

function deferred() {
  let resolve;
  const promise = new Promise(r => { resolve = r; });
  return { promise, resolve };
}
const settle = () => new Promise(resolve => setImmediate(resolve));

function page() {
  const elements = new Map();
  function element(id) {
    if (!elements.has(id)) elements.set(id, {
      innerHTML: '', textContent: '', value: '', hidden: false, listeners: {},
      querySelectorAll: () => [],
      addEventListener(name, handler) { this.listeners[name] = handler; }
    });
    return elements.get(id);
  }
  const alert = { alert_id: 1, project_id: 'test', project_name: 'Test project',
    alert_type: 'ML_RISK_WARNING', alert_class: 'PREDICTIVE', status: 'NEW',
    severity: 'WATCH', priority_score: 40, evidence: [], data_confidence_reasons: [] };
  let list = () => Promise.resolve([alert]);
  const context = {
    document: { getElementById: element }, location: { search: '' }, URLSearchParams,
    API: {
      getAlerts: () => list(),
      getAlertSummary: () => Promise.resolve({new: 1, immediate: 0, under_review: 0, resolved: 0}),
      getPriorityAlerts: () => Promise.resolve([]),
      updateAlertStatus: (_, status) => Promise.resolve({...alert, status})
    }
  };
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../frontend/js/early-warnings.js'), 'utf8'), context);
  return {
    element,
    setList: handler => { list = handler; },
    filter: name => element('alert-filters').listeners.click({target: {closest: () => ({dataset: {filter: name}})}}),
    act: status => element('alerts-container').listeners.click({target: {closest: () => ({
      dataset: {status}, closest: () => ({dataset: {alertId: '1'}, querySelectorAll: () => []})
    })}})
  };
}

for (const status of ['DISMISSED', 'RESOLVED']) {
  test(`${status} leaves All Active before list refresh completes`, async () => {
    const p = page();
    await settle();
    assert.match(p.element('alerts-container').innerHTML, /data-alert-id="1"/);
    const refresh = deferred();
    p.setList(() => refresh.promise);
    const action = p.act(status);
    await settle();
    assert.doesNotMatch(p.element('alerts-container').innerHTML, /data-alert-id="1"/);
    assert.match(p.element('warning-feedback').textContent, /no longer active/);
    refresh.resolve([]);
    await action;
  });
}

test('Acknowledged leaves New but stays in All Active', async () => {
  const p = page();
  await settle();
  p.filter('new');
  await settle();
  const updated = {alert_id:1,project_id:'test',project_name:'Test project',alert_type:'ML_RISK_WARNING',status:'ACKNOWLEDGED',priority_score:40,evidence:[],data_confidence_reasons:[]};
  p.setList(() => Promise.resolve([updated]));
  await p.act('ACKNOWLEDGED');
  assert.doesNotMatch(p.element('alerts-container').innerHTML, /data-alert-id="1"/);
  p.filter('active');
  await settle();
  assert.match(p.element('alerts-container').innerHTML, /data-alert-id="1"/);
  assert.match(p.element('warning-filter-help').textContent, /Acknowledging starts review/);
});
