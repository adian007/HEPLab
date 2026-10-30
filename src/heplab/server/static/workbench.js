'use strict';
const $ = id => document.getElementById(id);
const canvas = $('detector'), context = canvas.getContext('2d');
const inputIds = ['mode','backend','seed','events','momentum','field','thickness','noise','threshold','response-model','field-model','source-model','muon-pt-min','muon-eta-max','muon-iso-max','mass-min','mass-max'];
let token = '', capabilities = null, result = null, active = null, displayedJob = null;
let detectorGeometry=null, calibrationReport=null, hiddenSurfaces=new Set();
let cmsDisplay=null; const displayLayers=new Map(), displaySurfaces=new Map(), displayRemainders=new Map(), hiddenDisplay=new Set();
let selected = null, projection = 'xy-xz', zoom = 1, pan = [0,0], orbit = [-.65,.55];
let curvatureConversion = null;
let drag = null, pairDrag = null, screenTracks = [], history = [], historyIndex = -1, sessionRuns = [];
let comparison = null;
let roll=0,trackerShell=null;
let eventFocusSnapshot=null;
const layerOpacity=new Map();
try{const saved=JSON.parse(localStorage.getItem('heplab-display-opacity-v1')||'{}');for(const id of ['pixel','strips','ecal','hcal','dt','csc','rpc','shell'])if(typeof saved[id]==='number'&&Number.isFinite(saved[id]))layerOpacity.set(id,Math.max(0,Math.min(1,saved[id])));}catch{}
// GPU path for the viewport; null keeps the Canvas2D renderer below.
const renderer = window.HEPLabGL?.create($('detector-gl')) || null;
if (!renderer) $('detector-gl').hidden = true;
const reducedMotion = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
function announceRenderer(fallback=!renderer||renderer.lost){
  const label=fallback?'Canvas 2D fallback renderer active.':'WebGL detector renderer active.';
  if($('renderer-status').textContent!==label)$('renderer-status').textContent=label;
  if(reducedMotion){const note='Reduced-motion preference is active; use the path slider to inspect positions.';if($('replay-status').textContent!==note)$('replay-status').textContent=note;}
}
announceRenderer();
// Replay clock in metres of flight path; Infinity shows complete trajectories.
const playback = {time: Infinity, playing: false, last: 0, max: 0, frame: 0};
let trackPaths = [], syncedEvent = null, syncedMarkers = '', staticKey = '';
let live = {enabled: false, busy: false, pending: false, eta: .3, phi: .8};
let lastFailure = null;

let guidedTour = null;
function startGuidedTour() {
  if (guidedTour) return;
  if (!window.introJs) { log('Guided tour could not load. Restart the app to restore its bundled help.'); return; }
  const workspace = window.currentWorkspace || 'analysis';
  const selectedTab = group => document.querySelector(group+' [role=tab][aria-selected=true]').id.replace('-tab','');
  const inspector = selectedTab('.property-pane'), results = selectedTab('.results-pane');
  const scrollPositions = [...document.querySelectorAll('main section')].map(element=>[element,element.scrollTop]);
  const cms = workspace === 'data';
  const steps = cms ? [
    {title:'Explore CMS data',intro:'Load collision data, choose a selection, then compare the results. This quick tour shows the workflow without changing your inputs.'},
    {element:'.data-source-panel',title:'1. Choose your datasets',intro:'Choose recorded data and, optionally, simulation. After the tour, use Load selected datasets to read the events.',position:'bottom'},
    {element:'.data-cut-grid',title:'2. Define the selection',intro:'Set the muon momentum, acceptance, isolation and dimuon mass window. The same cuts apply to data and simulation.',position:'bottom'},
    {element:'.data-cut-actions',title:'3. Apply your cuts',intro:'Choose trigger and muon ID requirements, then use Apply cuts. You can change the selection after loading without reading the files again.',position:'bottom'},
    {title:'Ready to compare',intro:'After applying cuts, the mass plots and cutflow appear below. Browse selected events in 3D or export the analysis from the results toolbar. You can reopen this tour anytime.'}
  ] : [
    {title:'A quick look around',intro:'Configure a sample, run it locally, then inspect the event and its checks. This tour only shows the controls; your inputs stay as they are.'},
    {element:'#mode',title:'1. Choose a simulation',intro:'Choose the muon bench or Drell–Yan collisions. The Engine menu shows the runtimes available on this machine.',position:'bottom'},
    {element:'[data-property=source]',title:'2. Configure the sample',intro:'Start with the seed and event budget here. Further down, the parameter groups describe the field, material and electronics, with units beside each value.',position:'left'},
    {element:'#run-button',title:'3. Run your sample',intro:'When you finish the tour, select Run to create a saved local job. Progress appears in the status bar; Stop cancels an active job.',position:'bottom'},
    {element:'.viewport-tools',title:'4. Explore the event',intro:'After a run, switch between XY, XZ and 3D. Drag to pan or orbit, scroll to zoom, and use Fit to reset the camera.',position:'bottom'},
    {element:'#particles-panel',title:'5. Inspect a particle',intro:'After a run, select a row to see that particle’s properties. Use Run log for job messages and Surface crossings for detector intersections.',position:'top'},
    {element:'#checks-panel',title:'6. Review the evidence',intro:'Read the capability states and their scope before interpreting results. The educational muon bench is unvalidated. Finish to return to your workspace.',position:'top'}
  ];
  const tour = guidedTour = window.introJs.tour().setOptions({
    nextLabel:'Next →', prevLabel:'← Back', doneLabel:'Finish tour', skipLabel:'×',
    tooltipClass:'heplab-tour', showProgress:true, showStepNumbers:true, showBullets:false,
    hidePrev:true, exitOnOverlayClick:false, overlayOpacity:.4, disableInteraction:true,
    scrollToElement:false, helperElementPadding:6, tooltipRenderAsHtml:false, steps
  });
  tour.onbeforechange(element=>{
    if (cms) { element?.scrollIntoView({block:'nearest',behavior:'instant'}); return; }
    setWorkspace('display');
    activateTab('inspector','settings');
    if (element === $('particles-panel')) activateTab('results','particles');
    if (element === $('checks-panel')) activateTab('results','checks');
    if (element === document.querySelector('[data-property=source]')) $('settings-panel').scrollTop=0;
  });
  // Intro replaces the tooltip after its transition, after the change callback.
  const tooltipObserver=new MutationObserver(()=>{
    if (guidedTour !== tour) return;
    const tooltip=document.querySelector('.heplab-tour');
    if (!tooltip || tooltip.hasAttribute('aria-modal')) return;
    tooltip.setAttribute('role','dialog');
    tooltip.setAttribute('aria-modal','true');
    const title=tooltip.querySelector('.introjs-tooltip-title');
    title.id='guided-tour-title';tooltip.setAttribute('aria-labelledby',title.id);
    const close=tooltip.querySelector('.introjs-skipbutton');
    close.setAttribute('aria-label','Exit guided tour');close.setAttribute('title','Exit guided tour (Esc)');
    tooltip.querySelector('.introjs-nextbutton')?.focus({preventScroll:true});
  });
  tooltipObserver.observe(document.body,{childList:true,subtree:true});
  tour.onexit(()=>{
    tooltipObserver.disconnect();
    guidedTour=null;
    setWorkspace(workspace);
    activateTab('inspector',inspector);activateTab('results',results);
    scrollPositions.forEach(([element,top])=>element.scrollTop=top);
    $('start-tour').focus({preventScroll:true});
  });
  tour.start();
}
$('start-tour').addEventListener('click',startGuidedTour);
document.addEventListener('keydown',event=>{
  if (!guidedTour || event.key !== 'Tab') return;
  const buttons=[...document.querySelectorAll('.heplab-tour a, .heplab-tour button')].filter(el=>!el.classList.contains('introjs-disabled')&&el.getClientRects().length);
  if (!buttons.length) return;
  event.preventDefault();
  const index=buttons.indexOf(document.activeElement);
  buttons[(index+(event.shiftKey?-1:1)+buttons.length)%buttons.length].focus();
},true);

