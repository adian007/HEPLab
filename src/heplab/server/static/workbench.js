'use strict';
const $ = id => document.getElementById(id);
const canvas = $('detector'), context = canvas.getContext('2d');
const inputIds = ['mode','backend','seed','events','momentum','field','thickness','noise','threshold','response-model','field-model'];
let token = '', capabilities = null, result = null, active = null, displayedJob = null;
let detectorGeometry=null, calibrationReport=null, hiddenSurfaces=new Set();
let cmsDisplay=null; const displayLayers=new Map(), hiddenDisplay=new Set();
let selected = null, projection = 'xy', zoom = 1, pan = [0,0], orbit = [-.65,.55];
let drag = null, screenTracks = [], history = [], historyIndex = -1, sessionRuns = [];

function config() {
  return {mode:$('mode').value, backend:$('mode').value==='pythia'?'delphes':$('backend').value, seed:Number($('seed').value),
    events:Number($('events').value), momentum_gev:Number($('momentum').value),
    bz_tesla:Number($('field').value),field_model:$('mode').value==='pythia'?'ideal_bore':$('field-model').value, thickness_mm:Number($('thickness').value),
    noise_adc:Number($('noise').value), threshold_adc:Number($('threshold').value),response_model:$('mode').value==='pythia'?'ideal':$('response-model').value};
}
// Inside the desktop app the CSP blocks fetch('/api/...'); the same requests go
// through the shell's single validated command to the packaged worker.
const desktop = window.__TAURI_INTERNALS__;
function desktopRequest(path, body, extraHeaders) {
  const fixed = {session:'workbench.session', detector:'detector.geometry', calibration:'calibration.report', 'detector/display':'detector.display'};
  let match;
  if (fixed[path] && body === undefined) return [fixed[path], {}];
  if (path === 'jobs' && body !== undefined) {
    const key = extraHeaders['Idempotency-Key'];
    return ['jobs.submit', key ? {config:body, idempotency_key:key} : {config:body}];
  }
  if ((match = /^jobs\/([A-Za-z0-9]+)$/.exec(path)) && body === undefined) return ['jobs.get', {job_id:match[1]}];
  if ((match = /^jobs\/([A-Za-z0-9]+)\/cancel$/.exec(path)) && body !== undefined) return ['jobs.cancel', {job_id:match[1]}];
  if ((match = /^jobs\/([A-Za-z0-9]+)\/events\/(\d+)$/.exec(path)) && body === undefined) return ['jobs.event', {job_id:match[1], index:Number(match[2])}];
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
  const value = await response.json();
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
  check('Rust engine', rust?'Configured':'Unavailable', rust?'Compiled numerical backend':'Install binding or configure executable',rust?'pass':'pending');
  check('PYTHIA8 / DELPHES', capabilities?.simulation.available?'Installed':'Unavailable',
    capabilities?.simulation.available?'8.312 / 3.5.1 · fixed CMS card':(capabilities?.simulation.reason || 'Checking local runtime'),
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
    check('Generator conservation','Passed',`Max four-vector residual: ${result.summary.max_truth_four_momentum_residual_gev.toExponential(3)} GeV`,'pass');
    check('Cross section','Generator estimate',`${result.summary.cross_section_pb} ± ${result.summary.cross_section_error_pb} pb; independent validation pending`);
  }
  if (result?.mode === 'analytic') check('Event energy ledger','Passed',`${Math.max(...result.tracks.map(t=>Math.abs(t.material.energy_residual_gev))).toExponential(3)} GeV residual`,'pass');
}
function updateMode() {
  const collision = $('mode').value === 'pythia';
  const tracker=$('field-model').value==='cms_tracker';
  $('field').readOnly=tracker;if(tracker)$('field').value='3.8';
  $('propagation-model').textContent=tracker?'RK4 / tracker validity only':'Analytic vacuum helix';
  if (collision) $('backend').value='delphes';
  else if ($('backend').value==='delphes') $('backend').value=(capabilities?.engine.rust_extension||capabilities?.engine.rust_executable_configured)?'rust':'reference';
  document.querySelectorAll('.bench-settings').forEach(e=>e.hidden=collision);
  document.querySelectorAll('.collision-settings').forEach(e=>e.hidden=!collision);
  document.querySelectorAll('.bench-node').forEach(e=>e.disabled=collision);
  $('event-budget-row').hidden = !collision;
  $('backend').disabled = collision || !!active;
  $('document-title').textContent = collision?'Drell–Yan collisions':'Muon thin-slab bench';
  $('run-button').disabled = !token || !!active || (collision && !capabilities?.simulation.available);
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
  $('dirty').textContent = !result?'No computed result':Object.entries(config()).every(([key,value])=>result.config[key]===value)?'Result up to date':'Parameters modified · run required';
}
inputIds.forEach(id=>$(id).addEventListener('change',()=>changed()));
function restore(index) {
  if (active || index<0 || index>=history.length) return;
  historyIndex=index; const c=JSON.parse(history[index]);
  const values={mode:c.mode,backend:c.backend,seed:c.seed,events:c.events,momentum:c.momentum_gev,
    field:c.bz_tesla,thickness:c.thickness_mm,noise:c.noise_adc,threshold:c.threshold_adc,'response-model':c.response_model||'ideal','field-model':c.field_model||'ideal_bore'};
  for (const [id,value] of Object.entries(values)) $(id).value=value;
  changed(false);
}
$('undo').onclick=()=>restore(historyIndex-1); $('redo').onclick=()=>restore(historyIndex+1);
function saveJson(value,name) {
  const url=URL.createObjectURL(new Blob([JSON.stringify(value,null,2)],{type:'application/json'}));
  const link=document.createElement('a'); link.href=url; link.download=name; link.click();
  setTimeout(()=>URL.revokeObjectURL(url),1000);
}
$('save-setup').onclick=()=>saveJson({format:'heplab-workbench-config-v1',parameters:config()},'heplab-setup.json');
$('download').onclick=()=>{if(result) saveJson(result,'heplab-event-'+result.event+'.json');};
$('show-capabilities').onclick=()=>activateTab('results','checks');
document.querySelectorAll('[data-section]').forEach(button=>button.onclick=()=>{
  document.querySelectorAll('[data-section]').forEach(b=>{b.classList.toggle('selected',b===button);b.setAttribute('aria-selected',String(b===button));});
  selected=null;
  document.querySelectorAll('#track-list button').forEach(b=>{b.setAttribute('aria-selected','false');b.setAttribute('aria-pressed','false');});
  document.querySelectorAll('#particle-rows tr[data-id]').forEach(r=>r.setAttribute('aria-selected','false'));draw();
  activateTab('inspector','settings'); $('selection-title').textContent=button.textContent.replace(/[↳▾◇]/g,'').trim();
  const section=document.querySelector(`[data-property="${button.dataset.section}"]`);
  document.querySelectorAll('.property-section').forEach(e=>e.classList.remove('highlight'));
  section.classList.add('highlight'); section.scrollIntoView({block:'nearest'});
});

