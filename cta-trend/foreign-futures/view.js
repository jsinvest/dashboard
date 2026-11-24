'use strict';
const byId = id => document.getElementById(id);
const signed = (value, digits = 0) => (value > 0 ? '+' : value < 0 ? '−' : '') +
  Math.abs(value).toLocaleString('ko-KR', {minimumFractionDigits: digits, maximumFractionDigits: digits});
function money(netMillion) {
  const total = Math.abs(netMillion), trillion = Math.floor(total / 1000000);
  return (netMillion > 0 ? '+' : netMillion < 0 ? '−' : '') + (trillion ? trillion + '조 ' : '') +
    ((total % 1000000) / 100).toLocaleString('ko-KR', {maximumFractionDigits:2}) + '억 원';
}
const monthName = m => m.slice(0,4) + '년 ' + Number(m.slice(5)) + '월물';
const prettyDate = date => date.replaceAll('-', '.');
const svgNS = 'http://www.w3.org/2000/svg';
function add(svg, name, attributes, text) {
  const el = document.createElementNS(svgNS, name);
  for (const [key,value] of Object.entries(attributes)) el.setAttribute(key, value);
  if (text !== undefined) el.textContent = text;
  svg.append(el);
  return el;
}
function chart(svg, output, points, settings) {
  svg.replaceChildren();
  const w = Math.max(270, Math.round(svg.getBoundingClientRect().width || 750)), h = w < 480 ? 173 : 202;
  svg.setAttribute('viewBox', '0 0 ' + w + ' ' + h);
  const left = settings.isMoney ? 39 : 58, right = w - 15, top = 18, bottom = h - 27;
  const vals = points.map(p => p.value);
  const max = Math.max(1, ...vals.map(Math.abs), settings.guides ? 5 : 0);
  const rough = max / 3, base = 10 ** Math.floor(Math.log10(rough));
  const step = ([1, 2, 2.5, 5, 10].find(n => n * base >= rough) || 10) * base;
  const hi = Math.max(step, Math.ceil(Math.max(0,...vals,settings.guides ? 5 : 0) / step) * step);
  const lo = Math.min(0, Math.floor(Math.min(0,...vals,settings.guides ? -5 : 0) / step) * step);
  const x = i => left + (points.length === 1 ? 0.5 : i / (points.length-1)) * (right-left);
  const y = v => top + (hi-v)/(hi-lo) * (bottom-top);
  if (settings.guides) add(svg,'rect',{x:left,y:y(5),width:right-left,height:y(-5)-y(5),fill:'#ecf5f1'});
  for(let val=lo;val<=hi+step/1000;val+=step) {
    add(svg,'line',{x1:left,x2:right,y1:y(val),y2:y(val),stroke:val===0?'#758994':'#dce5e9','stroke-width':val===0?1.4:0.8});
    add(svg,'text',{x:left-5,y:y(val)+4,'text-anchor':'end','font-size':10},signed(val,Number.isInteger(val)?0:1));
  }
  if(settings.guides) for(const val of [-5,5]) add(svg,'line',{x1:left,x2:right,y1:y(val),y2:y(val),stroke:'#86aa99','stroke-dasharray':'4 4'});
  const xy = (p,i) => x(i) + ',' + y(p.value);
  const confirmed = points.filter(p=>!p.live);
  if(confirmed.length>1) add(svg,'polyline',{points:confirmed.map(xy).join(' '),fill:'none',stroke:'#136778','stroke-width':2.4,'stroke-linejoin':'round'});
  const end = points.length-1, tail=points[end];
  if(tail.live && end) add(svg,'line',{x1:x(end-1),y1:y(points[end-1].value),x2:x(end),y2:y(tail.value),stroke:'#b76616','stroke-width':2.7,'stroke-dasharray':'4 3'});
  points.forEach((p,i)=>add(svg,'circle',{cx:x(i),cy:y(p.value),r:i===end?4:2.3,fill:p.live?'#ba6417':'#136778'}));
  const ticks = Math.min(points.length, Math.max(2,Math.min(7,Math.floor((right-left)/80))));
  const indices = ticks === 1 ? [0] : Array.from({length:ticks},(_,i)=>Math.round(i*end/(ticks-1)));
  for(const i of indices) add(svg,'text',{x:x(i),y:h-8,'text-anchor':i===0?'start':i===end?'end':'middle','font-size':10},points[i].axis);
  let focus=end;
  const cursor=add(svg,'line',{x1:x(end),x2:x(end),y1:top,y2:bottom,stroke:'#748892','stroke-dasharray':'2 3',opacity:0});
  function select(i, active) {
    focus=i; cursor.setAttribute('x1',x(i));cursor.setAttribute('x2',x(i));cursor.setAttribute('opacity',active?0.8:0);
    const item=points[i];output.textContent=item.label+'  ·  '+(settings.isMoney ? money(item.netMillion) : signed(item.contracts)+'계약');
  }
  svg.onpointermove=e=>{const pos=e.clientX-svg.getBoundingClientRect().left;select(Math.max(0,Math.min(end,Math.round((pos-left)/(right-left)*end))),true);};
  svg.onpointerleave=()=>select(end,false);
  svg.onkeydown=e=>{if(['ArrowLeft','ArrowRight','Home','End'].includes(e.key)){e.preventDefault();select(e.key==='Home'?0:e.key==='End'?end:Math.max(0,Math.min(end,focus+(e.key==='ArrowRight'?1:-1))),true);}};
  select(end,false);
}
async function main() {
  const response=await fetch('data.json',{cache:'no-cache'});
  if(!response.ok) throw Error('data');
  const data=await response.json();
  const periods=data.periods.slice().sort((a,b)=>a.month.localeCompare(b.month));
  const current=periods.at(-1);
  if(!current || periods.some(p=>!(Number.isFinite(p.netMillion)&&Number.isInteger(p.contracts)&&p.start<=p.through&&p.through<=p.expiry))) throw Error('기간 자료');
  const finished=periods.filter(p=>p.through===p.expiry).slice(-40);
  const rows=current.through===current.expiry?finished:[...finished,current];
  const intra=data.intraday;
  const live=intra && intra.month===current.month && intra.observedAt.slice(0,10)>current.through && Number.isSafeInteger(intra.netEok) ? intra : null;
  byId('period').textContent=monthName(current.month)+' · '+prettyDate(current.start)+'부터';
  byId('main-label').textContent=live?'최근 장중 누적 순매수':'최근 확정 누적 순매수';
  byId('latest').textContent=money(live?live.netEok*100:current.netMillion);
  byId('latest').classList.toggle('provisional',!!live);
  byId('latest-date').textContent=live?prettyDate(live.observedAt.slice(0,10))+' '+live.observedAt.slice(11,16)+'경 KST · '+live.source:prettyDate(current.through)+' · KRX';
  byId('official').textContent=money(current.netMillion);byId('qty').textContent=signed(current.contracts)+'계약';
  byId('official-date').textContent=byId('qty-date').textContent=prettyDate(current.through)+' 기준';
  byId('week-title').textContent=monthName(current.month)+' · 주별 누적';
  const body=byId('rows');
  for(const p of rows.slice().reverse()){
    const tr=body.insertRow();
    for(const val of [monthName(p.month),p.through,signed(p.netMillion/1000000,3),signed(p.contracts)])tr.insertCell().textContent=val;
  }
  const weeks=data.weekly.filter(w=>w.month===current.month && w.through<=current.through).sort((a,b)=>a.through.localeCompare(b.through));
  const previousWeek=weeks.filter(w=>w.through<(live?live.observedAt.slice(0,10):current.through)).at(-1);
  if(!live){
    byId('secondary-label').textContent='직전 주 마감 대비';
    byId('official').textContent=previousWeek?money(current.netMillion-previousWeek.netMillion):'—';
    byId('official-date').textContent=previousWeek?prettyDate(previousWeek.through)+'와 비교':'이번 월물의 첫 관측';
  }
  let unit='money';
  function draw(){
    const isMoney=unit==='money';
    const decorate=(p,label,axis,isLive=false)=>({...p,label,axis,live:isLive,value:isMoney?p.netMillion/1000000:p.contracts});
    const monthly=rows.map(p=>decorate(p,monthName(p.month)+' · '+p.through+(p.through===p.expiry?' 만기':' 확정'),p.month.slice(2).replace('-','.')));
    const weekly=weeks.map(p=>decorate(p,p.through+' 주 마감',p.through.slice(5).replace('-','.')));
    if(!weekly.length||weeks.at(-1).through!==current.through)weekly.push(decorate(current,current.through+' 확정',current.through.slice(5).replace('-','.')));
    if(live&&isMoney){
      const tag=live.observedAt.slice(0,10),point=decorate({netMillion:live.netEok*100},tag+' '+live.observedAt.slice(11,16)+' 장중',tag.slice(5).replace('-','.'),true);
      monthly.push({...point,axis:current.month.slice(2).replace('-','.')+'*'}); weekly.push(point);
    }
    const inRange=finished.filter(p=>Math.abs(p.netMillion)<=5000000).length;
    const cvals=finished.map(p=>p.contracts);
    byId('range').textContent=isMoney?'음영은 −5조~+5조 원 · 만기 종료 '+finished.length+'개 중 '+inRange+'개 ('+(100*inRange/finished.length).toFixed(1)+'%)':'만기 종료 '+finished.length+'개 범위 '+signed(Math.min(...cvals))+' ~ '+signed(Math.max(...cvals))+'계약';
    const comparison=weeks.filter(w=>w.through<(isMoney&&live?live.observedAt.slice(0,10):current.through)).at(-1);
    byId('weekly-change').textContent=comparison?'직전 주 마감('+prettyDate(comparison.through)+') 대비 '+(isMoney?money((live?live.netEok*100:current.netMillion)-comparison.netMillion):signed(current.contracts-comparison.contracts)+'계약'):'';
    chart(byId('history'),byId('history-read'),monthly,{isMoney,guides:isMoney});
    chart(byId('weekly'),byId('weekly-read'),weekly,{isMoney,guides:false});
  }
  for(const b of document.querySelectorAll('[data-unit]'))b.onclick=()=>{unit=b.dataset.unit;document.querySelectorAll('[data-unit]').forEach(x=>x.setAttribute('aria-pressed',String(x===b)));draw();};
  byId('content').hidden=false;byId('status').textContent=''; draw();
  let lastWidth=0;new ResizeObserver(entries=>{const width=entries[0].contentRect.width;if(width>0&&Math.abs(width-lastWidth)>1){lastWidth=width;draw();}}).observe(byId('content'));
}
main().catch(()=>{byId('content').hidden=true;byId('status').textContent='선물 수급 자료를 불러오지 못했습니다. 페이지를 새로고침해 주세요.';});