function config() {
  return {mode:$('mode').value, backend:$('mode').value==='pythia'?'delphes':$('backend').value, seed:Number($('seed').value),
    events:$('mode').value==='analytic'&&$('source-model').value==='transverse_pair'?1:Number($('events').value), momentum_gev:Number($('momentum').value),
    bz_tesla:Number($('field').value),field_model:$('mode').value==='pythia'?'ideal_bore':$('field-model').value, thickness_mm:Number($('thickness').value),
    noise_adc:Number($('noise').value), threshold_adc:Number($('threshold').value),response_model:$('mode').value==='pythia'?'ideal':$('response-model').value,
    source_model:$('mode').value==='pythia'?'transverse_pair':$('source-model').value,
    muon_pt_min_gev:$('mode').value==='pythia'?Number($('muon-pt-min').value):20,
    muon_abs_eta_max:$('mode').value==='pythia'?Number($('muon-eta-max').value):2.4,
    muon_iso_max:$('mode').value==='pythia'?Number($('muon-iso-max').value):.15,
    mass_min_gev:$('mode').value==='pythia'?Number($('mass-min').value):60,
    mass_max_gev:$('mode').value==='pythia'?Number($('mass-max').value):120};
}
function runConfigEnvelope(c=config(),display={}) {
  const pick=keys=>Object.fromEntries(keys.map(key=>[key,c[key]]));
  return {schema:'heplab-run-config-v2',run:pick(['mode','backend','seed','events']),
    analytic:pick(['momentum_gev','bz_tesla','thickness_mm','noise_adc','threshold_adc','field_model','source_model']),
    collision:pick(['response_model']),
    display:{projection:display.projection||projection,region:display.region||$('detector-focus').value},
    analysis:pick(['muon_pt_min_gev','muon_abs_eta_max','muon_iso_max','mass_min_gev','mass_max_gev'])};
}
// Inside the desktop app the CSP blocks fetch('/api/...'); the same requests go
// through the shell's single validated command to the packaged worker.
const desktop = window.__TAURI_INTERNALS__;
function desktopRequest(path, body, extraHeaders) {
  if(path==='data/library'&&body===undefined)return ['data.library',{}];
  if(path.startsWith('data/'))return ['data.'+path.slice(5),body||{}];
  const fixed = {session:'workbench.session', detector:'detector.geometry', calibration:'calibration.report', 'detector/display':'detector.display',runs:'runs.list'};
  let match;
  if (fixed[path] && body === undefined) return [fixed[path], {}];
  if (path === 'jobs' && body === undefined) return ['jobs.list', {}];
  if (path === 'jobs' && body !== undefined) {
    const key = extraHeaders['Idempotency-Key'];
    return ['jobs.submit', key ? {config:body, idempotency_key:key} : {config:body}];
  }
  if ((match = /^jobs\/([A-Za-z0-9]+)$/.exec(path)) && body === undefined) return ['jobs.get', {job_id:match[1]}];
  if ((match = /^jobs\/([A-Za-z0-9]+)\/cancel$/.exec(path)) && body !== undefined) return ['jobs.cancel', {job_id:match[1]}];
  if ((match = /^jobs\/([A-Za-z0-9]+)\/events\/(\d+)$/.exec(path)) && body === undefined) return ['jobs.event', {job_id:match[1], index:Number(match[2])}];
  if ((match = /^runs\/([A-Za-z0-9_.-]+)$/.exec(path)) && body === undefined) return ['runs.get', {run_id:match[1]}];
  if (path === 'preview' && body !== undefined) return ['workbench.preview', {request:body}];
  if (path === 'lifetime' && body !== undefined) return ['workbench.lifetime', {config:body}];
  if (path === 'export-html' && body !== undefined) return ['workbench.export-html', body];
  throw Error('not available in the desktop app: '+path);
}
async function api(path, body, extraHeaders={}) {
  if (desktop) {
    const [op, args] = desktopRequest(path, body, extraHeaders);
    try { return await desktop.invoke('heplab_invoke', {op, args}); }
    catch (error) { throw Error(error && error.message ? error.message : String(error)); }
  }
  const response = await fetch('/api/v1/'+path, {
    method:body === undefined ? 'GET':'POST',
    headers:body === undefined ? {} : {'Content-Type':'application/json','X-HEPLab-Token':token,...extraHeaders},
    body:body === undefined ? undefined : JSON.stringify(body)
  });
  const text = await response.text();
  let value;
  try { value = JSON.parse(text); }
  catch { throw Error(response.ok ? 'malformed server response' : `HTTP ${response.status}: ${text.slice(0, 200)}`); }
  if (!response.ok) throw Error(typeof value.detail === 'string' ? value.detail : JSON.stringify(value.detail));
  return value;
}
function log(message) {
  $('log').textContent += '\n'+new Date().toLocaleTimeString()+'  '+message;
  $('diagnostics-panel').scrollTop = $('diagnostics-panel').scrollHeight;
}
function activateTab(group, id) {
  const names = group === 'inspector' ? ['settings','selection'] : ['particles','diagnostics','crossings','calibration','checks'];
  for (const name of names) {
    $(name+'-tab').setAttribute('aria-selected',String(name === id));
    $(name+'-panel').hidden = name !== id;
  }
}
for (const [group,names] of [['inspector',['settings','selection']],['results',['particles','diagnostics','crossings','calibration','checks']]]) {
  names.forEach((name,index) => {
    $(name+'-tab').onclick = () => activateTab(group,name);
    $(name+'-tab').onkeydown = event => {
      if (!['ArrowLeft','ArrowRight','Home','End'].includes(event.key)) return;
      event.preventDefault();
      const next = event.key === 'Home' ? 0 : event.key === 'End' ? names.length-1 : (index+(event.key === 'ArrowRight'?1:-1)+names.length)%names.length;
      $(names[next]+'-tab').focus(); activateTab(group,names[next]);
    };
  });
}
function cell(row, text, className='') {
  const value = document.createElement('td'); value.textContent = text; value.className = className;
  row.append(value); return value;
}
function check(name,state,scope,kind='pending') {
  const row = document.createElement('tr'); cell(row,name); cell(row,state,'check-'+kind); cell(row,scope);
  $('capability-rows').append(row);
}
function updateCapabilities() {
  $('capability-rows').replaceChildren();
  const rust = capabilities?.engine.rust_extension || capabilities?.engine.rust_executable_configured;
  const collision = $('mode').value === 'pythia';
  check('Python reference', 'Available', 'Analytic bench and response', 'pass');
  check('Rust engine', rust?'Available':'Unavailable', rust?'Native compiled numerical backend':(capabilities?.engine.rust_error||'Rust binding is not included in this build'),rust?'pass':'pending');
  check('PYTHIA8 / DELPHES', capabilities?.simulation.available?'Installed':'Unavailable',
    capabilities?.simulation.available?`${capabilities.simulation.host} · 8.312 / 3.5.1 · fixed CMS card`:(capabilities?.simulation.reason || 'Checking local runtime'),
    capabilities?.simulation.available?'pass':'pending');
  check('Selected model', collision?'Collision generation':'Thin-slab bench', collision?'Native generator + fast detector response':'Vacuum helix, continuous loss, Gaussian scattering');
  check('Input validation', $('run-form').checkValidity()?'In range':'Invalid values', 'Server revalidates all submitted values', $('run-form').checkValidity()?'pass':'fail');
  check('Material domain', collision?'Handled by DELPHES card':'Restricted approximation',collision?'No additional bench smearing is applied':'Heavy singly charged particles; thin steps only');
  check('Detector calibration','Pending','Measured Z target available; selected MC and correction payload pending');
  check('CMS tracker field',calibrationReport?.['cms-field-validation']?.passed?'Reference passed':'Loading','OAE 3.8 T; r<1.15 m, |z|<2.8 m; no full-map transport');
  if(cmsDisplay)check('CMS display layers','SHA256 verified','7 outline layers; no material properties','pass');
  check('Geometry navigation','Surface intersections','Finite cylinders/disks; original CMS pixel dimensions; envelope model','pass');
  check('Silicon ionization reference',calibrationReport?.['silicon-calibration']?.status||'Loading','PDG fit with held-out table points');
  check('Muon response reference',calibrationReport?.['muon-response-calibration']?.status||'Loading','Independent native generator shards; not measured CMS calibration');
  if (result?.summary) {
    const residual=result.summary.max_truth_four_momentum_residual_gev;
    const tolerance=Math.max(.002,2e-5*result.beam_energy_total_gev);
    // A missing or non-numeric residual is not evidence of failure: report Unknown.
    if(typeof residual!=='number'||!Number.isFinite(residual)||!Number.isFinite(tolerance))
      check('Generator conservation','Unknown','No finite four-vector residual was recorded for this run','pending');
    else{const passed=Math.abs(residual)<=tolerance;
      check('Generator conservation',passed?'Passed':'Failed',`Max four-vector residual: ${residual.toExponential(3)} GeV; ROOT rounding gate ${tolerance.toExponential(2)} GeV`,passed?'pass':'fail');}
    check('Cross section','Generator estimate',`${result.summary.cross_section_pb} ± ${result.summary.cross_section_error_pb} pb; independent validation pending`);
  }
  if (result?.mode === 'analytic') {
    const values=[...(result.analysis?.samples||[]),...result.tracks.map(t=>t.material)].map(t=>t?.energy_residual_gev);
    if(!values.length||values.some(v=>typeof v!=='number'||!Number.isFinite(v)))
      check('Event energy ledger','Unknown','One or more energy residuals were not recorded','pending');
    else{const residual=Math.max(...values.map(Math.abs)),passed=residual<=1e-9;
      check('Event energy ledger',passed?'Passed':'Failed',`${residual.toExponential(3)} GeV residual; absolute gate 1e-9 GeV`,passed?'pass':'fail');}
  }
}
function updateModelPreflight() {
  const panel=$('model-preflight');
  if($('mode').value==='pythia'){
    panel.textContent='Model IDs (v1): pythia8-delphes-dy-v1 + ideal-solenoid-helix-v1. PYTHIA8 Drell–Yan + DELPHES CMS card is fast simulation with no pileup. It is not Geant4 transport or measured CMS reconstruction; generator/card evidence is scoped to the recorded DY sample.';
    return;
  }
  const field=$('field-model').value==='cms_tracker'
    ?'Pinned CMS tracker OAE field reference (nominal 3.8 T; r < 1.15 m, |z| < 2.8 m; software parity only)'
    :'Analytic uniform axial-field vacuum helix';
  const source=$('source-model').value==='angular_sample'?'address-seeded angular muon test sample':'declared back-to-back muon test pair';
  const response=$('response-model').value==='delphes_reference'
    ?' Separate truth-to-object DY/DELPHES reference response; it does not alter the drawn trajectory.'
    :'';
  const sourceModelId=$('source-model').value==='angular_sample'?'angular-muon-sample-v1 v1':'declared-muon-pair-v1 v1';
  const fieldModelId=$('field-model').value==='cms_tracker'?'cms-tracker-oae-3.8t-v1 v1':'ideal-solenoid-helix-v1 v1';
  const responseModelId=$('response-model').value==='delphes_reference'?' · delphes-reference-response-v1 v1':'';
  const modelIds=`${sourceModelId} · ${fieldModelId} · pdg-si-muon-loglinear-split-v1 v1 · thin-slab-highland-v1 v1 · deposit-electronics-v1 v1${responseModelId}`;
  panel.textContent=`Model IDs: ${modelIds}. Source: ${source}. ${field}. PDG mean stopping table + one illustrative silicon slab / Highland Gaussian core; electronics illustrative. Domains and evidence are component-specific; the bench is educational and unvalidated.${response}`;
}
function updateMode() {
  const collision = $('mode').value === 'pythia';
  const angular = $('source-model').value==='angular_sample';
  const coarse = !collision&&$('response-model').value==='delphes_reference';
  const minimum=coarse?(angular?27.8:5):1;
  $('momentum').setCustomValidity(Number($('momentum').value)<minimum?`This response model requires momentum ≥ ${minimum} GeV/c.`:'');
  const tracker=$('field-model').value==='cms_tracker';
  $('field').readOnly=tracker;if(tracker)$('field').value='3.8';
  $('propagation-model').textContent=tracker?'RK4 / tracker validity only':'Analytic vacuum helix';
  if (collision) $('backend').value='delphes';
  else if ($('backend').value==='delphes') $('backend').value=(capabilities?.engine.rust_extension||capabilities?.engine.rust_executable_configured)?'rust':'reference';
  document.querySelectorAll('.bench-settings').forEach(e=>e.hidden=collision);
  document.querySelectorAll('.collision-settings').forEach(e=>e.hidden=!collision);
  document.querySelectorAll('.collision-settings input').forEach(e=>e.disabled=!collision||!!active);
  document.querySelectorAll('.bench-settings input,.bench-settings select').forEach(e=>e.disabled=collision||!!active);
  $('mass-max').setCustomValidity(collision&&Number($('mass-max').value)<=Number($('mass-min').value)?'Upper mass must exceed lower mass.':'');
  document.querySelectorAll('.bench-node').forEach(e=>e.disabled=collision);
  $('event-budget-row').hidden = !collision&&!angular;
  $('events').max=collision?'1000':'200';
  $('source-note').textContent=angular?'Isotropic directions within |η| < 2.4; fixed-momentum back-to-back pairs. Not collisions.':'One transverse back-to-back pair; seed changes scattering and electronics, not the input directions.';
  const fields=collision
    ?['seed','events','muon-pt-min','muon-eta-max','muon-iso-max','mass-min','mass-max']
    :['seed',...(angular?['events']:[]),'momentum','field','thickness','noise','threshold'];
  const firstInvalid=fields.map(id=>$(id)).find(input=>!input.disabled&&!input.checkValidity());
  $('configuration-error').hidden=!firstInvalid;
  $('configuration-error').textContent=firstInvalid
    ?`${firstInvalid.labels?.[0]?.textContent?.trim()||'Parameter'}: ${firstInvalid.validationMessage}`
    :'';
  $('backend').disabled = collision || !!active;
  $('document-title').textContent = window.currentWorkspace==='data'?'CMS data analysis':collision?'Drell–Yan collisions':angular?'Angular muon laboratory':'Single-pair bench';
  const unavailable=collision&&!capabilities?.simulation.available;
  $('runtime-notice').hidden=!collision||window.currentWorkspace==='data';
  $('runtime-notice').textContent=unavailable?(capabilities?.simulation.reason||'Checking collision runtime…'):`Collision runtime connected: ${capabilities?.simulation?.host||'Checking runtime…'} · PYTHIA8 8.312 → DELPHES 3.5.1 / CMS. Generator and detector validation remain pending.`;
  $('runtime-notice').classList.toggle('runtime-connected',collision&&!unavailable);
  $('collision-experiment').disabled=!token||!!active||!capabilities?.simulation.available;
  $('collision-runtime-status').textContent=capabilities?.simulation.available?`Collision runtime ready: ${capabilities.simulation.host}. No extra bench smearing is applied to DELPHES objects.`:(capabilities?.simulation.reason||'Checking collision runtime…');
  const invalid=!$('run-form').checkValidity();
  $('run-button').disabled = !token || !!active || invalid || (collision && !capabilities?.simulation.available);
  $('run-button').title=invalid?'Fix the highlighted parameters before running':'Run the configured simulation (F5)';
  if(capabilities)$('mode').options[1].textContent='Drell–Yan · PYTHIA8 / DELPHES'+(capabilities.simulation?.available?'':' (not installed)');
  document.querySelectorAll('[data-experiment]').forEach(b=>b.disabled=!token||!!active);
  $('next-seed').disabled=!token||!!active;
  updateModelPreflight();
  updateCapabilities();
}
function changed(record=true) {
  updateMode();
  if (record) {
    const next = JSON.stringify(config());
    if (history[historyIndex] !== next) {
      history = history.slice(0,historyIndex+1); history.push(next);
      if (history.length>100) history.shift(); historyIndex=history.length-1;
    }
  }
  $('undo').disabled = !!active || historyIndex<=0;
  $('redo').disabled = !!active || historyIndex>=history.length-1;
  const defaults={source_model:'transverse_pair',muon_pt_min_gev:20,muon_abs_eta_max:2.4,muon_iso_max:.15,mass_min_gev:60,mass_max_gev:120};
  const stale=!!result&&!Object.entries(config()).every(([key,value])=>(result.config[key]??defaults[key])===value);
  $('dirty').textContent = lastFailure?(result?`Run ${lastFailure} · showing previous successful result`:`Run ${lastFailure} · no result`)
    :!result?'No computed result':result.preview?'Live preview · not saved':stale?'Parameters modified · showing previous result':'Result up to date';
  $('dirty').classList.toggle('stale',stale||!!lastFailure);
  if(window.currentWorkspace==='data'&&window.cmsRefreshStatus)window.cmsRefreshStatus();
  else if(result?.mode==='cms')$('dirty').textContent='Saved CMS selection '+result.analysis_id.slice(0,8);
}
inputIds.forEach(id=>$(id).addEventListener('change',()=>changed()));
// Validity gates Run while typing, before the change event commits a value.
inputIds.forEach(id=>$(id).addEventListener('input',()=>updateMode()));
function restore(index) {
  if (active || index<0 || index>=history.length) return;
  historyIndex=index; const c=JSON.parse(history[index]);
  applyConfig(c);
  changed(false);
}
function applyConfig(c) {
  const values={mode:c.mode,backend:c.backend,seed:c.seed,events:c.events,momentum:c.momentum_gev,
    field:c.bz_tesla,thickness:c.thickness_mm,noise:c.noise_adc,threshold:c.threshold_adc,'response-model':c.response_model||'ideal','field-model':c.field_model||'ideal_bore','source-model':c.source_model||'transverse_pair',
    'muon-pt-min':c.muon_pt_min_gev??20,'muon-eta-max':c.muon_abs_eta_max??2.4,'muon-iso-max':c.muon_iso_max??.15,'mass-min':c.mass_min_gev??60,'mass-max':c.mass_max_gev??120};
  for (const [id,value] of Object.entries(values)) $(id).value=value;
}
$('undo').onclick=()=>restore(historyIndex-1); $('redo').onclick=()=>restore(historyIndex+1);
function saveJson(value,name) {
  const url=URL.createObjectURL(new Blob([JSON.stringify(value,null,2)],{type:'application/json'}));
  const link=document.createElement('a'); link.href=url; link.download=name; link.click();
  setTimeout(()=>URL.revokeObjectURL(url),1000);
}
let lifetimeResult=null;
function updateLifetimePathFields(){
  const altitude=$('life-path-mode').value==='altitude';
  $('life-fixed-row').hidden=altitude;$('life-altitude-fields').hidden=!altitude;
  $('life-path').disabled=altitude;
  for(const id of ['life-production','life-detector','life-zenith'])$(id).disabled=!altitude;
}
function presentLifetime(value){
  const s=value.summary,c=value.config,root=$('life-result');root.replaceChildren();
  const table=document.createElement('table');
  const entries=[
    ['Mean decay path',`${s.mean_decay_path_m.toPrecision(5)} m`],
    ['Analytic survival',s.expected_survival_probability.toPrecision(6)],
    ['Seeded survival',`${s.observed_survival_probability.toPrecision(6)} (${s.observed_survivors}/${c.sample_size})`],
    ['95% Wilson interval',s.survival_wilson_95_percent.map(x=>x.toPrecision(5)).join(' – ')],
    ['Result digest',value.result_sha256]
  ];
  for(const [name,text] of entries){const row=document.createElement('tr'),head=document.createElement('th'),cell=document.createElement('td');head.scope='row';head.textContent=name;cell.textContent=text;row.append(head,cell);table.append(row);}
  root.append(table);
  const note=document.createElement('p');note.className='field-note';note.textContent=`${c.path_mode==='altitude'?'Plane-parallel altitude path':'Fixed path'} · ${c.momentum_gev_c} GeV/c · seed ${c.seed}. Constant momentum and vacuum decay law only; no atmospheric shower or detector calibration.`;root.append(note);
  root.append(lifetimeProbabilityPlot(value));
}
function lifetimeProbabilityPlot(value){
  const {config:c,summary:s}=value,mean=s.mean_decay_path_m;
  const end=Math.max(c.path_length_m*1.15,mean*2,1),left=48,right=424,top=14,bottom=142;
  const x=path=>left+(right-left)*path/end,y=probability=>bottom-(bottom-top)*probability;
  const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');
  svg.setAttribute('viewBox','0 0 440 178');svg.setAttribute('role','img');
  svg.setAttribute('aria-label','Analytic muon survival probability versus path length with the seeded survival estimate and 95 percent Wilson interval');
  const add=(name,attrs,label)=>{const node=document.createElementNS(svg.namespaceURI,name);for(const [key,val]of Object.entries(attrs))node.setAttribute(key,String(val));if(label!==undefined)node.textContent=label;svg.append(node);return node;};
  for(let i=0;i<=4;i++){const probability=i/4,py=y(probability);add('line',{x1:left,y1:py,x2:right,y2:py,stroke:'#dce3e8'});add('text',{x:left-7,y:py+4,'text-anchor':'end',fill:'#64717c','font-size':10},probability.toFixed(2));}
  let path='';for(let i=0;i<=80;i++){const distance=end*i/80,px=x(distance),py=y(Math.exp(-distance/mean));path+=(i?'L':'M')+px.toFixed(2)+','+py.toFixed(2);}
  add('path',{d:path,fill:'none',stroke:'#2464a0','stroke-width':2});
  const observed=s.observed_survival_probability,interval=s.survival_wilson_95_percent,px=x(c.path_length_m),py=y(observed);
  add('line',{x1:px,y1:y(interval[0]),x2:px,y2:y(interval[1]),stroke:'#b56a22','stroke-width':2});
  add('line',{x1:px-5,y1:y(interval[0]),x2:px+5,y2:y(interval[0]),stroke:'#b56a22','stroke-width':2});
  add('line',{x1:px-5,y1:y(interval[1]),x2:px+5,y2:y(interval[1]),stroke:'#b56a22','stroke-width':2});
  add('circle',{cx:px,cy:py,r:4,fill:'#b56a22'});
  add('text',{x:left,y:166,fill:'#64717c','font-size':10},'0 m');
  add('text',{x:right,y:166,'text-anchor':'end',fill:'#64717c','font-size':10},`${Number(end.toPrecision(4))} m`);
  add('text',{x:left,y:10,fill:'#354d60','font-size':10},'Survival probability');
  const figure=document.createElement('figure');figure.className='survival-plot';
  const caption=document.createElement('figcaption');caption.textContent=`Survival versus path · analytic exponential (blue) · seeded estimate with 95% Wilson interval (orange) · ${c.sample_size} trials; binomial denominator is all trials.`;
  figure.append(caption,svg);return figure;
}
$('life-path-mode').addEventListener('change',updateLifetimePathFields);updateLifetimePathFields();
$('lifetime-form').onsubmit=async event=>{
  event.preventDefault();if(!$('lifetime-form').reportValidity())return;
  $('life-run').disabled=true;$('life-result').textContent='Running seeded survival experiment…';
  const config={path_mode:$('life-path-mode').value,momentum_gev_c:Number($('life-momentum').value),path_length_m:Number($('life-path').value),production_altitude_km:Number($('life-production').value),detector_altitude_km:Number($('life-detector').value),zenith_deg:Number($('life-zenith').value),seed:Number($('life-seed').value),sample_size:Number($('life-sample-size').value)};
  try{lifetimeResult=await api('lifetime',config);presentLifetime(lifetimeResult);$('life-export').disabled=false;}
  catch(error){lifetimeResult=null;$('life-export').disabled=true;$('life-result').textContent=`Lifetime experiment failed: ${error.message}`;}
  finally{$('life-run').disabled=false;}
};
$('life-export').onclick=async()=>{
  if(!lifetimeResult)return;
  $('life-export').disabled=true;
  try{const page=await api('export-html',{result:lifetimeResult});const url=URL.createObjectURL(new Blob([page.html],{type:'text/html;charset=utf-8'}));const link=document.createElement('a');link.href=url;link.download=`heplab-muon-survival-${lifetimeResult.result_sha256.slice(0,12)}.html`;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
  catch(error){$('life-result').append(document.createTextNode(` Export failed: ${error.message}`));}
  finally{$('life-export').disabled=false;}
};
$('save-setup').onclick=()=>saveJson({format:'heplab-workbench-config-v2',parameters:runConfigEnvelope()},'heplab-setup.json');
$('download').onclick=()=>{if(window.currentWorkspace==='data'&&window.exportCmsAnalysis){window.exportCmsAnalysis();return;}if(result) saveJson(result,`heplab-${displayedJob||'result'}-event-${result.event}.json`);};
$('load-setup').onclick=()=>$('setup-file').click();
$('setup-file').onchange=async()=>{
  const file=$('setup-file').files[0];if(!file)return;
  try{
    if(file.size>65536)throw Error('Setup must be smaller than 64 KiB.');
    const value=JSON.parse(await file.text());
    const version=/^heplab-workbench-config-v(\d+)$/.exec(value?.format??'');
    if(version&&!['1','2'].includes(version[1]))throw Error(`This setup uses format v${version[1]}; this HEPLab version reads setup formats v1 and v2 only.`);
    if(!version||!value.parameters||typeof value.parameters!=='object')throw Error('Choose a HEPLab setup JSON file.');
    let c=value.parameters,display=null;
    if(version[1]==='2'){
      const envelope=c,domains=['run','analytic','collision','display','analysis'];
      if(envelope.schema!=='heplab-run-config-v2'||Object.keys(envelope).sort().join('|')!==['analysis','analytic','collision','display','run','schema'].sort().join('|'))throw Error('Setup has an invalid v2 configuration envelope.');
      const allowed={run:['mode','backend','seed','events'],analytic:['momentum_gev','bz_tesla','thickness_mm','noise_adc','threshold_adc','field_model','source_model'],collision:['response_model'],display:['projection','region'],analysis:['muon_pt_min_gev','muon_abs_eta_max','muon_iso_max','mass_min_gev','mass_max_gev']};
      for(const group of domains)if(!envelope[group]||typeof envelope[group]!=='object'||Array.isArray(envelope[group])||Object.keys(envelope[group]).some(key=>!allowed[group].includes(key)))throw Error(`Setup has an invalid ${group} group.`);
      c={...envelope.run,...envelope.analytic,...envelope.collision,...envelope.analysis};display=envelope.display;
      if(display.projection&&!['xy-xz','xy','xz','3d'].includes(display.projection))throw Error('Invalid display projection.');
      if(display.region&&!['tracker','pixel','solenoid','cms'].includes(display.region))throw Error('Invalid display region.');
    }
    const unknown=Object.keys(c).filter(key=>!(key in config()));
    if(unknown.length)throw Error('Setup contains parameters this version does not recognise: '+unknown.join(', '));
    const numeric={seed:[1,900000000],events:[1,1000],momentum_gev:[1,100],bz_tesla:[-8,8],thickness_mm:[.1,5],noise_adc:[0,10],threshold_adc:[0,100]};
    for(const [key,[low,high]] of Object.entries(numeric))if(!Number.isFinite(c[key])||c[key]<low||c[key]>high)throw Error('Invalid setup parameter: '+key);
    for(const key of ['seed','events'])if(!Number.isInteger(c[key]))throw Error('Expected an integer: '+key);
    for(const [key,[low,high]]of Object.entries({muon_pt_min_gev:[0,500],muon_abs_eta_max:[.1,2.4],muon_iso_max:[0,10],mass_min_gev:[0,1000],mass_max_gev:[1,1000]}))if(c[key]!==undefined&&(!Number.isFinite(c[key])||c[key]<low||c[key]>high))throw Error('Invalid setup parameter: '+key);
    const enums={mode:['analytic','pythia'],backend:['reference','rust','delphes'],response_model:['ideal','delphes_reference'],field_model:['ideal_bore','cms_tracker'],source_model:['transverse_pair','angular_sample']};
    for(const [key,allowed] of Object.entries(enums))if(c[key]!==undefined&&!allowed.includes(c[key]))throw Error('Invalid setup parameter: '+key);
    if(!c.mode||!c.backend)throw Error('Setup requires mode and backend.');
    applyConfig(c);if(display){if(display.projection)setProjection(display.projection);if(display.region)$('detector-focus').value=display.region;fit();}changed();activateTab('inspector','settings');log('Loaded setup: '+file.name);
  }catch(error){log(error.message);activateTab('results','diagnostics');}
  finally{$('setup-file').value='';}
};
$('show-capabilities').onclick=()=>activateTab('results','checks');
document.querySelectorAll('[data-section]').forEach(button=>button.onclick=()=>{
  document.querySelectorAll('[data-section]').forEach(b=>{b.classList.toggle('selected',b===button);b.setAttribute('aria-selected',String(b===button));});
  selected=null;
  document.querySelectorAll('#track-list button').forEach(b=>{b.setAttribute('aria-selected','false');b.setAttribute('aria-pressed','false');});
  document.querySelectorAll('#particle-rows tr[data-id]').forEach(r=>r.setAttribute('aria-selected','false'));draw();
  activateTab('inspector','settings'); $('selection-title').textContent=button.textContent.replace(/[↳▾◇]/g,'').trim();
  const section=document.querySelector(`[data-property="${button.dataset.section}"]`);
  section.closest('details')?.setAttribute('open','');
  document.querySelectorAll('.property-section').forEach(e=>e.classList.remove('highlight'));
  section.classList.add('highlight'); section.scrollIntoView({block:'nearest'});
});

document.querySelector('[role=tree]').addEventListener('keydown',event=>{
  if(event.target.matches('input,select,textarea,button'))return;
  if(!['ArrowUp','ArrowDown','Home','End'].includes(event.key))return;
  event.preventDefault();const items=[...document.querySelectorAll('[role=treeitem]')].filter(e=>!e.disabled);
  const current=items.indexOf(document.activeElement);
  const next=event.key==='Home'?0:event.key==='End'?items.length-1:Math.max(0,Math.min(items.length-1,current+(event.key==='ArrowDown'?1:-1)));
  items[next]?.focus();
});

// Result artifacts this build can read; newer formats are refused, not guessed at.
const RESULT_FORMATS=new Set(['heplab-workbench-result-v2']);
function checkResultFormat(value){
  const format=value?.artifact?.format;
  if(format&&!RESULT_FORMATS.has(format))throw Error(`Run artifact format ${format} is newer than this app supports (${[...RESULT_FORMATS].join(', ')}). Open it with a matching HEPLab release.`);
  return value;
}
function rotate(point) {
  const [x,y,z]=point, [yaw,pitch]=orbit;
  const right=x*Math.cos(yaw)-y*Math.sin(yaw);
  const depth=x*Math.sin(yaw)+y*Math.cos(yaw);
  const [u,v]=projection==='xy'?[x,y]:projection==='xz'?[x,z]:[right,z*Math.cos(pitch)-depth*Math.sin(pitch)];
  return [u*Math.cos(roll)-v*Math.sin(roll),u*Math.sin(roll)+v*Math.cos(roll)];
}
function opacityFor(id){return layerOpacity.get(id)??(id==='shell'?.2:1);}
function setOpacity(id,value){
  if(!['pixel','strips','ecal','hcal','dt','csc','rpc','shell'].includes(id)||!Number.isFinite(value))return;
  layerOpacity.set(id,Math.max(0,Math.min(1,value)));
  try{localStorage.setItem('heplab-display-opacity-v1',JSON.stringify(Object.fromEntries(layerOpacity)));}catch{}
  document.querySelectorAll('[data-opacity-layer]').forEach(input=>{if(input.dataset.opacityLayer===id){input.value=Math.round(opacityFor(id)*100);input.nextElementSibling.value=input.value+'%';}});
}
function opacityControl(id,label){
  const controls=document.createElement('div');controls.className='layer-opacity';
  const input=document.createElement('input');input.type='range';input.min='0';input.max='100';input.step='1';input.value=Math.round(opacityFor(id)*100);input.dataset.opacityLayer=id;input.setAttribute('aria-label',label+' opacity');
  const output=document.createElement('output');output.value=input.value+'%';
  input.oninput=()=>{setOpacity(id,Number(input.value)/100);draw();};controls.append(input,output);return controls;
}
function shellGeometry(){
  const surface=detectorGeometry?.surfaces.find(s=>s.kind==='cylinder'&&s.subsystem==='tracker-envelope');
  if(!surface)return null;
  if(trackerShell?.radius===surface.radius_m&&trackerShell?.length===surface.half_length_m)return trackerShell.data;
  const data=[],r=surface.radius_m,z=surface.half_length_m;
  for(let i=0;i<96;i++){
    const a=i*Math.PI/48,b=(i+1)*Math.PI/48,p=[r*Math.cos(a),r*Math.sin(a)],q=[r*Math.cos(b),r*Math.sin(b)];
    data.push(...p,-z,...q,-z,...q,z,...p,-z,...q,z,...p,z);
  }
  trackerShell={radius:r,length:z,data:new Float32Array(data)};renderer?.setLayer('tracker-shell',trackerShell.data,'shell');return trackerShell.data;
}
function shellVisible(){return $('show-envelope').checked&&$('detector-focus').value!=='pixel';}
function scaleBar(scale){
  const target=90/scale,unit=10**Math.floor(Math.log10(target));
  const length=[5,2,1].find(n=>n*unit<=target)*unit;
  const label=length>=1?`${Number(length.toPrecision(2))} m`:length>=.01?`${Number((length*100).toPrecision(2))} cm`:`${Number((length*1000).toPrecision(2))} mm`;
  return {length,label};
}
function cutawaySettings(){
  return {enabled:$('cutaway').checked,angle:Number($('cutaway-angle').value)||0,opening:Number($('cutaway-opening').value)||100};
}
function solidDetector(){return ['solid','edges'].includes($('detector-style').value);}
function detectorLayerVisible(id){
  const focus=$('detector-focus').value;
  return !hiddenDisplay.has(id)&&!(focus==='pixel'&&id!=='pixel')&&!(focus==='tracker'&&!['pixel','strips'].includes(id));
}
function paintSolidDetector(project){
  const cut=cutawaySettings(),faces=[];
  const depth=p=>projection==='xy'?p[2]:projection==='xz'?-p[1]:(p[0]*Math.sin(orbit[0])+p[1]*Math.cos(orbit[0]))*Math.cos(orbit[1])+p[2]*Math.sin(orbit[1]);
  const meshes=solidDetector()&&$('show-modules').checked?[...displaySurfaces]:[];
  if(shellVisible()){const data=shellGeometry();if(data)meshes.push(['shell',data]);}
  for(const [id,data] of meshes){
    if((id!=='shell'&&!detectorLayerVisible(id))||!opacityFor(id))continue;
    const rgb=(id==='shell'?'#4e98ca':DISPLAY_COLORS[id]).slice(1).match(/../g).map(v=>parseInt(v,16));
    for(let i=0;i<data.length;i+=9){
      const points=[Array.from(data.slice(i,i+3)),Array.from(data.slice(i+3,i+6)),Array.from(data.slice(i+6,i+9))];
      const normal=window.HEPLabCutaway.normal(...points),light=.34+.66*Math.abs((.3*normal[0]-.5*normal[1]+.8*normal[2])/Math.sqrt(.98));
      const color=`rgb(${rgb.map(v=>Math.round(v*light)).join(',')})`;
      for(const polygon of window.HEPLabCutaway.polygon(points,cut))faces.push({points:polygon,depth:polygon.reduce((n,p)=>n+depth(p),0)/polygon.length,color,alpha:opacityFor(id)});
    }
  }
  faces.sort((a,b)=>b.depth-a.depth);
  for(const face of faces){context.globalAlpha=face.alpha;context.beginPath();face.points.forEach((p,i)=>i?context.lineTo(...project(p)):context.moveTo(...project(p)));context.closePath();context.fillStyle=face.color;context.fill();}
  context.globalAlpha=1;
}
// Canvas2D fallback when WebGL is unavailable or its context is lost.
function drawCanvas2D() {
  syncEventGeometry();
  const rect=canvas.getBoundingClientRect(), dpr=window.devicePixelRatio||1;
  if (!rect.width || !rect.height) return;
  canvas.width=Math.round(rect.width*dpr); canvas.height=Math.round(rect.height*dpr);
  context.scale(dpr,dpr);
  const width=rect.width,height=rect.height;
  const extent={pixel:.5,tracker:3,solenoid:7,cms:14}[$('detector-focus').value];
  const scale=Math.min(width,height)*.42*zoom/extent;
  const origin=[width/2+pan[0],height/2+pan[1]];
  context.fillStyle='#20252c';context.fillRect(0,0,width,height);
  const project=p=>{const q=rotate(p);return [origin[0]+q[0]*scale,origin[1]-q[1]*scale];};
  function line(points,color,lineWidth=1,dash=[],clip=false) {
    context.beginPath();context.strokeStyle=color;context.lineWidth=lineWidth;context.setLineDash(dash);
    if(clip){for(let i=1;i<points.length;i++)for(const [a,b] of window.HEPLabCutaway.segment(points[i-1],points[i],cutawaySettings())){context.moveTo(...project(a));context.lineTo(...project(b));}}
    else points.forEach((p,i)=>{const q=project(p);i?context.lineTo(...q):context.moveTo(...q);});context.stroke();context.setLineDash([]);
  }
  if ($('show-grid').checked) {
    for(let i=-10;i<=10;i++) {
      const a=i*extent/5, dark=i%5===0?'#47515d':'#323b46';
      if(projection==='xz'){line([[a,0,-2*extent],[a,0,2*extent]],dark);line([[-2*extent,0,a],[2*extent,0,a]],dark);}
      else {line([[a,-2*extent,0],[a,2*extent,0]],dark);line([[-2*extent,a,0],[2*extent,a,0]],dark);}
    }
  }
  paintSolidDetector(project);
  if($('show-guides').checked && detectorGeometry) {
    const guideLine=(points,color,width=1)=>line(points,color,width,[],true);
    const colors={pixel:'#c77882','tracker-envelope':'#6c9c86',solenoid:'#a69b6b'};
    const ring=(radius,z)=>Array.from({length:97},(_,i)=>[radius*Math.cos(i*Math.PI/48),radius*Math.sin(i*Math.PI/48),z]);
    for(const surface of detectorGeometry.surfaces) {
      if(hiddenSurfaces.has(surface.id))continue;
      const focus=$('detector-focus').value;
      if(focus==='pixel'&&surface.subsystem!=='pixel')continue;
      if(focus==='tracker'&&surface.subsystem==='solenoid')continue;
      const color=colors[surface.subsystem]||'#8293a7';
      if(surface.kind==='cylinder') {
        for(const z of [-surface.half_length_m,0,surface.half_length_m])guideLine(ring(surface.radius_m,z),color,1);
        if(projection!=='xy')for(let i=0;i<12;i++) {
          const a=i*Math.PI/6,x=surface.radius_m*Math.cos(a),y=surface.radius_m*Math.sin(a);
          guideLine([[x,y,-surface.half_length_m],[x,y,surface.half_length_m]],color,.65);
        }
      } else {
        guideLine(ring(surface.inner_radius_m,surface.z_m),color,1);
        guideLine(ring(surface.outer_radius_m,surface.z_m),color,1);
        if(projection!=='xy')for(let i=0;i<8;i++) {
          const a=i*Math.PI/4;
          guideLine([[surface.inner_radius_m*Math.cos(a),surface.inner_radius_m*Math.sin(a),surface.z_m],
                [surface.outer_radius_m*Math.cos(a),surface.outer_radius_m*Math.sin(a),surface.z_m]],color,.6);
        }
      }
    }
  }
  if ($('show-modules').checked) {
    const colors={pixel:'#d68c9a',strips:'#75ad98',ecal:'#8cb1cc',hcal:'#bba273',dt:'#b594bc',csc:'#b594bc',rpc:'#9ba5ca'};
    for (const [id, outlines] of displayLayers) {
      const values=solidDetector()&&$('detector-style').value!=='edges'?(displayRemainders.get(id)||outlines):outlines;
      if (hiddenDisplay.has(id)) continue;
      const focus=$('detector-focus').value;
      if (focus==='pixel' && id!=='pixel') continue;
      if (focus==='tracker' && !['pixel','strips'].includes(id)) continue;
      context.beginPath();context.strokeStyle=colors[id];context.lineWidth=.55;context.globalAlpha=(focus==='pixel'?.9:.4)*opacityFor(id);
      for(let i=0;i<values.length;i+=6) {
        const start=[values[i],values[i+1],values[i+2]],end=[values[i+3],values[i+4],values[i+5]];
        const a=project(start),b=project(end);
        if(Math.max(a[0],b[0])<0||Math.min(a[0],b[0])>width||Math.max(a[1],b[1])<0||Math.min(a[1],b[1])>height)continue;
        for(const [c,d] of window.HEPLabCutaway.segment(start,end,cutawaySettings())){context.moveTo(...project(c));context.lineTo(...project(d));}
      }
      context.stroke();context.globalAlpha=1;
    }
  }
  if($('detector-focus').value!=='pixel'&&!shellVisible()){
    line([[-extent,0,0],[extent,0,0]],'#874f51');
    line([[0,-extent,0],[0,extent,0]],'#4c755b');
    if(projection!=='xy')line([[0,0,-extent],[0,0,extent]],'#4e6e9b');
  }
  const time=Number.isFinite(playback.time)?Math.max(0,playback.time):Infinity;
  for(const layer of objectLayers){
    if(hiddenObjects.has(layer.group)||time<layer.at)continue;
    context.globalAlpha=layer.alpha;
    if(layer.mode==='triangles'){
      context.fillStyle=layer.color;
      for(let i=0;i<layer.data.length;i+=9){
        context.beginPath();
        for(let j=0;j<9;j+=3){const p=project(layer.data.slice(i+j,i+j+3));j?context.lineTo(...p):context.moveTo(...p);}
        context.closePath();context.fill();
      }
    }else{
      for(let i=0;i<layer.data.length;i+=6)line([layer.data.slice(i,i+3),layer.data.slice(i+3,i+6)],layer.color);
    }
    context.globalAlpha=1;
  }
  for(const track of objectTracks)line(visibleTrackPoints(track,time),track.color,1.5);
  screenTracks=[];
  for(const track of result?.tracks||[]) {
    const isSelected=track.object_id===selectedTrackId(), color=track.charge<0?'#68b9ef':'#e7ae65';
    const visible=visibleTrackPoints(track,time);
    line(visible,color,isSelected?2.5:1.5);
    const points=track.points.map(project),last=project(visible.at(-1));
    context.fillStyle=color;context.beginPath();context.arc(...last,isSelected?4:3,0,2*Math.PI);context.fill();
    if(time>=trackPath(track.points,track.trajectory?.path_m).at(-1)){context.font='12px Segoe UI,sans-serif';context.fillText(`${track.charge<0?'μ−':'μ+'} #${track.object_id}`,last[0]+7,last[1]-7);}
    screenTracks.push({id:track.object_id,points});
    for(const crossing of track.trajectory?.crossings||[]) {
      if(hiddenSurfaces.has(crossing.surface_id)||time<crossing.path_m)continue;
      const point=project(crossing.position_m);context.strokeStyle=color;context.lineWidth=1;
      context.strokeRect(point[0]-3,point[1]-3,6,6);
    }
    if(result?.mode==='analytic'&&track.material?.state?.position&&time>=1)
      drawMaterialMarker(project,track.material.state.position,track.object_id===0||isSelected);
  }
  // Stable orientation triad uses the same world-to-screen projection as tracks.
  const triad=[width-58,height-65];context.font='12px Segoe UI,sans-serif';
  for (const [vector,label,color] of [[[1,0,0],'X','#f17b7b'],[[0,1,0],'Y','#81c48b'],[[0,0,1],'Z','#7ca9ed']]) {
    const p=rotate(vector),end=[triad[0]+p[0]*32,triad[1]-p[1]*32];
    context.beginPath();context.strokeStyle=color;context.lineWidth=2;context.moveTo(...triad);context.lineTo(...end);context.stroke();context.fillStyle=color;context.fillText(label,end[0]+3,end[1]-3);
  }
  // Scale bar reports actual model-space distance under current zoom.
  const {length,label}=scaleBar(scale), x=15,y=height-42;
  context.strokeStyle='#c4ccd5';context.lineWidth=1;context.beginPath();context.moveTo(x,y-3);context.lineTo(x,y+3);context.moveTo(x,y);context.lineTo(x+length*scale,y);context.lineTo(x+length*scale,y-3);context.stroke();
  context.fillStyle='#c4ccd5';context.font='11px Consolas,monospace';context.fillText(label,x,y-7);
}

const DISPLAY_COLORS={pixel:'#d68c9a',strips:'#75ad98',ecal:'#8cb1cc',hcal:'#bba273',dt:'#b594bc',csc:'#b594bc',rpc:'#9ba5ca'};
// Normal alpha blending: dense layers converge to their own colour, not white.
const DISPLAY_ALPHA={pixel:.35,strips:.12,ecal:.07,hcal:.1,dt:.4,csc:.35,rpc:.14};
const SURFACE_COLORS={pixel:'#c77882','tracker-envelope':'#6c9c86',solenoid:'#a69b6b'};
const trackColor=track=>track.charge<0?'#68b9ef':'#e7ae65';
function viewFrame() {
  const rect=canvas.getBoundingClientRect();
  const width=rect.width,height=rect.height;
  const extent={pixel:.5,tracker:3,solenoid:7,cms:14}[$('detector-focus').value];
  const scale=Math.min(width,height)*.42*zoom/extent;
  const origin=[width/2+pan[0],height/2+pan[1]];
  const project=p=>{const q=rotate(p);return [origin[0]+q[0]*scale,origin[1]-q[1]*scale];};
  return {width,height,extent,scale,origin,project};
}
// Column-major matrix: world metres -> clip x/y, with view depth in z for fog.
function viewMatrix({width,height,extent,scale,origin}) {
  let R;
  if(projection==='xy')R=[[1,0,0],[0,1,0],[0,0,1]];
  else if(projection==='xz')R=[[1,0,0],[0,0,1],[0,-1,0]];
  else{const [yaw,pitch]=orbit,c=Math.cos(yaw),s=Math.sin(yaw),cp=Math.cos(pitch),sp=Math.sin(pitch);
    R=[[c,-s,0],[-s*sp,-c*sp,cp],[s*cp,c*cp,sp]];}
  const c=Math.cos(roll),s=Math.sin(roll),[right,up]=R;
  R=[right.map((v,i)=>v*c-up[i]*s),right.map((v,i)=>v*s+up[i]*c),R[2]];
  const sx=2*scale/width,sy=2*scale/height,sz=1/(extent*1.1);
  return new Float32Array([R[0][0]*sx,R[1][0]*sy,R[2][0]*sz,0, R[0][1]*sx,R[1][1]*sy,R[2][1]*sz,0,
    R[0][2]*sx,R[1][2]*sy,R[2][2]*sz,0, 2*origin[0]/width-1,1-2*origin[1]/height,0,1]);
}
function polylineSegments(points,out){for(let i=1;i<points.length;i++)out.push(...points[i-1],...points[i]);return out;}
// Grid, guide surfaces and axes depend only on view settings; rebuild on change.
function syncStaticLayers(extent) {
  const focus=$('detector-focus').value;
  const key=[projection,extent,focus,[...hiddenSurfaces].join(','),detectorGeometry?.sha256].join('|');
  if(key===staticKey)return;staticKey=key;
  const major=[],minor=[];
  for(let i=-10;i<=10;i++){
    const a=i*extent/5,target=i%5===0?major:minor;
    if(projection==='xz')target.push(a,0,-2*extent,a,0,2*extent,-2*extent,0,a,2*extent,0,a);
    else target.push(a,-2*extent,0,a,2*extent,0,-2*extent,a,0,2*extent,a,0);
  }
  renderer.setLayer('grid-major',major);renderer.setLayer('grid-minor',minor);
  const guides={};
  const ring=(radius,z)=>Array.from({length:97},(_,i)=>[radius*Math.cos(i*Math.PI/48),radius*Math.sin(i*Math.PI/48),z]);
  for(const surface of detectorGeometry?.surfaces||[]){
    if(hiddenSurfaces.has(surface.id))continue;
    if(focus==='pixel'&&surface.subsystem!=='pixel')continue;
    if(focus==='tracker'&&surface.subsystem==='solenoid')continue;
    const out=guides[surface.subsystem]??=[];
    if(surface.kind==='cylinder'){
      for(const z of [-surface.half_length_m,0,surface.half_length_m])polylineSegments(ring(surface.radius_m,z),out);
      if(projection!=='xy')for(let i=0;i<12;i++){const a=i*Math.PI/6,x=surface.radius_m*Math.cos(a),y=surface.radius_m*Math.sin(a);out.push(x,y,-surface.half_length_m,x,y,surface.half_length_m);}
    }else{
      polylineSegments(ring(surface.inner_radius_m,surface.z_m),out);polylineSegments(ring(surface.outer_radius_m,surface.z_m),out);
      if(projection!=='xy')for(let i=0;i<8;i++){const a=i*Math.PI/4;out.push(surface.inner_radius_m*Math.cos(a),surface.inner_radius_m*Math.sin(a),surface.z_m,surface.outer_radius_m*Math.cos(a),surface.outer_radius_m*Math.sin(a),surface.z_m);}
    }
  }
  for(const subsystem of ['pixel','tracker-envelope','solenoid','other'])renderer.setLayer('guide:'+subsystem,guides[subsystem]||[]);
  renderer.setLayer('axis-x',[-extent,0,0,extent,0,0]);renderer.setLayer('axis-y',[0,-extent,0,0,extent,0]);
  renderer.setLayer('axis-z',projection==='xy'?[]:[0,0,-extent,0,0,extent]);
}
// Reconstructed NanoAOD objects (recorded CMS events with a display sidecar).
// Geometry here is display construction from stored kinematics: cones and
// towers along each object's direction, not calorimeter hits or clustering.
const OBJECT_GROUPS={jets:['Jets (anti-kT 0.4)','#f2d14b'],towers:['Calorimeter towers','#ff6a55'],electrons:['Electrons','#5fe39a'],
  photons:['Photons','#c9f27c'],taus:['Taus','#c78bff'],isotracks:['Isolated tracks','#9fb3c8'],met:['Missing pT','#ff4fd8']};
// Unfiltered NanoAOD tau candidates mostly duplicate the selected muons; opt-in.
const hiddenObjects=new Set(['taus']);
let objectLayers=[],objectTracks=[];
const CAL={ecal:{r:1.29,z:3.15},hcal:{r:1.81,z:3.9}};
function direction(eta,phi){const t=2*Math.atan(Math.exp(-eta));return [Math.sin(t)*Math.cos(phi),Math.sin(t)*Math.sin(phi),Math.cos(t)];}
function reach(d,{r,z}){const rho=Math.hypot(d[0],d[1]);return Math.min(rho>1e-9?r/rho:Infinity,Math.abs(d[2])>1e-9?z/Math.abs(d[2]):Infinity);}
function basis(d){const a=Math.abs(d[2])<.9?[0,0,1]:[1,0,0];
  let u=[d[1]*a[2]-d[2]*a[1],d[2]*a[0]-d[0]*a[2],d[0]*a[1]-d[1]*a[0]];const n=Math.hypot(...u);u=u.map(v=>v/n);
  return [u,[d[1]*u[2]-d[2]*u[1],d[2]*u[0]-d[0]*u[2],d[0]*u[1]-d[1]*u[0]]];}
const along=(o,d,s)=>[o[0]+d[0]*s,o[1]+d[1]*s,o[2]+d[2]*s];
function cone(out,d,length,radius,segments=20){
  const [u,v]=basis(d),tip=along([0,0,0],d,length),ring=[];
  for(let i=0;i<=segments;i++){const a=2*Math.PI*i/segments;ring.push(tip.map((c,k)=>c+radius*(Math.cos(a)*u[k]+Math.sin(a)*v[k])));}
  for(let i=0;i<segments;i++)out.push(...ring[i],...ring[i+1]);
  for(let k=0;k<5;k++)out.push(0,0,0,...ring[Math.floor(k*segments/5)]);
}
// Box from distance s0 to s1 along d with square cross-section w: 12 triangles + 12 edges.
function tower(solid,edges,d,s0,s1,w,origin=[0,0,0]){
  const [u,v]=basis(d),c=[];
  for(const s of [s0,s1])for(const [a,b] of [[-1,-1],[1,-1],[1,1],[-1,1]])c.push(along(origin,d,s).map((x,k)=>x+w/2*(a*u[k]+b*v[k])));
  for(const [a,b,e,f] of [[0,1,2,3],[4,5,6,7],[0,1,5,4],[1,2,6,5],[2,3,7,6],[3,0,4,7]])solid.push(...c[a],...c[b],...c[e],...c[a],...c[e],...c[f]);
  for(const [a,b] of [[0,1],[1,2],[2,3],[3,0],[4,5],[5,6],[6,7],[7,4],[0,4],[1,5],[2,6],[3,7]])edges.push(...c[a],...c[b]);
}
const GEV_TO_M=.02;
function objectGeometry(objects){
  const layers=[],tracks=[];if(!objects)return {layers,tracks};
  const add=(group,key,data,color,alpha,at,mode='lines')=>{if(data.length)layers.push({group,key:'obj:'+key,data,color,alpha,at,mode});};
  const jetCones=[],towerSolidE=[],towerEdgeE=[],towerSolidH=[],towerEdgeH=[];
  for(const jet of objects.jets){
    const d=direction(jet.eta,jet.phi),energy=jet.pt*Math.cosh(jet.eta),ecal=reach(d,CAL.ecal),hcal=reach(d,CAL.hcal);
    cone(jetCones,d,ecal,Math.max(.06,ecal*Math.tan(.2)));
    const em=Math.min(1.5,energy*Math.max(0,jet.em_fraction)*GEV_TO_M),had=Math.min(2,energy*Math.max(0,jet.hadronic_fraction)*GEV_TO_M);
    if(em>.005)tower(towerSolidE,towerEdgeE,d,ecal,ecal+em,.12);
    if(had>.005)tower(towerSolidH,towerEdgeH,d,hcal,hcal+had,.16);
  }
  add('jets','jets',jetCones,OBJECT_GROUPS.jets[1],.55,.3);
  add('towers','ecal-solid',towerSolidE,'#ff5a4f',.45,1.3,'triangles');add('towers','ecal-edge',towerEdgeE,'#ffb0a8',.9,1.3);
  add('towers','hcal-solid',towerSolidH,'#4f8dff',.4,1.8,'triangles');add('towers','hcal-edge',towerEdgeH,'#a9c6ff',.9,1.8);
  const photons=[],photonTowers=[],photonEdges=[];
  for(const photon of objects.photons){
    const d=direction(photon.eta,photon.phi),ecal=reach(d,CAL.ecal);
    for(let s=0;s<ecal;s+=.12)photons.push(...along([0,0,0],d,s),...along([0,0,0],d,Math.min(ecal,s+.07)));
    tower(photonTowers,photonEdges,d,ecal,ecal+Math.min(1.5,photon.pt*Math.cosh(photon.eta)*GEV_TO_M),.08);
  }
  add('photons','photon-lines',photons,OBJECT_GROUPS.photons[1],.9,0);
  add('photons','photon-towers',photonTowers,'#ff5a4f',.5,1.3,'triangles');add('photons','photon-edges',photonEdges,'#ffd0a0',.9,1.3);
  const electronTowers=[],electronEdges=[];
  for(const electron of objects.electrons){
    if(electron.points?.length>1)tracks.push({id:'e'+electron.index,points:electron.points,color:OBJECT_GROUPS.electrons[1],group:'electrons'});
    const end=electron.points?.at(-1),radius=end?Math.hypot(...end):0;
    // Anchor the tower at the curved track's endpoint, extending outward.
    if(radius>0)tower(electronTowers,electronEdges,end.map(v=>v/radius),0,Math.min(1.5,electron.pt*Math.cosh(electron.eta)*GEV_TO_M),.08,end);
  }
  add('electrons','electron-towers',electronTowers,'#ff5a4f',.5,1.3,'triangles');add('electrons','electron-edges',electronEdges,'#ffd0a0',.9,1.3);
  const taus=[];for(const tau of objects.taus){const d=direction(tau.eta,tau.phi),s=reach(d,CAL.ecal);cone(taus,d,s,Math.max(.04,s*Math.tan(.08)),12);}
  add('taus','taus',taus,OBJECT_GROUPS.taus[1],.7,.3);
  const iso=[];for(const track of objects.isotracks){const d=direction(track.eta,track.phi);iso.push(0,0,0,...along([0,0,0],d,Math.min(1.1/Math.max(.05,Math.hypot(d[0],d[1])),2.8)));}
  add('isotracks','isotracks',iso,OBJECT_GROUPS.isotracks[1],.6,0);
  const met=objects.met;
  if(met&&met.pt>0){
    const length=Math.min(7,Math.max(.3,met.pt*.05)),d=[Math.cos(met.phi),Math.sin(met.phi),0],tip=along([0,0,0],d,length),side=[-d[1],d[0],0];
    tracks.push({id:'met',points:Array.from({length:11},(_,i)=>along([0,0,0],d,length*i/10)),color:OBJECT_GROUPS.met[1],group:'met'});
    const head=.12*length+.15;
    add('met','met-head',[...tip,...tip.map((v,k)=>v-d[k]*head+side[k]*head*.5),...tip,...tip.map((v,k)=>v-d[k]*head-side[k]*head*.5)],OBJECT_GROUPS.met[1],1,0);
  }
  if(objects.vertex)add('jets','vertex',[...objects.vertex.position_m.map((v,k)=>v-(k===2?.03:0)),...objects.vertex.position_m.map((v,k)=>v+(k===2?.03:0))],'#ffffff',1,0);
  return {layers,tracks};
}
function renderObjectToggles(){
  const groups=Object.keys(OBJECT_GROUPS).filter(group=>objectLayers.some(l=>l.group===group)||(group==='electrons'&&result?.objects?.electrons?.length));
  $('object-layers-title').hidden=!result?.objects;$('object-layers').replaceChildren();
  if(result?.objects_unavailable&&result.mode==='cms'){const p=document.createElement('p');p.className='muted inset';p.textContent=result.objects_unavailable;$('object-layers').append(p);$('object-layers-title').hidden=false;}
  for(const group of groups){
    const [label,color]=OBJECT_GROUPS[group],row=document.createElement('div');row.className='geometry-node';
    const toggle=document.createElement('input');toggle.type='checkbox';toggle.checked=!hiddenObjects.has(group);toggle.setAttribute('aria-label','Show '+label);
    toggle.onchange=()=>{toggle.checked?hiddenObjects.delete(group):hiddenObjects.add(group);syncedEvent=null;draw();};
    const swatch=document.createElement('span');swatch.className='object-swatch';swatch.style.background=color;
    const name=document.createElement('span');name.textContent=label;name.className='object-label';
    row.append(toggle,swatch,name);$('object-layers').append(row);
  }
}
// Tracks and crossing markers change only with the displayed event.
function syncEventGeometry() {
  const markerKey=[...hiddenSurfaces].join(',');
  if(syncedEvent===result&&syncedMarkers===markerKey)return;
  const tracks=result?.tracks||[];
  if(syncedEvent!==result){
    const gpu=renderer&&!renderer.lost;
    if(gpu)for(const layer of objectLayers)renderer.setLayer(layer.key,null);
    const objects=objectGeometry(result?.mode==='cms'?result.objects:null);
    objectLayers=objects.layers;
    if(gpu)for(const layer of objectLayers)renderer.setLayer(layer.key,layer.data,layer.mode);
    objectTracks=objects.tracks.filter(t=>!hiddenObjects.has(t.group));
    const allTracks=[...tracks.map(t=>({id:t.object_id,points:t.points,path_m:t.trajectory?.path_m,color:trackColor(t)})),...objectTracks];
    const paths=allTracks.map(t=>trackPath(t.points,t.path_m));
    if(gpu)renderer.setTracks(allTracks);
    trackPaths=paths.slice(0,tracks.length);
    playback.max=Math.max(0,...paths.map(p=>p.at(-1)||0),objectLayers.length?2.5:0);
  }
  const markers=[];
  for(const track of tracks)for(const crossing of track.trajectory?.crossings||[])
    if(!hiddenSurfaces.has(crossing.surface_id))markers.push({position:crossing.position_m,color:'#ffe08a',alpha:.95,at:crossing.path_m,size:7});
  if(renderer&&!renderer.lost)renderer.setMarkers(markers);syncedEvent=result;syncedMarkers=markerKey;
}
function trackPath(points,physicalPath){
  if(Array.isArray(physicalPath)&&physicalPath.length===points.length&&physicalPath.every((value,index)=>Number.isFinite(value)&&value>=0&&(index===0||value>=physicalPath[index-1])))return physicalPath;
  const path=[0];
  for(let i=1;i<points.length;i++)path.push(path[i-1]+Math.hypot(...points[i].map((v,k)=>v-points[i-1][k])));
  return path;
}
function visibleTrackPoints(track,time){
  const path=trackPath(track.points,track.trajectory?.path_m);
  if(time>=path.at(-1))return track.points;
  return [...track.points.filter((_,i)=>path[i]<time),pointAt(track,path,time)];
}
function pointAt(track,path,s){
  const p=track.points;if(s<=0)return p[0];
  for(let i=1;i<p.length;i++)if(path[i]>=s){const f=(s-path[i-1])/Math.max(1e-12,path[i]-path[i-1]);return p[i-1].map((v,k)=>v+f*(p[i][k]-v));}
  return p.at(-1);
}
function drawMaterialMarker(project,position,label=false){
  const [x,y]=project(position);context.save();context.translate(x,y);context.rotate(Math.PI/4);
  context.fillStyle='#f4c45e';context.strokeStyle='#20252c';context.lineWidth=1.5;
  context.fillRect(-4,-4,8,8);context.strokeRect(-4,-4,8,8);context.restore();
  if(label){context.fillStyle='#ffe4a0';context.font='11px Segoe UI,sans-serif';context.fillText('illustrative slab · 1 m',x+8,y-8);}
}
function drawTriadAndScale(width,height,extent,scale) {
  const triad=[width-58,height-65];context.font='12px Segoe UI,sans-serif';
  for (const [vector,label,color] of [[[1,0,0],'X','#f17b7b'],[[0,1,0],'Y','#81c48b'],[[0,0,1],'Z','#7ca9ed']]) {
    const p=rotate(vector),end=[triad[0]+p[0]*32,triad[1]-p[1]*32];
    context.beginPath();context.strokeStyle=color;context.lineWidth=2;context.moveTo(...triad);context.lineTo(...end);context.stroke();context.fillStyle=color;context.fillText(label,end[0]+3,end[1]-3);
  }
  const {length,label}=scaleBar(scale), x=15,y=height-42;
  context.strokeStyle='#c4ccd5';context.lineWidth=1;context.beginPath();context.moveTo(x,y-3);context.lineTo(x,y+3);context.moveTo(x,y);context.lineTo(x+length*scale,y);context.lineTo(x+length*scale,y-3);context.stroke();
  context.fillStyle='#c4ccd5';context.font='11px Consolas,monospace';context.fillText(label,x,y-7);
}
function drawSynchronizedProjectionPair(){
  syncEventGeometry();
  const root=$('linked-projection-pair');root.hidden=false;root.replaceChildren();
  $('detector').hidden=true;$('detector-gl').hidden=true;
  const width=root.clientWidth,focus=$('detector-focus').value;
  if(!width)return;
  const extent={pixel:.5,tracker:3,solenoid:7,cms:14}[focus],time=Number.isFinite(playback.time)?playback.time:Infinity;
  const views=[{name:'Transverse XY',a:0,b:1,axisA:'x',axisB:'y'},{name:'Longitudinal XZ',a:0,b:2,axisA:'x',axisB:'z'}];
  for(const view of views){
    const figure=document.createElement('figure');figure.className='linked-projection-pane';
    const caption=document.createElement('figcaption');caption.textContent=`${view.name} · coordinates in m · shared path ${Number.isFinite(time)?time.toFixed(2)+' m':'complete'} · ${['cms','pythia'].includes(result?.mode)?'IP-assumed display extrapolation; not hits':'model path; not hits'}`;
    const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');svg.setAttribute('viewBox','0 0 500 320');svg.setAttribute('role','group');
    svg.setAttribute('aria-label',`${view.name} synchronized projection. Click or keyboard-activate a muon path to select it. Axes in metres.`);
    const add=(name,attrs,label)=>{const node=document.createElementNS(svg.namespaceURI,name);for(const [key,value]of Object.entries(attrs))node.setAttribute(key,String(value));if(label!==undefined)node.textContent=label;svg.append(node);return node;};
    const scale=320*.42*zoom/extent,center=[250+pan[0],160+pan[1]];
    const point=position=>[center[0]+position[view.a]*scale,center[1]-position[view.b]*scale];
    const visibleExtent=extent/(.84*zoom);
    const step=extent<=.5?.1:extent<=3?.5:extent<=7?1:2;
    if($('show-grid').checked){
      const low=Math.floor(-visibleExtent/step),high=Math.ceil(visibleExtent/step);
      const world=(a,b)=>{const position=[0,0,0];position[view.a]=a;position[view.b]=b;return position;};
      for(let index=low;index<=high;index++){
        const value=index*step,p1=point(world(value,-visibleExtent)),p2=point(world(value,visibleExtent));
        const q1=point(world(-visibleExtent,value)),q2=point(world(visibleExtent,value));
        add('line',{x1:p1[0],y1:p1[1],x2:p2[0],y2:p2[1],stroke:index%5===0?'#46515d':'#333c47','stroke-width':1});
        add('line',{x1:q1[0],y1:q1[1],x2:q2[0],y2:q2[1],stroke:index%5===0?'#46515d':'#333c47','stroke-width':1});
      }
    }
    if($('show-guides').checked&&detectorGeometry?.surfaces){
      for(const surface of detectorGeometry.surfaces){
        if(hiddenSurfaces.has(surface.id))continue;
        const color=SURFACE_COLORS[surface.subsystem]||'#66717e';
        if(surface.kind==='cylinder'&&view.b===1){
          const radius=surface.radius_m*scale;add('circle',{cx:center[0],cy:center[1],r:radius,fill:'none',stroke:color,'stroke-dasharray':'4 4','stroke-width':1});
        }else if(surface.kind==='cylinder'&&view.b===2){
          for(const side of [-1,1]){const p1=point([side*surface.radius_m,0,-surface.half_length_m]),p2=point([side*surface.radius_m,0,surface.half_length_m]);add('line',{x1:p1[0],y1:p1[1],x2:p2[0],y2:p2[1],stroke:color,'stroke-dasharray':'4 4','stroke-width':1});}
        }else if(surface.kind==='disk'&&view.b===1){
          for(const radius of [surface.inner_radius_m,surface.outer_radius_m])add('circle',{cx:center[0],cy:center[1],r:radius*scale,fill:'none',stroke:color,'stroke-dasharray':'4 4','stroke-width':1});
        }else if(surface.kind==='disk'&&view.b===2){
          for(const radius of [surface.inner_radius_m,surface.outer_radius_m]){const p1=point([-radius,0,surface.z_m]),p2=point([radius,0,surface.z_m]);add('line',{x1:p1[0],y1:p1[1],x2:p2[0],y2:p2[1],stroke:color,'stroke-dasharray':'4 4','stroke-width':1});}
        }
      }
    }
    const origin=point([0,0,0]),xEnd=point([visibleExtent,0,0]),verticalEnd=point(view.b===1?[0,visibleExtent,0]:[0,0,visibleExtent]);
    add('line',{x1:origin[0],y1:origin[1],x2:xEnd[0],y2:xEnd[1],stroke:'#c98181','stroke-width':1.4});
    add('line',{x1:origin[0],y1:origin[1],x2:verticalEnd[0],y2:verticalEnd[1],stroke:'#83acdf','stroke-width':1.4});
    add('text',{x:476,y:304,'text-anchor':'end',class:'linked-projection-axis'},`${view.axisA} (m) ↔ ${view.axisB} (m)`);
    add('circle',{cx:origin[0],cy:origin[1],r:3,fill:'#fff'});
    for(let index=0;index<(result?.tracks||[]).length;index++){
      const track=result.tracks[index],path=trackPaths[index]||[],points=time<path.at(-1)?visibleTrackPoints(track,time):track.points;
      if(points.length<2)continue;
      const projected=points.map(point).map(pair=>pair.map(value=>value.toFixed(2)).join(',')).join(' '),color=trackColor(track),isSelected=selectedTrackId()===track.object_id;
      const line=add('polyline',{points:projected,fill:'none',stroke:color,'stroke-width':isSelected?3:1.8,'stroke-linejoin':'round','stroke-linecap':'round','data-track-id':track.object_id,'aria-pressed':String(isSelected),role:'button',tabindex:0,class:'linked-track','aria-label':`${track.charge<0?'Muon minus':'Muon plus'} ${track.object_id}; select in both projections`});
      const title=document.createElementNS(svg.namespaceURI,'title');title.textContent=`${track.charge<0?'μ−':'μ+'} / ${track.object_id} · ${track.model_ids?.join(', ')||'model identity not recorded'} · select this shared object`;line.append(title);
      const last=point(points.at(-1));add('circle',{cx:last[0],cy:last[1],r:isSelected?4:3,fill:color});
      if(Number.isFinite(time)&&time<(path.at(-1)||0)){const head=point(pointAt(track,path,time));add('circle',{cx:head[0],cy:head[1],r:5,fill:'#fff',stroke:color,'stroke-width':2});}
      if(result?.mode==='analytic'&&track.material?.state?.position&&time>=1){
        const marker=point(track.material.state.position);
        add('rect',{x:marker[0]-3,y:marker[1]-3,width:6,height:6,transform:`rotate(45 ${marker[0]} ${marker[1]})`,fill:'#f4c45e',stroke:'#20252c','stroke-width':1});
        if(track.object_id===0||isSelected)add('text',{x:marker[0]+8,y:marker[1]-8,class:'material-marker-label'},'illustrative slab · 1 m');
      }
    }
    figure.append(caption,svg);root.append(figure);
  }
}
function draw() {
  if(projection==='xy-xz'){
    drawSynchronizedProjectionPair();$('renderer-status').textContent='Synchronized vector projections active.';return;
  }
  $('linked-projection-pair').hidden=true;$('detector').hidden=false;
  if(!renderer||renderer.lost){if(renderer)$('detector-gl').hidden=true;announceRenderer(true);drawCanvas2D();return;}
  const frame=viewFrame(),dpr=window.devicePixelRatio||1;
  if(!frame.width||!frame.height)return;
  const {width,height,extent,scale,project}=frame,focus=$('detector-focus').value;
  syncStaticLayers(extent);syncEventGeometry();
  const layers=[];
  if($('show-grid').checked)layers.push({key:'grid-minor',color:'#323b46',alpha:1,additive:false},{key:'grid-major',color:'#47515d',alpha:1,additive:false});
  const solid=solidDetector(),cutaway=cutawaySettings();
  if($('show-modules').checked&&solid)for(const id of displaySurfaces.keys()){
    if(detectorLayerVisible(id))layers.push({key:'solid:'+id,color:DISPLAY_COLORS[id],alpha:opacityFor(id),additive:false,cutaway:true});
  }
  if(shellVisible()&&shellGeometry())layers.push({key:'tracker-shell',color:'#4e98ca',alpha:opacityFor('shell'),additive:false,cutaway:true});
  if($('show-modules').checked)for(const id of displayLayers.keys()){
    if(hiddenDisplay.has(id)||(focus==='pixel'&&id!=='pixel')||(focus==='tracker'&&!['pixel','strips'].includes(id)))continue;
    const remainder=solid&&$('detector-style').value!=='edges'&&displayRemainders.has(id);
    layers.push({key:(remainder?'cms-remainder:':'cms:')+id,color:DISPLAY_COLORS[id],alpha:(solid?.55:focus==='pixel'?.85:DISPLAY_ALPHA[id])*opacityFor(id),additive:false,cutaway:true,depthTest:solid});
  }
  if($('show-guides').checked&&detectorGeometry)for(const [subsystem,color] of Object.entries(SURFACE_COLORS))layers.push({key:'guide:'+subsystem,color,alpha:.75,additive:false,cutaway:true,depthTest:solid});
  // Objects appear as the replay clock reaches the detector layer they belong to.
  for(const layer of objectLayers)if(!hiddenObjects.has(layer.group)&&Math.max(0,Number.isFinite(playback.time)?playback.time:1e6)>=layer.at)
    layers.push({key:layer.key,color:layer.color,alpha:layer.alpha,additive:layer.mode!=='triangles',overlay:true});
  if(focus!=='pixel'&&!shellVisible())layers.push({key:'axis-x',color:'#874f51',alpha:1,additive:false},{key:'axis-y',color:'#4c755b',alpha:1,additive:false},{key:'axis-z',color:'#4e6e9b',alpha:1,additive:false});
  const time=Number.isFinite(playback.time)?Math.max(0,playback.time):1e6;
  if(renderer.render({width,height,dpr,view:viewMatrix(frame),depthScale:extent/50,cutaway,background:'#161b21',layers,fog:projection==='3d'?(focus==='pixel'?.25:.6):0,time,selected:selectedTrackId()})===false){$('detector-gl').hidden=true;announceRenderer(true);drawCanvas2D();return;}
  announceRenderer(false);
  $('detector-gl').hidden=false;
  // Overlay: labels, moving particle heads, triad and scale stay crisp in 2D.
  canvas.width=Math.round(width*dpr);canvas.height=Math.round(height*dpr);
  context.setTransform(dpr,0,0,dpr,0,0);context.clearRect(0,0,width,height);
  screenTracks=[];
  (result?.tracks||[]).forEach((track,index)=>{
    const path=trackPaths[index]||[],color=trackColor(track),isSelected=track.object_id===selectedTrackId();
    const points=track.points.map(project);screenTracks.push({id:track.object_id,points});
    const end=path.at(-1)||0;
    if(time<end){
      const head=project(pointAt(track,path,time)),glow=context.createRadialGradient(...head,0,...head,14);
      glow.addColorStop(0,'#ffffff');glow.addColorStop(.25,color);glow.addColorStop(1,color+'00');
      context.fillStyle=glow;context.beginPath();context.arc(...head,14,0,2*Math.PI);context.fill();
    }else{
      const last=points.at(-1);
      context.fillStyle=color;context.beginPath();context.arc(...last,isSelected?4:3,0,2*Math.PI);context.fill();
      context.font='12px Segoe UI,sans-serif';context.fillText(`${track.charge<0?'μ−':'μ+'} #${track.object_id}`,last[0]+7,last[1]-7);
    }
    if(result?.mode==='analytic'&&track.material?.state?.position&&time>=1)
      drawMaterialMarker(project,track.material.state.position,track.object_id===0||isSelected);
  });
  if(result?.tracks?.length&&time<.8){
    const ip=project([0,0,0]),r=6+time*40;
    context.strokeStyle=`rgba(255,240,200,${Math.max(0,1-time/.8)})`;context.lineWidth=2;
    context.beginPath();context.arc(...ip,r,0,2*Math.PI);context.stroke();
  }
  if(Number.isFinite(playback.time)){
    context.fillStyle='#e7edf3';context.font='12px Consolas,monospace';
    context.fillText(`displayed path ${time.toFixed(2)} m · accelerated visualization`,15,22);
  }
  drawTriadAndScale(width,height,extent,scale);
}
function updateTimeline(){
  const max=playback.max||0;$('timeline').disabled=!max;
  $('timeline').value=String(Number.isFinite(playback.time)&&max?Math.round(1000*playback.time/max):1000);
  $('replay').textContent=playback.playing?'❚❚ Pause':'▶ Path replay';
  $('replay').setAttribute('aria-label',playback.playing?'Pause accelerated path replay':'Start accelerated path replay (Space)');
  $('replay').setAttribute('aria-pressed',String(playback.playing));
}
function tick(now){
  if(!playback.playing)return;
  // rAF timestamps can predate the performance.now() taken when replay started.
  const dt=Math.max(0,Math.min(.1,(now-playback.last)/1000));playback.last=Math.max(now,playback.last);
  playback.time+=dt*Number($('replay-speed').value)*4;
  if(playback.time>=playback.max){playback.time=Infinity;playback.playing=false;}
  draw();updateTimeline();
  if(playback.playing)playback.frame=requestAnimationFrame(tick);
}
function replay(fromStart=true){
  if(!result?.tracks?.length||!playback.max){playback.time=Infinity;updateTimeline();return;}
  if(reducedMotion&&fromStart){playback.time=Infinity;draw();updateTimeline();return;}
  cancelAnimationFrame(playback.frame);
  if(fromStart||!Number.isFinite(playback.time))playback.time=0;
  playback.playing=true;playback.last=performance.now();playback.frame=requestAnimationFrame(tick);updateTimeline();
}
function pauseReplay(){playback.playing=false;cancelAnimationFrame(playback.frame);updateTimeline();}
$('replay').onclick=()=>playback.playing?pauseReplay():replay(!Number.isFinite(playback.time));
$('timeline').oninput=()=>{
  // Read the slider before pausing: pausing re-syncs the slider to the clock.
  const f=Number($('timeline').value)/1000;pauseReplay();
  playback.time=f>=1?Infinity:f*playback.max;draw();updateTimeline();
};
new ResizeObserver(draw).observe(canvas);

// Live mode: every slider move recomputes one bench event on the local
// backend (same physics as Run) and redraws it. Previews are never saved.
const liveInputs={'live-p':'momentum','live-b':'field','live-thick':'thickness'};
function liveLabels(){
  $('live-p-out').textContent=Number($('momentum').value).toFixed(1)+' GeV/c';
  $('live-b-out').textContent=Number($('field').value).toFixed(1)+' T';
  $('live-thick-out').textContent=Number($('thickness').value).toFixed(1)+' mm';
  $('live-eta-out').textContent=live.eta.toFixed(2);
  $('live-phi-out').textContent=live.phi.toFixed(2)+' rad';
  const p=Number($('momentum').value),pt=p/Math.cosh(live.eta),b=Math.abs(Number($('field').value));
  $('live-radius').textContent=!b?'No field: straight tracks':Number.isFinite(curvatureConversion)?`Helix radius ≈ pT/(k·B), k=${curvatureConversion} GeV/(c·T·m) = ${(pt/(curvatureConversion*b)).toFixed(2)} m`:'Loading sourced curvature constant…';
}
function syncLiveSliders(){
  $('live-p').value=String(Math.round(100*Math.log10(Number($('momentum').value))));
  $('live-b').value=$('field').value;$('live-thick').value=$('thickness').value;
  $('live-eta').value=String(live.eta);$('live-phi').value=String(live.phi);
  $('live-b').disabled=$('field-model').value==='cms_tracker';
  liveLabels();
}
async function livePreview(){
  if(!live.enabled)return;
  if(live.busy){live.pending=true;return;}
  if($('mode').value!=='analytic'){$('live-state').textContent='Live mode needs the muon bench, not collisions.';$('live-state').classList.add('error');return;}
  live.busy=true;const started=performance.now();
  try{
    await sessionReady;
    // The aimed pair replaces the angular source, so its sampling limits do not apply.
    // The server validates everything else and is the authority on what is allowed.
    const value=await api('preview',{config:{...config(),source_model:'transverse_pair',events:1},eta:live.eta,phi:live.phi});
    if(live.enabled){show(value,null);$('live-state').textContent=`Updated in ${Math.round(performance.now()-started)} ms`;$('live-state').classList.remove('error');}
  }catch(error){
    const reason=/Value error, ([^[\n]+)/.exec(error.message)?.[1]||error.message.split('\n')[0];
    $('live-state').textContent='Not computed: '+reason.trim().slice(0,160);$('live-state').classList.add('error');
  }
  finally{live.busy=false;if(live.pending){live.pending=false;livePreview();}}
}
function setLive(enabled){
  live.enabled=enabled;$('live-toggle').setAttribute('aria-pressed',String(enabled));
  $('live-panel').hidden=!enabled;
  if(enabled){
    if(active){live.enabled=false;$('live-panel').hidden=true;$('live-toggle').setAttribute('aria-pressed','false');log('Finish or stop the active run before using live mode.');return;}
    if(window.currentWorkspace!=='display')setWorkspace('display');
    syncLiveSliders();pauseReplay();playback.time=Infinity;livePreview();
  }
}
$('live-toggle').onclick=()=>setLive(!live.enabled);
for(const [id,target] of Object.entries(liveInputs))$(id).addEventListener('input',()=>{
  // Momentum slider is logarithmic (1–100 GeV/c) and snaps to the input's 0.1 step.
  $(target).value=id==='live-p'?String(Math.round(10*10**(Number($(id).value)/100))/10):$(id).value;
  updateMode();liveLabels();livePreview();
});
for(const [id,key] of [['live-eta','eta'],['live-phi','phi']])$(id).addEventListener('input',()=>{live[key]=Number($(id).value);liveLabels();livePreview();});
for(const id of [...Object.keys(liveInputs),'live-eta','live-phi'])$(id).addEventListener('change',()=>changed());
$('live-replay').onclick=()=>replay(true);
function setProjection(value) {
  projection=value; for(const [id,name]of [['xy-xz','xy-xz'],['xy','xy'],['xz','xz'],['three-d','3d']])$(id).setAttribute('aria-pressed',String(value===name));
  $('view-label').textContent=value==='3d'?'3D · orbit / orthographic':value==='xy-xz'?'XY + XZ · synchronized orthographic':value.toUpperCase()+' · orthographic';
  $('navigation-hint').textContent=value==='3d'?'Drag: orbit · Shift+drag: pan · wheel or +/−: zoom':value==='xy-xz'?'Both views share selection, path cursor, pan and zoom':'Drag: pan · wheel or +/−: zoom';
  $('show-modules').disabled=value==='xy-xz';$('show-modules').parentElement.title=value==='xy-xz'?'Detailed CMS module overlays are available in the single projection and 3D views.':'Toggle available CMS display geometry.';
  document.querySelector('.surface-tools').hidden=value==='xy-xz';
  $('rotate-view').disabled=value==='xy-xz';draw();
}
$('xy-xz').onclick=()=>setProjection('xy-xz');$('xy').onclick=()=>setProjection('xy');$('xz').onclick=()=>setProjection('xz');$('three-d').onclick=()=>setProjection('3d');
function updateZoomControls(){
  $('zoom-level').value=`${Math.round(zoom*100)}%`;
  $('zoom-in').disabled=zoom>=128;$('zoom-out').disabled=zoom<=.1;
}
function updateCutawayControls(){
  $('cutaway-angle-out').value=`${$('cutaway-angle').value}°`;
  $('cutaway-opening-out').value=`${$('cutaway-opening').value}°`;
  $('cutaway-angle').disabled=!$('cutaway').checked;$('cutaway-opening').disabled=!$('cutaway').checked;
}
for(const id of ['detector-style','cutaway','cutaway-angle','cutaway-opening'])$(id).oninput=()=>{updateCutawayControls();draw();};
updateCutawayControls();
function changeZoom(factor,anchor){
  const rect=(projection==='xy-xz'?linkedViews:canvas).getBoundingClientRect();
  const next=Math.max(.1,Math.min(128,zoom*factor)),ratio=next/zoom;
  const point=anchor||[rect.width/2,rect.height/2];
  pan=[point[0]-rect.width/2-(point[0]-rect.width/2-pan[0])*ratio,
       point[1]-rect.height/2-(point[1]-rect.height/2-pan[1])*ratio];
  zoom=next;updateZoomControls();draw();
}
function fit(){zoom=1;pan=[0,0];orbit=[-.65,.55];roll=0;updateZoomControls();draw();}
$('rotate-view').onclick=()=>{roll=(roll+Math.PI/2)%(Math.PI*2);draw();};
$('reset-opacity').onclick=()=>{for(const id of ['pixel','strips','ecal','hcal','dt','csc','rpc','shell'])setOpacity(id,id==='shell'?.2:1);draw();};
$('shell-opacity-controls').append(opacityControl('shell','Tracker shell'));
$('show-envelope').onchange=draw;
$('event-focus').onclick=()=>{
  const button=$('event-focus');
  if(eventFocusSnapshot){
    const saved=eventFocusSnapshot;eventFocusSnapshot=null;
    $('detector-focus').value=saved.region;$('detector-style').value=saved.style;
    for(const [id,value]of Object.entries(saved.checkboxes))$(id).checked=value;
    hiddenDisplay.clear();for(const id of saved.hiddenDisplay)hiddenDisplay.add(id);
    document.querySelectorAll('[data-display-layer]').forEach(input=>input.checked=!hiddenDisplay.has(input.dataset.displayLayer));
    for(const id of ['pixel','strips','ecal','hcal','dt','csc','rpc','shell'])setOpacity(id,saved.opacity[id]??(id==='shell'?.2:1));
    zoom=saved.zoom;pan=saved.pan;orbit=saved.orbit;roll=saved.roll;
    button.textContent='Event focus';button.title='Show the tracker with the event path, then restore your previous display settings';button.setAttribute('aria-pressed','false');
    updateZoomControls();updateCutawayControls();setProjection(saved.projection);return;
  }
  eventFocusSnapshot={
    region:$('detector-focus').value,style:$('detector-style').value,
    checkboxes:Object.fromEntries(['cutaway','show-grid','show-guides','show-modules','show-envelope'].map(id=>[id,$(id).checked])),
    opacity:Object.fromEntries(layerOpacity),hiddenDisplay:[...hiddenDisplay],projection,zoom,pan:[...pan],orbit:[...orbit],roll
  };
  $('detector-focus').value='tracker';$('detector-style').value='solid';$('cutaway').checked=false;
  $('show-grid').checked=false;$('show-guides').checked=false;$('show-modules').checked=true;$('show-envelope').checked=true;
  for(const id of ['pixel','strips','ecal','hcal','dt','csc','rpc'])setOpacity(id,id==='pixel'?.15:id==='strips'?.03:.05);
  setOpacity('shell',.2);
  for(const id of ['pixel','strips'])hiddenDisplay.delete(id);
  document.querySelectorAll('[data-display-layer]').forEach(input=>input.checked=!hiddenDisplay.has(input.dataset.displayLayer));
  zoom=1;pan=[0,0];orbit=[-.65,.25];roll=Math.PI/2;updateZoomControls();updateCutawayControls();
  button.textContent='Restore view';button.title='Restore the display settings from before Event focus';button.setAttribute('aria-pressed','true');setProjection('3d');draw();
};
$('zoom-in').onclick=()=>changeZoom(1.4);
$('zoom-out').onclick=()=>changeZoom(1/1.4);
$('focus-core').onclick=()=>{
  $('detector-focus').value='pixel';$('show-modules').checked=true;
  $('show-grid').checked=false;$('show-guides').checked=false;
  hiddenDisplay.delete('pixel');
  setOpacity('pixel',1);
  document.querySelectorAll('[data-display-layer="pixel"]').forEach(input=>input.checked=true);
  fit();
};
$('detector-focus').onchange=fit;
$('reset-view').onclick=fit;$('show-grid').onchange=draw;$('show-guides').onchange=draw;
// Handle both canvas surfaces and captions; leave the live panel's own scroll intact.
canvas.parentElement.addEventListener('wheel',event=>{
  if(event.target.closest('#live-panel'))return;
  event.preventDefault();
  const rect=canvas.getBoundingClientRect();
  const delta=event.deltaY*(event.deltaMode===1?16:event.deltaMode===2?rect.height:1);
  changeZoom(Math.exp(-Math.max(-240,Math.min(240,delta))*(event.ctrlKey?.01:.002)),[event.clientX-rect.left,event.clientY-rect.top]);
},{passive:false,capture:true});
canvas.addEventListener('pointerdown',event=>{drag={x:event.clientX,y:event.clientY,pan:[...pan],orbit:[...orbit],orbiting:projection==='3d'&&!event.shiftKey};canvas.setPointerCapture(event.pointerId);});
canvas.addEventListener('pointermove',event=>{
  if(!drag)return;const x=event.clientX-drag.x,y=event.clientY-drag.y;
  if(drag.orbiting)orbit=[drag.orbit[0]+x*.008,Math.max(-1.45,Math.min(1.45,drag.orbit[1]+y*.008))];
  else pan=[drag.pan[0]+x,drag.pan[1]+y];draw();
});
canvas.addEventListener('pointerup',event=>{
  if(drag&&Math.hypot(event.clientX-drag.x,event.clientY-drag.y)<4){
    const rect=canvas.getBoundingClientRect(),p=[event.clientX-rect.left,event.clientY-rect.top];let best=null,distance=10;
    for(const track of screenTracks)for(const q of track.points){const d=Math.hypot(q[0]-p[0],q[1]-p[1]);if(d<distance){best=track.id;distance=d;}}
    if(best!==null)selectTrack(best);
  }drag=null;
});canvas.addEventListener('pointercancel',()=>drag=null);
const linkedViews=$('linked-projection-pair');
new ResizeObserver(draw).observe(linkedViews);window.addEventListener('resize',draw);
linkedViews.addEventListener('click',event=>{
  const track=event.target.closest('[data-track-id]');if(track)selectTrack(Number(track.dataset.trackId));
});
linkedViews.addEventListener('keydown',event=>{
  if((event.key==='Enter'||event.key===' ')&&event.target.closest('[data-track-id]')){
    event.preventDefault();selectTrack(Number(event.target.closest('[data-track-id]').dataset.trackId));
  }
});
linkedViews.addEventListener('pointerdown',event=>{
  if(projection!=='xy-xz'||event.target.closest('[data-track-id]'))return;
  pairDrag={x:event.clientX,y:event.clientY,pan:[...pan]};linkedViews.setPointerCapture(event.pointerId);
});
linkedViews.addEventListener('pointermove',event=>{
  if(!pairDrag)return;pan=[pairDrag.pan[0]+event.clientX-pairDrag.x,pairDrag.pan[1]+event.clientY-pairDrag.y];draw();
});
linkedViews.addEventListener('pointerup',()=>{pairDrag=null;});
linkedViews.addEventListener('pointercancel',()=>{pairDrag=null;});
linkedViews.addEventListener('wheel',event=>{
  if(projection!=='xy-xz')return;event.preventDefault();changeZoom(event.deltaY>0?1/1.12:1.12);
},{passive:false});

function property(name,value){const dt=document.createElement('dt'),dd=document.createElement('dd');dt.textContent=name;dd.textContent=value;$('properties').append(dt,dd);}
function selectionEventId(){
  if(!result)return null;
  if(result.mode==='cms'&&result.identity)return `cms:${result.identity.run}:${result.identity.lumi}:${result.identity.event}`;
  return `${displayedJob||'preview'}:${result.event??0}`;
}
function selectedTrackId(){return selected?.kind==='muon'?selected.object_id:null;}
function selectTrack(id,{focus=true}={}) {
  document.querySelectorAll('[data-section]').forEach(b=>{b.classList.remove('selected');b.setAttribute('aria-selected','false');});
  document.querySelectorAll('#particle-rows tr[data-object-group]').forEach(row=>row.setAttribute('aria-selected','false'));
  const track=result?.tracks.find(t=>t.object_id===id);
  selected=track?{kind:'muon',event_id:selectionEventId(),object_id:id}:null;
  $('properties').replaceChildren();
  document.querySelectorAll('#track-list button').forEach(b=>(b.setAttribute('aria-pressed',String(Number(b.dataset.id)===id)),b.setAttribute('aria-selected',String(Number(b.dataset.id)===id))));
  document.querySelectorAll('#particle-rows tr[data-id]').forEach(row=>row.setAttribute('aria-selected',String(Number(row.dataset.id)===id)));
  if(!track){$('selection-path').textContent='No particle selected';draw();return;}
  const name=track.charge<0?'μ−':'μ+';$('selection-title').textContent=name+' / '+id;
  $('selection-path').textContent=`Event ${result.event} / Muon / ${id}`;
  property('Selection kind',selected.kind);property('Event identity',selected.event_id);
  property('Model IDs',(track.model_ids||[]).join(', ')||'Not declared');
  property('PDG ID',track.pdg_id);property('Charge',track.charge+' e');
  if(['pythia','cms'].includes(result.mode)) {
    property('pT',track.detector.pt.toFixed(4)+' GeV/c');property('η',track.detector.eta.toFixed(5));
    property('φ',track.detector.phi.toFixed(5)+' rad');property('Isolation',String(track.detector.iso));
    property('Source',result.mode==='cms'?'Recorded CMS NanoAOD muon':'DELPHES reconstructed muon');property('Display','IP-assumed ideal-solenoid extrapolation; not hits or fitted tracks');
  } else {
    property('Input |p|',result.config.momentum_gev+' GeV/c');
    const momentum=track.truth.momentum, pt=Math.hypot(momentum.px,momentum.py);
    property('Truth pT',pt.toFixed(5)+' GeV/c');property('η',Math.asinh(momentum.pz/pt).toFixed(5));
    property('Material deposit',(track.material.deposit_gev*1000).toFixed(6)+' MeV');
    property('Scattering θ₀',(track.material.theta0_rad*1e6).toFixed(4)+' μrad');
    property('Analog signal',track.digit.analog_adc.toFixed(4)+' ADC');
    property('Digitized channel',track.digit.accepted?track.digit.adc+' ADC':'Suppressed below threshold');
    property('Saturation',track.digit.saturated?'Saturated':'No');
    property('Energy residual',track.material.energy_residual_gev.toExponential(4)+' GeV');
    property('Outgoing energy',track.material.state.momentum.energy.toFixed(8)+' GeV');
  }
  property('Predicted crossings',track.trajectory?.crossings.length||0);
  if(track.material_reference)property('Material reference',track.material_reference.id);
  if(track.reference_response){
    const response=track.reference_response, sampled=response.sample.objects[0]?.state.momentum;
    property('Tracking reference sample',sampled?'Accepted':'Inefficient / lost');
    property('Sampled pT',sampled?Math.hypot(sampled.px,sampled.py).toFixed(5)+' GeV/c':'Lost / no reconstructed object');
    property('Reference efficiency',response.parameters.efficiency.toFixed(4));
    property('Relative pT resolution',(response.parameters.relative_pt_resolution*100).toFixed(3)+'%');
    property('Momentum scale',response.parameters.momentum_scale.toFixed(7));
    property('Response scope',response.parameters.validation_scope);
  }
  property('Validation',result.mode==='cms'?'Recorded momentum; ideal display extrapolation, no hit-level reconstruction':'Educational analytic path; PDG mean-table reference only; slab, scattering and electronics unvalidated');if(focus)activateTab('inspector','selection');draw();
}
const OBJECT_ROWS=[['jets','Jet','NanoAOD jet'],['electrons','Electron','NanoAOD electron'],['photons','Photon','NanoAOD photon'],['taus','Tau','NanoAOD tau'],['isotracks','Isolated track','NanoAOD isolated track']];
function selectObject(label,object,group){
  selected={kind:`nanoaod:${group}`,event_id:selectionEventId(),object_id:object.index??'met'};
  document.querySelectorAll('#track-list button').forEach(button=>{button.setAttribute('aria-pressed','false');button.setAttribute('aria-selected','false');});
  document.querySelectorAll('#particle-rows tr').forEach(row=>row.setAttribute('aria-selected','false'));
  const objectRow=group==='met'?document.querySelector('#particle-rows tr.object-row:last-of-type'):document.querySelector(`#particle-rows tr[data-object-group="${group}"][data-object-index="${object.index}"]`);
  if(objectRow)objectRow.setAttribute('aria-selected','true');
  activateTab('inspector','selection');$('selection-title').textContent=label;
  $('selection-path').textContent=`Run ${result.identity.run} / event ${result.identity.event} / ${label}`;$('properties').replaceChildren();
  property('Selection kind',selected.kind);property('Event identity',selected.event_id);
  property('Model IDs',(result.display_model_spec?.components||result.model_spec?.components||[]).map(item=>`${item.id} v${item.version}`).join(', ')||'Not declared');
  for(const [key,value] of Object.entries(object)){if(key==='points'||key==='index')continue;property(key,typeof value==='number'&&!Number.isInteger(value)?value.toPrecision(5):String(value));}
  property('Source',`${result.objects.source.file} · record ${result.objects.source.record}`);
  property('Display',group==='jets'?'Illustrative jet cone to ECAL; no measured charged-particle trajectory. Towers are schematic PF-fraction displays.':group==='electrons'?'Illustrative ideal 3.8 T path from the assumed IP; this is not a measured or fitted track. ECAL tower is schematic.':group==='met'?'Missing transverse momentum arrow; MET is not a particle trajectory.':'Direction from stored η/φ; not shown as a trajectory.');
  property('Validation','Reconstructed NanoAOD quantities; display geometry is illustrative, not hits or calibrated deposits');
  draw();
}
function appendObjectRows(){
  const objects=result?.objects;if(!objects)return;
  for(const [group,name,status] of OBJECT_ROWS)for(const object of objects[group]||[]){
    const row=document.createElement('tr');row.tabIndex=0;row.className='object-row';row.dataset.objectGroup=group;row.dataset.objectIndex=String(object.index);
    const p=object.pt*Math.cosh(object.eta),open=()=>selectObject(`${name} / ${object.index}`,object,group);
    row.onclick=open;row.onkeydown=event=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();open();}};
    cell(row,`${name} / ${object.index}`);cell(row,'—','number');cell(row,object.charge??'—','number');
    cell(row,p.toFixed(3),'number');cell(row,object.pt.toFixed(3),'number');cell(row,'—','number');cell(row,'—','number');
    cell(row,status+(group==='jets'?` · ID ${object.jet_id}`:object.cut_based_id!==undefined?` · ID ${object.cut_based_id}`:''));cell(row,'—','number');cell(row,object.eta.toFixed(3),'number');
    $('particle-rows').append(row);
  }
  if(objects.met){
    const row=document.createElement('tr');row.tabIndex=0;row.className='object-row';
    const open=()=>selectObject('Missing pT',objects.met,'met');row.onclick=open;
    row.onkeydown=event=>{if(event.key==='Enter'){event.preventDefault();open();}};
    cell(row,'Missing pT');cell(row,'—','number');cell(row,'—','number');cell(row,'—','number');cell(row,objects.met.pt.toFixed(3),'number');
    cell(row,'—','number');cell(row,'—','number');cell(row,`NanoAOD PF MET · φ ${objects.met.phi.toFixed(3)}`);cell(row,'—','number');cell(row,'—','number');
    $('particle-rows').append(row);
  }
}
function show(value,jobId=displayedJob) {
  const previousSelection=selected,isPreview=!!value.preview;
  result=value;displayedJob=jobId;$('download').disabled=false;
  if(!isPreview)lastFailure=null;
  if(!active||active===jobId){$('status').textContent='COMPLETED';$('operation-status').textContent='Completed result';}
  $('track-list').replaceChildren();$('particle-rows').replaceChildren();$('crossing-rows').replaceChildren();
  if(value.geometry)detectorGeometry=value.geometry;
  document.querySelector('#particle-table thead th:nth-child(5)').textContent=result.mode!=='analytic'?'Reconstructed pT / GeV':'Truth pT / GeV';
  const tracks=result.tracks||[];
  for(const track of tracks) {
    const button=document.createElement('button');button.dataset.id=track.object_id;
    button.textContent=`${track.charge<0?'μ−':'μ+'} [${track.object_id}]`;button.setAttribute('role','treeitem');
    button.onclick=()=>selectTrack(track.object_id);$('track-list').append(button);
    const row=document.createElement('tr');row.dataset.id=track.object_id;row.tabIndex=0;row.onclick=()=>selectTrack(track.object_id);
    row.onkeydown=event=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();selectTrack(track.object_id);}};
    cell(row,'Muon / '+track.object_id);cell(row,track.pdg_id,'number');cell(row,track.charge,'number');
    if(result.mode==='analytic') {
      const p=track.truth.momentum;
      cell(row,Math.hypot(p.px,p.py,p.pz).toFixed(3),'number');cell(row,Math.hypot(p.px,p.py).toFixed(3),'number');
      cell(row,(track.material.deposit_gev*1000).toFixed(4),'number');cell(row,track.digit.adc??'—','number');
      cell(row,track.digit.saturated?'Saturated':track.digit.accepted?'Digit accepted':'Below threshold');
    }else{
      cell(row,(track.detector.pt*Math.cosh(track.detector.eta)).toFixed(3),'number');
      cell(row,track.detector.pt.toFixed(3),'number');cell(row,'—','number');cell(row,'—','number');cell(row,result.mode==='cms'?'CMS recorded muon':'DELPHES reconstructed');
    }
    const sampled=track.reference_response?.sample.objects[0]?.state.momentum;
    cell(row,sampled?Math.hypot(sampled.px,sampled.py).toFixed(3):track.reference_response?'Lost':'—','number');
    const p=track.truth?.momentum;
    cell(row,p?Math.asinh(p.pz/Math.hypot(p.px,p.py)).toFixed(3):track.detector.eta.toFixed(3),'number');
    $('particle-rows').append(row);
  }
  for(const track of tracks)for(const crossing of track.trajectory?.crossings||[]) {
    const row=document.createElement('tr');cell(row,track.object_id);cell(row,crossing.surface_id);
    for(const value of [crossing.path_m,...crossing.position_m,crossing.time_ns])cell(row,value.toFixed(6),'number');
    row.onclick=()=>selectTrack(track.object_id);$('crossing-rows').append(row);
  }
  if(!tracks.length){const row=document.createElement('tr');const td=cell(row,'No reconstructed muons in this event.');td.colSpan=10;$('particle-rows').append(row);}
  $('object-count').textContent=tracks.length;$('particle-total').textContent=tracks.length;
  $('empty-state').hidden=true;$('display-note').textContent=result.display;
  $('event-label').textContent='Event '+result.event;$('event-index').value=result.event;
  const count=result.events||result.summary?.events||1;
  $('event-index').max=count-1;$('event-index').disabled=count<=1;$('event-total').textContent='/ '+(count-1);
  $('previous-event').disabled=result.event<=0;$('next-event').disabled=result.event>=count-1;
  $('previous-event').title=result.event<=0?'This is the first event':'Previous event (←)';
  $('next-event').title=result.event>=count-1?(count<=1?'This result has one event':'This is the last event'):'Next event (→)';
  $('event-source').textContent=result.mode==='analytic'?`${result.backend} · ${count>1?'angular sample':'declared μμ fixture'}`:'PYTHIA8 → DELPHES · reconstructed muons';
  if(result.mode==='cms'){
    const id=result.identity;
    $('event-source').textContent=`CMS recorded · selected event ${result.event+1} of ${count}`;
    $('event-label').textContent=`Run ${id.run} / lumi ${id.lumi} / event ${id.event}`;
    $('event-details').hidden=false;
    $('event-details').textContent=`Run ${id.run} · lumi ${id.lumi} · event ${id.event} · ROOT entry ${id.entry} · selected pair mass ${result.mass_gev.toFixed(3)} GeV · all reconstructed muons shown`;
    $('next-selected-event').hidden=true;
    $('metric-events').textContent=`Selected CMS events: ${count}`;
    for(const name of ['deposit','digits','residual'])$('metric-'+name).textContent='';
    $('dirty').textContent='Saved CMS selection '+result.analysis_id.slice(0,8);
    $('operation-status').textContent='Recorded CMS event';
    appendObjectRows();
    const objects=result.objects,objectCount=objects?objects.jets.length+objects.electrons.length+objects.photons.length+objects.taus.length+objects.isotracks.length:0;
    $('particle-total').textContent=tracks.length+objectCount;
    if(objects)$('event-details').textContent+=` · ${objects.jets.length} jets · ${objects.electrons.length} electrons · ${objects.photons.length} photons · MET ${objects.met.pt.toFixed(1)} GeV · ${objects.vertex.good_vertices} good vertices`;
    else if(result.objects_unavailable)$('event-details').textContent+=' · '+result.objects_unavailable;
    selected=null;if(tracks.length)selectTrack(tracks[0].object_id);else draw();
    renderObjectToggles();
    replay();
    return;
  }
  $('metric-events').textContent='Events: '+count;
  const bench=result.mode==='analytic';
  $('metric-deposit').textContent='Event deposit: '+(bench?(tracks.reduce((a,t)=>a+t.material.deposit_gev,0)*1000).toFixed(3)+' MeV':'not read');
  $('metric-digits').textContent='Channels: '+(bench?tracks.filter(t=>t.digit.accepted).length+'/'+tracks.length:'—');
  $('metric-residual').textContent='Energy residual: '+(bench?Math.max(...tracks.map(t=>Math.abs(t.material.energy_residual_gev))).toExponential(2)+' GeV':result.summary.max_truth_four_momentum_residual_gev.toExponential(2)+' GeV (run max)');
  const info=result.event_info;
  $('event-details').hidden=!info;
  $('event-details').textContent=info?`Event weight ${info.weight} · ${info.muons} muons · ${info.jets} jets · missing pT ${info.met_gev===null?'unavailable':info.met_gev.toFixed(2)+' GeV'} · ${info.selected?'passes dimuon selection':'fails dimuon selection'}${info.mass_gev===null?'':' · pair mass '+info.mass_gev.toFixed(3)+' GeV'}`:'';
  $('next-selected-event').hidden=result.mode!=='pythia';
  $('next-selected-event').disabled=!(result.analysis?.selected_events>0);
  if(isPreview){
    $('event-source').textContent='Live preview · '+result.backend+' · not saved';
    $('operation-status').textContent='Live preview';
    selected=null;const previousTrackId=previousSelection?.kind==='muon'?previousSelection.object_id:null;
    const keep=tracks.find(t=>t.object_id===previousTrackId)??tracks[0];
    if(keep)selectTrack(keep.object_id,{focus:false});else draw();
  }else{
    selected=null;if(tracks.length)selectTrack(tracks[0].object_id);else{$('properties').replaceChildren();$('selection-path').textContent='No reconstructed muons in this event';draw();}
  }
  changed(false);updateCapabilities();renderHistory();renderAnalysis();renderObjectToggles();
  if(!isPreview)replay();else updateTimeline();
}
async function loadEvent(index) {
  if(result?.mode==='cms'){await window.cmsLoadEvent(result.analysis_id,index);return;}
  if(!displayedJob||!result||index<0||index>= (result.events||result.summary?.events||1))return;
  const job=displayedJob;
  try{const value=await api(`jobs/${job}/events/${index}`);if(displayedJob===job)show({...value,config:result.config},job);}
  catch(error){log(error.message);activateTab('results','diagnostics');}
}
$('previous-event').onclick=()=>loadEvent(result.event-1);$('next-event').onclick=()=>loadEvent(result.event+1);
$('event-index').onchange=()=>{const n=Number($('event-index').value);if(Number.isInteger(n))loadEvent(n);};
$('next-selected-event').onclick=()=>{const rows=result?.analysis?.event_rows.filter(row=>row.selected)||[];const next=rows.find(row=>row.event>result.event)||rows[0];if(next)loadEvent(next.event);};
function renderHistory(){
  $('run-history').replaceChildren();
  if(!sessionRuns.length){const p=document.createElement('p');p.textContent='No runs in this session.';p.className='muted inset';$('run-history').append(p);}
  for(const run of [...sessionRuns].reverse()){
    const button=document.createElement('button'),dot=document.createElement('span');dot.className='run-state '+run.status;
    const label=run.config?(run.config.mode==='pythia'?`${run.config.events} pp events · seed ${run.config.seed}`:`${run.config.momentum_gev} GeV · seed ${run.config.seed} · ${run.config.backend}`):run.id.slice(0,8);
    const when=run.created_utc?new Date(run.created_utc):null;
    const stamp=when&&!isNaN(when)?when.toLocaleString([], {month:'short',day:'numeric',hour:'2-digit',minute:'2-digit'})+' · ':'';
    button.append(dot,document.createTextNode(`${stamp}${label} · ${run.status}`));button.classList.toggle('active',run.id===displayedJob);
    button.title=`Run ${run.id}${run.mode?' · '+run.mode:''}`;
    button.disabled=run.status!=='completed'||!!active;button.onclick=async()=>{
      try{if(!run.result){run.result=checkResultFormat(await api('runs/'+run.id));run.config=run.result.config;}
        if(!run.config||!Array.isArray(run.result.tracks))throw Error('This artifact is not a workbench event.');
        applyConfig(run.config);changed();show({...run.result,config:run.config},run.id);
      }catch(error){log(error.message);activateTab('results','diagnostics');}
    };$('run-history').append(button);
  }
  const previous=$('compare-run').value;
  $('compare-run').replaceChildren(new Option('No comparison',''));
  for(const run of [...sessionRuns].reverse())if(run.status==='completed'&&run.id!==displayedJob)$('compare-run').append(new Option(run.config?`${run.config.mode==='pythia'?run.config.events+' pp events':run.config.momentum_gev+' GeV'} · seed ${run.config.seed} · ${run.id.slice(0,6)}`:run.id.slice(0,8),run.id));
  if([...$('compare-run').options].some(o=>o.value===previous))$('compare-run').value=previous;
}
async function refreshRuns(){
  try{const saved=await api('runs');for(const run of saved)if(!sessionRuns.some(r=>r.id===run.id))sessionRuns.unshift({...run,status:'completed'});renderHistory();}
  catch(error){log('Saved runs could not load: '+error.message);}
}
$('refresh-runs').onclick=refreshRuns;
function busy(value){inputIds.forEach(id=>$(id).disabled=value);$('cancel').disabled=!value;$('save-setup').disabled=value;$('load-setup').disabled=value;changed(false);renderHistory();}
async function poll(id, failures=0) {
  let terminal=false;
  try{
    const job=await api('jobs/'+id),entry=sessionRuns.find(r=>r.id===id);Object.assign(entry,job);
    $('status').textContent=job.status.toUpperCase();$('operation-status').textContent=job.progress?`${job.phase||job.status} · ${job.progress.completed}/${job.progress.total} events`:(job.phase||job.status);renderHistory();
    if(['queued','running'].includes(job.status)){setTimeout(()=>poll(id),400);return;}
    terminal=true;
    if(job.status==='completed'){
      entry.result={...job.result,config:job.config};show(entry.result,id);
      log(`Completed ${id}. ${job.result.mode}; validation: ${job.result.validation}.`);
      if(job.result.summary)log(`Accepted ${job.result.summary.events} events. Generator estimate ${job.result.summary.cross_section_pb} ± ${job.result.summary.cross_section_error_pb} pb (not independently validated).`);
      activateTab('results','particles');if(job.result.analysis)setWorkspace('analysis');
    }else{lastFailure=job.status;log(`${job.status}: ${job.error||'No result committed.'}`);activateTab('results','diagnostics');}
  }catch(error){
    // The job keeps running server-side; ride out transient poll failures before giving up.
    if(failures<5){setTimeout(()=>poll(id,failures+1),400*2**failures);return;}
    terminal=true;lastFailure='failed';log(error.message);$('status').textContent='ERROR';activateTab('results','diagnostics');}
  if(terminal){active=null;busy(false);reattach();}
}
// Runs are durable: after a reload or worker restart, pick up the oldest unfinished one.
async function reattach(){
  if(active)return;
  try{
    const live=(await api('jobs')).filter(j=>['queued','running'].includes(j.status)).at(-1);
    if(!live||active)return;
    if(!sessionRuns.some(r=>r.id===live.id))sessionRuns.push({...live});
    active=live.id;busy(true);log(`Reattached to ${live.status} run ${live.id}.`);poll(live.id);
  }catch(error){log('Run queue unavailable: '+error.message);}
}
$('run-form').onsubmit=async event=>{
  event.preventDefault();if(active||!$('run-form').reportValidity())return;
  const submitted=config(),requestConfig=runConfigEnvelope(submitted);$('run-button').disabled=true;lastFailure=null;
  $('status').textContent='SUBMITTING';$('operation-status').textContent='Submitting run…';$('next-seed').disabled=true;
  try{const job=await api('jobs',requestConfig,{'Idempotency-Key':crypto.randomUUID()});active=job.id;sessionRuns.push({...job,config:submitted,created_utc:new Date().toISOString()});busy(true);
    log(`Submitted ${job.id}: ${submitted.mode}, seed ${submitted.seed}.`);activateTab('results','diagnostics');poll(job.id);
  }catch(error){lastFailure='rejected';log(error.message);$('status').textContent='FAILED';activateTab('results','diagnostics');changed(false);}
};
$('cancel').onclick=async()=>{if(!active)return;try{await api('jobs/'+active+'/cancel',{});log('Cancellation requested; waiting for the worker to stop.');$('cancel').disabled=true;}catch(error){log(error.message);}};