document.querySelector('[role=tree]').addEventListener('keydown',event=>{
  if(!['ArrowUp','ArrowDown','Home','End'].includes(event.key))return;
  event.preventDefault();const items=[...document.querySelectorAll('[role=treeitem]')].filter(e=>!e.disabled);
  const current=items.indexOf(document.activeElement);
  const next=event.key==='Home'?0:event.key==='End'?items.length-1:Math.max(0,Math.min(items.length-1,current+(event.key==='ArrowDown'?1:-1)));
  items[next]?.focus();
});

function rotate(point) {
  if (projection==='xy') return [point[0],point[1]];
  if (projection==='xz') return [point[0],point[2]];
  const [x,y,z]=point, [yaw,pitch]=orbit;
  const right=x*Math.cos(yaw)-y*Math.sin(yaw);
  const depth=x*Math.sin(yaw)+y*Math.cos(yaw);
  return [right,z*Math.cos(pitch)-depth*Math.sin(pitch)];
}
function draw() {
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
  function line(points,color,lineWidth=1,dash=[]) {
    context.beginPath();context.strokeStyle=color;context.lineWidth=lineWidth;context.setLineDash(dash);
    points.forEach((p,i)=>{const q=project(p);i?context.lineTo(...q):context.moveTo(...q);});context.stroke();context.setLineDash([]);
  }
  if ($('show-grid').checked) {
    for(let i=-10;i<=10;i++) {
      const a=i*extent/5, dark=i%5===0?'#47515d':'#323b46';
      if(projection==='xz'){line([[a,0,-2*extent],[a,0,2*extent]],dark);line([[-2*extent,0,a],[2*extent,0,a]],dark);}
      else {line([[a,-2*extent,0],[a,2*extent,0]],dark);line([[-2*extent,a,0],[2*extent,a,0]],dark);}
    }
  }
  if($('show-guides').checked && detectorGeometry) {
    const colors={pixel:'#c77882','tracker-envelope':'#6c9c86',solenoid:'#a69b6b'};
    const ring=(radius,z)=>Array.from({length:97},(_,i)=>[radius*Math.cos(i*Math.PI/48),radius*Math.sin(i*Math.PI/48),z]);
    for(const surface of detectorGeometry.surfaces) {
      if(hiddenSurfaces.has(surface.id))continue;
      const focus=$('detector-focus').value;
      if(focus==='pixel'&&surface.subsystem!=='pixel')continue;
      if(focus==='tracker'&&surface.subsystem==='solenoid')continue;
      const color=colors[surface.subsystem]||'#8293a7';
      if(surface.kind==='cylinder') {
        for(const z of [-surface.half_length_m,0,surface.half_length_m])line(ring(surface.radius_m,z),color,1);
        if(projection!=='xy')for(let i=0;i<12;i++) {
          const a=i*Math.PI/6,x=surface.radius_m*Math.cos(a),y=surface.radius_m*Math.sin(a);
          line([[x,y,-surface.half_length_m],[x,y,surface.half_length_m]],color,.65);
        }
      } else {
        line(ring(surface.inner_radius_m,surface.z_m),color,1);
        line(ring(surface.outer_radius_m,surface.z_m),color,1);
        if(projection!=='xy')for(let i=0;i<8;i++) {
          const a=i*Math.PI/4;
          line([[surface.inner_radius_m*Math.cos(a),surface.inner_radius_m*Math.sin(a),surface.z_m],
                [surface.outer_radius_m*Math.cos(a),surface.outer_radius_m*Math.sin(a),surface.z_m]],color,.6);
        }
      }
    }
  }
  if ($('show-modules').checked) {
    const colors={pixel:'#d68c9a',strips:'#75ad98',ecal:'#8cb1cc',hcal:'#bba273',dt:'#b594bc',csc:'#b594bc',rpc:'#9ba5ca'};
    for (const [id, values] of displayLayers) {
      if (hiddenDisplay.has(id)) continue;
      const focus=$('detector-focus').value;
      if (focus==='pixel' && id!=='pixel') continue;
      if (focus==='tracker' && !['pixel','strips'].includes(id)) continue;
      context.beginPath();context.strokeStyle=colors[id];context.lineWidth=.55;context.globalAlpha=.4;
      for(let i=0;i<values.length;i+=6) {
        const a=project([values[i],values[i+1],values[i+2]]),b=project([values[i+3],values[i+4],values[i+5]]);
        if(Math.max(a[0],b[0])<0||Math.min(a[0],b[0])>width||Math.max(a[1],b[1])<0||Math.min(a[1],b[1])>height)continue;
        context.moveTo(...a);context.lineTo(...b);
      }
      context.stroke();context.globalAlpha=1;
    }
  }
  line([[-extent,0,0],[extent,0,0]],'#874f51');
  line([[0,-extent,0],[0,extent,0]],'#4c755b');
  if(projection!=='xy')line([[0,0,-extent],[0,0,extent]],'#4e6e9b');
  screenTracks=[];
  for(const track of result?.tracks||[]) {
    const isSelected=track.object_id===selected, color=track.charge<0?'#68b9ef':'#e7ae65';
    line(track.points,color,isSelected?2.5:1.5);
    const points=track.points.map(project),last=points.at(-1);
    context.fillStyle=color;context.beginPath();context.arc(...last,isSelected?4:3,0,2*Math.PI);context.fill();
    context.font='12px Segoe UI,sans-serif';context.fillText(`${track.charge<0?'μ−':'μ+'} #${track.object_id}`,last[0]+7,last[1]-7);
    screenTracks.push({id:track.object_id,points});
    for(const crossing of track.trajectory?.crossings||[]) {
      if(hiddenSurfaces.has(crossing.surface_id))continue;
      const point=project(crossing.position_m);context.strokeStyle=color;context.lineWidth=1;
      context.strokeRect(point[0]-3,point[1]-3,6,6);
    }
  }
  // Stable orientation triad uses the same world-to-screen projection as tracks.
  const triad=[width-58,height-65];context.font='12px Segoe UI,sans-serif';
  for (const [vector,label,color] of [[[1,0,0],'X','#f17b7b'],[[0,1,0],'Y','#81c48b'],[[0,0,1],'Z','#7ca9ed']]) {
    const p=rotate(vector),end=[triad[0]+p[0]*32,triad[1]-p[1]*32];
    context.beginPath();context.strokeStyle=color;context.lineWidth=2;context.moveTo(...triad);context.lineTo(...end);context.stroke();context.fillStyle=color;context.fillText(label,end[0]+3,end[1]-3);
  }
  // Scale bar reports actual model-space distance under current zoom.
  const length=extent*(zoom>2?.1:zoom<.7?1:.5), x=15,y=height-42;
  context.strokeStyle='#c4ccd5';context.lineWidth=1;context.beginPath();context.moveTo(x,y-3);context.lineTo(x,y+3);context.moveTo(x,y);context.lineTo(x+length*scale,y);context.lineTo(x+length*scale,y-3);context.stroke();
  context.fillStyle='#c4ccd5';context.font='11px Consolas,monospace';context.fillText(Number(length.toPrecision(2))+' m',x,y-7);
}
new ResizeObserver(draw).observe(canvas);
function setProjection(value) {
  projection=value; for(const [id,name]of [['xy','xy'],['xz','xz'],['three-d','3d']])$(id).setAttribute('aria-pressed',String(value===name));
  $('view-label').textContent=value==='3d'?'3D · orbit / orthographic':value.toUpperCase()+' · orthographic';
  $('navigation-hint').textContent=value==='3d'?'Drag: orbit · Shift+drag: pan · wheel: zoom':'Drag: pan · wheel: zoom';draw();
}
$('xy').onclick=()=>setProjection('xy');$('xz').onclick=()=>setProjection('xz');$('three-d').onclick=()=>setProjection('3d');
function fit(){zoom=1;pan=[0,0];orbit=[-.65,.55];draw();}
$('detector-focus').onchange=fit;
$('reset-view').onclick=fit;$('show-grid').onchange=draw;$('show-guides').onchange=draw;
canvas.addEventListener('wheel',event=>{event.preventDefault();zoom=Math.max(.3,Math.min(8,zoom*Math.exp(-event.deltaY*.001)));draw();},{passive:false});
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

