const fs=require('fs'),path=require('path'),http=require('http'),vm=require('vm'),assert=require('assert');
const {chromium}=require('C:/Users/skylo/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const root=path.resolve(__dirname,'..'),output=path.resolve(process.argv[3]);
fs.mkdirSync(output,{recursive:true});
const html=fs.readFileSync(path.join(root,'index.html'),'utf8');
for(const m of html.matchAll(/<script\b([^>]*)>([\s\S]*?)<\/script>/gi))if(!/\bsrc=|application\/json|application\/ld\+json/i.test(m[1])&&m[2].trim())new vm.Script(m[2]);
for(const file of ['scripts/dashboard-freshness.js','scripts/futures-index-context.js'])new vm.Script(fs.readFileSync(path.join(root,file),'utf8'));
const expected=JSON.parse(fs.readFileSync(path.join(root,'dashboard-health/latest.json'),'utf8'));
const ai=JSON.parse(fs.readFileSync(path.join(root,'market-analysis/analysis_latest.json'),'utf8'));
const candidateSummary=JSON.parse(fs.readFileSync(path.join(root,'market-analysis/candidate_hit_rate_latest.json'),'utf8')).summary;
const marketSummary=JSON.parse(fs.readFileSync(path.join(root,'market-analysis/market_view_hit_rate_latest.json'),'utf8')).summary;
const futures=JSON.parse(fs.readFileSync(path.join(root,'supply-zone/latest.json'),'utf8'));
const futuresZip=JSON.parse(fs.readFileSync(path.join(root,'supply-zone/data_bundle_latest.json'),'utf8'));
(async()=>{
 let server,browser;
 try{
  let url=process.argv[2];
  if(url==='local'){
   server=http.createServer((req,res)=>{
    let file=path.resolve(root,'.'+decodeURIComponent(new URL(req.url,'http://local').pathname));
    if(file===root)file=path.join(root,'index.html');
    if(!file.startsWith(root+path.sep)||!fs.existsSync(file)||!fs.statSync(file).isFile()){res.writeHead(404);return res.end()}
    const mime={'.html':'text/html; charset=utf-8','.json':'application/json; charset=utf-8','.js':'text/javascript; charset=utf-8','.png':'image/png','.css':'text/css; charset=utf-8'}[path.extname(file)]||'application/octet-stream';
    res.writeHead(200,{'Content-Type':mime,'Cache-Control':'no-store'});fs.createReadStream(file).pipe(res);
   });
   await new Promise(r=>server.listen(0,'127.0.0.1',r));url=`http://127.0.0.1:${server.address().port}/`;
  }
  browser=await chromium.launch({headless:true,channel:'chrome'});
  const results=[];
  for(const width of [1280,390]){
   const context=await browser.newContext({viewport:{width,height:920}}),page=await context.newPage(),errors=[];
   page.on('pageerror',e=>errors.push(e.message));
   await page.goto(url+'?freshness_qa='+Date.now(),{waitUntil:'domcontentloaded',timeout:45000});
   await page.waitForFunction(()=>window.dashboardFreshnessReady===true);
   const dates=await page.evaluate(()=>[
    dashboardFreshnessAge('20261105',new Date('2026-11-10T00:00:00Z')),
    dashboardFreshnessAge('2026-11-06',new Date('2026-11-10T00:00:00Z')),
    dashboardFreshnessAge('2026-11-06',new Date('2026-11-10T15:00:00Z')),
    dashboardFreshnessAge('2026-02-30'),dashboardFreshnessAge('')]);
   assert.deepStrictEqual(dates,[5,4,5,null,null]);
   const health=await page.locator('#dashboardFreshness summary').innerText();assert(health.includes(`5일 이상 지난 자료 ${expected.summary.stale}개`));
   await page.locator('#dashboardFreshness summary').click();
   await page.screenshot({path:path.join(output,`health-${width}.png`)});
   await page.locator('[data-tab="market"]').click();
   await page.waitForFunction(asOf=>document.querySelector('#marketAIMeta').textContent.includes(asOf),ai.as_of);
   assert((await page.locator('#marketAIContent').innerText()).includes(ai.headline));
   if(ai.publication_kind==='DATA_REFRESH'){
    assert((await page.locator('#marketAIContent').innerText()).includes('종목 재선정 미실시'));
    const archive=page.locator('#marketAIContent > details');
    await archive.locator('summary').click();
    await page.waitForFunction(()=>document.querySelector('#marketAIContent > details')?.dataset.loaded==='1');
    assert((await archive.locator('summary').innerText()).includes('현재 추천으로 사용 불가'));
    await archive.locator('summary').click();
   }
   await page.screenshot({path:path.join(output,`market-${width}.png`)});
   await page.locator('[data-market-subtab="hit-rate"]').click();
   await page.waitForFunction(([signals,evaluated])=>document.querySelector('#candidateHitRateStats')?.textContent.includes(signals)&&document.querySelector('#marketViewHitRateStats')?.textContent.includes(evaluated),[Number(candidateSummary.signals).toLocaleString('en-US'),String(marketSummary.evaluated)]);
   const hitText=await page.locator('[data-tab-panel="market"]').innerText();
   assert(!hitText.includes('누적승률 자료를 불러오지 못'));
   await page.locator('[data-tab="leaders"]').click();
   assert((await page.locator('.sector-weight-heading').innerText()).includes('2026-08-28'));
   assert(await page.locator('.sector-weight-panel[data-reference="fixed"]').count()===1);
   assert(!((await page.locator('#dashboardFreshness').innerText()).includes('시장 섹터 시총 지도')));
   await page.locator('[data-tab="supply"]').click();
   await page.waitForFunction(asOf=>document.querySelector('#supplyMeta')?.textContent.includes(asOf),futures.as_of);
   let zip=null;
   const zipLink=page.locator('#futuresValidation a[download="futures_options_data_bundle_latest.zip"]');
   if(String(futuresZip.as_of).replaceAll('-','')===String(futures.as_of).replaceAll('-','')){
    await zipLink.waitFor({state:'attached'});zip=await zipLink.getAttribute('href');
    assert(zip.includes('supply-zone/futures_options_data_bundle_latest.zip'));
   }else assert(await zipLink.count()===0,'Mismatched-date ZIP must remain hidden');
   const liveDates=await page.evaluate(()=>Object.fromEntries([...document.querySelectorAll('[id$="Date"],#nightTime')].filter(x=>x.id!=='analysisDate').map(x=>[x.id,x.textContent])));
   const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+2);
   assert(!overflow,'Page horizontal overflow');assert.deepStrictEqual(errors,[]);
   const actual=await page.evaluate(async()=>await(await fetch('dashboard-health/latest.json?t='+Date.now(),{cache:'no-store'})).json());
   assert.deepStrictEqual(actual,expected);
   results.push({width,health,zip,liveDates,overflow,page_errors:errors});await context.close();
  }
  fs.writeFileSync(path.join(output,'validation.json'),JSON.stringify({status:'PASS',verified_at:new Date().toISOString(),results},null,2));
  console.log(JSON.stringify({status:'PASS',widths:results.map(x=>x.width)}));
 }finally{if(browser)await browser.close();if(server)await new Promise(r=>server.close(r))}
})().catch(e=>{console.error(e);process.exitCode=1});
