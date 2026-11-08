'use strict';
// Persistent, JSONL browser worker. Only operator-defined capabilities are executable.
const fs = require('fs');
const path = require('path');
const http = require('http');
const crypto = require('crypto');
const readline = require('readline');
const sha = bytes => crypto.createHash('sha256').update(bytes).digest('hex');
const sameJson = (a,b) => {
  if (a === null || b === null || typeof a !== 'object' || typeof b !== 'object') return a === b;
  if (Array.isArray(a) !== Array.isArray(b)) return false;
  const ka = Object.keys(a).sort(), kb = Object.keys(b).sort();
  return JSON.stringify(ka) === JSON.stringify(kb) && ka.every(k => sameJson(a[k],b[k]));
};
function boundedFetch(req, timeout) {
  return new Promise((resolve,reject) => {
    const body = req.postData();
    const headers = {Accept:'*/*'};
    if (body !== null) { headers['Content-Type']='application/json'; headers['Content-Length']=Buffer.byteLength(body); }
    let finished = false;
    const finish = (error, result) => { if (finished) return; finished = true; clearTimeout(timer); error ? reject(error) : resolve(result); };
    const outgoing = http.request(req.url(), {method:req.method(),headers,agent:false}, response => {
      if (response.statusCode >= 300 && response.statusCode < 400) {
        response.destroy(); outgoing.destroy(); finish(new Error('Redirect blocked')); return;
      }
      let size=0; const chunks=[];
      response.on('data',chunk => {
        size += chunk.length;
        if(size>262144) { response.destroy(); outgoing.destroy(); finish(new Error('Response byte budget exceeded')); }
        else chunks.push(chunk);
      });
      response.on('end',()=>finish(null,{status:response.statusCode,headers:Object.fromEntries(
        Object.entries(response.headers).filter(([k,v]) => ['content-type','cache-control'].includes(k) && typeof v === 'string')),
        body:Buffer.concat(chunks)}));
      response.on('error', error => finish(error));
    });
    const timer=setTimeout(()=>{outgoing.destroy();finish(new Error('Request time budget exceeded'));},timeout);
    outgoing.on('error', error => finish(error));
    if(body!==null) outgoing.write(body);
    outgoing.end();
  });
}
let browser, context, page, auth, config, dir, tracePath;
let closed=false, initialized=false, failed=false, armed=null, requestCount=0, events=0, sequence=0;
const observations=[], steps=[], network=[], uses=Object.create(null);
function trace(type,data={}) {
  if (!tracePath) return;
  if(events>=400) {failed=true; return;}
  fs.appendFileSync(tracePath,JSON.stringify({...data,index:++events,type})+'\n');
}
function block(reason) { failed=true; trace('blocked',{reason}); }
async function cleanup() {
  if(closed) return;
  closed=true;
  const errors=[];
  if(context) { try { await context.close(); } catch(error) { errors.push(String(error)); } }
  if(browser) { try { await browser.close(); } catch(error) { errors.push(String(error)); } }
  trace('closed');
  if(errors.length) throw new Error('Browser cleanup failed: '+errors.join('; '));
}
for(const signal of ['SIGTERM','SIGINT']) process.on(signal,()=>{
  const timer=setTimeout(()=>process.exit(143),5000);
  cleanup().finally(()=>{clearTimeout(timer);process.exit(143);});
});
async function initialize(input) {
  if(initialized) throw new Error('Already initialized');
  initialized=true; auth=input.authorization; config=input.config || {};
  const origin=new URL(auth.origin);
  if(origin.protocol!=='http:' || !['127.0.0.1','[::1]'].includes(origin.hostname) || !origin.port || origin.origin!==auth.origin)
    throw new Error('Only exact numerical loopback origins are permitted');
  dir=path.resolve(input.output_dir); fs.mkdirSync(dir,{recursive:true});
  tracePath=path.join(dir,'trace.jsonl'); fs.writeFileSync(tracePath,'');
  const playwright=require(config.playwright_module || 'playwright');
  const options={headless:config.headless!==false,chromiumSandbox:true,timeout:20000};
  if(config.executable_path) options.executablePath=config.executable_path;
  else if(fs.existsSync('/usr/bin/chromium')) options.executablePath='/usr/bin/chromium';
  browser=await playwright.chromium.launch(options);
  context=await browser.newContext({viewport:{width:1100,height:800},serviceWorkers:'block',acceptDownloads:false,permissions:[]});
  page=await context.newPage(); page.setDefaultTimeout(config.timeout_ms || 8000);
  page.on('dialog', dialog=>{block('dialog');dialog.dismiss().catch(()=>{});});
  page.on('download', download=>{block('download');download.cancel().catch(()=>{});});
  context.on('page', other=>{if(other!==page){block('popup');other.close().catch(()=>{});}});
  page.on('framenavigated',frame=>{if(frame===page.mainFrame() && frame.url()!=='about:blank') {
    try {if(new URL(frame.url()).origin!==auth.origin) {block('navigation outside origin');page.close().catch(()=>{});}}
    catch(_){block('invalid navigation');}
  }});
  if(typeof context.routeWebSocket!=='function') throw new Error('Playwright >=1.48 is required');
  await context.routeWebSocket('**/*',ws=>{block('websocket');ws.close();});
  await context.route('**/*',async route=>{
    const req=route.request(); let allowed=false; let grant=null;
    requestCount++;
    try {
      const url=new URL(req.url()); const target=url.pathname+url.search;
      const same=!failed && events<390 && requestCount<=80 && req.frame()===page.mainFrame()
        && url.origin===auth.origin && !url.username && !url.password && !url.hash;
      if(same && req.method()==='GET' && req.postData()===null && auth.get_paths.includes(target)) allowed=true;
      if(same && armed && req.method()===armed.method && target===armed.path && (req.postData()||'').length<=1024
        && sameJson(req.postDataJSON(),armed.json)) { allowed=true;grant=armed;armed=null; }
    } catch(_) {}
    const record={method:req.method(),url:req.url().slice(0,500),allowed};
    if(network.length<80) network.push(record);
    trace('request',record);
    if(!allowed) {block('request outside capabilities or budget');await route.abort('blockedbyclient');return;}
    try {
      const response=await boundedFetch(req,config.timeout_ms || 8000);
      if(grant) trace('mutation_response',{status:response.status});
      await route.fulfill(response);
    } catch(error) {block(String(error).slice(0,500));await route.abort('failed').catch(()=>{});}
  });
  trace('initialized',{origin:auth.origin});
  return {ready:true,runtime:{node:process.version,browser:browser.version(),platform:process.platform}};
}
async function probeValue(probe) {
  const locator=page.getByTestId(probe.test_id);
  const count=await locator.count();
  if(probe.kind==='count') return count;
  if(count!==1) return null;
  const value=probe.kind==='value' ? await locator.inputValue() : (await locator.innerText()).trim();
  if(value.length>4000) throw new Error('Probe text byte budget exceeded');
  return value;
}
async function waitForProbe(wait) {
  const deadline=Date.now()+(config.timeout_ms || 8000);
  while(Date.now()<deadline) {
    if(failed) throw new Error('Browser boundary was violated');
    if(await probeValue(auth.probes[wait.probe])===wait.equals) return;
    await new Promise(resolve=>setTimeout(resolve,30));
  }
  throw new Error('Action acknowledgment probe timed out');
}
async function act(id) {
  if(!initialized || closed || failed || !Object.prototype.hasOwnProperty.call(auth.actions,id)) throw new Error('Action is not available');
  const action=auth.actions[id];
  const limit=action.max_uses || (action.request?1:2);
  if((uses[id] || 0)>=limit || sequence>=(auth.budgets?.max_steps || 12)) throw new Error('Action/step budget exceeded');
  if(page.url()==='about:blank' && action.kind!=='navigate') throw new Error('Navigate to an approved page before other actions');
  uses[id]=(uses[id] || 0)+1; sequence++;
  const step={index:sequence,action_id:id,status:'started'}; steps.push(step); trace('action_started',step);
  try {
    let waiter;
    if(action.request) {
      armed=action.request;
      waiter=page.waitForResponse(r=>r.url()===auth.origin+action.request.path && r.request().method()===action.request.method);
      waiter.catch(()=>{});
    }
    if(action.kind==='navigate') {
      const response=await page.goto(auth.origin+action.path,{waitUntil:'domcontentloaded'});
      if(!response || !response.ok()) throw new Error('Navigation unavailable: HTTP '+(response?response.status():'unknown'));
    } else if(action.kind==='reload') {
      const response=await page.reload({waitUntil:'domcontentloaded'});
      if(!response || !response.ok()) throw new Error('Reload unavailable: HTTP '+(response?response.status():'unknown'));
    } else if(action.kind==='click') await page.getByTestId(action.test_id).click();
    else if(action.kind==='fill') await page.getByTestId(action.test_id).fill(action.value);
    else if(action.kind==='select') await page.getByTestId(action.test_id).selectOption(action.value);
    else if(action.kind!=='observe') throw new Error('Unsupported action kind');
    if(waiter) {
      const response=await waiter;
      if(armed || response.status()>=500) throw new Error('Authorized mutation did not complete');
    }
    armed=null;
    if(action.wait_for) await waitForProbe(action.wait_for);
    if(failed || events>=390 || requestCount>80) throw new Error('Browser capability/budget boundary was violated');
    const url=new URL(page.url());
    if(url.origin!==auth.origin || !auth.get_paths.includes(url.pathname+url.search)) throw new Error('Observed page outside approved read paths');
    const values={};
    for(const [key,probe] of Object.entries(auth.probes)) values[key]=await probeValue(probe);
    const observationId=`obs-${String(sequence).padStart(4,'0')}`;
    const screenshot=observationId+'.png';
    const bytes=await page.screenshot({path:path.join(dir,screenshot),fullPage:false});
    const observation={id:observationId,after_action:id,url:page.url(),values,screenshot,screenshot_sha256:sha(bytes),
      visible_text:(await page.locator('body').innerText()).slice(0,6000)};
    // Late callbacks cannot turn a blocked action into a successful observation.
    if(failed) throw new Error('Browser boundary was violated during observation');
    observations.push(observation);step.status='completed';step.observation_id=observationId;
    trace('observation',observation);trace('action_completed',step);
    return {observation,step};
  } catch(error) {
    armed=null;failed=true;step.status='failed';trace('action_failed',{action_id:id,error:String(error).slice(0,1000)});throw error;
  }
}
async function command(message) {
  if(message.command==='init') return initialize(message);
  if(message.command==='act') return act(message.action_id);
  if(message.command==='close') {
    await cleanup();
    return {observations,steps,network,completed:!failed,trace:'trace.jsonl',trace_sha256:sha(fs.readFileSync(tracePath))};
  }
  throw new Error('Unsupported worker command');
}
async function main() {
  const lines=readline.createInterface({input:process.stdin,crlfDelay:Infinity});
  for await(const line of lines) {
    if(line.length>65536) throw new Error('Worker command byte budget exceeded');
    try {const result=await command(JSON.parse(line)); process.stdout.write(JSON.stringify({ok:true,result})+'\n');}
    catch(error) {failed=true;process.stdout.write(JSON.stringify({ok:false,error:String(error).slice(0,1500)})+'\n');}
    if(closed) break;
  }
  await cleanup();
}
main().catch(error=>{process.stderr.write(String(error));process.exitCode=2;cleanup().catch(()=>{});});
