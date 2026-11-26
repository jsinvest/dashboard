'use strict';
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const {test}=require('node:test');
const source=fs.readFileSync(path.join(__dirname,'../live-monitors/dashboard.js'),'utf8');
const tabs={'program-live':'programLive','investor-live':'investorLive','cvd-live':'cvdLive'};
const config=url=>({mode:'readonly',url});
const ok=body=>({ok:true,json:async()=>body});

function harness(){
  let now=100000,response=()=>ok(config('https://first-live.trycloudflare.com'));
  const elements=new Map(),calls=[],timers=new Map();let timerId=0;
  const parent={insertBefore(element){elements.set(element.id,element);}};
  function element(id){
    let src='';
    return {id,dataset:{},hidden:true,textContent:'',parentNode:parent,nextSibling:null,assignments:[],
      get src(){return src;},set src(value){src=value;this.assignments.push(value);},
      removeAttribute(name){delete this[name];}};
  }
  for(const prefix of Object.values(tabs))for(const suffix of ['Frame','Status','Open'])elements.set(prefix+suffix,element(prefix+suffix));
  const context={window:{},URL,Date:{now:()=>now},Map,Promise,AbortController,
    setTimeout:fn=>{timers.set(++timerId,fn);return timerId;},clearTimeout:id=>timers.delete(id),
    document:{getElementById:id=>elements.get(id),createElement:()=>element('')},
    fetch:async(...args)=>{calls.push(args);return response(...args);}};
  vm.runInNewContext(source,context,{filename:'dashboard.js'});
  return {load:context.window.loadLiveMonitor,elements,calls,
    advance(ms){now+=ms;},respond(fn){response=fn;},
    runTimeouts(){for(const fn of [...timers.values()])fn();},
    frame(tab){return elements.get(tabs[tab]+'Frame');},
    retry(tab){return elements.get(tabs[tab]+'Retry');}};
}

test('three tabs share one in-flight manifest and use their own readonly paths',async()=>{
  const h=harness();
  await Promise.all(Object.keys(tabs).map(tab=>h.load(tab)));
  assert.equal(h.calls.length,1);
  for(const [tab,prefix] of Object.entries(tabs)){
    assert.equal(h.frame(tab).hidden,false);
    assert.equal(h.frame(tab).src,'https://first-live.trycloudflare.com/'+tab.replace('-live','')+'/');
    assert.equal(h.elements.get(prefix+'Open').hidden,false);
  }
  assert.equal(h.calls[0][1].cache,'no-store');
});

test('tab revisits reuse short-lived config without reloading an unchanged iframe',async()=>{
  const h=harness();
  await h.load('program-live');
  h.advance(14999);await h.load('program-live');
  assert.equal(h.calls.length,1);
  assert.equal(h.frame('program-live').assignments.length,1);
});

