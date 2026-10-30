async page => {
  const out={};
  await page.waitForFunction(()=>!document.getElementById('data-load').disabled);
  await page.getByRole('button',{name:'Apply cuts',exact:true}).click();
  await page.waitForFunction(()=>document.getElementById('data-status').textContent.includes('Selected 10,863'),null,{timeout:120000});
  out.baseline=await page.locator('#data-status').textContent();
  for(const [label,name] of [['Export mass SVG','mass.svg'],['Export analysis JSON','analysis.json'],['Export selected data CSV','data.csv'],['Export selected MC CSV','mc.csv']]){
    const pending=page.waitForEvent('download',{timeout:30000});
    await page.getByRole('button',{name:label,exact:true}).click();
    await (await pending).saveAs('D:/HEPLab/output/cms-data-workspace/browser-'+name);
    await page.waitForFunction(()=>!document.getElementById('data-load').disabled);
  }
  await page.locator('#data-min-pt').fill('30');
  await page.locator('#data-leading-pt').fill('40');
  await page.locator('#data-leading-pt').blur();
  out.stale=await page.locator('#data-stale').textContent();
  await page.getByRole('button',{name:'Apply cuts',exact:true}).click();
  await page.waitForFunction(()=>document.getElementById('data-status').textContent.includes('Selected 6,678'),null,{timeout:120000});
  out.tight=await page.locator('#data-status').textContent();
  await page.locator('#data-min-pt').fill('999');
  await page.locator('#data-leading-pt').fill('1000');
  await page.getByRole('button',{name:'Apply cuts',exact:true}).click();
  await page.waitForFunction(()=>document.getElementById('data-status').textContent.includes('Selected 0'),null,{timeout:120000});
  out.empty=await page.locator('#data-status').textContent();
  await page.reload();
  await page.getByRole('button',{name:'Reopen last analysis',exact:true}).click();
  await page.waitForFunction(()=>document.getElementById('data-status').textContent.includes('Reopened'),null,{timeout:30000});
  out.reopened=await page.locator('#data-metrics').textContent();
  await page.locator('#data-file').setInputFiles('D:/HEPLab/artifacts/cms/measured/run2016g-100k.root');
  await page.waitForFunction(()=>document.getElementById('data-status').textContent.includes('Dataset imported'),null,{timeout:120000});
  out.imported=await page.locator('#data-source').inputValue();
  await page.locator('#data-min-pt').fill('15');
  await page.locator('#data-leading-pt').fill('25');
  await page.getByRole('button',{name:'Apply cuts',exact:true}).click();
  await page.waitForFunction(()=>document.getElementById('data-status').textContent.includes('Selected 10,863'),null,{timeout:120000});
  out.import_selection=await page.locator('#data-status').textContent();
  await page.screenshot({path:'D:/HEPLab/output/cms-data-workspace/browser-workspace.png',fullPage:true});
  return out;
}
