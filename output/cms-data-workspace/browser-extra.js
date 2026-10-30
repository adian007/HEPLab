async page => {
  await page.locator('#data-mc').selectOption('');
  await page.getByRole('button',{name:'Apply cuts',exact:true}).click();
  await page.waitForFunction(()=>document.getElementById('data-status').textContent.includes('Selected 10,863 data events.'),null,{timeout:120000});
  const dataOnly={status:await page.locator('#data-status').textContent(),mcExportDisabled:await page.locator('#data-export-mc').isDisabled()};
  for(const key of ['mass','leading_pt','leading_eta','pair_pt'])for(const format of ['SVG','PNG']){
    const pending=page.waitForEvent('download',{timeout:10000});
    await page.getByRole('button',{name:`Export ${key} ${format}`,exact:true}).click();
    await (await pending).saveAs(`D:/HEPLab/output/cms-data-workspace/browser-data-only-${key}.${format.toLowerCase()}`);
    await page.waitForFunction(()=>!document.getElementById('data-load').disabled);
  }
  await page.locator('#data-mc').selectOption('cms-dy-ul16');
  await page.getByRole('button',{name:'Apply cuts',exact:true}).click();
  await page.waitForFunction(()=>document.getElementById('data-status').textContent.includes('and 11,430 MC events'),null,{timeout:120000});
  return dataOnly;
}