for(const [id,variable,side] of [['left-splitter','--left',1],['right-splitter','--right',-1]]){
  const element=$(id);let resizing=null;
  element.onpointerdown=event=>{resizing={x:event.clientX,width:parseFloat(getComputedStyle(document.documentElement).getPropertyValue(variable))};element.setPointerCapture(event.pointerId);};
  element.onpointermove=event=>{if(resizing)document.documentElement.style.setProperty(variable,Math.max(170,Math.min(440,resizing.width+side*(event.clientX-resizing.x)))+'px');};
  element.onpointerup=()=>resizing=null;element.onpointercancel=()=>resizing=null;
  element.onkeydown=event=>{if(['ArrowLeft','ArrowRight'].includes(event.key)){event.preventDefault();const width=parseFloat(getComputedStyle(document.documentElement).getPropertyValue(variable));document.documentElement.style.setProperty(variable,Math.max(170,Math.min(440,width+(event.key==='ArrowRight'?10:-10)*side))+'px');}};
}
document.addEventListener('keydown',event=>{
  if(guidedTour) return;
  const editing=['INPUT','SELECT','TEXTAREA'].includes(document.activeElement.tagName);
  if(event.key==='F5'){
    event.preventDefault();
    if(window.currentWorkspace==='data'){if(!$('data-apply').disabled)$('data-cuts').requestSubmit();}
    else if(!$('run-button').disabled)$('run-form').requestSubmit();
  }
  if(event.key==='Escape'&&active)$('cancel').click();
  if((event.ctrlKey||event.metaKey)&&event.key.toLowerCase()==='s'){event.preventDefault();$('download').click();}
  if(!editing&&(event.ctrlKey||event.metaKey)&&['z','y'].includes(event.key.toLowerCase())){event.preventDefault();restore(historyIndex+(event.key.toLowerCase()==='z'?-1:1));}
  if(!editing&&!event.ctrlKey&&!event.metaKey&&!event.altKey&&window.currentWorkspace==='display'&&result){
    if(['ArrowRight','PageDown'].includes(event.key)&&!$('next-event').disabled){event.preventDefault();loadEvent(result.event+1);}
    if(['ArrowLeft','PageUp'].includes(event.key)&&!$('previous-event').disabled){event.preventDefault();loadEvent(result.event-1);}
    if(event.key===' '&&!['BUTTON','A'].includes(document.activeElement.tagName)){event.preventDefault();$('replay').click();}
  }
  if(!editing&&!event.ctrlKey&&!event.metaKey&&window.currentWorkspace==='display'){if(event.key==='0')setProjection('xy-xz');if(event.key==='1')setProjection('xy');if(event.key==='2')setProjection('xz');if(event.key==='3')setProjection('3d');if(event.key.toLowerCase()==='f')fit();if(['+','=','-'].includes(event.key)){event.preventDefault();changeZoom(event.key==='-'?1/1.4:1.4);}}
});
changed();
setProjection('xy-xz');
const sessionReady=api('session').then(session=>{
  token=session.token;capabilities=session;
  curvatureConversion=session.constants?.values?.find(value=>value.name==='curvature_conversion')?.value??null;
  const rust=session.engine.rust_extension||session.engine.rust_executable_configured;
  $('backend').options[1].disabled=!rust;
  if(rust){$('backend').value='rust';changed();}
  $('connection').textContent='Local service connected';updateMode();
  liveLabels();
  log('Local service connected. Capability report is available.');
  refreshRuns();reattach();
}).catch(error=>{$('connection').textContent='Service unavailable';log(error.message);$('run-button').disabled=true;});

