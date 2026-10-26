// Verify the actual report UI against local expected JSON, without changing the page code.
const fs=require('fs'),path=require('path'),http=require('http'),crypto=require('crypto'),vm=require('vm');
const {chromium}=require('C:/Users/skylo/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const root=path.resolve(__dirname,'..');
const daily=JSON.parse(fs.readFileSync(path.join(root,'daily-reports/latest.json'),'utf8'));
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
   await page.locator('[data-tab="daily-report"]').click();
   await page.waitForFunction(()=>document.getElementById('dailyReportDate').options.length>0);
   const loaded=await page.evaluate(async()=>await(await fetch('daily-reports/latest.json?v='+Date.now())).json());
   assert(hash(loaded)===hash(daily),'Published daily data mismatch');
   for(const date of Object.keys(daily.days)){
    await page.locator('#dailyReportDate').selectOption(date);
    const d=daily.days[date];
    assert(await page.locator('#dailyReportResults .up article').count()===d.up,'Up count');
    assert(await page.locator('#dailyReportResults .down article').count()===d.down,'Down count');
   }
   await page.locator('#dailyReportDate').selectOption(daily.latest_date);
   const first=daily.days[daily.latest_date].reports[0];
   assert(first,'Need real report for interaction QA');
   await page.locator('#dailyReportSearch').fill(first.code);
   assert((await page.locator('#dailyReportResults').innerText()).includes(first.name),'Code search');
   const historyExample=daily.days[daily.latest_date].reports.find(r=>report.summary.some(h=>h['종목코드']===r.code));
   assert(historyExample,'Need historical comparison example');
   const high=report.summary.find(h=>h['종목코드']===historyExample.code);
   await page.locator('#dailyReportSearch').fill(historyExample.code);
   const comparison=page.locator('#dailyReportComparison');
   await page.waitForFunction(()=>document.querySelector('#dailyReportComparison [data-history-code]'));
   assert((await comparison.innerText()).includes(Number(high['최고목표주가']).toLocaleString('ko-KR')+'원'),'Historical maximum');
   assert((await comparison.innerText()).includes(high['최고가날짜']),'Historical date');
   const label=historyExample.price>Number(high['최고목표주가'])?'DB 최고가 초과':historyExample.price===Number(high['최고목표주가'])?'DB 최고가 동일':'DB 최고가 미만';
   assert((await comparison.innerText()).includes(label),'Maximum comparison');
   await page.locator('#dailyReportSearch').fill(historyExample.name.toUpperCase().split('').join(' '));
   assert((await page.locator('#dailyReportResults').innerText()).includes(historyExample.name),'Whitespace and case search');
   await page.locator('#dailyReportSearch').fill(first.code);
   const detail=page.locator('#dailyReportResults details').first();
   await detail.locator('summary').click();assert(await detail.getAttribute('open')!==null,'Expand');
   await detail.locator('summary').click();assert(await detail.getAttribute('open')===null,'Collapse');
   await page.locator('#dailyReportSearch').fill('NO_MATCH_000xyz');
   assert(await page.locator('#dailyReportResults article').count()===0,'Empty search');
   await page.locator('#dailyReportSearch').fill('');
   assert(await comparison.isHidden(),'No comparison without search');
   assert(!await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+2),'Overflow');
   assert(!errors.length,JSON.stringify(errors));
   assert(!httpErrors.some(x=>/daily-reports/.test(x.url)),JSON.stringify(httpErrors));
   await page.screenshot({path:path.join(output,name+'.png'),fullPage:false});
   results.push({name,width,latest:daily.latest_date,up:daily.days[daily.latest_date].up,down:daily.days[daily.latest_date].down,search:true,dates:true,expand:true,collapse:true,errors});
   await context.close();
  }
  fs.writeFileSync(path.join(output,'validation.json'),JSON.stringify({status:'PASS',results},null,2));
  console.log(JSON.stringify({status:'PASS',results}));
 }finally{if(browser)await browser.close();if(server)await new Promise(r=>server.close(r))}
})().catch(e=>{console.error(e);process.exitCode=1});
