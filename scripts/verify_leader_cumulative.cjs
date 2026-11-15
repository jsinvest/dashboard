const fs=require('fs'),path=require('path'),http=require('http'),vm=require('vm'),assert=require('assert'),cp=require('child_process');
const {chromium}=require(path.join(require('os').homedir(),'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright'));
const root=path.resolve(__dirname,'..'),output=path.resolve(process.argv[3]);
fs.mkdirSync(output,{recursive:true});
const html=fs.readFileSync(path.join(root,'index.html'),'utf8');
const baselineRef=process.env.LEADER_BASE_REF||'HEAD';
const baseline=cp.execFileSync('git',['show',baselineRef+':index.html'],{cwd:root,encoding:'utf8',maxBuffer:8*1024*1024});
for(const match of html.matchAll(/<script\b([^>]*)>([\s\S]*?)<\/script>/gi))if(!/\bsrc=|application\/json|application\/ld\+json/i.test(match[1])&&match[2].trim())new vm.Script(match[2]);
const payload=text=>JSON.parse(text.match(/const LEADER_CUMULATIVE_\d{8}=(.*?);\s*for\(const market/s)[1]);
const data=payload(html);
assert.deepStrictEqual(data,payload(baseline),'Weekly view must not modify embedded source data');
const activeHistory=JSON.parse(html.match(/const LEADER_CUMULATIVE_HISTORY=(.*?);\s*/s)[1]);
for(const market of ['KOSPI','KOSDAQ'])Object.assign(activeHistory[market],data[market].history);
const sourceData=Object.fromEntries(Object.entries(data).map(([market,source])=>[market,{...source,history:activeHistory[market]}]));
function calculate(text,source,market,period){
 const context=vm.createContext({LEADER_CUMULATIVE_HISTORY_ACTIVE:{[market]:source.history},leaderCumulativeMarket:market,leaderCumulativePeriod:period});
 vm.runInContext(text.slice(text.indexOf('function leaderTreeDateLabel'),text.indexOf('function leaderTreeGap')),context);
 context.base=source;
 return JSON.parse(vm.runInContext('JSON.stringify(leaderPeriodData(base))',context));
}
function fixture(dates){return {days:dates.map(date=>[`${Number(date.slice(4,6))}/${Number(date.slice(6,8))}`,[]]),frequency:[],tree:[],history:{sector:{d:dates.map((date,index)=>[date,index+1,index%2?'B':'A',70,'대표주']),l:[]}}};}
const boundaries=[
 {dates:['20261106','20261109','20261111','20261113'],included:['20261109','20261111','20261113'],range:'11/9~11/13'},
 {dates:['20261112','20261113','20261116'],included:['20261116'],range:'11/16~11/20'},
 {dates:['20261127','20261130','20261201','20261202'],included:['20261130','20261201','20261202'],range:'11/30~12/4'},
 {dates:['20261224','20261228','20261231','20270101'],included:['20261228','20261231','20270101'],range:'12/28~1/1'}
];
for(const test of boundaries){
 const result=calculate(html,fixture(test.dates),'KOSPI','weekly');
 assert.deepStrictEqual(result.history.sector.d.map(row=>row[0]),test.included);
 assert.equal(result.days.length,test.included.length);assert.equal(result.tree[0][1],test.included.length);
 assert(result.periodTitle.includes(test.range));
 assert.equal(result.tree[0][2],test.included.length);
 assert.equal(result.tree[0][3],test.included.includes(test.dates[0])?1:0);
 assert.equal(result.history.sector.l.reduce((total,row)=>total+row[1],0),test.included.length);
}
assert.deepStrictEqual(calculate(html,fixture([]),'KOSPI','weekly').tree,[]);
for(const market of ['KOSPI','KOSDAQ'])for(const period of ['daily','monthly','quarterly'])assert.deepStrictEqual(calculate(html,sourceData[market],market,period),calculate(baseline,sourceData[market],market,period),`${market} ${period} changed`);
const expected={};
for(const market of ['KOSPI','KOSDAQ']){
 const source=sourceData[market];
 const dates=[...new Set(Object.values(source.history).flatMap(item=>item.d.map(row=>row[0])))].sort();
 const last=dates.at(-1),anchor=new Date(`${last.slice(0,4)}-${last.slice(4,6)}-${last.slice(6,8)}T00:00:00Z`);
 const monday=new Date(anchor);monday.setUTCDate(anchor.getUTCDate()-(anchor.getUTCDay()+6)%7);
 const start=monday.toISOString().slice(0,10).replaceAll('-','');
 const included=dates.filter(date=>date>=start&&date<=last);
 const result=calculate(html,source,market,'weekly');
 assert.deepStrictEqual(result.days.map(day=>day[0]),included.map(date=>`${Number(date.slice(4,6))}/${Number(date.slice(6,8))}`));
 assert.equal(Object.values(result.history).reduce((sum,item)=>sum+item.d.length,0),included.length*15,'Every sourced day must have 15 sector observations');
 for(const row of result.tree){
  const records=source.history[row[0]].d.filter(day=>included.includes(day[0]));
  assert.equal(row[1],records.length);assert.equal(row[2],records.filter(day=>day[1]<=5).length);assert.equal(row[3],records.filter(day=>day[1]===1).length);
 }
 expected[market]={result,included};
}
(async()=>{
 let server,browser;
 try{
  let url=process.argv[2];
  if(url==='local'){
   server=http.createServer((req,res)=>{
    let file=path.resolve(root,'.'+decodeURIComponent(new URL(req.url,'http://local').pathname));if(file===root)file=path.join(root,'index.html');
    if(!file.startsWith(root+path.sep)||!fs.existsSync(file)||!fs.statSync(file).isFile()){res.writeHead(404);return res.end()}
    const mime={'.html':'text/html; charset=utf-8','.json':'application/json; charset=utf-8','.js':'text/javascript; charset=utf-8','.css':'text/css; charset=utf-8','.png':'image/png'}[path.extname(file)]||'application/octet-stream';
    res.writeHead(200,{'Content-Type':mime,'Cache-Control':'no-store'});fs.createReadStream(file).pipe(res);
   });
   await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));url=`http://127.0.0.1:${server.address().port}/`;
  }
  browser=await chromium.launch({headless:true,channel:'chrome'});const results=[];
  for(const width of [1600,390]){
   const context=await browser.newContext({viewport:{width,height:1000}}),page=await context.newPage(),errors=[];page.on('pageerror',error=>errors.push(error.message));
   await page.goto(url+'?leader_weekly_qa='+Date.now(),{waitUntil:'domcontentloaded',timeout:45000});
   await page.locator('[data-tab="leaders"]').click();await page.locator('[data-leader-mode="cumulative"]').click();
   await page.locator('[data-cumulative-period="weekly"]').click();
   for(const market of ['KOSPI','KOSDAQ']){
    await page.locator(`[data-cumulative-market="${market}"]`).click();
    const actual=await page.evaluate(()=>leaderPeriodData(LEADER_CUMULATIVE_DATA[leaderCumulativeMarket]));
    assert.deepStrictEqual(actual,expected[market].result);
    const host=page.locator('#leaderCumulativeBody');assert((await host.innerText()).includes(expected[market].result.periodTitle));
    assert.equal(await host.locator('.leader-tree-root span').innerText(),'주간 누적');
    assert.equal(await host.locator('[data-leader-tree-sector]').count(),expected[market].result.tree.length);
    for(const row of expected[market].result.tree){
     await host.locator(`[data-leader-tree-sector="${row[0]}"]`).click();
     assert.equal(await host.locator('.leader-tree-leaf').count(),row[1]);
    }
    await page.locator('.leader-cumulative-controls').scrollIntoViewIfNeeded();
    await page.screenshot({path:path.join(output,`weekly-${market}-${width}.png`)});
    const overflow=await host.evaluate(element=>element.scrollWidth>element.clientWidth+2);assert(!overflow,'Weekly panel overflows');
    results.push({width,market,dates:expected[market].included,sectors:expected[market].result.tree.length,overflow});
   }
   for(const period of ['monthly','quarterly','daily']){await page.locator(`[data-cumulative-period="${period}"]`).click();assert.deepStrictEqual(await page.evaluate(()=>leaderPeriodData(LEADER_CUMULATIVE_DATA[leaderCumulativeMarket])),calculate(html,sourceData.KOSDAQ,'KOSDAQ',period));}
   assert.deepStrictEqual(errors,[]);await context.close();
  }
  const validation={status:'PASS',baseline:baselineRef,boundary_cases:boundaries.length,existing_periods_unchanged:true,source_data_unchanged:true,results};
  fs.writeFileSync(path.join(output,'validation.json'),JSON.stringify(validation,null,2));console.log(JSON.stringify(validation));
 }finally{if(browser)await browser.close();if(server)await new Promise(resolve=>server.close(resolve))}
})().catch(error=>{console.error(error);process.exitCode=1});
