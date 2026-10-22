const fs=require('fs'),path=require('path'),http=require('http'),vm=require('vm');
const {chromium}=require('C:/Users/skylo/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const root=path.resolve(__dirname,'..');
const expected=JSON.parse(fs.readFileSync(path.join(root,'news/index.json'),'utf8')).reports;
const assert=(x,m)=>{if(!x)throw Error(m)};
for(const file of ['news/dashboard.js'])new vm.Script(fs.readFileSync(path.join(root,file),'utf8'));
for(const m of fs.readFileSync(path.join(root,'index.html'),'utf8').matchAll(/<script\b([^>]*)>([\s\S]*?)<\/script>/gi))if(!/src=|application\/json|application\/ld\+json/i.test(m[1])&&m[2].trim())new vm.Script(m[2]);
(async()=>{
 let server,browser;
 try{
  let url=process.argv[2]||'local';
  if(url==='local'){
   server=http.createServer((req,res)=>{
    let f=path.resolve(root,'.'+new URL(req.url,'http://local').pathname);
    if(fs.existsSync(f)&&fs.statSync(f).isDirectory())f=path.join(f,'index.html');
    if(!f.startsWith(root+path.sep)||!fs.existsSync(f)){res.writeHead(404);return res.end()}
    res.setHeader('Content-Type',({'.html':'text/html; charset=utf-8','.js':'text/javascript; charset=utf-8','.css':'text/css; charset=utf-8','.json':'application/json; charset=utf-8'})[path.extname(f)]||'application/octet-stream');
    fs.createReadStream(f).pipe(res);
   });
   await new Promise(r=>server.listen(0,'127.0.0.1',r));url=`http://127.0.0.1:${server.address().port}/`;
  }
  browser=await chromium.launch({headless:true,channel:'msedge'});
  const results=[];
  for(const width of [1280,390]){
   const context=await browser.newContext({viewport:{width,height:900}});
   const page=await context.newPage(),errors=[];
   page.on('pageerror',e=>errors.push(e.message));
   await page.goto(url+'?news_verify='+Date.now()+'#news',{waitUntil:'domcontentloaded'});
   await page.waitForFunction(()=>document.querySelector('[data-daily-pane="news"]').dataset.newsLoaded==='true');
   assert(await page.locator('#dashboardLock').isVisible(),'Password lock was not preserved');
   // Exercise the existing remembered-session state in this disposable QA browser only.
   await page.evaluate(()=>sessionStorage.setItem('js-dashboard-unlocked-v1','1'));
   await page.reload({waitUntil:'domcontentloaded'});
   await page.waitForFunction(()=>document.querySelector('[data-daily-pane="news"]').dataset.newsLoaded==='true');
   assert(await page.locator('[data-daily-pane="news"]').isVisible(),'News deep link invisible');
   assert(await page.locator('[data-tab="daily-report"]').innerText()==='[당일 체크]','Parent label mismatch');
   assert(await page.locator('[data-tab="news"]').count()===0,'Old top-level news menu remains');
   await page.locator('[data-daily-tab="report"]').click();
   assert(await page.locator('[data-daily-pane="report"]').isVisible(),'Report subpane invisible');
   await page.waitForFunction(()=>document.querySelector('#dailyReportResults article'));
   const reportCount=await page.locator('#dailyReportResults article').count();
   assert(reportCount>0,'Existing reports missing');
   await page.locator('[data-daily-tab="news"]').click();
   assert(await page.locator('[data-daily-pane="report"]').isHidden(),'Report pane did not hide');
   assert(await page.locator('#newsList li').count()===expected.length,'Archive count mismatch');
   assert(await page.locator('#newsCalendar').count()===0,'Stale calendar pinned');
   assert((await page.locator('#newsLatest').innerText()).includes('업로드'),'Publication time not displayed');
   const rows=await page.locator('#newsList time').allTextContents();
   assert(rows[0].includes((expected[0].published_at || '').slice(0,10)),'Latest upload not first');
   assert((await page.locator('.news-note').innerText()).includes('19:00'),'Schedule note stale');
   for(const edition of ['morning','evening']){
    const r=expected.find(r=>r.edition===edition);
    assert(await page.locator(`#newsLatest a[href="${r.url}"]`).count()===1,'Latest report mismatch');
    await page.locator('#newsEdition').selectOption(edition);
    assert(await page.locator('#newsList li').count()===expected.filter(r=>r.edition===edition).length,'Edition filter mismatch');
   }
   await page.locator('#newsEdition').selectOption('all');
   const overflow=await page.locator('.news-shell').evaluate(e=>e.scrollWidth>e.clientWidth+1);
   assert(!overflow,'News panel overflow');
   await page.locator('[data-tab="report"]').click();
   assert(await page.locator('[data-tab-panel="report"]').isVisible(),'Existing report tab broken');
   await page.locator('[data-tab="daily-report"]').click();
   await page.locator('[data-daily-tab="news"]').click();
   assert(await page.locator('[data-daily-pane="news"]').isVisible(),'News tab switch failed');
   for(const r of expected){
    const response=await context.request.get(new URL(r.url,url).href);
    assert(response.ok()&&(await response.text()).includes('<title>'),'Report link unavailable');
   }
   await page.locator('.news-shell').screenshot({path:path.join(root,`reports/news/dashboard-news-${width}.png`)});
   assert(!errors.length,JSON.stringify(errors));
   results.push({width,reportCount:expected.length,filters:true,lockPreserved:true,overflow:false,errors});
   await context.close();
  }
  console.log(JSON.stringify({url,pass:true,results}));
 }finally{if(browser)await browser.close();if(server)server.close();}
})().catch(e=>{console.error(e);process.exitCode=1});
