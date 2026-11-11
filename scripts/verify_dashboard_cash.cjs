// Read-only cash-menu QA in fresh isolated headless browser contexts.
const fs=require('fs'),path=require('path'),http=require('http'),assert=require('assert');
const {chromium}=require('C:/Users/skylo/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const root=path.resolve(__dirname,'..'),out=process.argv[3];
if(!out)throw Error('Usage: node scripts/verify_dashboard_cash.cjs local|https://... output-directory');
const expected=JSON.parse(fs.readFileSync(path.join(root,'cash-management/latest.json'),'utf8'));
const date=(expected.trade_date||expected.as_of).replaceAll('-','').slice(0,8);
const displayDate=`${date.slice(0,4)}-${date.slice(4,6)}-${date.slice(6,8)}`;
fs.mkdirSync(out,{recursive:true});
(async()=>{let server,browser;const results=[];
try{
 let base=process.argv[2];
 if(base==='local'){
  server=http.createServer((req,res)=>{
   const url=new URL(req.url,'http://localhost');
   let file=path.resolve(root,'.'+decodeURIComponent(url.pathname));
   if(file===root)file=path.join(root,'index.html');
   if(!file.startsWith(root+path.sep)||!fs.existsSync(file)||!fs.statSync(file).isFile()){res.writeHead(404);res.end();return;}
   const mime={'.html':'text/html; charset=utf-8','.js':'text/javascript; charset=utf-8','.css':'text/css','.json':'application/json','.png':'image/png'}[path.extname(file)]||'application/octet-stream';
   res.writeHead(200,{'Content-Type':mime,'Cache-Control':'no-store'});fs.createReadStream(file).pipe(res);
  });
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));base=`http://127.0.0.1:${server.address().port}/`;
 }
 base=base.replace(/\/?$/,'/');
 browser=await chromium.launch({headless:true,channel:'msedge'});
 for(const width of [1280,390]){
  const context=await browser.newContext({viewport:{width,height:950}}),page=await context.newPage(),errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  await page.goto(base+'?cash_qa='+Date.now(),{waitUntil:'domcontentloaded',timeout:45000});
  const lock=page.locator('#dashboardLock');const locked=await lock.count()>0&&await lock.isVisible();
  if(locked){
   if(!process.env.JS_DASHBOARD_QA_PASSWORD)throw Error('BLOCKED_CREDENTIAL_REQUIRED: actual visible dashboard lock');
   await page.locator('#dashboardPassword').fill(process.env.JS_DASHBOARD_QA_PASSWORD);
   await page.locator('#dashboardUnlockButton').click();
   await lock.waitFor({state:'hidden',timeout:15000});
  }
  await page.locator('[data-tab="cash"]').click();
  await page.waitForFunction(date=>document.querySelector('#cashManagementContent')?.textContent.includes(date),displayDate);
  assert(await page.locator('#cashManagementContent').isVisible(),'Cash content must actually be visible');
  const text=await page.locator('#cashManagementContent').innerText();
  for(const term of ['월간','MA10','MA3','단계형',displayDate])assert(text.includes(term),term);
  const guidance=expected.combined_guidance;
  for(const pct of [guidance.target_cash_pct,guidance.target_risky_pct])assert(text.includes(Number(pct).toLocaleString('ko-KR')+'%'),'Rendered reference percentage');
  assert(!/불러오지 못|로딩 실패/.test(text),'Cash fallback must not be active');
  const response=await page.request.get(base+'cash-management/latest.json?cash_qa='+Date.now());
  assert(response.ok());assert.deepStrictEqual(await response.json(),expected);
  assert.deepStrictEqual(errors,[]);
  await page.screenshot({path:path.join(out,`cash-${width}.png`)});
  results.push({width,status:'PASS',date,authentication_gate_present:locked,credential_used:locked,auth_bypass:false,
   actual_cash_content_visible:true,public_json_matches_expected:true,cash_pct:guidance.target_cash_pct,risky_cap_pct:guidance.target_risky_pct,page_errors:errors,text});
  await context.close();
 }
 fs.writeFileSync(path.join(out,'validation.json'),JSON.stringify({status:'PASS',checked_at:new Date().toISOString(),results},null,2));
 console.log(JSON.stringify({status:'PASS',date,widths:results.map(r=>r.width)}));
}catch(error){
 fs.writeFileSync(path.join(out,'validation.json'),JSON.stringify({status:'INCOMPLETE',checked_at:new Date().toISOString(),reason:error.message,results},null,2));throw error;
}finally{if(browser)await browser.close();if(server)await new Promise(r=>server.close(r));}
})().catch(e=>{console.error(e.message);process.exitCode=1});
