'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');
const api=require('./app.js');
const data=JSON.parse(fs.readFileSync(path.join(__dirname,'demo.json'),'utf8'));
const clone=()=>structuredClone(data);

test('all curated historical cases validate',()=>assert.equal(api.validateData(data),data));
test('fixed app preserves model / final / oracle distinction',()=>{
 const [a,b]=data.cases[0].runs;
 assert.equal(api.proposedLabel(a),'Confirmed');assert.equal(a.verdict,'inconclusive');assert.equal(a.server.expected_verdict,'not_reproduced');
 assert.equal(api.proposedLabel(b),'Facts, not a verdict');assert.equal(b.verdict,'not_reproduced');assert.equal(b.model_assessment.verdict,undefined);
 assert.deepEqual(api.gradeCount(a.grade),{passed:30,total:31});assert.deepEqual(api.gradeCount(b.grade),{passed:31,total:31});
});
test('bug example preserves actual reversion and confirmed final',()=>{
 for(const r of data.cases[1].runs){assert.deepEqual(r.observations.map(o=>o.values.persisted_status),['todo','done','todo']);assert.equal(r.verdict,'confirmed');}
});
test('refusal is not a model or browser trial',()=>{
 for(const r of data.cases[2].runs){assert.equal(r.model_calls.length,0);assert.equal(r.events.length,0);assert.equal(r.observations.length,0);assert.equal(api.proposedLabel(r),'Not called');assert.equal(r.verdict,'inconclusive');}
});
test('deep link round trip keeps only allowlisted state',()=>{
 const state={case:'persistence',view:'candidate',phase:'saved',filter:'network'};
 assert.deepEqual(api.parseState(api.stateHash(state)),state);
 assert.deepEqual(api.parseState('#case=__proto__&view=<script>&phase=unknown&filter=oops'),{case:'fixed',view:'compare',phase:'reloaded',filter:'actions'});
});
test('all event filters preserve original ordering and counts',()=>{
 const events=data.cases[0].runs[0].events;
 assert.equal(api.filterEvents(events,'actions').length,7);assert.equal(api.filterEvents(events,'observations').length,3);assert.equal(api.filterEvents(events,'network').length,10);assert.equal(api.filterEvents(events,'all').length,28);
 for(const f of ['actions','observations','network','all']){const result=api.filterEvents(events,f);assert.deepEqual(result,[...result].sort((a,b)=>a.index-b.index));}
 assert.deepEqual(api.filterEvents([],'all'),[]);
});
test('missing, unknown and stringified grade states fail closed',()=>{
 for(const mutate of [d=>{d.cases[0].runs[0].verdict='success'},d=>{delete d.cases[0].runs[0].grade},d=>{d.cases[0].runs[0].grade.checks[0].passed='false'},d=>{d.cases[0].runs[0].grade.passed=true}]){const d=clone();mutate(d);assert.throws(()=>api.validateData(d));}
 assert.equal(api.verdictLabel('unknown'),'Unknown');
});
test('bad citations, duplicate IDs, reversed trace and overlarge bundle rejected',()=>{
 for(const mutate of [d=>{d.cases[0].runs[0].model_assessment.evidence_ids=['obs-9999']},d=>{d.cases[0].runs[0].observations[1].id='obs-0001'},d=>{d.cases[0].runs[0].events.reverse()},d=>{d.cases[0].runs[0].events=Array(2001).fill({})},d=>{d.cases[1].id=d.cases[0].id}]){const d=clone();mutate(d);assert.throws(()=>api.validateData(d));}
});
test('missing screenshots cannot become verified screenshots',()=>{
 const d=clone();d.cases[0].runs[0].screenshot_status='verified';assert.throws(()=>api.validateData(d));
});
test('classic offline script and download JSON contain identical evidence',()=>{
 const context={window:{}};vm.runInNewContext(fs.readFileSync(path.join(__dirname,'demo-data.js'),'utf8'),context);
 assert.equal(JSON.stringify(context.window.TRACE_DATA),JSON.stringify(data));
});
test('rendering avoids HTML, navigation and network sinks for data',()=>{
 const app=fs.readFileSync(path.join(__dirname,'app.js'),'utf8');
 for(const sink of [/\.innerHTML\b/,/\.outerHTML\b/,/insertAdjacentHTML/,/\beval\s*\(/,/\bfetch\s*\(/,/XMLHttpRequest/,/document\.write\s*\(/,/localStorage/,/sessionStorage/])assert.doesNotMatch(app,sink);
 assert.match(app,/n\.textContent=String\(text\)/);
 const html=fs.readFileSync(path.join(__dirname,'index.html'),'utf8');assert.match(html,/connect-src 'none'/);assert.match(html,/object-src 'none'/);assert.match(html,/base-uri 'none'/);assert.match(html,/form-action 'none'/);assert.doesNotMatch(html,/https?:[^"']+\.(?:js|css)/);
});
test('untrusted-looking text is accepted as text, never treated as verdict',()=>{
 const d=clone();d.cases[0].runs[0].observations[0].visible_text='<script>alert(1)</script><img src=x onerror=alert(1)>';assert.equal(api.validateData(d),d);
});

test('empty check collection cannot yield a passing trial',()=>{const d=clone();d.cases[0].runs[0].grade={passed:true,checks:[]};assert.throws(()=>api.validateData(d));});
