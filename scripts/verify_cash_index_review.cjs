// Isolated headless rendering QA. Does not touch the user's browser or HTS.
const fs = require('fs');
const path = require('path');
const http = require('http');
const crypto = require('crypto');
const vm = require('vm');
const {chromium} = require('C:/Users/skylo/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const root = path.resolve(__dirname, '..');
const output = process.argv[3];
if (!output) throw new Error('Usage: node verify_cash_index_review.cjs local|https://... output-directory');
fs.mkdirSync(output, {recursive:true});
const html = fs.readFileSync(path.join(root, 'index.html'), 'utf8');
for (const m of html.matchAll(/<script\b([^>]*)>([\s\S]*?)<\/script>/gi)) {
  if (!/\bsrc=|application\/json|application\/ld\+json/i.test(m[1]) && m[2].trim()) new vm.Script(m[2]);
}
const expected = JSON.parse(fs.readFileSync(path.join(root,'supply-zone/latest.json'),'utf8'));
// Git normalizes CRLF to LF; compare parsed content, retaining transport hash.
const expectedHash = crypto.createHash('sha256').update(JSON.stringify(expected)).digest('hex');
(async()=>{
  let server, browser;
  try {
    let url = process.argv[2];
    if (url === 'local') {
      server = http.createServer((req,res)=>{
        let file = path.resolve(root, '.' + decodeURIComponent(new URL(req.url,'http://localhost').pathname));
        if (file === root) file = path.join(root,'index.html');
        if (!file.startsWith(root+path.sep) || !fs.existsSync(file) || !fs.statSync(file).isFile()) {res.writeHead(404);res.end();return;}
        const mime={'.html':'text/html; charset=utf-8','.js':'text/javascript; charset=utf-8','.css':'text/css; charset=utf-8','.json':'application/json; charset=utf-8','.png':'image/png'}[path.extname(file)] || 'application/octet-stream';
        res.writeHead(200,{'Content-Type':mime,'Cache-Control':'no-store'});fs.createReadStream(file).pipe(res);
      });
      await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
      url = `http://127.0.0.1:${server.address().port}/`;
    }
    browser = await chromium.launch({headless:true,channel:'chrome'});
    const results=[];
    for(const [name,width,height] of [['desktop',1440,1000],['mobile',390,844]]) {
      const context = await browser.newContext({viewport:{width,height},deviceScaleFactor:1});
      const page=await context.newPage();
      const errors=[];
      page.on('pageerror',e=>errors.push(e.message));
      await page.goto(url+'?cash_review_verify='+Date.now(),{waitUntil:'domcontentloaded',timeout:45000});
      await page.waitForSelector('.cash-review', {state:'attached',timeout:45000});
      // Use the existing project access form in an isolated QA browser only.
      const candidate = process.env.JS_DASHBOARD_QA_PASSWORD;
      if (!candidate) throw new Error('Set the project QA access credential in JS_DASHBOARD_QA_PASSWORD');
      const configuredHash = html.match(/const passwordHash='([^']+)'/)[1];
      if (crypto.createHash('sha256').update(candidate).digest('hex') !== configuredHash) throw new Error('QA access credential changed; do not bypass lock');
      await page.locator('#dashboardPassword').fill(candidate);
      await page.locator('#dashboardUnlockButton').click();
      await page.waitForFunction(()=>document.getElementById('dashboardLock').hidden);
      await page.locator('[data-tab="supply"]').click();
      await page.waitForSelector('.cash-review',{state:'visible'});
      await page.waitForFunction(()=>[...document.querySelectorAll('.cash-review img')].every(i=>i.complete && i.naturalWidth>100));
      const live = await page.evaluate(async()=>{
        const response=await fetch('supply-zone/latest.json?verify='+Date.now(),{cache:'no-store'});
        const bytes=await response.arrayBuffer();
        const hash=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes)),x=>x.toString(16).padStart(2,'0')).join('');
        const canonical=new TextEncoder().encode(JSON.stringify(JSON.parse(new TextDecoder().decode(bytes))));
        const contentHash=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',canonical)),x=>x.toString(16).padStart(2,'0')).join('');
        const panel=document.querySelector('[data-tab-panel="supply"]');
        return {hash,contentHash,meta:document.getElementById('supplyMeta').textContent,
          headline:panel.querySelector('h2').textContent,
          indices:[...panel.querySelectorAll('[data-cash-index]')].map(x=>x.dataset.cashIndex),
          images:[...panel.querySelectorAll('img')].map(i=>({src:i.getAttribute('src'),width:i.naturalWidth,height:i.naturalHeight})),
          timeframeCards:panel.querySelectorAll('.cash-timeframes>div').length,
          flowCollapsed:!document.getElementById('cashDerivatives').open,
          originalChartsCollapsed:[...panel.querySelectorAll('.cash-index details')].every(x=>!x.open),
          bodyOverflow:document.documentElement.scrollWidth>innerWidth+2,
          failureVisible:[...panel.querySelectorAll('*')].some(x=>x.children.length===0 && /로딩 실패|AI 분석 준비되지 않음|필수 형식.*누락/.test(x.textContent) && x.getClientRects().length)};
      });
      if(live.contentHash!==expectedHash || !live.meta.includes(expected.as_of) || live.headline!==expected.review.headline ||
        live.indices.join(',')!=='KOSPI,NASDAQ,SOX,NIKKEI,DOW' || live.timeframeCards!==20 || live.images.length!==6 ||
        !live.flowCollapsed || !live.originalChartsCollapsed || live.failureVisible || live.bodyOverflow || errors.length) {
        throw new Error(JSON.stringify({name,live,errors}));
      }
      await page.screenshot({path:path.join(output,name+'_top.png')});
      await page.locator('.cash-levels').screenshot({path:path.join(output,name+'_levels.png')});
      await page.locator('[data-cash-index="SOX"] details').first().locator('summary').click();
      await page.locator('[data-cash-index="SOX"] .cash-chart').screenshot({path:path.join(output,name+'_sox_chart.png')});
      results.push({name,url,...live,errors});
      await context.close();
    }
    fs.writeFileSync(path.join(output,'render_validation.json'),JSON.stringify({verified_at:new Date().toISOString(),results},null,2));
    console.log(JSON.stringify({status:'PASS',results},null,2));
  }finally{
    if(browser)await browser.close();
    if(server)await new Promise(r=>server.close(r));
  }
})().catch(e=>{console.error(e);process.exitCode=1;});
