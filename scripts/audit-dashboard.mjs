// Real Chromium DOM regression check. Uses only an audit-owned local CDP tab.
import assert from 'node:assert/strict';
import { writeFile } from 'node:fs/promises';

const tabs = await (await fetch('http://127.0.0.1:9223/json/list')).json();
const tab = tabs.find(t => t.type === 'page');
const ws = new WebSocket(tab.webSocketDebuggerUrl);
await new Promise(resolve => ws.addEventListener('open', resolve, { once: true }));
let id = 0;
const pending = new Map();
ws.addEventListener('message', event => {
  const data = JSON.parse(event.data);
  if (pending.has(data.id)) {
    const { resolve, reject } = pending.get(data.id);
    pending.delete(data.id);
    if (data.error) reject(new Error(JSON.stringify(data.error)));
    else resolve(data.result);
  }
});
function cdp(method, params = {}) {
  return new Promise((resolve, reject) => {
    const callId = ++id;
    pending.set(callId, { resolve, reject });
    ws.send(JSON.stringify({ id: callId, method, params }));
  });
}
async function evaluate(expression) {
  const data = await cdp('Runtime.evaluate', { expression, awaitPromise: true, returnByValue: true });
  if (data.exceptionDetails) throw new Error(JSON.stringify(data.exceptionDetails));
  return data.result.value;
}
const failures = [];
function check(name, callback) {
  try { callback(); console.log(`PASS ${name}`); }
  catch (error) { failures.push(name); console.log(`FAIL ${name}: ${error.message}`); }
}
try {
  await cdp('Page.enable');
  await cdp('Network.enable');
  await cdp('Network.setCacheDisabled', { cacheDisabled: true });
  await cdp('Emulation.setDeviceMetricsOverride', { width: 390, height: 844, deviceScaleFactor: 1, mobile: false });
  await cdp('Page.navigate', { url: 'about:blank' });
  await cdp('Page.navigate', { url: 'http://127.0.0.1:8080/?audit=refresh' });
  await new Promise(resolve => setTimeout(resolve, 2500));
  const state = await evaluate(`(async () => {
    const metrics = await (await fetch('/v1/metrics')).json();
    return {
      title: document.title,
      actualCount: metrics.total_queries,
      shownCount: Number(document.getElementById('metrics-queries-count').textContent),
      strategies: [...document.getElementById('strategy-select').options].map(o => o.value),
      width: innerWidth, contentWidth: document.documentElement.scrollWidth,
      resources: performance.getEntriesByType('resource').map(r => r.name)
    };
  })()`);
  console.log(JSON.stringify(state));
  check('metrics match real API', () => assert.equal(state.shownCount, state.actualCount));
  check('only implemented strategy offered', () => assert.deepEqual(state.strategies, ['heuristic_adaptive']));
  check('390px layout has no horizontal overflow', () => assert.ok(state.contentWidth <= state.width));
  check('page resources are same-origin', () => assert.ok(state.resources.every(url => url.startsWith('http://127.0.0.1:8080/'))));
  // Controlled network outcomes exercise the actual dashboard event handlers and DOM.
  for (const [status, expected] of [[429, 'Busy'], [503, 'Unavailable'], [504, 'Timeout']]) {
    const label = await evaluate(`(async () => {
      const original = window.fetch;
      window.fetch = (url, options) => url === '/v1/query'
        ? Promise.resolve(new Response(JSON.stringify({error:{message:'Controlled diagnostic'}}), {status:${status}, headers:{'Content-Type':'application/json'}}))
        : original(url, options);
      document.getElementById('query-input').value = 'Test question';
      document.getElementById('query-form').dispatchEvent(new Event('submit', {cancelable:true}));
      await new Promise(resolve => setTimeout(resolve, 150));
      window.fetch = original;
      return document.getElementById('answer-status-tag').textContent;
    })()`);
    check(`HTTP ${status} state`, () => assert.equal(label, expected));
  }
  const screenshot = await cdp('Page.captureScreenshot', { format: 'png', captureBeyondViewport: true });
  await writeFile('artifacts/audit-dashboard-390.png', Buffer.from(screenshot.data, 'base64'));
} finally { ws.close(); }
if (failures.length) process.exitCode = 1;