function inspectSurface(surface) {
  activateTab('inspector','selection');$('selection-title').textContent=surface.id;
  $('selection-path').textContent=detectorGeometry.id+' / '+surface.id;$('properties').replaceChildren();
  property('Surface',surface.kind);property('Subsystem',surface.subsystem);
  for(const key of ['radius_m','half_length_m','z_m','inner_radius_m','outer_radius_m'])if(key in surface)property(key,surface[key]+' m');
  property('Source',surface.source);property('Era',detectorGeometry.era);property('Geometry SHA256',detectorGeometry.sha256);
  property('Interpretation','Sourced surface/envelope; no full material or module map');
}
api('detector').then(value=>{
  detectorGeometry=value;$('geometry-tree').replaceChildren();
  for(const surface of value.surfaces) {
    const row=document.createElement('div');row.className='geometry-node';
    const toggle=document.createElement('input');toggle.type='checkbox';toggle.checked=true;toggle.setAttribute('aria-label','Show '+surface.id);
    toggle.onchange=()=>{toggle.checked?hiddenSurfaces.delete(surface.id):hiddenSurfaces.add(surface.id);draw();};
    const button=document.createElement('button');button.textContent=surface.id;button.onclick=()=>inspectSurface(surface);
    row.append(toggle,button);$('geometry-tree').append(row);
  }
  if(!result)$('empty-state').hidden=true;
  if(!result)$('display-note').textContent='CMS original pixel surfaces and detector envelopes / ideal solenoid';draw();
}).catch(error=>log(error.message));

