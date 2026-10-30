'use strict';
// CMS data operations use the same bounded IPC channel as the workbench.
let cmsReport=null, cmsBusy=false, cmsLibrary=[];
let cmsEventBusy=false;
window.cmsLoadEvent=async(analysisId,index)=>{
  if(cmsEventBusy)return;
  cmsEventBusy=true;
  try{
    const value=await cmsApi('event',{analysis_id:analysisId,index});
    setWorkspace('display');show(value,null);setProjection('3d');
    for(const id of ['mode','backend','run-button'])$(id).hidden=true;
    document.querySelectorAll('.command-bar label').forEach(e=>e.hidden=true);
    activateTab('inspector','selection');
  }catch(error){log(error.message);$('event-source').textContent='CMS event unavailable: '+error.message;}
  finally{cmsEventBusy=false;}
};
$('data-display-events').onclick=()=>{if(cmsReport?.populations.data.selected_events)window.cmsLoadEvent(cmsReport.id,0);else cmsStatus('No selected data events. Change cuts and apply them first.',true);};
const cmsInputs=['data-source','data-mc','data-min-pt','data-leading-pt','data-max-eta','data-max-iso','data-mass-low','data-mass-high','data-bins','data-trigger','data-tight'];
const cmsFields={min_pt:'data-min-pt',leading_pt:'data-leading-pt',max_eta:'data-max-eta',max_iso:'data-max-iso',mass_low:'data-mass-low',mass_high:'data-mass-high',bins:'data-bins'};
const cmsApi=(action,args={})=>api('data/'+action,action==='library'?undefined:args);
function cmsStatus(text,error=false){$('data-status').textContent=text;$('data-status').classList.toggle('error',error);}
function cmsConfig(){
  const value={data_id:$('data-source').value,mc_id:$('data-mc').value||null,require_trigger:$('data-trigger').checked,require_tight:$('data-tight').checked};
  for(const [key,id]of Object.entries(cmsFields))value[key]=Number($(id).value);
  return value;
}
function cmsChanged(){
  $('data-mass-high').setCustomValidity(Number($('data-mass-high').value)<=Number($('data-mass-low').value)?'Upper mass must exceed lower mass.':'');
  $('data-leading-pt').setCustomValidity(Number($('data-leading-pt').value)<Number($('data-min-pt').value)?'Leading pT must be at least the minimum muon pT.':'');
  const stale=cmsReport&&JSON.stringify(cmsConfig())!==JSON.stringify(Object.fromEntries(Object.keys(cmsConfig()).map(k=>[k,cmsReport.config[k]])));
  $('data-stale').textContent=stale?'Cuts changed · showing previous analysis':cmsReport?'Analysis matches these cuts':'Load datasets, then apply cuts.';
  if(window.currentWorkspace==='data'){
    $('dirty').textContent=stale?'Cuts changed · showing previous analysis':cmsReport?'CMS analysis ready':'No CMS analysis yet';
    $('dirty').classList.toggle('stale',!!stale);
  }
}
window.cmsRefreshStatus=cmsChanged;
async function cmsAction(work){
  if(cmsBusy)return;
  if(active){cmsStatus('Finish or stop the active simulation before loading CMS data.',true);return;}
  cmsBusy=true;
  const controls=[...$('data-view').querySelectorAll('button,input,select'),...$('data-library-summary').querySelectorAll('button')];
  const prior=controls.map(e=>e.disabled);controls.forEach(e=>e.disabled=true);
  try{
    if(!desktop){await sessionReady;if(!token)throw Error('Local service unavailable. Reload the workbench to reconnect.');}
    await work();
  }catch(error){cmsStatus(error.message,true);}
  finally{controls.forEach((e,i)=>e.disabled=prior[i]);cmsBusy=false;$('data-export-mc').disabled=!cmsReport?.populations.mc;cmsChanged();}
}
async function cmsRefresh(preferred){
  cmsLibrary=await cmsApi('library');
  const previous=cmsConfig();
  $('data-source').replaceChildren();$('data-mc').replaceChildren(new Option('Data only',''));
  $('data-library-summary').replaceChildren();
  for(const item of cmsLibrary){
    const option=new Option(item.name,item.id);$(item.kind==='data'?'data-source':'data-mc').append(option);
    const button=document.createElement('button');button.textContent=item.name;
    const detail=document.createElement('small');detail.textContent=`${item.kind==='data'?'Recorded':'Simulation'} · ${(item.bytes/1048576).toFixed(1)} MiB · ${item.loaded?'events cached':'local ROOT file'}`;button.append(detail);
    button.onclick=()=>{$(item.kind==='data'?'data-source':'data-mc').value=item.id;cmsChanged();cmsStatus('Dataset selected. Load it or apply cuts to analyze it.');};
    $('data-library-summary').append(button);
  }
  for(const [id,value]of [['data-source',previous.data_id||'cms-run2016g'],['data-mc',previous.mc_id??'cms-dy-ul16']])if([...$(id).options].some(o=>o.value===value))$(id).value=value;
  if(!previous.data_id&&cmsLibrary.some(i=>i.id==='cms-dy-ul16'))$('data-mc').value='cms-dy-ul16';
  if(preferred){const item=cmsLibrary.find(i=>i.id===preferred);if(item)$(item.kind==='data'?'data-source':'data-mc').value=preferred;}
  if(!cmsLibrary.length)cmsStatus('No bundled samples in this build. Import compatible CMS NanoAOD ROOT files to begin.');
}
$('data-load').onclick=()=>cmsAction(async()=>{
  const config=cmsConfig();if(!config.data_id)throw Error('Choose recorded data or import a CMS file.');
  cmsStatus('Loading selected ROOT files and checking their identities…');
  const loaded=[await cmsApi('load',{dataset_id:config.data_id})];
  if(config.mc_id)loaded.push(await cmsApi('load',{dataset_id:config.mc_id}));
  await cmsRefresh();
  $('metric-events').textContent='Loaded events: '+loaded.reduce((n,r)=>n+r.events,0).toLocaleString();
  cmsStatus(loaded.map((r,i)=>`${i?'Simulation':'Data'}: ${r.events.toLocaleString()} events ${r.reused?'reused from memory':'loaded'}`).join(' · ')+'. Apply cuts to compare them.');
});
$('data-cuts').onsubmit=event=>{event.preventDefault();cmsChanged();if(!$('data-cuts').reportValidity())return;cmsAction(async()=>{
  const config=cmsConfig();if(!config.data_id)throw Error('Choose recorded data first.');
  cmsStatus('Applying the same cuts to cached events…');
  const report=await cmsApi('analyze',{config});cmsShow(report);
  try{localStorage.setItem('heplab-cms-analysis',report.id);}catch{}
  await cmsRefresh();
  cmsStatus(`Selected ${report.populations.data.selected_events.toLocaleString()} data events${report.populations.mc?' and '+report.populations.mc.selected_events.toLocaleString()+' MC events':''}. ROOT reads in this session: ${report.root_reads}. Cuts reuse loaded events.`);
});};
cmsInputs.forEach(id=>$(id).addEventListener('change',cmsChanged));
$('data-reopen').onclick=()=>cmsAction(async()=>{
  let id;try{id=localStorage.getItem('heplab-cms-analysis');}catch{}
  if(!id)throw Error('No saved CMS analysis in this app yet. Load datasets and apply cuts first.');
  cmsShow(await cmsApi('get',{analysis_id:id}));
  cmsStatus('Reopened the saved analysis. Apply cuts to load its datasets and create a new selection.');
});
function cmsApplyConfig(value){
  $('data-source').value=value.data_id;$('data-mc').value=value.mc_id||'';
  for(const [key,id]of Object.entries(cmsFields))$(id).value=value[key];
  $('data-trigger').checked=value.require_trigger;$('data-tight').checked=value.require_tight;
}
function cmsShow(report){
  cmsReport=report;cmsApplyConfig(report.config);window.cmsAnalysisAvailable=true;
  $('operation-status').textContent='CMS analysis complete';
  $('metric-events').textContent='Data selected: '+report.populations.data.selected_events.toLocaleString();
  if(window.currentWorkspace==='data')$('download').disabled=false;
  $('data-results').hidden=false;$('data-analysis-id').textContent=`Analysis ${report.id.slice(0,8)} · ${new Date(report.created_utc).toLocaleString()}`;
  $('data-metrics').replaceChildren();
  for(const [label,value]of [['Data input',report.populations.data.events],['Data selected',report.populations.data.selected_events],['MC input',report.populations.mc?.events??'—'],['MC selected',report.populations.mc?.selected_events??'—']]){
    const box=document.createElement('div'),dt=document.createElement('span'),dd=document.createElement('strong');dt.textContent=label;dd.textContent=typeof value==='number'?value.toLocaleString():value;box.append(dt,dd);$('data-metrics').append(box);
  }
  $('data-normalization').textContent=`${report.normalization}. One pair per selected event; all plots use the mass-window selection. Statistical errors only; no luminosity scaling or physics corrections. Flow bins are retained in JSON.`;
  $('data-plots').replaceChildren();
  for(const [key,title,units]of [['mass','Dimuon invariant mass','GeV/c²'],['leading_pt','Leading muon transverse momentum','GeV/c'],['leading_eta','Leading muon pseudorapidity','η'],['pair_pt','Dimuon transverse momentum','GeV/c']]){
    const figure=document.createElement('figure'),caption=document.createElement('figcaption'),actions=document.createElement('span');actions.className='data-plot-actions';caption.append(document.createTextNode(title),actions);
    const svg=cmsPlot(report,key,title,units);figure.append(caption,svg);$('data-plots').append(figure);
    for(const format of ['svg','png']){const b=document.createElement('button');b.textContent=format.toUpperCase();b.setAttribute('aria-label',`Export ${key} ${format.toUpperCase()}`);b.onclick=()=>cmsAction(()=>cmsExportPlot(svg,key,format));actions.append(b);}
  }
  const table=document.createElement('table'),head=document.createElement('tr');
  for(const label of ['Selection','Data events','Data Σw',...(report.populations.mc?['MC events','MC Σw']:[])]){const th=document.createElement('th');th.textContent=label;head.append(th);}table.append(head);
  report.populations.data.cutflow.forEach((cut,i)=>{const row=document.createElement('tr');cell(row,cut.stage);cell(row,cut.events,'number');cell(row,cut.sumw.toFixed(3),'number');if(report.populations.mc){const mc=report.populations.mc.cutflow[i];cell(row,mc.events,'number');cell(row,mc.sumw.toFixed(3),'number');}table.append(row);});
  $('data-cutflow').replaceChildren(table);$('data-provenance').replaceChildren();
  for(const [role,p]of Object.entries(report.populations)){
    const paragraph=document.createElement('p');paragraph.textContent=`${role==='data'?'Recorded data':'Simulation'}: ${p.dataset.name}. Local SHA256 ${p.dataset.sha256}. Source: ${p.dataset.source.url||p.dataset.source.integrity||'local file'}. ${p.dataset.source.integrity||'Local derived-file identity verified.'}`;$('data-provenance').append(paragraph);
  }
  for(const text of [`2016 certification SHA256: ${report.certification_sha256}`,`Selection: ${JSON.stringify(report.config)}`,report.uncertainties,...report.limitations]){const p=document.createElement('p');p.textContent=text;$('data-provenance').append(p);}
  $('data-export-mc').disabled=!report.populations.mc;cmsChanged();
}
function cmsPlot(report,key,title,units){
  const ns='http://www.w3.org/2000/svg',svg=document.createElementNS(ns,'svg');
  const ratio=key==='mass'&&report.populations.mc,height=ratio?420:294;
  svg.setAttribute('xmlns',ns);svg.setAttribute('viewBox',`0 0 760 ${height}`);svg.setAttribute('role','img');svg.setAttribute('aria-label',title+(ratio?' with data over simulation ratio':''));
  const add=(name,attrs={},text)=>{const el=document.createElementNS(ns,name);for(const [k,v]of Object.entries(attrs))el.setAttribute(k,String(v));if(text!==undefined)el.textContent=text;svg.append(el);return el;};
  add('rect',{width:760,height,fill:'#fff'});add('title',{},title);add('desc',{},JSON.stringify({analysis_id:report.id,selection:report.config,sources:Object.fromEntries(Object.entries(report.populations).map(([k,p])=>[k,p.dataset.sha256])),normalization:report.normalization,uncertainties:report.uncertainties}));
  add('text',{x:64,y:22,fill:'#243f54','font-size':15,'font-family':'sans-serif','font-weight':600},title);
  add('text',{x:64,y:40,fill:'#637585','font-size':10,'font-family':'sans-serif'},`CMS extracts · analysis ${report.id.slice(0,8)} · fraction of selected events / bin · statistical errors`);
  const series=Object.entries(report.populations).map(([role,p])=>({role,h:p.histograms[key],color:role==='data'?'#24303a':'#2464a0',label:role==='data'?'Recorded CMS':'CMS simulation'}));
  const edges=series[0].h.edges,bins=edges.length-1,x=i=>64+i*670/bins;
  let low=0,high=.01;
  for(const s of series)if(s.h.fractions)for(let i=1;i<=bins;i++){const v=s.h.fractions[i],err=Math.sqrt(Math.max(0,s.h.covariance[i][i]));low=Math.min(low,v-err);high=Math.max(high,v+err);}
  const y=v=>218-(v-low)/(high-low)*154;
  for(let i=0;i<=4;i++){const v=low+(high-low)*i/4,pos=y(v);add('line',{x1:64,y1:pos,x2:734,y2:pos,stroke:'#dce4ea'});add('text',{x:56,y:pos+4,'text-anchor':'end',fill:'#64717c','font-size':10,'font-family':'sans-serif'},Number(v.toPrecision(3)).toString());}
  for(const s of series){
    if(!s.h.fractions)continue;
    for(let i=0;i<bins;i++){
      const v=s.h.fractions[i+1],err=Math.sqrt(Math.max(0,s.h.covariance[i+1][i+1])),cx=(x(i)+x(i+1))/2;
      if(s.role==='mc'){add('rect',{x:x(i),y:Math.min(y(v),y(0)),width:670/bins,height:Math.abs(y(v)-y(0)),fill:s.color,'fill-opacity':.16,stroke:s.color,'stroke-width':1});}
      add('line',{x1:cx,y1:y(v-err),x2:cx,y2:y(v+err),stroke:s.color,'stroke-width':1});
      const dot=add('circle',{cx,cy:y(v),r:s.role==='data'?2.4:1.2,fill:s.color});
      const t=document.createElementNS(ns,'title');t.textContent=`${s.label} [${edges[i]}, ${edges[i+1]}): ${v.toPrecision(5)} ± ${err.toPrecision(4)}; entries ${s.h.entries[i+1]}`;dot.append(t);
    }
  }
  for(let i=0;i<=5;i++){const v=edges[0]+(edges.at(-1)-edges[0])*i/5;add('text',{x:64+670*i/5,y:237,'text-anchor':i===0?'start':i===5?'end':'middle',fill:'#546d7d','font-size':10,'font-family':'sans-serif'},Number(v.toPrecision(4)).toString());}
  add('text',{x:398,y:256,'text-anchor':'middle',fill:'#354f64','font-size':11,'font-family':'sans-serif'},units);
  series.forEach((s,i)=>add('text',{x:64+i*280,y:ratio?279:277,fill:s.color,'font-size':11,'font-family':'sans-serif'},`● ${s.label} · selected Σw ${s.h.total_sumw.toPrecision(6)}`));
  if(!series[0].h.fractions)add('text',{x:270,y:140,fill:'#795b24','font-size':13,'font-family':'sans-serif'},'No positive selected data weight; shape unavailable');
  if(ratio){
    const valid=report.mass_ratio.filter(r=>r.value!==null),max=Math.max(2,...valid.map(r=>r.value+r.error));
    const ry=v=>376-v/max*72;
    for(const v of [0,1,max]){add('line',{x1:64,y1:ry(v),x2:734,y2:ry(v),stroke:v===1?'#2464a0':'#e5eaf0'});add('text',{x:56,y:ry(v)+3,'text-anchor':'end',fill:'#64717c','font-size':9,'font-family':'sans-serif'},v.toFixed(2));}
    report.mass_ratio.forEach((r,i)=>{if(r.value===null)return;const cx=(x(i)+x(i+1))/2;add('line',{x1:cx,y1:ry(Math.max(0,r.value-r.error)),x2:cx,y2:ry(r.value+r.error),stroke:'#24303a'});add('circle',{cx,cy:ry(r.value),r:2,fill:'#24303a'});});
    add('text',{x:64,y:297,fill:'#506a7c','font-size':10,'font-family':'sans-serif'},`Data / MC · undefined bins: ${report.mass_ratio.length-valid.length} (nonpositive MC or empty population)`);
    add('text',{x:64,y:403,fill:'#6c7b86','font-size':10,'font-family':'sans-serif'},'Shapes normalized separately; no luminosity, efficiency, pileup or systematic corrections.');
  }
  return svg;
}
function cmsDownload(blob,filename){
  const url=URL.createObjectURL(blob),link=document.createElement('a');link.href=url;link.download=filename;link.click();setTimeout(()=>URL.revokeObjectURL(url),3000);
  cmsStatus(`Export requested: ${filename}. Check Downloads for the file.`);
}
window.exportCmsAnalysis=()=>{if(cmsReport)cmsDownload(new Blob([JSON.stringify(cmsReport,null,2)],{type:'application/json'}),`cms-analysis-${cmsReport.id}.json`);};
$('data-export-json').onclick=window.exportCmsAnalysis;
async function cmsExportPlot(svg,key,format){
  const source=new XMLSerializer().serializeToString(svg),name=`cms-${cmsReport.id}-${key}.${format}`;
  if(format==='svg'){cmsDownload(new Blob([source],{type:'image/svg+xml'}),name);return;}
  const url=URL.createObjectURL(new Blob([source],{type:'image/svg+xml'}));
  try{
    const img=new Image();await new Promise((resolve,reject)=>{img.onload=resolve;img.onerror=()=>reject(Error('PNG rendering failed. SVG export is still available.'));img.src=url;});
    const canvas=document.createElement('canvas'),box=svg.viewBox.baseVal;canvas.width=1520;canvas.height=Math.round(1520*box.height/box.width);const ctx=canvas.getContext('2d');ctx.fillStyle='#fff';ctx.fillRect(0,0,canvas.width,canvas.height);ctx.drawImage(img,0,0,canvas.width,canvas.height);
    const blob=await new Promise(resolve=>canvas.toBlob(resolve,'image/png'));if(!blob)throw Error('PNG export failed');cmsDownload(blob,name);
  }finally{URL.revokeObjectURL(url);}
}
for(const [id,role]of [['data-export-rows','data'],['data-export-mc','mc']])$(id).onclick=()=>cmsAction(async()=>{
  if(!cmsReport)return;cmsStatus(`Exporting selected ${role} events…`);const chunks=[];let offset=0;
  while(true){const page=await cmsApi('rows',{analysis_id:cmsReport.id,role,offset});chunks.push(page.text);if(page.next_offset>=page.total)break;if(page.next_offset<=offset)throw Error('Event export stopped making progress');offset=page.next_offset;}
  cmsDownload(new Blob(chunks,{type:'text/csv;charset=utf-8'}),`cms-${cmsReport.id}-${role}-selected.csv`);
});
$('data-import').onclick=()=>$('data-file').click();
$('data-file').onchange=()=>cmsAction(async()=>{
  const file=$('data-file').files[0];if(!file)return;
  let upload;
  try{
    if(!/\.root$/i.test(file.name))throw Error('Choose a CMS NanoAOD ROOT file.');
    if(file.size>512*1024*1024)throw Error('Import a ROOT projection no larger than 512 MiB.');
    upload=await cmsApi('import_begin',{config:{name:file.name.slice(0,120),kind:$('data-import-kind').value,size:file.size}});
    for(let offset=0;offset<file.size;offset+=32768){const bytes=new Uint8Array(await file.slice(offset,offset+32768).arrayBuffer());await cmsApi('import_chunk',{config:{id:upload.id,offset,base64:btoa(String.fromCharCode(...bytes))}});if(offset%1048576<32768)cmsStatus(`Importing ${file.name}: ${Math.min(100,Math.round((offset+bytes.length)/file.size*100))}%`);}
    cmsStatus('Checking ROOT branches, event identities and measurements…');
    const item=await cmsApi('import_finish',{upload_id:upload.id});upload=null;await cmsRefresh(item.id);cmsChanged();cmsStatus('Dataset imported and cached. Choose the other population, then Apply cuts.');
  }catch(error){if(upload)await cmsApi('import_abort',{upload_id:upload.id}).catch(()=>{});throw error;}
  finally{$('data-file').value='';}
});
cmsRefresh().then(()=>{cmsChanged();if(cmsLibrary.length)cmsStatus('Choose local CMS samples or import a ROOT file. Load selected datasets to begin.');}).catch(error=>cmsStatus(error.message,true));
setWorkspace('data');
let cmsHistoryOffset=0;
async function cmsHistory(offset=0){
  const page=await cmsApi('analyses',{offset});cmsHistoryOffset=offset;
  $('data-history-panel').hidden=false;
  $('data-history-count').textContent=page.total?`${offset+1}–${Math.min(offset+25,page.total)} of ${page.total} saved analyses`:'No saved analyses yet. Apply cuts to create one.';
  $('data-history-list').replaceChildren();
  for(const item of page.items){
    const row=document.createElement('div');row.className='data-history-row';
    const text=document.createElement('p'),c=item.config;
    text.textContent=`${new Date(item.created_utc).toLocaleString()} · ${item.id.slice(0,8)} · ${Object.entries(item.populations).map(([role,p])=>`${role}: ${p.name} (${p.selected_events.toLocaleString()} selected)`).join(' · ')} · pT > ${c.min_pt}, leading > ${c.leading_pt} GeV · |η| < ${c.max_eta} · isolation < ${c.max_iso} · mass ${c.mass_low}–${c.mass_high} GeV · ${c.bins} bins · trigger ${c.require_trigger?'on':'off'} · tight ID ${c.require_tight?'on':'off'}`;
    const button=document.createElement('button');button.textContent='Open '+item.id.slice(0,8);
    button.onclick=()=>cmsAction(async()=>{await cmsRefresh();cmsShow(await cmsApi('get',{analysis_id:item.id}));try{localStorage.setItem('heplab-cms-analysis',item.id);}catch{}cmsStatus('Reopened saved analysis '+item.id.slice(0,8)+'.');});
    row.append(text,button);$('data-history-list').append(row);
  }
  $('data-history-prev').hidden=offset===0;$('data-history-next').hidden=page.next_offset>=page.total;
}
$('data-history').onclick=()=>cmsAction(()=>cmsHistory());
$('data-history-prev').onclick=()=>cmsAction(()=>cmsHistory(Math.max(0,cmsHistoryOffset-25)));
$('data-history-next').onclick=()=>cmsAction(()=>cmsHistory(cmsHistoryOffset+25));
