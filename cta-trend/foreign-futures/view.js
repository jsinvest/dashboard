'use strict';
const signed=(n,d=0)=>(n>0?'+':n<0?'−':'')+Math.abs(n).toLocaleString('ko-KR',{minimumFractionDigits:d,maximumFractionDigits:d});
const price=n=>n.toLocaleString('ko-KR',{minimumFractionDigits:2,maximumFractionDigits:2});
const money=n=>{const a=Math.abs(n),tr=Math.floor(a/1000000);return (n>0?'+':n<0?'−':'')+(tr?tr+'조 ':'')+((a%1000000)/100).toLocaleString('ko-KR',{maximumFractionDigits:2})+'억 원';};
const monthName=m=>m.slice(0,4)+'년 '+Number(m.slice(5))+'월물';
const labels={foreign:'외국인',institution:'기관',v:'선물 금액',q:'선물 계약 수',c:'현물 금액'};
const val=(n,u)=>Number.isFinite(n)?(u==='q'?signed(n)+'계약':money(n)):'자료 없음';
const esc=x=>String(x).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function weekKey(d){const t=new Date(d+'T12:00:00Z');t.setUTCDate(t.getUTCDate()-(t.getUTCDay()+6)%7);return t.toISOString().slice(0,10);}
function groupWeeks(rows){const w=new Map();for(const p of rows)w.set(weekKey(p.date),p);return Array.from(w.values());}
function series(base,comp,owner,unit){
 const foreign=owner==='foreign', periodMap=new Map(base.periods.map(p=>[p.month,p])), sorted=base.periods.slice().sort((a,b)=>a.month.localeCompare(b.month));
 const official=sorted.at(-1), active=foreign&&unit!=='c'?official.month:comp.month;
 const match=active===comp.month, lookup=(date)=>comp.index[date]??null;
 const published=base.weekly.filter(w=>w.month===active).concat(official.month===active?[official]:[]).sort((a,b)=>a.through.localeCompare(b.through));
 const anchors=new Map(published.map(w=>[w.through,w]));
 let v=0,q=0,c=0;
 const days=(match?comp.daily:[]).map(r=>{
   v+=foreign?r.fv:r.iv; q+=foreign?r.fq:r.iq;c+=foreign?r.fc:r.ic;
   const a=foreign&&anchors.get(r.d);
   if(a){v=a.netMillion;q=a.contracts;}
   return {date:r.d,v,q,c,idx:lookup(r.d),moneyStatus:a?'KRX 확정':'복수 마감자료 잠정',month:active};
 });
 const confirmedRows=published.map(w=>({date:w.through,v:w.netMillion,q:w.contracts,idx:lookup(w.through),moneyStatus:'KRX 확정',month:active}));
 const weeksMap=new Map((foreign&&unit!=='c'?confirmedRows:[]).map(p=>[p.date,p]));
 for(const p of days)weeksMap.set(p.date,p);
 const weeks=groupWeeks(Array.from(weeksMap.values()).sort((a,b)=>a.date.localeCompare(b.date)));
 const now=weeks.at(-1);
 const history=foreign? sorted.filter(p=>p.through===p.expiry&&(unit!=='c'||p.month<active||comp.foreignCash?.[active]?.through===p.through)).slice(-40).map(p=>{
   const cash=comp.foreignCash?.[p.month];
   return {month:p.month,date:p.through,v:p.netMillion,q:p.contracts,c:cash?.through===p.through?cash.c:null,idx:lookup(p.through),done:true,moneyStatus:'KRX 확정'};
 }):
 comp.institution.map(p=>({month:p.month,date:p.through,v:p.v,q:p.q,qr:p.qr,c:p.c,idx:lookup(p.through),done:true,moneyStatus:'만기 종료'}));
 const activePeriod=periodMap.get(active);
 const months=history.slice();
 if(now&&months.at(-1)?.month!==active)months.push({...now,done:false});
 const shot=foreign&&base.intraday?.month===active&&now&&base.intraday.observedAt.slice(0,10)>now.date?base.intraday:null;
 return {days,weeks,months,history,now,shot,active,start:activePeriod?.start??days[0]?.date,official:foreign?official:null};
}
function scaleBounds(values,div,zero){
 let min=Math.min(...values),max=Math.max(...values);if(zero){min=Math.min(0,min);max=Math.max(0,max);}
 if(!(max>min)){let p=Math.max(Math.abs(max)*0.04,1);min-=p;max+=p;}
 const raw=(max-min)/div,b=10**Math.floor(Math.log10(raw)),step=([1,2,2.5,5,10].find(x=>x*b>=raw)||10)*b;
 let lo=Math.floor(min/step)*step,hi=Math.ceil(max/step)*step;if(lo===hi)hi+=step;return {lo,hi,step};
}
function svgTag(name,attrs,body=''){return '<'+name+' '+Object.entries(attrs).map(([k,v])=>k+'="'+esc(v)+'"').join(' ')+'>'+body+'</'+name+'>';}
function quantile(sorted, fraction){
 const rank=(sorted.length-1)*fraction, low=Math.floor(rank), high=Math.ceil(rank);
 return sorted[low]+(sorted[high]-sorted[low])*(rank-low);
}
function bandFor(history,unit,mode){
 if(unit==='q')return [-50000,50000];
 if(unit==='v'||mode==='fixed')return [-5,5];
 const values=history.map(p=>p.c).filter(Number.isFinite).map(v=>v/1e6).sort((a,b)=>a-b);
 return values.length<2?null:[quantile(values,.05),quantile(values,.95)];
}
function chart(data,unit,showIndex,width,id,history,projection,band){
 const W=Math.max(280,Math.round(width)),H=W<540?218:246,L=unit==='q'?(W<540?50:65):40,R=W-(showIndex?54:15),T=28,B=H-28;
 const factor=unit==='q'?1:1000000;
 const isRef=p=>unit==='q'&&p.q==null&&Number.isInteger(p.qr);
 const raw=p=>isRef(p)?p.qr:p[unit], available=data.filter(p=>Number.isFinite(raw(p)));
 if(!available.length)return {html:'<p>이 기간의 비교 자료가 없습니다.</p>',list:[],left:0,right:1,W};
 const yn=data.filter(p=>Number.isFinite(raw(p))).map(p=>raw(p)/factor);
 const scale=scaleBounds(yn.concat(band??[]),5,true);
 const indexVals=showIndex?data.map(p=>p.idx).filter(Number.isFinite):[];
 const indexScale=indexVals.length?scaleBounds(indexVals,4,false):null;
 const x=i=>data.length===1?(L+R)/2:L+(R-L)*i/(data.length-1), y=(v,s=scale)=>B-(v-s.lo)*(B-T)/(s.hi-s.lo);
 const line=(x1,y1,x2,y2,attrs)=>svgTag('line',{x1,y1,x2,y2,...attrs});
 const tx=(x,y,text,attrs={})=>svgTag('text',{x,y,'font-size':W<540?10:11,...attrs},esc(text));
 let g='';
 if(band)g+=svgTag('rect',{x:L,y:y(band[1]),width:R-L,height:y(band[0])-y(band[1]),fill:'#e5f1ec'});
 for(let z=scale.lo;z<=scale.hi+scale.step/100;z+=scale.step){
   g+=line(L,y(z),R,y(z),{stroke:z===0?'#9aadb1':'#dce6e6','stroke-width':z===0?1.25:0.8});
   g+=tx(L-5,y(z)+4,signed(z,Number.isInteger(z)?0:1),{'text-anchor':'end',fill:'#37606b'});
 }
 if(band)for(const b of band)g+=line(L,y(b),R,y(b),{stroke:'#67a38c','stroke-width':1.2,'stroke-dasharray':'5 4'});
 g+=tx(L,14,unit==='q'?'계약':'조 원',{fill:'#246574'});
 if(indexScale){g+=tx(R,14,'지수 (pt)',{fill:'#96520b','text-anchor':'end'});for(let z=indexScale.lo;z<=indexScale.hi+indexScale.step/100;z+=indexScale.step)g+=tx(R+5,y(z,indexScale)+4,z.toLocaleString('ko-KR'),{fill:'#96520b'});}
 function segments(get,sty){let s='';let started=false;data.forEach((p,i)=>{const v=get(p);if(!Number.isFinite(v)){started=false;return;}s+=(started?' L':' M')+x(i).toFixed(2)+' '+v.toFixed(2);started=true;});return svgTag('path',{d:s,fill:'none','stroke-linejoin':'round','stroke-linecap':'round',...sty});}
 if(indexScale)g+=segments(p=>Number.isFinite(p.idx)?y(p.idx,indexScale):null,{stroke:'#b46b23','stroke-width':2,'stroke-dasharray':'6 4'});
 g+=segments(p=>!p.live&&!isRef(p)&&Number.isFinite(p[unit])?y(p[unit]/factor):null,{stroke:'#126b7a','stroke-width':2.5});
 data.forEach((p,i)=>{const n=raw(p);if(!Number.isFinite(n))return;
  if(p.live&&i>0&&Number.isFinite(raw(data[i-1])))g+=line(x(i-1),y(raw(data[i-1])/factor),x(i),y(n/factor),{stroke:'#126b7a','stroke-dasharray':'3 3'});
  g+=svgTag('circle',{cx:x(i),cy:y(n/factor),r:i===data.length-1?4:isRef(p)?3:2.1,fill:isRef(p)?'#fff':'#126b7a',stroke:isRef(p)?'#80939b':'#126b7a','stroke-width':isRef(p)?1.5:0.6});});
 if(indexScale&&Number.isFinite(data.at(-1).idx))g+=svgTag('circle',{cx:x(data.length-1),cy:y(data.at(-1).idx,indexScale),r:3,fill:'#b46b23'});
 const n=Math.min(data.length,Math.max(2,Math.min(8,Math.floor((R-L)/70))));
 Array.from({length:n},(_,i)=>n===1?0:Math.round(i*(data.length-1)/(n-1))).forEach(i=>{const p=data[i];g+=tx(x(i),H-7,history?p.month.slice(2).replace('-','.'):p.date.slice(5).replace('-','.'),{'text-anchor':i===0?'start':i===data.length-1?'end':'middle',fill:'#506875'});});
 g+=line(R,T,R,B,{id:id+'-cursor',stroke:'#607682','stroke-dasharray':'2 3',opacity:0});
 return {html:svgTag('svg',{id,viewBox:'0 0 '+W+' '+H,'aria-label':(history?'최근 10년 월물별':projection==='week'?'주별':'일별')+' '+labels[unit]+' 누적'+(indexScale?' 및 코스피200 현물지수 종가':''),tabindex:0,role:'img',class:'plot'},g),list:data,left:L,right:R,W};
}
function chartDetails(p,unit,showIndex){
 if(!p)return '';
 const ref=unit==='q'&&p.q==null&&Number.isInteger(p.qr);
 let text=(p.month?monthName(p.month)+' · ':'')+p.date+'  |  '+labels[unit]+' '+val(ref?p.qr:p[unit],unit);
 if(ref)text+=' (참고)';else if(unit==='v'&&p.moneyStatus)text+=' ('+p.moneyStatus+')';
 if(showIndex)text+='  |  코스피200 종가 '+(Number.isFinite(p.idx)?price(p.idx)+' pt':'미확인');
 return text;
}
function drawPage(base,comp,s,width){
 const a=series(base,comp,s.owner,s.unit),p=a.now;if(!p)throw Error('누적 자료 없음');
 const u=s.unit, useDays=s.freq==='day', lastDate=p.date;
 const freq=useDays?'일별':'주별',n=s.owner==='foreign'?'외국인':'기관';
 const live=a.shot&&u==='v'?{month:a.active,date:a.shot.observedAt.slice(0,10),v:a.shot.netEok*100,live:true,moneyStatus:'장중 '+a.shot.observedAt.slice(11,16),idx:null}:null;
 const monthly=a.months.slice();if(live)monthly.push(live);
 const detail=(useDays?a.days:a.weeks).slice();if(live)detail.push(live);
 const band=bandFor(a.history,u,s.band);
 const chart1=chart(monthly,u,s.overlay,width,'history',true,s.freq,band);
 const chart2=chart(detail,u,s.overlay,width,'current',false,s.freq,band);
 const valid=a.history.map(p=>p[u]).filter(Number.isFinite).map(v=>u==='q'?v:v/1e6);
 const inBand=band?valid.filter(v=>v>=band[0]&&v<=band[1]).length:0;
 const bounds=u==='q'?'±5만 계약':u==='v'||s.band==='fixed'?'±5조 원':band?signed(band[0],2)+' ~ '+signed(band[1],2)+'조 원 (5~95백분위)':'자료 부족';
 const bandNote=(u==='c'?'코스피 '+n+' 현물 · ':'')+'음영 '+bounds+(band?' · 만기 종료 '+valid.length+'개 중 '+inBand+'개가 밴드 안에서 마감':'');
 const refNote=u==='q'&&s.owner==='institution'?' · 빈 원은 추가 검증이 필요한 20개 월물로, 밴드 통계에서 제외':'';
 const pressed=(g,k,caption)=>'<button type="button" data-group="'+g+'" data-value="'+k+'" aria-pressed="'+String(s[g]===k)+'">'+caption+'</button>';
 const controller=(owner,opts)=>'<div class="controls" role="group" aria-label="'+esc(owner)+'">'+opts+'</div>';
 const labelsLine='<span class="legend flow">누적 순매수 · 왼쪽</span>'+(s.overlay?'<span class="legend index">코스피200 종가 · 오른쪽</span>':'');
 const overlay='<label class="overlay"><input type="checkbox" data-overlay '+(s.overlay?'checked':'')+'> 코스피200 종가 겹쳐보기</label>';
 const ucontrols=pressed('unit','v','선물 금액')+pressed('unit','q','계약 수')+pressed('unit','c','현물 금액');
 const cashBandControls=u==='c'?controller('현물 밴드 기준',pressed('band','percentile','과거 90% 구간')+pressed('band','fixed','±5조 원')):'';
 const spot=Number.isFinite(p.c)?money(p.c):'자료 없음';
 const metric=(t,c,d)=>'<div><small>'+t+'</small><strong>'+c+'</strong><span>'+d+'</span></div>';
 const most=a.shot?a.shot.netEok*100:p.v;
 const hdr='<header><div class="bar"><h1>코스피200 '+n+' 누적 수급</h1>'+controller('투자자',pressed('owner','foreign','외국인')+pressed('owner','institution','기관'))+'</div><p class="subtitle">'+monthName(a.active)+' · '+a.start+' ~ '+lastDate+' 마감</p><div class="metrics">'+metric('선물 누적 순매수',money(most),a.shot?a.shot.observedAt.slice(0,16).replace('T',' ')+' 장중':p.moneyStatus)+metric('선물 누적 계약 수',val(p.q,'q'),lastDate+' 마감')+metric('코스피 현물 누적 순매수',spot,lastDate+' 기준')+'</div></header>';
 const mkSection=(title,controls,note,ch,id)=>'<section><div class="bar"><h2>'+title+'</h2>'+controls+'</div><p class="note">'+note+'</p><div class="legends">'+labelsLine+'</div>'+ch.html+'<output id="'+id+'-out">'+esc(chartDetails(ch.list.at(-1),u,s.overlay))+'</output></section>';
 const hist=mkSection('월물별 누적 순매수 · 최근 10년',controller('표시 지표',ucontrols),bandNote+refNote,chart1,'history');
 const previousWeek=a.weeks.filter(w=>weekKey(w.date)<weekKey(p.date)).at(-1);
 const weekChange=previousWeek&&Number.isFinite(p[u])&&Number.isFinite(previousWeek[u])?' · 직전 주 마감('+previousWeek.date+') 대비 '+val(p[u]-previousWeek[u],u):'';
 const detailSection=mkSection(monthName(a.active)+' · '+freq+' 누적',controller('시간 단위',pressed('freq','week','주별')+pressed('freq','day','일별')),(useDays?'매 거래일 마감 기준 · 직전 만기 다음 거래일부터 누적':'각 주의 마지막 거래일 기준 · 진행 중인 주는 최근 마감일까지 누적')+weekChange,chart2,'current');
 const link='<a href="kospi200-foreign-futures-20261124.xlsx" download>외국인 선물 10년 원자료 엑셀</a>';
 const notes='<section><details><summary>월물별 수치와 집계 기준</summary><p>선물은 직전 분기 만기 다음 거래일부터 코스피200 일반선물 전 결제월의 순매수를 누적합니다. 현물 수급은 코스피 전체이며, 오른쪽 축은 코스피200 현물지수 종가(pt)입니다. 지수는 같은 거래일 자료가 있을 때만 표시합니다.</p><p>'+ (s.owner==='institution'?'진행 월물 선물 금액은 KRX·키움 등 마감 자료 합산 잠정치입니다. 과거 계약 수 15개 월물은 KRX 기준표와 집계 차이, 5개는 투자자 합계 불일치로 참고 표시했습니다.':'금액·계약 수는 KRX 확정 자료를 우선합니다. KRX 확정일 사이의 일별 금액과 이후 마감 금액은 복수 자료 합산 잠정치입니다. 2017년 3월 27일 거래승수는 50만 원에서 25만 원으로 변경됐습니다.')+'</p>'+
 '<p>현물 밴드는 주체별로 최근 완료 월물 종료값의 5·95백분위를 선형 보간합니다. ±5조 원으로도 비교할 수 있습니다. 밴드 포함 횟수는 만기 종료값 기준입니다. 과거 외국인 현물은 네이버 코스피 외국인·기타외국인의 일별 합계, 이번 조사(2026년 12월물)는 지표담 코스피 종합 외인계(등록+미등록)입니다. 두 원천의 집계 범위·시각에 따라 값이 달라질 수 있습니다.</p><p>최근 지수는 키움 ka20006과 LS t8429 마감 종가를 대조했습니다. 과거 지수는 키움 코스피200 일봉을 사용했습니다.</p><div class="scroll"><table><thead><tr><th>월물</th><th>기준일</th><th>선물 (조 원)</th><th>선물 (계약)</th><th>현물 (조 원)</th><th>코스피200 (pt)</th></tr></thead><tbody>'+a.months.slice().reverse().map(z=>'<tr><td>'+monthName(z.month)+'</td><td>'+z.date+'</td><td>'+signed(z.v/1e6,3)+'</td><td>'+(!Number.isFinite(z.q)?signed(z.qr)+' (참고)':signed(z.q))+'</td><td>'+(Number.isFinite(z.c)?signed(z.c/1e6,3):'—')+'</td><td>'+(Number.isFinite(z.idx)?price(z.idx):'—')+'</td></tr>').join('')+'</tbody></table></div><p>'+link+' · <a href="https://data.krx.co.kr/contents/MDC/MDI/mdiLoader/index.cmd?menuId=MDC0201050302">KRX 투자자별 거래실적</a></p></details></section>';
 const officialLine=s.owner==='foreign'&&a.official?'<small>최근 KRX 확정 · '+a.official.through+' · '+money(a.official.netMillion)+' · '+val(a.official.contracts,'q')+'</small>':'';
 return {html:hdr+'<div class="settings">'+overlay+cashBandControls+officialLine+'</div>'+hist+detailSection+notes,charts:[chart1,chart2]};
}
function mount(base,comp){
 const app=document.getElementById('app'),s={owner:'foreign',unit:'v',freq:'week',band:'percentile',overlay:true};
 let plots;
 function draw(){
  const width=Math.max(280,app.clientWidth-(app.clientWidth<600?28:48));
  const page=drawPage(base,comp,s,width);app.innerHTML=page.html;plots=page.charts;
  for(const [i,id] of ['history','current'].entries()){
   const d=plots[i],el=document.getElementById(id);if(!el)continue;
   const cursor=document.getElementById(id+'-cursor'),out=document.getElementById(id+'-out');let focus=d.list.length-1;
   function pick(j,active){focus=Math.max(0,Math.min(d.list.length-1,j));const x=d.list.length===1?(d.left+d.right)/2:d.left+(d.right-d.left)*focus/(d.list.length-1);cursor.setAttribute('x1',x);cursor.setAttribute('x2',x);cursor.setAttribute('opacity',active?'1':'0');out.textContent=chartDetails(d.list[focus],s.unit,s.overlay);}
   el.onpointermove=el.onpointerdown=e=>{const box=el.getBoundingClientRect(),pos=(e.clientX-box.left)*d.W/box.width;pick(Math.round((pos-d.left)/(d.right-d.left)*(d.list.length-1)),true);};
   el.onpointerleave=()=>pick(d.list.length-1,false);
   el.onkeydown=e=>{if(['ArrowLeft','ArrowRight','Home','End'].includes(e.key)){e.preventDefault();pick(e.key==='Home'?0:e.key==='End'?d.list.length-1:focus+(e.key==='ArrowRight'?1:-1),true);}};
  }
 }
 app.onclick=e=>{const b=e.target.closest('button[data-group]');if(!b)return;const g=b.dataset.group;if(!['owner','unit','freq','band'].includes(g))return;s[g]=b.dataset.value;draw();app.querySelector('button[data-group="'+g+'"][data-value="'+s[g]+'"]')?.focus({preventScroll:true});};
 app.onchange=e=>{if(e.target.matches('[data-overlay]')){s.overlay=e.target.checked;draw();app.querySelector('[data-overlay]').focus({preventScroll:true});}};
 draw();let w=app.clientWidth;new ResizeObserver(()=>{if(Math.abs(w-app.clientWidth)>1){w=app.clientWidth;draw();}}).observe(app);
}
if(typeof document!=='undefined'){
 const fetchJSON=async url=>{const r=await fetch(url,{cache:'no-cache'});if(!r.ok)throw Error(url);return r.json();};
 Promise.all(['data.json','comparison.json'].map(fetchJSON)).then(([b,c])=>mount(b,c)).catch(()=>{document.getElementById('load-status').textContent='최근 데이터를 불러오지 못했습니다. 아래에는 게시 시점의 마감 자료를 표시합니다.';});
}