function setWorkspace(name) {
  window.currentWorkspace=name;
  for(const value of ['data','analysis','display']){
    $(value+'-view').hidden=value!==name;
    $(value+'-tab').setAttribute('aria-selected',String(value===name));
  }
  if(name==='display')draw();
  const cms=name==='data';
  $('work-area').classList.toggle('cms-workspace',cms);
  document.body.classList.toggle('cms-data-active',cms);
  $('data-library-summary').hidden=!cms;
  document.querySelector('.scene-pane>.pane-title').textContent=cms?'Dataset library':'Model browser';
  for(const id of ['save-setup','load-setup','undo','redo','mode','backend','run-button'])$(id).hidden=cms;
  $('cancel').hidden=cms&&!active;
  document.querySelectorAll('.command-bar label').forEach(e=>e.hidden=cms);
  $('runtime-notice').hidden=cms||$('mode').value!=='pythia';
  $('download').disabled=cms?!window.cmsAnalysisAvailable:!result;
  updateMode();
  if(cms){$('operation-status').textContent='CMS data workspace';window.cmsRefreshStatus?.();}
  else{
    // Leaving the data view must not keep its label in the status bar.
    if(!active)$('operation-status').textContent=!result?'Ready':result.preview?'Live preview':result.mode==='cms'?'Recorded CMS event':'Completed result';
    changed(false);
  }
  if(name!=='display'&&live.enabled)setLive(false);
}
$('data-tab').onclick=()=>setWorkspace('data');
$('analysis-tab').onclick=()=>setWorkspace('analysis');
$('display-tab').onclick=()=>setWorkspace('display');
for(const [index,name] of ['data','analysis','display'].entries())$(name+'-tab').onkeydown=event=>{
  if(!['ArrowLeft','ArrowRight','Home','End'].includes(event.key))return;
  event.preventDefault();const names=['data','analysis','display'];const next=event.key==='Home'?'data':event.key==='End'?'display':names[(index+(event.key==='ArrowRight'?1:2))%3];
  setWorkspace(next);$(next+'-tab').focus();
};
document.querySelectorAll('[data-experiment]').forEach(button=>button.onclick=()=>{
  const kind=button.dataset.experiment;
  if(kind==='lifetime'){
    $('lifetime-lab').open=true;$('life-path-mode').value='altitude';updateLifetimePathFields();
    $('life-momentum').focus();$('lifetime-lab').scrollIntoView({block:'nearest',behavior:reducedMotion?'instant':'smooth'});
    activateTab('inspector','settings');$('operation-status').textContent='Muon survival experiment ready; fixed-momentum vacuum model.';return;
  }
  applyConfig({mode:'analytic',backend:$('backend').value==='rust'?'rust':'reference',source_model:'angular_sample',seed:42,events:32,
    momentum_gev:kind==='bending'?5:45,bz_tesla:3.8,field_model:kind==='field'?'cms_tracker':'ideal_bore',thickness_mm:1,
    noise_adc:kind==='electronics'?3:1,threshold_adc:kind==='electronics'?55:5,
    response_model:kind==='response'?'delphes_reference':'ideal'});
  changed();$('run-form').requestSubmit();
});
$('next-seed').onclick=()=>{
  if(active)return;
  $('seed').value=Number($('seed').value)%900000000+1;changed();$('run-form').requestSubmit();
};
$('signal-metric').onchange=renderAnalysis;
$('collision-experiment').onclick=()=>{
  applyConfig({mode:'pythia',backend:'delphes',source_model:'transverse_pair',events:100,seed:42,
    momentum_gev:45,bz_tesla:3.8,field_model:'ideal_bore',thickness_mm:1,noise_adc:1,threshold_adc:5,response_model:'ideal'});
  changed();$('run-form').requestSubmit();
};
$('export-events').onclick=()=>{
  const rows=result?.analysis?.event_rows;if(!rows)return;
  const header=['event','weight','reconstructed_muons','jets','missing_pt_gev','passes_selection','candidate_mass_gev','pair_muon_ids'];
  const text=[header.join(','),...rows.map(r=>[r.event,r.weight,r.muons,r.jets,r.met_gev??'',r.selected,r.mass_gev??'',r.pair_ids.join(':')].join(','))].join('\r\n');
  const url=URL.createObjectURL(new Blob([text],{type:'text/csv;charset=utf-8'})),link=document.createElement('a');
  link.href=url;link.download=`heplab-${displayedJob}-events.csv`;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
};
$('compare-run').onchange=async()=>{
  const id=$('compare-run').value;comparison=null;
  if(id){
    const run=sessionRuns.find(r=>r.id===id);
    try{if(!run.result){run.result=checkResultFormat(await api('runs/'+id));run.config=run.result.config;}
      if($('compare-run').value!==id)return;
      comparison=run.result;
    }catch(error){log(error.message);}
  }
  renderAnalysis();
};
$('export-comparison').onclick=()=>{
  const other=sessionRuns.find(run=>run.id===$('compare-run').value);
  if(!other?.result||!result)return;
  const describe=value=>({
    run_id:value.artifact?.run_id??null,
    result_sha256:value.artifact?.result_sha256??null,
    seed:value.config?.seed??null,
    config:value.config??null,
    model_ids:value.model_spec?.components?.map(item=>`${item.id} v${item.version}`)??[],
    source_kind:value.analysis?.kind??value.mode??null,
    selection:value.analysis?.selection??null
  });
  const current=describe(result),reference=describe(other.result),keys=[...new Set([...Object.keys(current.config||{}),...Object.keys(reference.config||{})])];
  const configuration_differences=Object.fromEntries(keys.filter(key=>JSON.stringify(current.config?.[key])!==JSON.stringify(reference.config?.[key])).map(key=>[key,{current:current.config?.[key]??null,comparison:reference.config?.[key]??null}]));
  saveJson({schema:'heplab-run-comparison-v1',scope:'saved-run comparison; display overlays and summary statistics only',runs:{current,comparison:reference},configuration_differences,plot_method:'Common bins; raw counts or signed sum of weights; no normalization; event-level statistical errors where the analysis records them.',limits:['No inference of detector calibration or experimental agreement.','Result digests are null when the stored artifact has no recorded digest; this export does not create replacement hashes.','Systematic and cross-section uncertainties are not included in the visual overlays.']},`heplab-comparison-${current.run_id||'current'}-${reference.run_id||'comparison'}.json`);
};
function observables(value){
  if(value?.analysis)return value.analysis;
  if(value?.mode!=='analytic')return null;
  const samples=value.tracks.map(track=>{
    const p=track.truth.momentum,pt=Math.hypot(p.px,p.py),q=track.reference_response?.sample.objects[0]?.state.momentum;
    return {pt_gev:pt,eta:Math.asinh(p.pz/pt),deposit_mev:track.material.deposit_gev*1000,adc:track.digit.adc,
      digit_accepted:track.digit.accepted,response_pt_gev:q?Math.hypot(q.px,q.py):null,
      response_status:q?'accepted':track.reference_response?'lost':'not_requested',energy_residual_gev:track.material.energy_residual_gev};
  });
  return {events:1,particles:samples.length,samples,pairs:[],scope:'Single saved event; aggregate distributions were not recorded in this older run.'};
}
function wilson95(successes,trials){
  if(!trials)return null;
  const z=1.959963984540054,p=successes/trials,d=1+z*z/trials;
  const center=(p+z*z/(2*trials))/d,half=z*Math.sqrt(p*(1-p)/trials+z*z/(4*trials*trials))/d;
  return [Math.max(0,center-half),Math.min(1,center+half)];
}
function plotHistogram(id,series){
  const target=$(id);target.replaceChildren();
  series=series.map(s=>{
    const observations=s.values.map((value,index)=>({value,event:s.events?.[index]??`entry:${index}`}))
      .filter(item=>Number.isFinite(item.value));
    return {...s,values:observations.map(item=>item.value),events:observations.map(item=>item.event)};
  });
  const values=series.flatMap(s=>s.values);
  if(!values.length){const p=document.createElement('p');p.className='plot-empty';p.textContent='No sampled entries. Enable the DY reference response to compare reconstructed kinematics.';target.append(p);return;}
  let low=Math.min(...values),high=Math.max(...values);
  if(high-low<Math.max(1e-9,Math.abs(low)*1e-8)){const pad=Math.max(Math.abs(low)*.025,.01);low-=pad;high+=pad;}
  const bins=14,width=(high-low)/bins;
  const histograms=series.map(s=>{
    const counts=Array(bins).fill(0),clusterCounts=Array.from({length:bins},()=>new Map());
    s.values.forEach((value,index)=>{
      const bin=Math.min(bins-1,Math.max(0,Math.floor((value-low)/width)));
      counts[bin]++;const event=s.events[index],group=clusterCounts[bin];group.set(event,(group.get(event)||0)+1);
    });
    const variance=clusterCounts.map(group=>[...group.values()].reduce((sum,n)=>sum+n*n,0));
    return {counts,variance};
  });
  const maximum=Math.max(1,...histograms.flatMap(h=>h.counts.map((n,i)=>n+Math.sqrt(h.variance[i])))),svg=document.createElementNS('http://www.w3.org/2000/svg','svg');
  svg.setAttribute('viewBox','0 0 440 172');svg.setAttribute('role','img');
  svg.setAttribute('aria-label',series.map(s=>`${s.label}: ${s.values.length} entries; event-clustered statistical errors`).join('; '));
  const add=(name,attrs,text)=>{const el=document.createElementNS(svg.namespaceURI,name);for(const [key,value]of Object.entries(attrs))el.setAttribute(key,String(value));if(text!==undefined)el.textContent=text;svg.append(el);return el;};
  for(let i=0;i<=3;i++){
    const y=140-i*38;
    add('line',{x1:37,y1:y,x2:429,y2:y,stroke:'#dce3e8','stroke-width':1});
    add('text',{x:30,y:y+4,'text-anchor':'end',fill:'#64717c','font-size':10},String(Math.round(maximum*i/3)));
  }
  series.forEach((s,index)=>histograms[index].counts.forEach((n,bin)=>{
    const error=Math.sqrt(histograms[index].variance[bin]),center=38+(bin+.5)*390/bins;
    const rect=add('rect',{x:38+bin*390/bins,y:140-n/maximum*114,width:390/bins-1,height:n/maximum*114,
      fill:s.color,'fill-opacity':index===0?.28:.18,stroke:s.color,'stroke-width':index===0?1.2:1.5,'stroke-dasharray':index>1?'3 2':''});
    const upper=140-Math.min(maximum,n+error)/maximum*114,lower=140-Math.max(0,n-error)/maximum*114;
    add('line',{x1:center,y1:upper,x2:center,y2:lower,stroke:s.color,'stroke-width':1.2});
    add('line',{x1:center-2,y1:upper,x2:center+2,y2:upper,stroke:s.color,'stroke-width':1.2});
    add('line',{x1:center-2,y1:lower,x2:center+2,y2:lower,stroke:s.color,'stroke-width':1.2});
    const title=document.createElementNS(svg.namespaceURI,'title');title.textContent=`${s.label}: ${Number((low+bin*width).toPrecision(5))} to ${Number((low+(bin+1)*width).toPrecision(5))}: ${n} entries ± ${error.toPrecision(3)} event-clustered standard error`;rect.append(title);
  }));
  for(let i=0;i<=4;i++)add('text',{x:38+i*390/4,y:157,'text-anchor':i===0?'start':i===4?'end':'middle',fill:'#64717c','font-size':10},Number((low+(high-low)*i/4).toPrecision(4)).toString());
  target.append(svg);
  const legend=document.createElement('div');legend.className='plot-legend';
  series.forEach(s=>{const span=document.createElement('span');span.style.color=s.color;span.textContent=`● ${s.label} (${s.values.length})`;legend.append(span);});target.append(legend);
}
function plotResponseEfficiency(current,comparison){
  const target=$('response-efficiency-plot');target.replaceChildren();
  const bins=[[0,.8],[.8,1.6],[1.6,2.4]],datasets=[{label:'Current run',color:'#2464a0',value:current},...(comparison?[{label:'Comparison',color:'#207e75',value:comparison}]:[])];
  const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');svg.setAttribute('viewBox','0 0 440 180');svg.setAttribute('role','img');
  svg.setAttribute('aria-label','Truth-to-object response efficiency in absolute pseudorapidity intervals, with 95 percent Wilson intervals');
  const add=(name,attrs,label)=>{const node=document.createElementNS(svg.namespaceURI,name);for(const [key,val]of Object.entries(attrs))node.setAttribute(key,String(val));if(label!==undefined)node.textContent=label;svg.append(node);return node;};
  const left=48,right=425,top=15,bottom=138,y=value=>bottom-(bottom-top)*value;
  for(const value of [0,.5,1]){const py=y(value);add('line',{x1:left,y1:py,x2:right,y2:py,stroke:'#dce3e8'});add('text',{x:left-7,y:py+4,'text-anchor':'end',fill:'#64717c','font-size':10},value.toFixed(1));}
  bins.forEach((interval,index)=>{
    const center=left+(index+.5)*(right-left)/bins.length;
    add('text',{x:center,y:157,'text-anchor':'middle',fill:'#64717c','font-size':10},`${interval[0]}–${interval[1]}`);
    datasets.forEach((dataset,datasetIndex)=>{
      const selected=dataset.value.samples.filter(sample=>sample.response_status!=='not_requested'&&Math.abs(sample.eta)>=interval[0]&&(index===bins.length-1?Math.abs(sample.eta)<=interval[1]:Math.abs(sample.eta)<interval[1]));
      const accepted=selected.filter(sample=>sample.response_status==='accepted'&&Number.isFinite(sample.response_pt_gev)).length;
      const bounds=wilson95(accepted,selected.length);if(!bounds)return;
      const px=center+(datasetIndex-(datasets.length-1)/2)*12,efficiency=accepted/selected.length;
      add('line',{x1:px,y1:y(bounds[0]),x2:px,y2:y(bounds[1]),stroke:dataset.color,'stroke-width':2});
      add('line',{x1:px-3,y1:y(bounds[0]),x2:px+3,y2:y(bounds[0]),stroke:dataset.color});
      add('line',{x1:px-3,y1:y(bounds[1]),x2:px+3,y2:y(bounds[1]),stroke:dataset.color});
      add('circle',{cx:px,cy:y(efficiency),r:4,fill:dataset.color});
      const title=document.createElementNS(svg.namespaceURI,'title');title.textContent=`${dataset.label}, |η| ${interval[0]}–${interval[1]}: ${accepted}/${selected.length} accepted; Wilson 95% ${bounds[0].toFixed(4)}–${bounds[1].toFixed(4)}`;svg.lastChild.append(title);
    });
  });
  target.append(svg);const legend=document.createElement('div');legend.className='plot-legend';
  datasets.forEach(dataset=>{const span=document.createElement('span');span.style.color=dataset.color;span.textContent='● '+dataset.label;legend.append(span);});target.append(legend);
}
function renderAnalysis(){
  const a=observables(result);let b=$('compare-run').value?observables(comparison):null;
  $('analysis-empty').hidden=!!a;$('analysis-content').hidden=!a;
  const collision=a?.kind==='collision';
  $('collision-results').hidden=!collision;$('export-events').hidden=!collision;
  $('signal-metric').hidden=collision;
  $('signal-plot-title').textContent=collision?'Missing transverse momentum / GeV':'Material / electronics';
  $('export-comparison').hidden=!$('compare-run').value;
  $('pt-plot-units').textContent=collision?'GeV/c · Σw':'GeV/c · counts';
  $('mass-plot-units').textContent=collision?'GeV/c² · Σw':'GeV/c² · counts';
  $('eta-plot-units').textContent=collision?'η · Σw':'η · counts';
  $('response-plots').hidden=true;
  if(!a)return;
  if(collision){renderCollisionAnalysis(a,b?.kind==='collision'?b:null);return;}
  if(b?.kind==='collision')b=null;
  $('analysis-title').textContent=result.config.source_model==='angular_sample'?'Angular muon sample':'Single-pair experiment';
  $('analysis-scope').textContent=`${result.backend} · seed ${result.config.seed} · ${result.config.momentum_gev} GeV/c input · ${a.scope}. Histograms show raw counts; losses are not renormalized.`;
  const matched=a.samples.filter(s=>s.response_status==='accepted').length;
  const requested=a.samples.some(s=>s.response_status!=='not_requested');
  $('response-plots').hidden=!requested;
  $('analysis-metrics').replaceChildren();
  for(const [label,value]of [['Events',a.events],['Truth muons',a.particles],['Sampled tracks',requested?`${matched} / ${a.particles}`:'Ideal only'],['Channels accepted',`${a.samples.filter(s=>s.digit_accepted).length} / ${a.particles}`]]){
    const box=document.createElement('div'),dt=document.createElement('span'),dd=document.createElement('strong');dt.textContent=label;dd.textContent=value;box.append(dt,dd);$('analysis-metrics').append(box);
  }
  const color={truth:'#2464a0',response:'#b56a22',compare:'#207e75'};
  const observations=(samples,key)=>samples.filter(s=>Number.isFinite(s[key])).map(s=>({value:s[key],event:s.event}));
  const makeSeries=(label,color,samples,key)=>{const rows=observations(samples,key);return {label,color,values:rows.map(row=>row.value),events:rows.map(row=>row.event)};};
  const series=(key,responseKey,include=()=>true)=>{
    const items=[makeSeries('Truth',color.truth,a.samples.filter(include),key)];
    if(responseKey&&requested)items.push(makeSeries('Sampled response',color.response,a.samples.filter(include),responseKey));
    if(b)items.push(makeSeries('Comparison truth',color.compare,b.samples.filter(include),key));
    return items;
  };
  plotHistogram('plot-pt',series('pt_gev','response_pt_gev'));
  const mass=[makeSeries('Truth pairs',color.truth,a.pairs,'truth_mass_gev')];
  if(requested)mass.push(makeSeries('Both tracks sampled',color.response,a.pairs,'response_mass_gev'));
  if(b)mass.push(makeSeries('Comparison truth',color.compare,b.pairs,'truth_mass_gev'));
  plotHistogram('plot-mass',mass);plotHistogram('plot-eta',series('eta'));
  const metric=$('signal-metric').value,signal=series(metric,null,metric==='adc'?sample=>sample.digit_accepted:()=>true);signal[0].label=metric==='adc'?'Accepted channels':'Ionization deposits';
  plotHistogram('plot-signal',signal);
  if(requested){
    plotResponseEfficiency(a,b?.samples?.some(sample=>sample.response_status!=='not_requested')?b:null);
    const residuals=value=>value.samples.filter(sample=>sample.response_status==='accepted'&&Number.isFinite(sample.response_pt_gev)).map(sample=>({value:(sample.response_pt_gev-sample.pt_gev)/sample.pt_gev,event:sample.event}));
    const responseSeries=[{label:'Current run',color:color.response,values:residuals(a).map(item=>item.value),events:residuals(a).map(item=>item.event)}];
    if(b){const other=residuals(b);if(other.length)responseSeries.push({label:'Comparison',color:color.compare,values:other.map(item=>item.value),events:other.map(item=>item.event)});}
    plotHistogram('response-resolution-plot',responseSeries);
  }
  const countDefinition=`${a.events} generated events; 14 equal-width bins on the combined displayed range; raw counts, not normalized. Whiskers use √(Σ event-bin count²), clustering objects within each event. These are statistical sampling errors only; no systematic uncertainty.`;
  for(const id of ['pt','eta'])$(`${id}-plot-definition`).textContent=`Population: ${a.particles} truth muons; response overlays include matched objects only. ${countDefinition}`;
  $('mass-plot-definition').textContent=`Population: one truth pair per event; the sampled pair denominator includes events with both tracks accepted. ${countDefinition}`;
  $('signal-plot-definition').textContent=`Population: ${metric==='adc'?'accepted digitized channels only':'all truth muons with a mean silicon deposit'}. ${countDefinition} Electronics response is illustrative and not calibrated.`;
  $('comparison-note').textContent=b?'Overlays use the same combined bins and raw counts. Different sample sizes are not normalized; whiskers are event-clustered statistical errors only.':'';
  const mean=xs=>xs.length?xs.reduce((x,y)=>x+y,0)/xs.length:null;
  const metrics=value=>[
    mean(value.samples.map(s=>s.pt_gev)),mean(value.samples.map(s=>s.response_pt_gev).filter(x=>x!==null)),
    mean(value.samples.map(s=>s.deposit_mev)),mean(value.pairs.map(p=>p.response_mass_gev).filter(x=>x!==null)),
    Math.max(...value.samples.map(s=>Math.abs(s.energy_residual_gev)))];
  const first=metrics(a),second=b?metrics(b):null,table=document.createElement('table'),head=document.createElement('tr');
  for(const label of ['Observable','This run',...(b?['Comparison','Difference']:[])]){const th=document.createElement('th');th.textContent=label;head.append(th);}table.append(head);
  const fmt=n=>n===null||!Number.isFinite(n)?'—':Math.abs(n)<1e-6&&n!==0?n.toExponential(3):n.toFixed(4);
  ['Mean truth pT / GeV','Mean sampled pT / GeV','Mean deposit / MeV','Mean sampled pair mass / GeV','Max |energy residual| / GeV'].forEach((name,i)=>{
    const row=document.createElement('tr');cell(row,name);cell(row,fmt(first[i]),'number');
    if(b){cell(row,fmt(second[i]),'number');cell(row,fmt(first[i]!==null&&second[i]!==null?first[i]-second[i]:null),'number');}table.append(row);
  });
  const responseDiagnostics=value=>{
    const requestedRows=value.samples.filter(sample=>sample.response_status!=='not_requested');
    const matched=requestedRows.filter(sample=>sample.response_status==='accepted'&&Number.isFinite(sample.response_pt_gev));
    const residuals=matched.map(sample=>(sample.response_pt_gev-sample.pt_gev)/sample.pt_gev);
    const interval=wilson95(matched.length,requestedRows.length);
    return requestedRows.length?{
      efficiency:`${matched.length}/${requestedRows.length} = ${(matched.length/requestedRows.length*100).toFixed(2)}%; Wilson 95% ${(interval[0]*100).toFixed(2)}–${(interval[1]*100).toFixed(2)}%`,
      bias:residuals.length?`${(100*residuals.reduce((sum,x)=>sum+x,0)/residuals.length).toFixed(3)}% (n=${residuals.length})`:'No matched objects',
      rms:residuals.length?`${(100*Math.sqrt(residuals.reduce((sum,x)=>sum+x*x,0)/residuals.length)).toFixed(3)}% (n=${residuals.length})`:'No matched objects'
    }:null;
  };
  const currentDiagnostics=responseDiagnostics(a),comparisonDiagnostics=b?responseDiagnostics(b):null;
  if(currentDiagnostics){
    for(const [name,key]of [['Illustrative response efficiency (truth-muon denominator)', 'efficiency'],['Matched relative pT bias (mean residual)', 'bias'],['Matched relative pT RMS residual (resolution proxy)', 'rms']]){
      const row=document.createElement('tr');cell(row,name);cell(row,currentDiagnostics[key]);
      if(b){cell(row,comparisonDiagnostics?.[key]||'No response sample');cell(row,'—');}table.append(row);
    }
  }
  $('comparison-table').replaceChildren(table);
  if(currentDiagnostics)$('comparison-table').append(Object.assign(document.createElement('p'),{className:'plot-definition',textContent:'Response diagnostics use matched objects only for bias/RMS and all truth muons requested for efficiency. The Wilson interval treats each muon trial as Bernoulli; these values describe the illustrative truth-to-object branch, not detector calibration or DELPHES performance.'}));
}
function plotWeighted(id,items){
  const target=$(id);target.replaceChildren();
  const base=items[0].histogram;
  items=items.filter(s=>JSON.stringify(s.histogram.edges)===JSON.stringify(base.edges));
  const edges=base.edges, bins=edges.length-1;
  let minimum=0,maximum=1;
  for(const item of items){
    const h=item.histogram,variance=h.event_sumw2_with_flow||h.sumw2_with_flow;
    for(let i=1;i<=bins;i++){const w=h.sumw_with_flow[i],error=Math.sqrt(variance[i]);minimum=Math.min(minimum,w-error);maximum=Math.max(maximum,w+error);}
  }
  const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');
  svg.setAttribute('viewBox','0 0 440 184');svg.setAttribute('role','img');svg.setAttribute('aria-label','Signed-weight histogram with event-level statistical error bars');
  const add=(name,attrs,text)=>{const el=document.createElementNS(svg.namespaceURI,name);for(const [k,v]of Object.entries(attrs))el.setAttribute(k,String(v));if(text!==undefined)el.textContent=text;svg.append(el);return el;};
  const y=v=>140-(v-minimum)/(maximum-minimum)*114;
  for(let i=0;i<=3;i++){const value=minimum+(maximum-minimum)*i/3,pos=y(value);add('line',{x1:38,y1:pos,x2:429,y2:pos,stroke:'#dce3e8'});add('text',{x:31,y:pos+4,'text-anchor':'end',fill:'#64717c','font-size':10},Number(value.toPrecision(3)).toString());}
  items.forEach((item,index)=>{
    const h=item.histogram,variance=h.event_sumw2_with_flow||h.sumw2_with_flow;
    for(let i=0;i<bins;i++){
      const n=h.sumw_with_flow[i+1],error=Math.sqrt(variance[i+1]),x=38+i*390/bins,w=390/bins-1;
      const rect=add('rect',{x,y:Math.min(y(n),y(0)),width:w,height:Math.abs(y(n)-y(0)),fill:item.color,'fill-opacity':index===0?.28:.1,stroke:item.color});
      const title=document.createElementNS(svg.namespaceURI,'title');title.textContent=`${item.label}: [${edges[i]}, ${edges[i+1]}) · sumw ${n.toPrecision(5)} ± ${error.toPrecision(4)}; entries ${h.entries_with_flow[i+1]}`;rect.append(title);
      if(error){add('line',{x1:x+w/2,y1:y(n-error),x2:x+w/2,y2:y(n+error),stroke:item.color,'stroke-width':1});}
    }
  });
  for(let i=0;i<=4;i++)add('text',{x:38+i*390/4,y:158,'text-anchor':i===0?'start':i===4?'end':'middle',fill:'#64717c','font-size':10},Number((edges[0]+(edges.at(-1)-edges[0])*i/4).toPrecision(4)).toString());
  add('text',{x:38,y:178,fill:'#657786','font-size':9},`Flow Σw: below ${base.sumw_with_flow[0].toPrecision(3)} · above ${base.sumw_with_flow.at(-1).toPrecision(3)}; full flow bins in JSON`);
  target.append(svg);const legend=document.createElement('div');legend.className='plot-legend';
  for(const item of items){const span=document.createElement('span');span.style.color=item.color;span.textContent='● '+item.label;legend.append(span);}target.append(legend);
}
function renderCollisionAnalysis(a,b){
  $('analysis-title').textContent='Drell–Yan collision analysis';
  $('analysis-scope').textContent=`${result.runtime_host||'PYTHIA8 / DELPHES'} · pp at ${(result.beam_energy_total_gev/1000).toFixed(1)} TeV · seed ${result.config.seed} · ${a.normalization}. Muon pT/η and missing pT use all events; mass uses one OS isolated pair before the mass cut.`;
  $('analysis-metrics').replaceChildren();
  for(const [label,value]of [['Generated events',a.events],['Reconstructed muons',a.particles],['Selected events',`${a.selected_events} / ${a.events}`],['Generator σ / pb',result.summary.cross_section_pb.toFixed(1)+' ± '+result.summary.cross_section_error_pb.toFixed(1)]]){
    const box=document.createElement('div'),dt=document.createElement('span'),dd=document.createElement('strong');dt.textContent=label;dd.textContent=value;box.append(dt,dd);$('analysis-metrics').append(box);
  }
  const specs=[['plot-pt','pt'],['plot-mass','mass'],['plot-eta','eta'],['plot-signal','met']];
  for(const [id,key]of specs){const items=[{label:'DELPHES reconstructed',color:'#2464a0',histogram:a.histograms[key]}];if(b)items.push({label:'Comparison',color:'#207e75',histogram:b.histograms[key]});plotWeighted(id,items);}
  const bins=a.histograms.pt.edges.length-1,base=`${bins} fixed bins; y-axis is signed Σw, not normalized. Whiskers are √(Σ per-event bin weight²), statistical only; trigger, correction, pileup and detector systematics are omitted.`;
  $('pt-plot-definition').textContent=`Population: reconstructed muons in all ${a.events} generated events. ${base}`;
  $('mass-plot-definition').textContent=`Population: one highest-scalar-pT opposite-sign isolated pair per event before the mass cut; the denominator is the pre-mass selected pair population. ${base}`;
  $('eta-plot-definition').textContent=`Population: reconstructed muons in all ${a.events} generated events. ${base}`;
  $('signal-plot-definition').textContent=`Population: missing transverse momentum, one value per generated event; no particle-count denominator. ${base}`;
  const s=a.selection;
  $('selection-description').textContent=`Muon pT ≥ ${s.muon_pt_min_gev} GeV/c, |η| < ${s.muon_abs_eta_max}, DELPHES isolation ≤ ${s.muon_iso_max}; opposite charge; ${s.mass_min_gev} ≤ mμμ < ${s.mass_max_gev} GeV/c². Highest scalar-pT pair selected before mass cut. No measured CMS ID or detector calibration claim.`;
  const table=document.createElement('table'),head=document.createElement('tr');
  for(const label of ['Cut','Events','Σw','Stat. σ (Σw²)½']){const th=document.createElement('th');th.textContent=label;head.append(th);}table.append(head);
  for(const cut of a.cutflow){const row=document.createElement('tr');cell(row,cut.stage);cell(row,cut.events,'number');cell(row,cut.sumw.toFixed(4),'number');cell(row,Math.sqrt(cut.sumw2).toFixed(4),'number');table.append(row);}
  $('collision-cutflow').replaceChildren(table);
  $('collision-files').textContent=`Generated ROOT data, cards and log: ${result.output_directory}. Export result saves the full analysis JSON; Export event table saves every generated event and its selection status.`;
  $('comparison-note').textContent=b?'Raw signed weights on common axes; comparison omitted from a plot if its bin edges differ.':$('compare-run').value?'Choose another collision run to compare.':'Statistical bars include correlations between muons in the same event. Cross-section validation remains pending.';
  const summary=document.createElement('table'),header=document.createElement('tr');
  for(const label of ['Analysis population','This run',...(b?['Comparison']:[])]){const th=document.createElement('th');th.textContent=label;header.append(th);}summary.append(header);
  for(const [label,get]of [['Selected events',x=>x.selected_events],['Generated Σw',x=>x.cutflow[0].sumw],['Selected Σw',x=>x.cutflow.at(-1).sumw]]){
    const row=document.createElement('tr');cell(row,label);cell(row,get(a),'number');if(b)cell(row,get(b),'number');summary.append(row);
  }$('comparison-table').replaceChildren(summary);
}
api('calibration').then(value=>{
  // Missing report files arrive as {status:'unavailable'}; treat them as absent below.
  for(const key of ['cms-field-validation','cms-measured-validation','cms-mass-calibration'])if(value[key]?.status==='unavailable')value[key]=null;
  calibrationReport=value;const table=$('calibration-rows');table.replaceChildren();
  const silicon=value['silicon-calibration'];let row=document.createElement('tr');
  cell(row,'Muon ionization in silicon');cell(row,silicon.training_rows?.length||'--');cell(row,silicon.heldout_rows?.length||'--');
  cell(row,silicon.status+' / max error '+((silicon.max_abs_relative_error||0)*100).toFixed(3)+'%');table.append(row);
  const muon=value['muon-response-calibration'];
  for(const bin of muon.bins||[]) {
    row=document.createElement('tr');cell(row,'Muon |eta| '+bin.eta_abs.join(' to '));
    cell(row,bin.training.matched+' / '+bin.training.denominator+' matched');cell(row,bin.heldout.matched+' / '+bin.heldout.denominator+' matched');
    cell(row,(bin.passed?'PASS':'FAIL')+' / width ratio '+bin.width_ratio.toFixed(3)+' / efficiency pull '+bin.efficiency_pull.toFixed(2));table.append(row);
  }
  const field=value['cms-field-validation'];
  if(field){row=document.createElement('tr');cell(row,'CMS tracker OAE field');cell(row,'Fixed CMS coefficients');cell(row,field.tracker_rows+' CMS reference points');cell(row,(field.passed?'PASS':'FAIL')+' / max '+(field.max_vector_error_t*1e6).toFixed(3)+' µT');table.append(row);}
  const measured=value['cms-measured-validation'];
  if(measured){row=document.createElement('tr');cell(row,'Measured CMS Z→μμ target');cell(row,measured.training.pairs+' pairs');cell(row,measured.heldout.pairs+' pairs');cell(row,'Split check '+(measured.consistency.passed?'PASS':'FAIL')+' / KS p='+measured.consistency.ks_pvalue.toFixed(3)+'; detector calibration pending');table.append(row);}
  const mass=value['cms-mass-calibration'];
  if(mass){
    row=document.createElement('tr');cell(row,'CMS Z mass template (exploratory)');
    cell(row,mass.data_selected_pairs[0]+' data / '+mass.mc_selected_pairs[0]+' MC');
    cell(row,mass.data_selected_pairs[1]+' data / '+mass.mc_selected_pairs[1]+' MC');
    cell(row,(mass.heldout.passed?'PASS':'FAIL')+' / p='+mass.heldout.pvalue.toFixed(3)+' / '+mass.bootstrap.successful+' bootstrap fits; detector calibration pending');
    row.tabIndex=0;
    const inspect=()=>{
      activateTab('inspector','selection');$('selection-title').textContent='Measured mass-template fit';
      $('selection-path').textContent='CMS data 30522 / DY MC 35671';$('properties').replaceChildren();
      property('Scope',mass.fit.scope);property('Mass scale',mass.fit.mass_scale.toPrecision(7));
      property('Additional mass σ',mass.fit.additional_fractional_mass_sigma.toPrecision(5));
      property('Statistical uncertainty',mass.fit.uncertainty_status);
      property('Held-out p-value',mass.heldout.pvalue.toFixed(6));
      property('Production physics changed',String(mass.production_transport_parameters_changed));
      for(const limitation of mass.limitations)property('Limitation',limitation);
    };
    row.onclick=inspect;row.onkeydown=event=>{if(event.key==='Enter'){event.preventDefault();inspect();}};
    table.append(row);
  }
  updateCapabilities();
}).catch(error=>log(error.message));

