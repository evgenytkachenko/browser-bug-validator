'use strict';
// A bounded browser controller. Model/page text never becomes executable code.
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const http = require('http');
let activeBrowser;
for (const signal of ['SIGTERM','SIGINT']) process.on(signal, async () => {
  const fallback = setTimeout(() => process.exit(143), 10000);
  try { if (activeBrowser) await activeBrowser.close(); } finally { clearTimeout(fallback); process.exit(143); }
});
const sha = bytes => crypto.createHash('sha256').update(bytes).digest('hex');
// Native loopback HTTP has no redirects, proxy settings, retries, cookies, or unbounded buffering.
function boundedFetch(request, timeout) {
  return new Promise((resolve, reject) => {
    const body = request.postData();
    const headers = {'Accept': '*/*'};
    if (body !== null) { headers['Content-Type'] = 'application/json'; headers['Content-Length'] = Buffer.byteLength(body); }
    const outgoing = http.request(request.url(), {method: request.method(), headers, agent: false}, response => {
      if (response.statusCode >= 300 && response.statusCode < 400) {
        response.destroy(); outgoing.destroy(); reject(Object.assign(new Error('Redirect blocked'), {code: 'redirect_blocked'})); return;
      }
      const chunks = []; let size = 0;
      response.on('data', chunk => {
        size += chunk.length;
        if (size > 262144) { response.destroy(); outgoing.destroy(); reject(Object.assign(new Error('Response body budget exceeded'), {code: 'response_budget_exceeded'})); }
        else chunks.push(chunk);
      });
      response.on('end', () => resolve({status: response.statusCode,
        headers: Object.fromEntries(Object.entries(response.headers).filter(([key,value]) =>
          !['transfer-encoding','connection','content-length','set-cookie'].includes(key) && typeof value === 'string')),
        body: Buffer.concat(chunks)}));
      response.on('error', reject);
    });
    outgoing.setTimeout(timeout, () => outgoing.destroy(new Error('Network request timed out')));
    outgoing.on('error', reject);
    if (body !== null) outgoing.write(body);
    outgoing.end();
  });
}
async function main(config) {
  const result = {observations: [], steps: [], limitations: [], network: [], completed: false};
  const dir = path.resolve(config.output_dir);
  fs.mkdirSync(dir, {recursive: true});
  const tracePath = path.join(dir, 'trace.jsonl');
  let index = 0;
  let budgetExceeded = false;
  const trace = (type, data = {}) => {
    if (index >= 400) { budgetExceeded = true; return; }
    if (index === 399) { type = 'event_budget_exceeded'; data = {allowed: false}; budgetExceeded = true; }
    let event = {index: ++index, timestamp: new Date().toISOString(), type, ...data};
    let encoded = JSON.stringify(event);
    if (encoded.length > 20000) { event = {index, timestamp: event.timestamp, type: 'oversize_event_blocked', allowed: false, original_type: type}; encoded = JSON.stringify(event); budgetExceeded = true; }
    fs.appendFileSync(tracePath, encoded + '\n'); return event;
  };
  let browser, context;
  let mutationArmed = false;
  let savedResponse = null;
  let forbiddenAttempt = false;
  try {
    const origin = new URL(config.origin);
    if (origin.protocol !== 'http:' || !['127.0.0.1', 'localhost', '[::1]'].includes(origin.hostname) || !origin.port)
      throw new Error('Only explicit loopback origins are permitted');
    if (!/^T-[0-9]{1,6}$/.test(config.task_id) || !['todo','doing','done'].includes(config.expected_status))
      throw new Error('Invalid target or status');
    const exactSelectors = {ready:'board-ready', blocked:'access-blocked', row:`task-row-${config.task_id}`, status:`task-status-${config.task_id}`, save:`save-task-${config.task_id}`, persisted:`persisted-status-${config.task_id}`};
    if (Object.keys(config.selectors).length !== 6 || Object.entries(exactSelectors).some(([key,value]) => config.selectors[key] !== value)) throw new Error('Selectors outside reviewed adapter');
    for (const value of Object.values(config.selectors))
      if (!/^[A-Za-z0-9_-]{1,80}$/.test(value)) throw new Error('Invalid test ID');
    const playwright = require(config.playwright_module || 'playwright');
    const opts = {headless: config.headless !== false, chromiumSandbox: true, timeout: 20000};
    if (config.executable_path) opts.executablePath = config.executable_path;
    else if (fs.existsSync('/usr/bin/chromium')) opts.executablePath = '/usr/bin/chromium';
    browser = await playwright.chromium.launch(opts);
    activeBrowser = browser;
    result.runtime = {node: process.version, platform: process.platform, browser: browser.version()};
    try { result.runtime.playwright = require(path.join(path.dirname(require.resolve(config.playwright_module || 'playwright')), 'package.json')).version; } catch (_) {}
    context = await browser.newContext({viewport: {width: 1100, height: 800}, serviceWorkers: 'block',
      acceptDownloads: false, permissions: []});
    const page = await context.newPage();
    page.setDefaultTimeout(config.timeout_ms || 8000);
    page.on('dialog', dialog => { trace('dialog_dismissed', {kind: dialog.type()}); dialog.dismiss().catch(()=>{}); });
    page.on('download', download => { trace('download_blocked'); download.cancel().catch(()=>{}); });
    context.on('page', other => { if (other !== page) { trace('popup_blocked'); other.close().catch(()=>{}); } });
    page.on('console', msg => trace('console', {level: msg.type(), message: msg.text().slice(0, 1500)}));
    page.on('pageerror', err => trace('page_error', {message: String(err).slice(0,1500)}));
    if (typeof context.routeWebSocket !== 'function') throw new Error('Playwright WebSocket blocking support is required (>=1.48)');
    await context.routeWebSocket('**/*', ws => { forbiddenAttempt = true; trace('websocket_blocked', {url: ws.url()}); ws.close(); });
    let requestCount = 0;
    await context.route('**/*', async route => {
      requestCount += 1;
      const req = route.request();
      let allowed = false;
      let parsed;
      try {
        parsed = new URL(req.url());
        const frame = req.frame();
        const same = !budgetExceeded && requestCount <= 60 && frame === page.mainFrame() && parsed.origin === origin.origin && !parsed.username && !parsed.password && !parsed.search && !parsed.hash;
        if (same && req.method() === 'GET' && ['/', '/api/tasks', '/favicon.ico'].includes(parsed.pathname)) allowed = true;
        if (same && mutationArmed && req.method() === 'POST' && parsed.pathname === `/api/tasks/${config.task_id}/status`) {
          const body = req.postDataJSON();
          if (body && (req.postData() || '').length <= 128 && Object.keys(body).length === 1 && body.status === config.expected_status) {
            allowed = true; mutationArmed = false;
          }
        }
      } catch (_) {}
      trace('network_request', {method: req.method(), url: req.url().slice(0,1500), allowed});
      if (result.network.length < 60) result.network.push({method: req.method(), url: req.url().slice(0,1500), allowed});
      if (!allowed) { forbiddenAttempt = true; return route.abort('blockedbyclient'); }
      // Never follow redirects. Stream into a capped buffer before fulfilling the browser request.
      try {
        const response = await boundedFetch(req, config.timeout_ms || 8000);
        await route.fulfill(response);
      } catch (error) {
        forbiddenAttempt = true;
        trace(error.code || 'network_error', {url: req.url().slice(0,1500), allowed: false, error: String(error).slice(0,1000)});
        await route.abort('failed').catch(()=>{});
      }
    });
    page.on('response', response => trace('network_response', {url: response.url(), status: response.status()}));
    const sel = key => ['status','save','persisted'].includes(key) ? page.getByTestId(config.selectors.row).getByTestId(config.selectors[key]) : page.getByTestId(config.selectors[key]);
    const observation = async phase => {
      const id = `obs-${String(result.observations.length+1).padStart(4,'0')}`;
      const screenshot = `${id}-${phase}.png`;
      const bytes = await page.screenshot({path: path.join(dir, screenshot), fullPage: false});
      const values = {target_task_id: null};
      if (await sel('row').count() === 1) {
        const rowTestId = await sel('row').getAttribute('data-testid');
        const visibleTaskId = (await sel('row').locator('small').innerText()).trim();
        if (rowTestId !== `task-row-${config.task_id}` || visibleTaskId !== config.task_id) throw new Error('Rendered row identity does not match authorized target');
        values.target_task_id = visibleTaskId;
      }
      if (await sel('status').count() === 1) values.selected_status = await sel('status').inputValue();
      if (await sel('persisted').count() === 1) values.persisted_status = (await sel('persisted').innerText()).trim();
      const item = {id, phase, url: page.url(), screenshot, screenshot_sha256: sha(bytes),
        visible_text: (await page.locator('body').innerText()).slice(0, 12000), values};
      result.observations.push(item); trace('observation', item); return id;
    };
    const step = async (action, fn) => {
      const record = {index: result.steps.length+1, action, status: 'started', observation_ids: []};
      result.steps.push(record); trace('action_started', {action});
      try { const id = await fn(); if (typeof id === 'string' && id.startsWith('obs-')) record.observation_ids.push(id);
        record.status = 'completed'; trace('action_completed', {action, observation_ids: record.observation_ids});
      } catch (e) { record.status = 'failed'; trace('action_failed', {action, error: String(e).slice(0,1500)}); throw e; }
    };
    await step('navigate', async () => {
      const response = await page.goto(origin.origin + '/', {waitUntil:'domcontentloaded'});
      if (!response || response.status() >= 400) {
        await observation('blocked'); throw new Error(`App unavailable: HTTP ${response ? response.status() : 'unknown'}`);
      }
      if (await sel('blocked').count()) { await observation('blocked'); throw new Error('Access denied; do not infer absence of bug'); }
      await sel('ready').waitFor({state:'visible'});
      await sel('row').waitFor({state:'visible'});
    });
    await step('observe_initial', () => observation('initial'));
    const initial = result.observations.at(-1).values;
    if (!initial.persisted_status || initial.persisted_status === config.expected_status)
      throw new Error('Initial state does not permit the requested status-change reproduction');
    await step('select_status', () => sel('status').selectOption(config.expected_status));
    await step('save', async () => {
      mutationArmed = true;
      const waiter = page.waitForResponse(r => r.url() === origin.origin + `/api/tasks/${config.task_id}/status` && r.request().method() === 'POST');
      waiter.catch(() => {}); // Keep a click failure from leaving an unhandled timeout promise.
      await sel('save').click();
      savedResponse = await waiter;
      mutationArmed = false;
      if (!savedResponse.ok()) throw new Error(`Save blocked: HTTP ${savedResponse.status()}`);
      // Wait for the observable UI, not an arbitrary sleep.
      await page.waitForFunction(({id,status}) => document.querySelector(`[data-testid="${id}"]`)?.textContent.trim() === status,
        {id: config.selectors.persisted, status: config.expected_status});
    });
    await step('observe_saved', () => observation('saved'));
    await step('reload', async () => {
      const response = await page.reload({waitUntil:'domcontentloaded'});
      if (!response || !response.ok()) throw new Error('Reload did not return a successful document');
      await sel('ready').waitFor({state:'visible'});
      await sel('row').waitFor({state:'visible'});
    });
    await step('observe_reloaded', () => observation('reloaded'));
    if (budgetExceeded || requestCount > 60) throw new Error('Browser event/request budget exceeded');
    result.completed = true;
    if (forbiddenAttempt) result.limitations.push('The page attempted a request outside the fixture capability boundary; it was blocked.');
  } catch (err) {
    result.limitations.push(`${err.name || 'Error'}: ${String(err.message || err).slice(0,2500)}`);
    trace('execution_error', {error: result.limitations.at(-1)});
  } finally {
    if (context) await context.close().catch(e => result.limitations.push('Context cleanup failed: ' + String(e)));
    if (browser) await browser.close().catch(e => result.limitations.push('Browser cleanup failed: ' + String(e)));
    trace('execution_finished', {completed: result.completed});
    result.trace = 'trace.jsonl';
    result.trace_sha256 = sha(fs.readFileSync(tracePath));
  }
  return result;
}
let input = '';
process.stdin.setEncoding('utf8');
process.stdin.on('data', data => { input += data; if(input.length > 1024*1024) { process.stderr.write('Input too large'); process.exit(2); } });
process.stdin.on('end', () => { Promise.resolve().then(() => main(JSON.parse(input))).then(r => process.stdout.write(JSON.stringify(r))).catch(e => {process.stderr.write(String(e)); process.exitCode=2;}); });
