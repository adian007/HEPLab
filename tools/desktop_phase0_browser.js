// Playwright CLI: run-code --filename tools/desktop_phase0_browser.js
// Only use against the isolated server created by desktop_phase0.py serve.
async (page) => {
  const output = new URL(page.url()).searchParams.get('phase0-output');
  if (!output || !/^D:\/HEPLab\/output\/[\w/-]+$/.test(output)) {
    throw Error('Set phase0-output in the page URL to a fresh D:/HEPLab/output/ subdirectory');
  }
  const base = output.replace(/\/$/,'')+'/';
  const evidence = {url: page.url(), findings: {}, automation_errors: []};
  if (new URL(page.url()).port !== '8771') throw Error('Use the isolated Phase 0 server on port 8771');
  await page.setViewportSize({width:1440,height:900});
  await page.waitForFunction(() => document.querySelector('#connection').textContent.includes('connected'));
  const inspect = () => page.evaluate(() => ({
    draft: config(), displayed_id: displayedJob, result_config: result?.config,
    status: $('status').textContent, dirty: $('dirty').textContent,
    dirty_visible: getComputedStyle($('dirty')).display !== 'none' && $('dirty').getBoundingClientRect().height > 0,
    history: [...$('run-history').querySelectorAll('button')].map(b=>({text:b.textContent,title:b.title})),
    checks: $('capability-rows').innerText, properties: $('properties').innerText,
    particles: $('particle-rows').innerText,
  }));
  async function set(id, value) {
    const element = page.locator('#'+id);
    if (await element.evaluate(e=>e.tagName==='SELECT')) await element.selectOption(value);
    else {await element.fill(value);await element.press('Tab');}
  }
  async function run() {
    const response = page.waitForResponse(r=>r.url().endsWith('/api/v1/jobs') && r.request().method()==='POST');
    await page.getByRole('button',{name:'▶ Run',exact:true}).click();
    const submitted = await response;
    if(submitted.status()!==202)throw Error('Unexpected submission: '+await submitted.text());
    const {id}=await submitted.json();
    await page.waitForFunction(id=>displayedJob===id && !active,id,{timeout:60000});
    await page.getByRole('tab',{name:'Parameters',exact:true}).click();
    return id;
  }
  async function probe(number, action) {
    try {evidence.findings[number]=await action();}
    catch(error){evidence.automation_errors.push({finding:number,error:String(error)});}
  }
  async function recall(id) {
    await page.locator(`#run-history button[title="${id}"]`).click();
    await page.waitForFunction(id=>displayedJob===id,id);
  }
  await set('source-model','transverse_pair');
  await set('response-model','ideal');
  const firstId=await run();
  evidence.normal=await inspect();
  await probe('1',async()=>{
    // Browser memory only: original result and persisted numerical artifacts stay intact.
    return page.evaluate(()=>{
      const original=result, outcomes={};
      try {
        for(const [name,residual] of [['normal',1e-15],['injected_0_5',.5],['nan',NaN],['missing',undefined]]) {
          result=structuredClone(original);
          result.tracks.forEach(t=>{t.material.energy_residual_gev=residual;});
          result.analysis?.samples.forEach(t=>{t.energy_residual_gev=residual;});
          updateCapabilities();
          outcomes[name]=[...$('capability-rows').rows].find(r=>r.cells[0].textContent==='Event energy ledger').innerText;
        }
        outcomes.generator={};
        for(const [name,residual] of [['normal',1e-15],['injected_0_5',.5],['nan',NaN],['missing',undefined]]) {
          result={summary:{max_truth_four_momentum_residual_gev:residual}};
          try {updateCapabilities();outcomes.generator[name]=$('capability-rows').innerText;}
          catch(error){outcomes.generator[name]={exception:String(error)};}
        }
        outcomes.result_tolerance_fields=Object.keys(original).filter(k=>/tolerance|conservation/.test(k));
      }finally {result=original;updateCapabilities();}
      return outcomes;
    });
  });
  let setupPath;
  await probe('2',async()=>{
    const before=await inspect();
    await page.reload();
    await page.waitForFunction(()=>sessionRuns.length>0);
    const after=await inspect();
    await recall(firstId);
    const reopened=await inspect();
    const pending=page.waitForEvent('download');
    await page.getByRole('button',{name:'Save setup…',exact:true}).click();
    const saved=await pending;
    setupPath=base+'saved-setup.json';await saved.saveAs(setupPath);
    await page.getByRole('tab',{name:'Parameters',exact:true}).click();
    await set('momentum','30');
    await page.locator('#setup-file').setInputFiles(setupPath);
    await page.waitForFunction(()=>$('momentum').value==='45');
    const restored=await inspect();
    const originalSetup=await page.evaluate(()=>({format:'heplab-workbench-config-v1',parameters:config()}));
    const importValue=async(value)=>{
      await page.locator('#setup-file').setInputFiles({name:'probe-setup.json',mimeType:'application/json',buffer:Buffer.from(JSON.stringify(value))});
      await page.waitForFunction(()=>$('setup-file').value==='');
      return {draft:await page.evaluate(()=>config()),log:await page.locator('#log').innerText()};
    };
    const incompatible=await importValue({...originalSetup,format:'heplab-workbench-config-v999'});
    const malformed=await importValue({...originalSetup,parameters:{...originalSetup.parameters,seed:0}});
    const unknownKey=await importValue({...originalSetup,parameters:{...originalSetup.parameters,unrecognized_physics_model:'test'}});
    // A future result envelope is substituted only while reading; no on-disk change.
    await page.reload();await page.waitForFunction(()=>sessionRuns.length>0);
    await page.evaluate(id=>{
      window.phase0RealApi=api;
      api=async (...args)=>{
        const value=await window.phase0RealApi(...args);
        if(args[0]==='runs/'+id)value.artifact={...value.artifact,format:'heplab-workbench-result-v999'};
        return value;
      };
    },firstId);
    await recall(firstId);
    const futureAccepted=await page.evaluate(()=>result?.artifact?.format);
    await page.evaluate(()=>{api=window.phase0RealApi;delete window.phase0RealApi;});
    return {before,after,reopened,restored,incompatible,malformed,unknownKey,futureAccepted,setupFilename:saved.suggestedFilename()};
  });
  await probe('3',async()=>{
    await page.getByRole('tab',{name:'Parameters',exact:true}).click();
    await set('momentum','20');await run();
    await recall(firstId);
    const recalled=await inspect();
    await page.getByRole('tab',{name:'Parameters',exact:true}).click();
    await set('momentum','20');
    await page.setViewportSize({width:1100,height:680});
    const minimum=await inspect();
    await page.screenshot({path:base+'minimum-window.png'});
    await page.setViewportSize({width:1440,height:900});
    return {recalled,minimum,explicit_use_settings_action:await page.getByRole('button',{name:/Use this run/}).count()};
  });
  await probe('4',async()=>{
    await page.getByRole('tab',{name:'Parameters',exact:true}).click();
    await set('momentum','45');await set('response-model','delphes_reference');
    await run();
    const state=await inspect();
    const response=await page.evaluate(()=>result.tracks.map(t=>({truth:t.truth.momentum,response:t.reference_response})));
    await page.getByRole('tab',{name:'Run analysis',exact:true}).click();
    const analysis=await page.locator('#analysis-view').innerText();
    await page.screenshot({path:base+'response-analysis.png'});
    return {state,response,analysis};
  });
  await probe('5',async()=>{
    await page.getByRole('tab',{name:'Parameters',exact:true}).click();
    await set('momentum','1');
    const state=await inspect();
    const validation=await page.locator('#configuration-error').innerText();
    const runEnabled=await page.locator('#run-button').isEnabled();
    let submissions=0;const listen=request=>{if(request.url().endsWith('/api/v1/jobs')&&request.method()==='POST')submissions++;};
    page.on('request',listen);await page.locator('#run-button').click();
    page.off('request',listen);
    const blocked=await inspect();
    // Exercise the failed-submission UI independently from client validity.
    await set('momentum','45');
    await page.evaluate(()=>{
      window.phase0RealApi=api;
      api=async(...args)=>{if(args[0]==='jobs'&&args[1])throw Error('Injected submission failure for Phase 0 recovery probe');return window.phase0RealApi(...args);};
    });
    await page.locator('#run-button').click();
    await page.waitForFunction(()=>$('status').textContent==='FAILED');
    const failed=await inspect();
    const exportEnabled=await page.locator('#download').isEnabled();
    await page.evaluate(()=>{api=window.phase0RealApi;delete window.phase0RealApi;});
    return {state,validation,runEnabled,submissions,blocked,failed,exportEnabled};
  });
  await probe('6',async()=>{
    await set('mode','pythia');
    const notice=await page.locator('#runtime-notice').innerText();
    const state=await inspect();
    const selector=await page.locator('#mode').innerText();
    const title=await page.locator('#document-title').innerText();
    const navigation=await page.evaluate(()=>['previous-event','next-event'].map(id=>({id,disabled:$(id).disabled,title:$(id).title})));
    await page.screenshot({path:base+'unavailable-collision.png'});
    return {notice,state,selector,title,navigation,helpLinks:await page.locator('#runtime-notice a').count(),runDisabled:await page.locator('#run-button').isDisabled()};
  });
  await probe('7',async()=>{
    const pending=page.waitForEvent('download');await page.locator('#download').click();
    const downloaded=await pending;await downloaded.saveAs(base+'exported-result.json');
    return {filename:downloaded.suggestedFilename(),payload:await page.evaluate(()=>result),setupPath};
  });
  // Use a download for evidence so this probe needs no filesystem access in the CLI VM.
  const pending=page.waitForEvent('download');
  await page.evaluate(value=>saveJson(value,'phase0-browser-evidence.json'),evidence);
  const download=await pending;await download.saveAs(base+'browser-evidence.json');
  return {findings:Object.keys(evidence.findings),automation_errors:evidence.automation_errors};
}
