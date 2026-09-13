// Verify the actual report UI against local expected JSON, without changing the page code.
const fs=require('fs'),path=require('path'),http=require('http'),crypto=require('crypto'),vm=require('vm');
const {chromium}=require('C:/Users/skylo/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const root=path.resolve(__dirname,'..');
const report=JSON.parse(fs.readFileSync(path.join(root,'report_data.json'),'utf8'));
const signals=JSON.parse(fs.readFileSync(path.join(root,'report_signal_data.json'),'utf8'));
const html=fs.readFileSync(path.join(root,'index.html'),'utf8');
const output=path.resolve(process.argv[3]);
const assert=(ok,msg)=>{if(!ok)throw Error(msg)};
const hash=v=>crypto.createHash('sha256').update(JSON.stringify(v)).digest('hex');
for(const m of html.matchAll(/<script\b([^>]*)>([\s\S]*?)<\/script>/gi))if(!/\bsrc=|application\/json|application\/ld\+json/i.test(m[1])&&m[2].trim())new vm.Script(m[2]);
const targets=signals.up.filter(r=>r['구분']==='목표주가 상향');
const unique=new Set(targets.map(r=>r['종목코드'])).size;
const latest=targets.map(r=>r['날짜']).sort().at(-1);
const example=targets.find(r=>r['날짜']===latest);
fs.mkdirSync(output,{recursive:true});
(async()=>{
 let server,browser;
 try{
  let url=process.argv[2];
  if(url==='local'){
   server=http.createServer((req,res)=>{
    let f=path.resolve(root,'.'+decodeURIComponent(new URL(req.url,'http://localhost').pathname));
    if(f===root)f=path.join(root,'index.html');
    if(!f.startsWith(root+path.sep)||!fs.existsSync(f)||!fs.statSync(f).isFile()){res.writeHead(404);return res.end()}
    const mime={'.html':'text/html; charset=utf-8','.js':'text/javascript; charset=utf-8','.css':'text/css; charset=utf-8','.json':'application/json; charset=utf-8'}[path.extname(f)]||'application/octet-stream';
    res.writeHead(200,{'Content-Type':mime,'Cache-Control':'no-store'});fs.createReadStream(f).pipe(res);
   });
   await new Promise(r=>server.listen(0,'127.0.0.1',r));url=`http://127.0.0.1:${server.address().port}/`;
  }
  const password=process.env.JS_DASHBOARD_QA_PASSWORD;
  assert(password&&crypto.createHash('sha256').update(password).digest('hex')===html.match(/const passwordHash='([^']+)'/)[1],'Valid user-provided QA password required');
  browser=await chromium.launch({headless:true,channel:'chrome'});
  const results=[];
  for(const [name,width,height] of [['desktop',1440,1000],['mobile',390,844]]){
   const context=await browser.newContext({viewport:{width,height}}),page=await context.newPage();
   const errors=[],consoleErrors=[],httpErrors=[];
   page.on('pageerror',e=>errors.push(e.message));
   page.on('console',m=>{if(m.type()==='error')consoleErrors.push(m.text())});
   page.on('response',r=>{if(r.status()>=400)httpErrors.push({status:r.status(),url:r.url()})});
   await page.goto(url+'?report_verify='+Date.now(),{waitUntil:'domcontentloaded',timeout:45000});
   await page.locator('#dashboardPassword').fill(password);
   await page.locator('#dashboardUnlockButton').click();
   await page.waitForFunction(()=>document.getElementById('dashboardLock').hidden);
   await page.locator('[data-tab="report"]').click();
   await page.waitForFunction(()=>reportData.details.length>0&&reportSignalData.up.length>0);
   const loaded=await page.evaluate(()=>({report:reportData,signals:reportSignalData}));
   assert(hash(loaded.report)===hash({summary:report.summary,details:report.details,meta:report.meta}),'Rendered report source mismatch');
   assert(hash(loaded.signals)===hash(signals),'Rendered signal source mismatch');
   const meta=await page.locator('#reportMeta').innerText();
   assert(meta.includes(report.details.length.toLocaleString('en-US')),'Report total not rendered');
   await page.locator('#reportSearchInput').fill(example['종목코드']);
   await page.locator('.report-search-row button').click();
   assert((await page.locator('#reportResults').innerText()).includes(example['종목명']),'Summary search failed');
   await page.locator('#reportDetailBtn').click();
   assert((await page.locator('#reportResults').innerText()).includes(latest),'Latest detail not searchable');
   await page.locator('#reportSectionUpBtn').click();
   const card=page.locator('#reportUpStats .signal-stat').filter({has:page.locator('small',{hasText:'목표주가 상향'})});
   assert((await card.innerText()).includes(targets.length.toLocaleString('en-US')+'건'),'Target count card mismatch');
   assert((await card.innerText()).includes('중복 제외 '+unique.toLocaleString('en-US')+'종목'),'Unique count mismatch');
   await page.locator('#reportUpCategory').selectOption('목표주가 상향');
   const grouped=await page.locator('#reportUpResults').evaluate(box=>[...box.querySelectorAll('tbody')].map(b=>({first:b.rows[0].cells[0].textContent,code:b.rows[0].cells[2].textContent,dates:[...b.rows].map(r=>r.cells[0].textContent),visible:[...b.rows].filter(r=>!r.hidden).length})));
   assert(grouped.length===unique&&grouped.every(g=>g.visible===1&&g.first===[...g.dates].sort().at(-1)),'Grouping/latest representative mismatch');
   assert(new Set(grouped.map(g=>g.code)).size===unique,'Duplicate representative code');
   const more=page.locator('#reportUpResults .signal-more-btn').first();
   const group=await more.getAttribute('aria-controls'), extra=page.locator(`[data-signal-group="${group}"]`);
   assert(await extra.count()>0,'No expandable group found');
   await more.click();
   assert(await more.getAttribute('aria-expanded')==='true'&&(await extra.first().isVisible()),'Expand failed');
   await more.click();
   assert(await more.getAttribute('aria-expanded')==='false'&&!(await extra.first().isVisible()),'Collapse failed');
   await page.locator('#reportUpSearch').fill(example['종목코드']);
   assert(await page.locator('#reportUpResults tbody').count()===1,'Code search grouping failed');
   assert((await page.locator('#reportUpResults tbody tr').first().innerText()).includes(latest),'Search latest failed');
   await page.locator('#reportUpSearch').fill('ZZZ_NO_MATCH_0123456789');
   assert((await page.locator('#reportUpResults').innerText()).includes('조건에 맞는 시그널이 없습니다.'),'Empty filter failed');
   await page.locator('#reportUpSearch').fill('');
   assert(await page.locator('#reportUpResults tbody').count()===unique,'Filter reset failed');
   const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+2);
   assert(!overflow,'Page horizontal overflow');
   assert(!errors.length,JSON.stringify(errors));
   assert(!consoleErrors.some(e=>/report_data|report_signal_data/i.test(e)),JSON.stringify(consoleErrors));
   await page.screenshot({path:path.join(output,name+'.png'),fullPage:false});
   const raw=await page.evaluate(async()=>({report:await(await fetch('report_data.json?verify='+Date.now(),{cache:'no-store'})).json(),signals:await(await fetch('report_signal_data.json?verify='+Date.now(),{cache:'no-store'})).json()}));
   assert(hash(raw.report)===hash(report)&&hash(raw.signals)===hash(signals),'Cache-busted public data mismatch');
   results.push({name,url,meta,target_count:targets.length,unique_stocks:unique,latest,search:true,filter:true,expand:true,collapse:true,grouping:true,overflow,errors,consoleErrors,httpErrors});
   await context.close();
  }
  fs.writeFileSync(path.join(output,'validation.json'),JSON.stringify({status:'PASS',verified_at:new Date().toISOString(),results},null,2));
  console.log(JSON.stringify({status:'PASS',results},null,2));
 }finally{if(browser)await browser.close();if(server)await new Promise(r=>server.close(r))}
})().catch(e=>{console.error(e);process.exitCode=1});