test('expired cache rotates a previously loaded iframe for all three tabs',async()=>{
  const h=harness();
  await Promise.all(Object.keys(tabs).map(tab=>h.load(tab)));
  h.advance(15000);h.respond(()=>ok(config('https://rotated-live.trycloudflare.com')));
  await Promise.all(Object.keys(tabs).map(tab=>h.load(tab)));
  assert.equal(h.calls.length,2);
  for(const tab of Object.keys(tabs)){
    assert.match(h.frame(tab).src,/^https:\/\/rotated-live\.trycloudflare\.com\//);
    assert.equal(h.frame(tab).assignments.length,2);
  }
});

test('repeated requests for the same tab share fetch and only latest request paints',async()=>{
  const h=harness();let finish;
  h.respond(()=>new Promise(resolve=>{finish=resolve;}));
  const first=h.load('program-live'),second=h.load('program-live');
  await Promise.resolve();await Promise.resolve();
  assert.equal(h.calls.length,1);
  finish(ok(config('https://newest-live.trycloudflare.com')));
  await Promise.all([first,second]);
  assert.equal(h.frame('program-live').assignments.length,1);
  assert.equal(h.frame('program-live').src,'https://newest-live.trycloudflare.com/program/');
});

test('manual retry refreshes config even before TTL expires',async()=>{
  const h=harness();await h.load('cvd-live');
  h.respond(()=>ok(config('https://retry-live.trycloudflare.com')));
  await h.retry('cvd-live').onclick();
  assert.equal(h.calls.length,2);
  assert.equal(h.frame('cvd-live').src,'https://retry-live.trycloudflare.com/cvd/');
});

test('a stalled manifest is aborted and cannot hold future retries or overwrite recovered config',async()=>{
  const h=harness();let finish;
  h.respond(()=>new Promise(resolve=>{finish=resolve;}));
  const stalled=h.load('program-live');await Promise.resolve();await Promise.resolve();
  h.runTimeouts();await stalled;
  assert.equal(h.calls[0][1].signal.aborted,true);
  assert.equal(h.frame('program-live').hidden,true);
  h.respond(()=>ok(config('https://recovered-live.trycloudflare.com')));
  await h.retry('program-live').onclick();
  assert.equal(h.frame('program-live').src,'https://recovered-live.trycloudflare.com/program/');
  finish(ok(config('https://obsolete-live.trycloudflare.com')));
  await Promise.resolve();await Promise.resolve();await h.load('program-live');
  assert.equal(h.frame('program-live').src,'https://recovered-live.trycloudflare.com/program/');
  assert.equal(h.calls.length,2);
});

test('manifest HTTP failure hides stale frame/link and permits recovery for each tab',async()=>{
  for(const [tab,prefix] of Object.entries(tabs)){
    const h=harness();await h.load(tab);h.advance(15000);
    h.respond(()=>({ok:false}));await h.load(tab);
    assert.equal(h.frame(tab).hidden,true);assert.equal(h.frame(tab).src,'about:blank');
    assert.equal(h.frame(tab).dataset.loaded,undefined);
    assert.equal(h.elements.get(prefix+'Open').hidden,true);
    assert.equal(h.elements.get(prefix+'Open').href,undefined);
    assert.equal(h.retry(tab).hidden,false);
    h.respond(()=>ok(config('https://recovered-live.trycloudflare.com')));
    await h.retry(tab).onclick();
    assert.equal(h.frame(tab).hidden,false);
    assert.match(h.frame(tab).src,/^https:\/\/recovered-live\.trycloudflare\.com\//);
  }
});

test('invalid config and unsafe URL variants never reach an iframe',async()=>{
  const invalid=[null,[],{},config('http://a.trycloudflare.com'),config('https://trycloudflare.com'),
    config('https://a.trycloudflare.com.evil.example'),config('https://nested.a.trycloudflare.com'),
    config('https://user:secret@a.trycloudflare.com'),config('https://a.trycloudflare.com:8443'),
    config('https://a.trycloudflare.com/other/'),config('https://a.trycloudflare.com/?token=abc'),
    config('https://a.trycloudflare.com/#fragment'),{url:'https://a.trycloudflare.com',mode:'write'}];
  for(const body of invalid){
    const h=harness();h.respond(()=>ok(body));
    await Promise.all(Object.keys(tabs).map(tab=>h.load(tab)));
    for(const tab of Object.keys(tabs)){
      assert.equal(h.frame(tab).hidden,true,JSON.stringify(body));
      assert.equal(h.frame(tab).src,'about:blank');
    }
  }
});

test('network/JSON manifest failure is recoverable without claiming tunnel health',async()=>{
  for(const respond of [()=>Promise.reject(new Error('offline')),()=>({ok:true,json:async()=>{throw new Error('bad JSON');}})]){
    const h=harness();h.respond(respond);await h.load('investor-live');
    assert.equal(h.frame('investor-live').hidden,true);
    assert.match(h.elements.get('investorLiveStatus').textContent,/연결 정보를 확인하지 못/);
    assert.equal(h.retry('investor-live').hidden,false);
    h.respond(()=>ok(config('https://retry-live.trycloudflare.com')));
    await h.retry('investor-live').onclick();assert.equal(h.frame('investor-live').hidden,false);
  }
});

test('unknown tabs do not fetch or alter monitor frames',async()=>{
  const h=harness();await h.load('unrelated-tab');assert.equal(h.calls.length,0);
});