$('show-modules').onchange=draw;
api('detector/display').then(async manifest=>{
  const labels={pixel:'Pixel modules (original)',strips:'Silicon strip modules',ecal:'ECAL outlines (barrel reduced)',hcal:'HCAL / HF / HO outlines',dt:'Muon drift tubes',csc:'Muon CSC chambers',rpc:'Muon RPC chambers'};
  const rows=await Promise.all(manifest.layers.map(async layer=>{
    // The desktop app bundles the pinned layers; integrity is still checked below.
    const response=await fetch(desktop?'cms-display/'+layer.file:'/api/v1/detector/display/'+layer.id);
    if(!response.ok)throw Error('CMS display download failed: '+layer.id);
    const buffer=await response.arrayBuffer();
    const digest=[...new Uint8Array(await crypto.subtle.digest('SHA-256',buffer))].map(x=>x.toString(16).padStart(2,'0')).join('');
    if(buffer.byteLength!==layer.bytes || digest!==layer.sha256)throw Error('CMS display integrity failure: '+layer.id);
    displayLayers.set(layer.id,new Float32Array(buffer));
    renderer?.setLayer('cms:'+layer.id,displayLayers.get(layer.id));
    for(const [kind,suffix,target,mode,key] of [['surfaces','-surfaces',displaySurfaces,'surface','solid:'],['surface_outlines','-surface-outlines',displayRemainders,'lines','cms-remainder:']]){
      const asset=layer[kind];if(!asset)continue;
      const response=await fetch(desktop?'cms-display/'+asset.file:'/api/v1/detector/display/'+layer.id+suffix);
      if(!response.ok)throw Error('CMS surface download failed: '+layer.id);
      const buffer=await response.arrayBuffer();
      const hash=[...new Uint8Array(await crypto.subtle.digest('SHA-256',buffer))].map(x=>x.toString(16).padStart(2,'0')).join('');
      if(buffer.byteLength!==asset.bytes||hash!==asset.sha256)throw Error('CMS surface integrity failure: '+layer.id);
      target.set(layer.id,new Float32Array(buffer));renderer?.setLayer(key+layer.id,target.get(layer.id),mode);
    }
    const row=document.createElement('div');row.className='geometry-node';
    const toggle=document.createElement('input');toggle.type='checkbox';toggle.checked=true;toggle.dataset.displayLayer=layer.id;toggle.setAttribute('aria-label','Show '+labels[layer.id]);
    toggle.onchange=()=>{toggle.checked?hiddenDisplay.delete(layer.id):hiddenDisplay.add(layer.id);draw();};
    const button=document.createElement('button');button.textContent=labels[layer.id];
    button.onclick=()=>{
      activateTab('inspector','selection');$('selection-title').textContent=labels[layer.id];
      $('selection-path').textContent='CMS iSpy / display geometry';$('properties').replaceChildren();
      property('Line segments',layer.vertices/2);property('Units','metres');property('Source commit',manifest.commit);
      property('SHA256',layer.sha256);property('Source',manifest.source);property('Conditions',manifest.conditions);
      property('Scope',manifest.scope);property('Omitted',manifest.omissions.join('; '));
      if(layer.surfaces){property('Surface triangles',layer.surfaces.vertices/3);property('Native source triangles',layer.surfaces.native_triangles);property('Planar outline triangles',layer.surfaces.planar_outline_triangles);property('Surface scope',manifest.surface_scope);}
      property('Transport use','Disabled: outlines have no materials or alignment IOV');
    };
    const heading=document.createElement('div');heading.className='layer-heading';heading.append(toggle,button);
    row.classList.add('detector-layer');row.append(heading,opacityControl(layer.id,labels[layer.id]));return row;
  }));
  cmsDisplay=manifest;rows.forEach(row=>$('cms-display-tree').append(row));updateCapabilities();
  if(!result)$('display-note').textContent='CMS display meshes · faces and cutaway are illustrative; no material thickness inferred';
  draw();log('CMS display edges and surfaces loaded and SHA256 verified. Transport conditions remain separate.');
}).catch(error=>log(error.message));