function property(name,value){const dt=document.createElement('dt'),dd=document.createElement('dd');dt.textContent=name;dd.textContent=value;$('properties').append(dt,dd);}
function selectTrack(id) {
  document.querySelectorAll('[data-section]').forEach(b=>{b.classList.remove('selected');b.setAttribute('aria-selected','false');});
  selected=id;const track=result?.tracks.find(t=>t.object_id===id);$('properties').replaceChildren();
  document.querySelectorAll('#track-list button').forEach(b=>(b.setAttribute('aria-pressed',String(Number(b.dataset.id)===id)),b.setAttribute('aria-selected',String(Number(b.dataset.id)===id))));
  document.querySelectorAll('#particle-rows tr[data-id]').forEach(row=>row.setAttribute('aria-selected',String(Number(row.dataset.id)===id)));
  if(!track){$('selection-path').textContent='No particle selected';draw();return;}
  const name=track.charge<0?'μ−':'μ+';$('selection-title').textContent=name+' / '+id;
  $('selection-path').textContent=`Event ${result.event} / Muon / ${id}`;
  property('PDG ID',track.pdg_id);property('Charge',track.charge+' e');
  if(result.mode==='pythia') {
    property('pT',track.detector.pt.toFixed(4)+' GeV/c');property('η',track.detector.eta.toFixed(5));
    property('φ',track.detector.phi.toFixed(5)+' rad');property('Isolation',String(track.detector.iso));
    property('Source','DELPHES reconstructed muon');property('Display','IP-assumed ideal-solenoid extrapolation; not hits or fitted tracks');
  } else {
    property('Input |p|',result.config.momentum_gev+' GeV/c');
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
  if(track.reference_response){property('Tracking reference sample',track.reference_response.sample.accepted_objects?'Accepted':'Inefficient / lost');property('Reference efficiency',track.reference_response.parameters.efficiency.toFixed(4));property('Response scope',track.reference_response.parameters.validation_scope);}
  property('Validation','Analytic trajectory; scoped reference calibration only');activateTab('inspector','selection');draw();
}
function show(value,jobId=displayedJob) {
  result=value;displayedJob=jobId;$('download').disabled=false;
  if(!active||active===jobId){$('status').textContent='COMPLETED';$('operation-status').textContent='Completed result';}
  $('track-list').replaceChildren();$('particle-rows').replaceChildren();$('crossing-rows').replaceChildren();
  if(value.geometry)detectorGeometry=value.geometry;
  const tracks=result.tracks||[];
  for(const track of tracks) {
    const button=document.createElement('button');button.dataset.id=track.object_id;
    button.textContent=`${track.charge<0?'μ−':'μ+'} [${track.object_id}]`;button.setAttribute('role','treeitem');
    button.onclick=()=>selectTrack(track.object_id);$('track-list').append(button);
    const row=document.createElement('tr');row.dataset.id=track.object_id;row.tabIndex=0;row.onclick=()=>selectTrack(track.object_id);
    row.onkeydown=event=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();selectTrack(track.object_id);}};
    cell(row,'Muon / '+track.object_id);cell(row,track.pdg_id,'number');cell(row,track.charge,'number');
    if(result.mode==='analytic') {
      cell(row,result.config.momentum_gev.toFixed(3),'number');cell(row,result.config.momentum_gev.toFixed(3),'number');
      cell(row,(track.material.deposit_gev*1000).toFixed(4),'number');cell(row,track.digit.adc??'—','number');
      cell(row,track.digit.saturated?'Saturated':track.digit.accepted?'Digit accepted':'Below threshold');
    }else{
      cell(row,(track.detector.pt*Math.cosh(track.detector.eta)).toFixed(3),'number');
      cell(row,track.detector.pt.toFixed(3),'number');cell(row,'—','number');cell(row,'—','number');cell(row,'DELPHES reconstructed');
    }$('particle-rows').append(row);
  }
  for(const track of tracks)for(const crossing of track.trajectory?.crossings||[]) {
    const row=document.createElement('tr');cell(row,track.object_id);cell(row,crossing.surface_id);
    for(const value of [crossing.path_m,...crossing.position_m,crossing.time_ns])cell(row,value.toFixed(6),'number');
    row.onclick=()=>selectTrack(track.object_id);$('crossing-rows').append(row);
  }
  if(!tracks.length){const row=document.createElement('tr');const td=cell(row,'No reconstructed muons in this event.');td.colSpan=8;$('particle-rows').append(row);}
  $('object-count').textContent=tracks.length;$('particle-total').textContent=tracks.length;
  $('empty-state').hidden=true;$('display-note').textContent=result.display;
  $('event-label').textContent='Event '+result.event;$('event-index').value=result.event;
  const count=result.mode==='analytic'?1:result.summary.events;
  $('event-index').max=count-1;$('event-index').disabled=count<=1;$('event-total').textContent='/ '+(count-1);
  $('previous-event').disabled=result.event<=0;$('next-event').disabled=result.event>=count-1;
  $('event-source').textContent=result.mode==='analytic'?`${result.backend} · declared μμ fixture`:'PYTHIA8 → DELPHES · reconstructed muons';
  $('metric-events').textContent='Events: '+count;
  const bench=result.mode==='analytic';
  $('metric-deposit').textContent='Event deposit: '+(bench?(tracks.reduce((a,t)=>a+t.material.deposit_gev,0)*1000).toFixed(3)+' MeV':'not read');
  $('metric-digits').textContent='Channels: '+(bench?tracks.filter(t=>t.digit.accepted).length+'/'+tracks.length:'—');
  $('metric-residual').textContent='Energy residual: '+(bench?Math.max(...tracks.map(t=>Math.abs(t.material.energy_residual_gev))).toExponential(2)+' GeV':result.summary.max_truth_four_momentum_residual_gev.toExponential(2)+' GeV (run max)');
  selected=null;if(tracks.length)selectTrack(tracks[0].object_id);else{$('properties').replaceChildren();$('selection-path').textContent='No reconstructed muons in this event';draw();}
  changed(false);updateCapabilities();renderHistory();
}
async function loadEvent(index) {
  if(!displayedJob||!result||index<0||index>= (result.summary?.events||1))return;
  try{const value=await api(`jobs/${displayedJob}/events/${index}`);show({...value,config:result.config});}
  catch(error){log(error.message);activateTab('results','diagnostics');}
}
$('previous-event').onclick=()=>loadEvent(result.event-1);$('next-event').onclick=()=>loadEvent(result.event+1);
$('event-index').onchange=()=>{const n=Number($('event-index').value);if(Number.isInteger(n))loadEvent(n);};
function renderHistory(){
  $('run-history').replaceChildren();
  if(!sessionRuns.length){const p=document.createElement('p');p.textContent='No runs in this session.';p.className='muted inset';$('run-history').append(p);}
  for(const run of [...sessionRuns].reverse()){
    const button=document.createElement('button'),dot=document.createElement('span');dot.className='run-state '+run.status;
    button.append(dot,document.createTextNode(`${run.id.slice(0,8)} · ${run.status}`));button.classList.toggle('active',run.id===displayedJob);
    button.disabled=run.status!=='completed';button.onclick=()=>show({...run.result,config:run.config},run.id);$('run-history').append(button);
  }
}
function busy(value){inputIds.forEach(id=>$(id).disabled=value);$('cancel').disabled=!value;$('save-setup').disabled=value;changed(false);}
async function poll(id) {
  let terminal=false;
  try{
    const job=await api('jobs/'+id),entry=sessionRuns.find(r=>r.id===id);Object.assign(entry,job);
    $('status').textContent=job.status.toUpperCase();$('operation-status').textContent=job.status;renderHistory();
    if(['queued','running'].includes(job.status)){setTimeout(()=>poll(id),400);return;}
    terminal=true;
    if(job.status==='completed'){
      entry.result={...job.result,config:job.config};show(entry.result,id);
      log(`Completed ${id}. ${job.result.mode}; validation: ${job.result.validation}.`);
      if(job.result.summary)log(`Accepted ${job.result.summary.events} events. Generator estimate ${job.result.summary.cross_section_pb} ± ${job.result.summary.cross_section_error_pb} pb (not independently validated).`);
      activateTab('results','particles');
    }else{log(`${job.status}: ${job.error||'No result committed.'}`);activateTab('results','diagnostics');}
  }catch(error){terminal=true;log(error.message);$('status').textContent='ERROR';activateTab('results','diagnostics');}
  if(terminal){active=null;busy(false);}
}
$('run-form').onsubmit=async event=>{
  event.preventDefault();if(active||!$('run-form').reportValidity())return;
  const submitted=config();$('run-button').disabled=true;
  try{const job=await api('jobs',submitted,{'Idempotency-Key':crypto.randomUUID()});active=job.id;sessionRuns.push({...job,config:submitted});busy(true);
    log(`Submitted ${job.id}: ${submitted.mode}, seed ${submitted.seed}.`);activateTab('results','diagnostics');poll(job.id);
  }catch(error){log(error.message);$('status').textContent='FAILED';activateTab('results','diagnostics');updateMode();}
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
  const editing=['INPUT','SELECT','TEXTAREA'].includes(document.activeElement.tagName);
  if(event.key==='F5'){event.preventDefault();if(!$('run-button').disabled)$('run-form').requestSubmit();}
  if(event.key==='Escape'&&active)$('cancel').click();
  if((event.ctrlKey||event.metaKey)&&event.key.toLowerCase()==='s'){event.preventDefault();$('download').click();}
  if(!editing&&(event.ctrlKey||event.metaKey)&&['z','y'].includes(event.key.toLowerCase())){event.preventDefault();restore(historyIndex+(event.key.toLowerCase()==='z'?-1:1));}
  if(!editing&&!event.ctrlKey&&!event.metaKey){if(event.key==='1')setProjection('xy');if(event.key==='2')setProjection('xz');if(event.key==='3')setProjection('3d');if(event.key.toLowerCase()==='f')fit();if(['+','=','-'].includes(event.key)){event.preventDefault();zoom=Math.max(.3,Math.min(8,zoom*(event.key==='-'?.9:1.1)));draw();}}
});
changed();
setProjection('3d');
api('session').then(session=>{
  token=session.token;capabilities=session;
  const rust=session.engine.rust_extension||session.engine.rust_executable_configured;
  $('backend').options[1].disabled=!rust;
  if(rust){$('backend').value='rust';changed();}
  $('connection').textContent='Local service connected';updateMode();
  log('Local service connected. Capability report is available.');
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
api('calibration').then(value=>{
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
    const row=document.createElement('div');row.className='geometry-node';
    const toggle=document.createElement('input');toggle.type='checkbox';toggle.checked=true;toggle.setAttribute('aria-label','Show '+labels[layer.id]);
    toggle.onchange=()=>{toggle.checked?hiddenDisplay.delete(layer.id):hiddenDisplay.add(layer.id);draw();};
    const button=document.createElement('button');button.textContent=labels[layer.id];
    button.onclick=()=>{
      activateTab('inspector','selection');$('selection-title').textContent=labels[layer.id];
      $('selection-path').textContent='CMS iSpy / display geometry';$('properties').replaceChildren();
      property('Line segments',layer.vertices/2);property('Units','metres');property('Source commit',manifest.commit);
      property('SHA256',layer.sha256);property('Source',manifest.source);property('Conditions',manifest.conditions);
      property('Scope',manifest.scope);property('Omitted',manifest.omissions.join('; '));
      property('Transport use','Disabled: outlines have no materials or alignment IOV');
    };
    row.append(toggle,button);return row;
  }));
  cmsDisplay=manifest;rows.forEach(row=>$('cms-display-tree').append(row));updateCapabilities();
  if(!result)$('display-note').textContent='CMS iSpy outlines · display only / trajectories use ideal bore field';
  draw();log('CMS iSpy outlines loaded and SHA256 verified. Transport conditions remain separate.');
}).catch(error=>log(error.message));
