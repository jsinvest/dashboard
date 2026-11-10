// Earnings periods are evidence-based; calendar months are never a substitute.
let reportPeriods={events:[],overrides:{}},reportPeriod='unknown';
function reportPeriodInfo(r){
 const override=reportPeriods.overrides[r['텔레그램URL']];
 if(override)return {...override,label:'실적 대상',sameDay:false};
 const date=r['날짜']||r['최근날짜']||'',code=r['종목코드'];
 const events=reportPeriods.events.filter(e=>e.code===code&&e.date<=date).sort((a,b)=>b.date.localeCompare(a.date));
 const e=events[0];
 if(!e)return {period:'unknown',label:'실적 분기·발표일 미확인'};
 return {...e,label:'발표 이후 구간',sameDay:e.date===date};
}
function reportPeriodRows(rows){return rows.filter(r=>reportPeriod==='all'||reportPeriodInfo(r).period===reportPeriod);}
function reportPeriodLabel(p){return p==='unknown'?'분기 미확인':p.replace('-Q','년 ')+'분기';}
function periodSummary(rows){
 const groups=new Map();rows.forEach(r=>{const k=r['종목코드'];if(!groups.has(k))groups.set(k,[]);groups.get(k).push(r)});
 return [...groups.values()].map(rs=>{
  const high=[...rs].sort((a,b)=>Number(b['목표주가'])-Number(a['목표주가'])||b['날짜'].localeCompare(a['날짜']))[0];
  const latest=[...rs].sort((a,b)=>b['날짜'].localeCompare(a['날짜'])||Number(b['목표주가'])-Number(a['목표주가']))[0];
  return {'종목명':high['종목명'],'종목코드':high['종목코드'],'최고가날짜':high['날짜'],'최고목표주가':high['목표주가'],'최근날짜':latest['날짜'],'최근목표주가':latest['목표주가'],'언급횟수':rs.length,'제목(최고가기준)':high['제목'],'내용(최고가기준)':high['내용'],'기관(최고가기준)':high['기관']};
 }).sort((a,b)=>b['최근날짜'].localeCompare(a['최근날짜']));
}
function periodBadge(r){
 const p=reportPeriodInfo(r);let text=p.period==='unknown'?p.label:reportPeriodLabel(p.period)+' · '+p.label;
 text+=p.date?' · 발표 '+p.date:' · 발표일 미확인';
 if(p.sameDay)text+=' · 같은 날 전후 미확인';
 if(p.report_date&&p.report_date!==r['날짜'])text+=' · 원문 발간 '+p.report_date+' / 기존 저장 '+r['날짜'];
 const source=p.source?` <a href="${escapeHtml(p.source)}" target="_blank" rel="noopener">분기 근거</a>`:'';
 return `<small class="report-period-badge" title="${escapeHtml(p.basis||'')}">${escapeHtml(text)}${source}</small>`;
}
const originalSignalRow=renderSignalRow;
renderSignalRow=function(r,d,o){return originalSignalRow(r,d,o).replace('</strong>','</strong>'+periodBadge(r)).replace('</tr>',`<td>${r['출처']?escapeHtml(r['출처']):'기존 보관 자료'}${r['원문URL']?` <a href="${escapeHtml(r['원문URL'])}" target="_blank" rel="noopener">원문</a>`:''}</td></tr>`);};
const originalSignalTable=renderSignalTable;
renderSignalTable=function(rows,d){return originalSignalTable(rows,d).replace('<th>원문</th>','<th>텔레그램</th><th>출처</th>');};
const originalDetail=renderReportDetail;
renderReportDetail=function(rows){let html=originalDetail(rows);rows.forEach(r=>{const needle=`<td>${escapeHtml(r['종목명'])}</td>`;html=html.replace(needle,`<td>${escapeHtml(r['종목명'])}${periodBadge(r)}</td>`)});return html;};
searchReports=function(){
 const q=document.getElementById('reportSearchInput').value.trim(),box=document.getElementById('reportResults');lastReportQuery=q;
 const rows=reportPeriodRows(reportData.details),source=reportMode==='detail'?rows:periodSummary(rows);
 const results=source.filter(r=>!q||reportMatch(r,q)).sort((a,b)=>(b['날짜']||b['최근날짜']).localeCompare(a['날짜']||a['최근날짜']));
 box.className=results.length?'':'report-empty';box.innerHTML=results.length?(reportMode==='detail'?renderReportDetail(results.slice(0,200)):renderReportSummary(results.slice(0,200))):'선택한 분기에 검색 결과가 없습니다.';
 document.getElementById('reportPeriodResultCount').textContent=`검색 ${results.length.toLocaleString()}건${results.length>200?' · 최신 200건 표시':''} · 최고목표가는 선택한 분기 내 기준`;
};
renderSignalList=function(direction){
 const up=direction==='up',q=document.getElementById(up?'reportUpSearch':'reportDownSearch').value.trim(),cat=document.getElementById(up?'reportUpCategory':'reportDownCategory').value;
 const rows=reportPeriodRows(reportSignalData[direction]||[]).filter(r=>(!cat||r['구분']===cat)&&signalSearchMatch(r,q));
 const box=document.getElementById(up?'reportUpResults':'reportDownResults');box.className=rows.length?'':'report-empty';box.innerHTML=rows.length?renderSignalTable(rows,direction):'조건에 맞는 시그널이 없습니다.';
};
const originalStats=renderSignalStats;
renderSignalStats=function(direction){const all=reportSignalData[direction];try{reportSignalData[direction]=reportPeriodRows(all||[]);originalStats(direction)}finally{reportSignalData[direction]=all}};
const originalSetReportMode=setReportMode;setReportMode=function(mode){originalSetReportMode(mode);searchReports();};
function changeReportPeriod(){
 reportPeriod=document.getElementById('reportPeriodSelect').value;
 searchReports();['up','down'].forEach(d=>{renderSignalStats(d);renderSignalList(d)});
}
(async()=>{
 try{
  const res=await fetch('report-periods/data.json?v='+Date.now(),{cache:'no-store'});if(!res.ok)throw Error('분기 자료 HTTP '+res.status);reportPeriods=await res.json();
  await Promise.all([loadReportData(),loadReportSignalData()]);
  const periods=[...new Set([...reportPeriods.events.map(e=>e.period),...Object.values(reportPeriods.overrides).map(e=>e.period)])].sort().reverse();
  const select=document.getElementById('reportPeriodSelect');select.innerHTML=periods.map(p=>`<option value="${p}">${reportPeriodLabel(p)} 발표 이후</option>`).join('')+'<option value="unknown">분기 미확인 (보관)</option><option value="all">전체 이력</option>';const lastDate=reportPeriods.events.map(e=>e.date).sort().at(-1);const cutoff=new Date(Date.parse(lastDate+'T00:00:00Z')-30*86400000).toISOString().slice(0,10);const counts={};reportPeriods.events.filter(e=>e.date>=cutoff).forEach(e=>counts[e.period]=(counts[e.period]||0)+1);select.value=Object.keys(counts).sort((a,b)=>counts[b]-counts[a]||b.localeCompare(a))[0]||'unknown';
  const latest=reportData.details.map(r=>r['날짜']).sort().at(-1);
  document.getElementById('reportMeta').textContent=`전체 보관 ${reportData.details.length.toLocaleString()}건 · 최신 리포트 ${latest} · 수집 ${reportData.meta.generated_at||'-'}`;
  const unknown=reportData.details.filter(r=>reportPeriodInfo(r).period==='unknown').length;
  document.getElementById('reportPeriodNote').textContent=`종목별 실적발표일부터 다음 발표 전까지 구분합니다(DAJU 공시 요약 기준). 동일 날짜는 발표 전후 미확인. 분기 미확인 ${unknown.toLocaleString()}건은 별도 보관하며 삭제하지 않습니다. 리포트가 다루는 실적 분기와 발표 이후 구간은 다를 수 있습니다.`;
  changeReportPeriod();window.reportPeriodsReady=true;
 }catch(e){document.getElementById('reportPeriodNote').textContent='분기 자료 검증·로딩 실패: '+e.message;console.error(e);}
})();
