/* No dependencies, network, HTML interpolation, or model calls. Evidence is text. */
(function () {
  'use strict';
  const VIEWS = ['compare', 'baseline', 'candidate'];
  const PHASES = ['initial', 'saved', 'reloaded'];
  const FILTERS = ['actions', 'observations', 'network', 'all'];
  const VERDICTS = ['confirmed', 'not_reproduced', 'inconclusive'];
  const EVENT_TYPES = ['action_started', 'action_completed', 'network_request', 'network_response', 'observation', 'execution_finished'];
  const LABELS = {confirmed:'Confirmed', not_reproduced:'Not reproduced', inconclusive:'Inconclusive'};
  const DEFAULT = {case:'fixed', view:'compare', phase:'reloaded', filter:'actions'};
  const CHECK_LABELS = {
    verdict_matches_private_oracle:'Final verdict matches fixture oracle',
    independent_save_observed:'Save independently observed', independent_reload_observed:'Reload independently observed',
    independent_final_state:'Independent final server state', server_request_scope:'Server requests within scope',
    unrelated_task_unchanged:'Unrelated task unchanged', evidence_files_and_hashes:'Evidence files and hashes (historical)',
    controller_trace_hash:'Controller trace hash (historical)', controller_no_unsafe_attempts:'No unsafe controller attempts',
    observations_bound_to_controller:'Observations bound to controller', required_public_workflow_completed:'Required workflow completed',
  };
  const HIGHLIGHT_CHECKS = ['verdict_matches_private_oracle', 'independent_save_observed', 'independent_reload_observed', 'independent_final_state', 'controller_no_unsafe_attempts'];
  function ensure(condition, message) { if (!condition) throw new Error(message); }
  function object(v) { return v !== null && typeof v === 'object' && !Array.isArray(v); }
  function textValue(v, max=20000) { return typeof v === 'string' && v.length <= max; }
  function array(v, max) { return Array.isArray(v) && v.length <= max; }
  function validateData(data) {
    ensure(object(data) && data.schema_version === 1, 'Unsupported evidence schema');
    ensure(array(data.cases, 20) && data.cases.length > 0, 'Missing cases');
    ensure(object(data.comparability), 'Missing comparison provenance');
    const caseIds = new Set();
    for (const c of data.cases) {
      ensure(object(c) && /^[a-z0-9-]{1,40}$/.test(c.id) && !caseIds.has(c.id), 'Invalid or duplicate case ID'); caseIds.add(c.id);
      for (const k of ['title','headline','lesson']) ensure(textValue(c[k]), 'Missing case description');
      ensure(array(c.runs,2) && c.runs.length===2, 'Two recorded versions are required');
      for (const r of c.runs) {
        ensure(object(r) && VERDICTS.includes(r.verdict), 'Unknown final verdict');
        for (const k of ['agent_version','backend','summary','trial_id','started_at']) ensure(textValue(r[k]), 'Invalid report field');
        ensure(Number.isFinite(r.elapsed_seconds) && r.elapsed_seconds>=0, 'Invalid run duration');
        ensure(object(r.bug) && textValue(r.bug.title) && textValue(r.bug.description), 'Invalid bug report');
        ensure(array(r.observations,200) && array(r.events,2000) && array(r.steps,200) && array(r.model_calls,200), 'Oversized or missing trace');
        const ids=new Set();
        for (const o of r.observations) {
          ensure(object(o) && /^obs-\d{4}$/.test(o.id) && !ids.has(o.id) && PHASES.includes(o.phase), 'Invalid observation'); ids.add(o.id);
          ensure(object(o.values) && textValue(o.visible_text), 'Invalid observation text');
        }
        for (const e of r.events) ensure(object(e) && Number.isInteger(e.index) && EVENT_TYPES.includes(e.type), 'Invalid controller event');
        ensure(r.events.every((e,i)=>e.index===i+1), 'Unordered controller events');
        ensure(object(r.grade) && typeof r.grade.passed==='boolean' && array(r.grade.checks,200) && r.grade.checks.length > 0, 'Missing historical grades');
        ensure(r.grade.checks.every(c=>object(c) && textValue(c.name) && typeof c.passed==='boolean'), 'Invalid historical check result');
        ensure(r.grade.passed===r.grade.checks.every(c=>c.passed), 'Historical aggregate contradicts checks');
        if (r.model_assessment) {
          ensure(object(r.model_assessment) && textValue(r.model_assessment.explanation), 'Invalid model output');
          ensure(array(r.model_assessment.evidence_ids,200) && r.model_assessment.evidence_ids.every(id=>ids.has(id)), 'Unresolved model citation');
          if ('verdict' in r.model_assessment) ensure(VERDICTS.includes(r.model_assessment.verdict), 'Unknown proposed verdict');
        }
        ensure(object(r.server) && object(r.source_hashes), 'Missing independent provenance');
        ensure(r.screenshot_status === 'not_included_not_visually_verified', 'Unsupported screenshot claim');
      }
    }
    return data;
  }
  function parseState(hash, ids=['fixed','persistence','missing-target']) {
    const p = new URLSearchParams(String(hash).replace(/^#/,''));
    return {case:ids.includes(p.get('case'))?p.get('case'):ids[0], view:VIEWS.includes(p.get('view'))?p.get('view'):DEFAULT.view, phase:PHASES.includes(p.get('phase'))?p.get('phase'):DEFAULT.phase, filter:FILTERS.includes(p.get('filter'))?p.get('filter'):DEFAULT.filter};
  }
  function stateHash(s) { return '#' + new URLSearchParams(s).toString(); }
  function filterEvents(events, filter) {
    return events.filter(e=>filter==='all'||(filter==='actions' && e.type==='action_completed')||(filter==='observations' && e.type==='observation')||(filter==='network' && e.type.startsWith('network_')));
  }
  function gradeCount(grade) { return {passed:grade.checks.filter(c=>c.passed===true).length,total:grade.checks.length}; }
  function verdictLabel(value) { return LABELS[value] || 'Unknown'; }
  function proposedLabel(run) { if (!run.model_assessment) return 'Not called'; return run.model_assessment.verdict ? verdictLabel(run.model_assessment.verdict) : 'Facts, not a verdict'; }
  function literal(value) { return typeof value==='string'?value:JSON.stringify(value,null,2); }
  function humanize(v) { return String(v).replaceAll('_',' ').replace(/^./,c=>c.toUpperCase()); }
  const api = {validateData,parseState,stateHash,filterEvents,gradeCount,verdictLabel,proposedLabel};
  if (typeof module !== 'undefined' && module.exports) module.exports=api;
  if (typeof document === 'undefined') return;
  function el(tag, text, className) { const n=document.createElement(tag); if(text!==undefined && text!==null)n.textContent=String(text); if(className)n.className=className; return n; }
  function append(n,...children) { children.forEach(c=>{if(c)n.append(c);}); return n; }
  function scrollRegion(node,label) {node.tabIndex=0;node.setAttribute('role','region');node.setAttribute('aria-label',label);return node;}
  function byId(id) {return document.getElementById(id);}
  function chip(text,tone='neutral') {return el('span',text,'chip '+tone);}
  function button(text, attrs={}, className='') {const b=el('button',text,className); b.type='button'; for(const [k,v] of Object.entries(attrs)) b.setAttribute(k,String(v));return b;}
  let data,state,pendingEvidence;
  function commit(patch) {const next={...state,...patch}; const hash=stateHash(next); if(location.hash!==hash)location.hash=hash; else render();}
  function cite(id,runIndex,context='model') {
    return button(id,{'data-observation':id,'data-run':runIndex,'data-key':`cite-${runIndex}-${id}-${context}`,'aria-label':`Inspect ${id} in v0.${runIndex+2}`},'citation');
  }
  function renderModel(r,i) {
    const panel=el('section',null,'panel'); panel.setAttribute('aria-label','Model output and final report');
    const top=el('div',null,'panel-top');append(top,el('p','02 / MODEL OUTPUT','panel-label'));
    const row=append(el('div',null,'verdict-row'),el('h4',proposedLabel(r)),chip(r.model_assessment?(r.model_assessment.verdict?'Proposed verdict':'Extracted facts'):'No inference',r.model_assessment?.verdict==='confirmed' && r.verdict==='inconclusive'?'fail':'neutral'));append(top,row);
    append(top,el('p',r.model_assessment?.explanation||'Required input was missing. The system stopped before invoking the model.','quote'));
    if(r.model_assessment && !r.model_assessment.verdict){const fields=el('div',null,'model-fields');for(const k of ['saved_status','reloaded_status','status_persisted']) if(k in r.model_assessment) append(fields,el('span',`${k}: ${r.model_assessment[k]}`));append(top,fields);}
    if(r.model_assessment?.evidence_ids?.length){const c=el('div','Cites','citations');r.model_assessment.evidence_ids.forEach(id=>append(c,cite(id,i)));append(top,c);}
    const final=el('div',null,'final-output');append(final,el('p','SAFEGUARDED FINAL REPORT','panel-label'),append(el('div',null,'verdict-row'),el('h4',verdictLabel(r.verdict)),chip(r.verdict==='inconclusive'?'Stopped safely':r.assessment_mapping?'Mapped in code':'Accepted after checks',r.verdict==='inconclusive'?'warn':'pass')),el('p',r.summary,'quote'));
    if(r.assessment_mapping)append(final,el('p','The model did not propose this verdict. Code mapped its checked facts using '+r.assessment_mapping.version+'.','guard-note'));
    if(r.verdict==='inconclusive' && r.model_assessment)append(final,el('p','The disagreement was caught. The incorrect model verdict was not delivered as the final result.','guard-note'));
    if(r.limitations.length){const details=el('details');append(details,el('summary','Recorded limitations'));const list=el('ul',null,'checks-note');r.limitations.forEach(l=>append(list,el('li',l)));append(details,list);append(final,details);}
    return append(panel,top,final);
  }
  function renderObservation(r,i) {
    const panel=el('section',null,'panel');panel.id=`evidence-${i}`;panel.tabIndex=-1;panel.setAttribute('aria-label','Recorded browser observations');
    append(panel,append(el('div',null,'section-heading'),el('h4','Browser observations'),el('p','Captured text and values. Screenshot pixels are not included.')));
    if(!r.observations.length) return append(panel,append(el('div',null,'empty'),el('strong','No browser session'),el('p','This run stopped at input validation. There are no observations, screenshots, or browser actions to show.')));
    const tabs=el('div',null,'phase-tabs');tabs.setAttribute('role','group');tabs.setAttribute('aria-label',`Observation phase v0.${i+2}`);
    for (const p of PHASES)append(tabs,button(humanize(p),{'data-phase':p,'data-key':`phase-${i}-${p}`,'aria-pressed':state.phase===p}));append(panel,tabs);
    const o=r.observations.find(o=>o.phase===state.phase);if(!o)return append(panel,el('p','No observation was recorded for this phase.','empty'));
    const body=el('div',null,'observation');
    append(body,append(el('div',null,'observation-state'),append(el('div'),el('span',`${o.id} · ${o.phase}`),el('strong',o.values.persisted_status||'Unknown')),append(el('div'),el('span','TARGET'),el('strong',o.values.target_task_id||'Not provided','target'))));
    append(body,el('p','Recorded visible text, rendered inertly:','evidence-note'),scrollRegion(el('pre',o.visible_text,'text-capture'),`v0.${i+2} ${o.phase} recorded visible text`),el('p','No screenshot preview: original PNGs were omitted from the text-only transfer. A recorded hash is not visual verification.','evidence-note'));
    const detail=append(el('details'),el('summary','Recorded screenshot hash (pixels unavailable)'),el('p',o.screenshot_sha256||'No hash recorded.','hash'));append(body,detail);return append(panel,body);
  }
  function renderTimeline(r,i) {
    const panel=el('section',null,'panel');append(panel,append(el('div',null,'section-heading'),el('h4','Controller timeline'),el('p',r.events.length?'These v0.2/v0.3 actions came from a bounded controller after the model selected a workflow. They were not individually chosen by a general-loop agent.':'Input validation stopped this run before model or browser execution.')));
    if(!r.events.length)return append(panel,el('p','No controller events: browser execution was never started.','empty'));
    const controls=el('div',null,'timeline-tools'), label=el('label','Show events');label.htmlFor=`filter-${i}`;
    const select=el('select');select.id=`filter-${i}`;select.dataset.filter='true';select.dataset.key=`filter-${i}`;
    for(const f of FILTERS){const option=el('option',f==='actions'?'Completed actions':humanize(f));option.value=f;select.append(option);}select.value=state.filter;
    const filtered=filterEvents(r.events,state.filter);append(controls,label,select,el('span',`${filtered.length} / ${r.events.length}`));append(panel,controls);
    const list=el('ol',null,'timeline');list.setAttribute('aria-label',`v0.${i+2} ${state.filter} events`);list.tabIndex=0;
    for(const e of filtered){const li=el('li',null,'event');let title=e.action?humanize(e.action):humanize(e.type);if(e.type==='observation')title=`Observe ${e.phase}`;if(e.type==='network_request')title=`${e.method} ${e.url}`;if(e.type==='network_response')title=`HTTP ${e.status}`;
      append(li,append(el('div',null,'event-heading'),el('strong',title),el('span',`#${String(e.index).padStart(2,'0')}`,'event-num')),el('small',e.timestamp?.split('T')[1]||'Time not recorded'));
      if(e.type==='network_response')append(li,el('small',e.url));
      if(e.type==='network_request')append(li,el('small',e.allowed===true?'Allowed by controller':e.allowed===false?'Blocked by controller':'Permission not recorded'));
      const ids=e.type==='observation'?[e.id]:(e.observation_ids||[]);ids.forEach(id=>append(li,cite(id,i,`event-${e.index}`)));append(list,li);
    }
    if(!filtered.length)append(list,el('li','No recorded events match this filter.','empty'));return append(panel,list);
  }
  function checkRow(c) {
    const row=el('li',null,'check-row'),content=el('div');append(content,el('strong',CHECK_LABELS[c.name]||humanize(c.name)));
    if(c.name==='verdict_matches_private_oracle')append(content,el('small',`Final: ${verdictLabel(c.detail.actual)} · Oracle: ${verdictLabel(c.detail.expected)}`));
    else if(c.name==='independent_final_state')append(content,el('small',`Actual: ${c.detail.actual} · Expected: ${c.detail.expected}`));
    else if(c.name==='evidence_files_and_hashes')append(content,el('small','Passed on the original machine. Not rerun here; screenshot pixels are unavailable.'));
    return append(row,chip(c.passed?'PASS':'FAIL',c.passed?'pass':'fail'),content);
  }
  function renderChecks(r) {
    const panel=el('section',null,'panel');const count=gradeCount(r.grade);
    append(panel,append(el('div',null,'section-heading'),el('h4','Independent deterministic checks'),el('p','Historical evaluator results, separate from the model’s own claims.')),
      append(el('div',null,'check-summary'),el('strong',`${count.passed}/${count.total}`),el('span','recorded checks passed'),chip(r.grade.passed?'Trial passed':'Trial failed',r.grade.passed?'pass':'fail')),
      el('p','Recorded on the original trial machine, not rerun by this viewer. No human or model-judge semantic quality score is claimed.','checks-note'));
    const list=el('ul',null,'check-list');r.grade.checks.filter(c=>HIGHLIGHT_CHECKS.includes(c.name)).forEach(c=>append(list,checkRow(c)));append(panel,list);
    const details=el('details',null,'all-checks');append(details,el('summary',`All ${count.total} recorded checks`));const all=scrollRegion(el('ul',null,'check-list'),'All recorded historical check results');r.grade.checks.forEach(c=>append(all,checkRow(c)));append(details,all);append(panel,details);
    const server=el('details',null,'all-checks');append(server,el('summary','Independent fixture state & request journal'),scrollRegion(el('pre',literal(r.server),'raw-json'),'Independent server evidence JSON'));return append(panel,server);
  }
  function renderRun(r,i) {
    const run=el('article',null,'run');run.setAttribute('aria-label',`Agent v0.${i+2} recorded run`);
    const heading=el('div',null,'run-heading');append(heading,append(el('h3'),el('span',`v${r.agent_version}`,'version'),document.createTextNode(' '+(!r.model_assessment?'Input validation stop':i===0?'Verdict proposal':'Checked fact extraction'))),el('span',`${r.elapsed_seconds.toFixed(2)}s recorded`,'run-time'));append(run,heading,renderModel(r,i),renderObservation(r,i),renderTimeline(r,i),renderChecks(r));
    const raw=el('details',null,'raw-details');append(raw,el('summary','Inspect curated run JSON'),scrollRegion(el('pre',literal(r),'raw-json'),`v0.${i+2} curated run JSON`));return append(run,raw);
  }
  function renderProvenance() {
    const dest=byId('provenance-details');dest.replaceChildren();
    const labels={app_source:'Fixture application',evaluator_source:'Independent evaluator',effective_tasks_sha256:'Effective task definitions',model_artifact:'Local model artifact'};
    for(const [key,value] of Object.entries(data.comparability)){const row=el('div',null,'fingerprint');append(row,el('strong',`${labels[key]||key} · ${value.same?'same fingerprint':'different fingerprints'}`),el('code',value.baseline));if(!value.same)append(row,el('code',value.candidate));append(dest,row);}
    append(dest,el('p','Source file hashes identify the original retained bytes. Curated JSON is a derivative: local origins/ports become [local fixture], unused fields and local configuration are omitted, and original PNGs are absent. No human labels or reviewer details are included.','checks-note'),el('p','The source hashes were checked while preparing this bundle. Hash agreement proves byte identity to the retained records, not authentic execution by itself. Historical grade results are displayed as recorded. A text transfer cannot verify screenshot contents.','checks-note'));
  }
  function render() {
    const focused=document.activeElement?.getAttribute('data-key');
    const c=data.cases.find(c=>c.id===state.case);const list=byId('case-list');list.replaceChildren();
    data.cases.forEach((item,i)=>{const b=button('',{'data-case':item.id,'data-key':`case-${item.id}`,'aria-pressed':item.id===state.case},'case-button');append(b,el('span',String(i+1).padStart(2,'0'),'case-number'),append(el('span'),el('strong',item.title),el('small',i===0?'Caught disagreement':i===1?'Confirmed by evidence':'Correct refusal')));append(list,b);});
    byId('case-meta').textContent=`RECORDED CASE / ${c.runs[0].trial_id}`;byId('case-title').textContent=c.headline;byId('case-lesson').textContent=c.lesson;
    const bug=c.runs[0].bug, body=el('div',null,'bug-body');append(body,el('p',bug.title,'bug-title'),el('p',bug.description,'bug-description'));
    const facts=el('div',null,'bug-facts');for(const [label,value] of [['Target',bug.target_task_id||'Not supplied'],['Expected',bug.expected||'Not supplied'],['Environment','Isolated fictional task board']])append(facts,append(el('div'),el('span',label),el('strong',value)));append(body,facts);byId('bug-report').replaceChildren(body);
    document.querySelectorAll('[data-view]').forEach(b=>{b.setAttribute('aria-pressed',b.dataset.view===state.view);b.dataset.key=`view-${b.dataset.view}`;});
    byId('comparison-note').textContent=c.id==='fixed'?'What changed: the final outcome moved from inconclusive to not reproduced. The browser observed the same correct persistence; the model’s job changed from choosing a verdict to extracting checkable facts.':c.id==='persistence'?'What stayed the same: both final reports confirmed the controlled persistence bug. The model-output contract changed, not the app behavior.':'Neither version ran a browser or called the model. Do not count this input-validation success as a full browser-validation trial.';
    const grid=byId('run-grid');grid.className='run-grid'+(state.view==='compare'?'':' single');grid.replaceChildren();c.runs.forEach((r,i)=>{if(state.view==='compare'||(state.view==='baseline' && i===0)||(state.view==='candidate' && i===1))append(grid,renderRun(r,i));});
    renderProvenance();byId('announcer').textContent=`${c.title}. ${state.view==='compare'?'Comparing v0.2 and v0.3':state.view==='baseline'?'v0.2 only':'v0.3 only'}. ${humanize(state.phase)} observation.`;
    if(pendingEvidence!==undefined){const panel=byId(`evidence-${pendingEvidence}`);pendingEvidence=undefined;panel?.focus({preventScroll:true});panel?.scrollIntoView({block:'center',behavior:'instant'});return;}
    if(focused){const target=Array.from(document.querySelectorAll('[data-key]')).find(n=>n.dataset.key===focused);if(target)target.focus({preventScroll:true});}
  }
  try {
    data=validateData(window.TRACE_DATA);
    state=parseState(location.hash,data.cases.map(c=>c.id));render();
    document.addEventListener('click',event=>{
      if(event.target.closest('a.skip')){event.preventDefault();byId('workspace').focus();byId('workspace').scrollIntoView({block:'start'});return;}
      const b=event.target.closest('button');if(!b)return;
      if(b.dataset.case)commit({case:b.dataset.case,phase:'reloaded',filter:'actions'});
      else if(b.dataset.view)commit({view:b.dataset.view});
      else if(b.dataset.phase)commit({phase:b.dataset.phase});
      else if(b.dataset.observation){const c=data.cases.find(c=>c.id===state.case),i=Number(b.dataset.run),o=c.runs[i]?.observations.find(o=>o.id===b.dataset.observation);if(o){pendingEvidence=i;commit({phase:o.phase});}}
    });
    document.addEventListener('change',event=>{if(event.target.matches('select[data-filter]'))commit({filter:event.target.value});});
    window.addEventListener('hashchange',()=>{state=parseState(location.hash,data.cases.map(c=>c.id));render();});
  } catch(error) {
    const box=el('div',null,'error');box.setAttribute('role','alert');append(box,el('h2','This evidence could not be loaded.'),el('p','The bundle is missing or invalid. No verdict or check result is being treated as a pass.'),el('p',error.message));byId('workspace').replaceChildren(box);
  }
})();
