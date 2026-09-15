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
   await page.waitForFunction(()=>document.querySelector('[data-tab-panel="news"]').dataset.newsLoaded==='true');
   assert(await page.locator('#dashboardLock').isVisible(),'Password lock was not preserved');
   // Exercise the existing remembered-session state in this disposable QA browser only.
   await page.evaluate(()=>sessionStorage.setItem('js-dashboard-unlocked-v1','1'));
   await page.reload({waitUntil:'domcontentloaded'});
   await page.waitForFunction(()=>document.querySelector('[data-tab-panel="news"]').dataset.newsLoaded==='true');
   assert(await page.locator('[data-tab-panel="news"]').isVisible(),'News deep link invisible');
   assert(await page.locator('#newsList li').count()===expected.length,'Archive count mismatch');
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
   await page.locator('[data-tab="news"]').click();
   assert(await page.locator('[data-tab-panel="news"]').isVisible(),'News tab switch failed');
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
