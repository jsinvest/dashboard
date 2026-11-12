const fs=require('fs'),path=require('path'),http=require('http'),assert=require('assert'),vm=require('vm');
const {chromium}=require(path.join(require('os').homedir(),'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright'));
const root=path.resolve(__dirname,'..'),output=path.resolve(process.argv[3]);
fs.mkdirSync(output,{recursive:true});
const html=fs.readFileSync(path.join(root,'index.html'),'utf8');
for(const m of html.matchAll(/<script\b([^>]*)>([\s\S]*?)<\/script>/gi))if(!/\bsrc=|application\/json|application\/ld\+json/i.test(m[1])&&m[2].trim())new vm.Script(m[2]);
const analysis=JSON.parse(fs.readFileSync(path.join(root,'market-analysis/analysis_latest.json'),'utf8'));
const futures=JSON.parse(fs.readFileSync(path.join(root,'supply-zone/latest.json'),'utf8'));
(async()=>{
 let server,browser;
 try{
  let url=process.argv[2];
  if(url==='local'){
   server=http.createServer((req,res)=>{
    let file=path.resolve(root,'.'+decodeURIComponent(new URL(req.url,'http://local').pathname));
    if(file===root)file=path.join(root,'index.html');
    if(!file.startsWith(root+path.sep)||!fs.existsSync(file)||!fs.statSync(file).isFile()){res.writeHead(404);return res.end()}
    const type={'.html':'text/html; charset=utf-8','.json':'application/json; charset=utf-8','.js':'text/javascript; charset=utf-8','.png':'image/png','.css':'text/css; charset=utf-8'}[path.extname(file)]||'application/octet-stream';
    res.writeHead(200,{'Content-Type':type,'Cache-Control':'no-store'});fs.createReadStream(file).pipe(res);
   });
   await new Promise(r=>server.listen(0,'127.0.0.1',r));url=`http://127.0.0.1:${server.address().port}/`;
  }
  browser=await chromium.launch({headless:true,channel:'chrome'});
  const results=[];
  for(const width of [1280,390]){
   const context=await browser.newContext({viewport:{width,height:920}}),page=await context.newPage(),errors=[];
   page.on('pageerror',e=>errors.push(e.message));
   await page.goto(url+'?privacy_qa='+Date.now(),{waitUntil:'domcontentloaded',timeout:45000});
   await page.waitForFunction(()=>document.querySelectorAll('#linkBody tr').length>1);
   const links=await page.locator('#linkBody').innerText();
   assert(!links.includes('제이의 투자노트'));
   assert(!links.includes('docs.google.com/spreadsheets'));
   await page.locator('[data-tab="links"]').click();
   const linkCount=await page.locator('#linkBody tr').count();
   await page.screenshot({path:path.join(output,`links-${width}.png`)});
   await page.locator('[data-tab="market"]').click();
   await page.waitForFunction(date=>document.querySelector('#marketAIMeta')?.textContent.includes(date),analysis.as_of);
   const market=await page.locator('#marketAIContent').innerText();
   assert(market.includes(analysis.headline));assert(!market.includes('AI 분석 준비되지 않음'));
   for(const view of analysis.market_views)assert(market.includes(view.market));
   for(const pick of analysis.final_picks)assert(market.includes(pick.name||pick.stock_name||pick.code));
   await page.screenshot({path:path.join(output,`market-${width}.png`)});
   await page.locator('[data-tab="supply"]').click();
   await page.waitForFunction(date=>document.querySelector('#supplyMeta')?.textContent.includes(date),futures.as_of);
   assert.deepStrictEqual(errors,[]);
   results.push({width,link_count:linkCount,investment_note_rendered:false,analysis_date:analysis.as_of,final_picks:analysis.final_picks.length,futures_date:futures.as_of,page_errors:errors});
   await context.close();
  }
  const result={status:'PASS',checked_at:new Date().toISOString(),scope:'Rendered public dashboard; external server inventory and Drive sharing verified separately.',results};
  fs.writeFileSync(path.join(output,'validation.json'),JSON.stringify(result,null,2));console.log(JSON.stringify(result));
 }finally{if(browser)await browser.close();if(server)await new Promise(r=>server.close(r))}
})().catch(e=>{console.error(e);process.exitCode=1});
