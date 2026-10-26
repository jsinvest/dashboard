(()=>{
  const el=id=>document.getElementById(id);
  const escape=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const normalize=v=>String(v??'').toLowerCase().replace(/\s+/g,'');
  let data, history=[], historyState='loading';
  const comparison=document.createElement('div');
  comparison.id='dailyReportComparison';
  el('dailyReportResults').before(comparison);
  function renderComparison(query,rows){
    comparison.hidden=!query;
    if(!query){comparison.innerHTML='';return;}
    if(historyState!=='ready'){
      comparison.textContent=historyState==='loading'?'보유 리포트 최고목표주가 조회 중…':'보유 리포트 DB를 불러오지 못해 최고목표주가 비교가 불가능해요.';
      return;
    }
    const codes=new Set(rows.map(r=>r.code));
    const matches=history.filter(r=>codes.has(r['종목코드'])||Object.values(r).some(v=>normalize(v).includes(query)));
    const matchedCodes=new Set(matches.map(r=>r['종목코드']));
    const missing=[...new Map(rows.filter(r=>!matchedCodes.has(r.code)).map(r=>[r.code,r])).values()];
    comparison.innerHTML='<h3>보유 리포트 DB 최고목표주가</h3><p>기존 리포트 검색과 같은 DB 기준이에요. 시장 전체 최고가가 아니며, 현재 당일 리포트는 이 기준값에 합산하지 않아요.</p>'+matches.map(r=>{
      const high=Number(r['최고목표주가']), code=r['종목코드'];
      const selected=rows.filter(x=>x.code===code);
      const comparisons=selected.map(x=>{
        let status='비교 불가';
        if(Number.isFinite(high)&&high>0&&r['최고가날짜']<=x.date){
          const difference=x.price-high;
          status=(difference>0?'DB 최고가 초과':difference===0?'DB 최고가 동일':'DB 최고가 미만')+' · '+(difference>0?'+':'')+difference.toLocaleString('ko-KR')+'원 ('+(difference>0?'+':'')+(difference/high*100).toFixed(2)+'%)';
        }
        return `<li>${escape(x.date)} · ${escape(x.broker)} · ${x.price.toLocaleString('ko-KR')}원 → <b>${escape(status)}</b></li>`;
      }).join('');
      return `<article data-history-code="${escape(code)}"><strong>${escape(r['종목명'])} (${escape(code)})</strong><p>최고목표주가 <b>${high.toLocaleString('ko-KR')}원</b> · ${escape(r['최고가날짜'])} · ${escape(r['기관(최고가기준)'])}</p><p>최근목표주가 ${Number(r['최근목표주가']).toLocaleString('ko-KR')}원 · ${escape(r['최근날짜'])} · 언급 ${escape(r['언급횟수'])}건</p>${comparisons?'<ul>'+comparisons+'</ul>':'<p>선택한 날짜에 일치하는 상향·하향 리포트가 없어요.</p>'}</article>`;
    }).join('')+missing.map(r=>`<p>${escape(r.name)} (${escape(r.code)}): 보유 DB 비교자료 없음</p>`).join('')+(!matches.length&&!missing.length?'<p>보유 DB 검색 결과가 없어요.</p>':'');
  }
  fetch('report_data.json?v='+Date.now(),{cache:'no-store'}).then(r=>{if(!r.ok)throw Error('HTTP '+r.status);return r.json()}).then(value=>{
    if(!Array.isArray(value.summary))throw Error('Invalid report summary');
    history=value.summary;historyState='ready';if(data)render();
  }).catch(()=>{historyState='error';if(data)render();});
  function render(){
    const day=data.days[el('dailyReportDate').value];
    const query=normalize(el('dailyReportSearch').value);
    const rows=day.reports.filter(r=>[r.name,r.code,r.broker,r.title,r.summary].some(v=>normalize(v).includes(query)));
    renderComparison(query,rows);
    el('dailyReportCounts').textContent=`원문 전체 ${day.source_count}건 · 상향 ${day.up}건 · 하향 ${day.down}건 · 중복 제외 ${new Set(day.reports.map(r=>r.code)).size}종목 · 검색 결과 ${rows.length}건`;
    el('dailyReportResults').innerHTML=[['up','목표주가 상향'],['down','목표주가 하향']].map(([cls,status])=>{
      const list=rows.filter(r=>r.status===status);
      return `<section class="${cls}" aria-label="${status}"><h3>${status} · ${list.length}건</h3>${list.map(r=>`<article><strong>${escape(r.name)} (${escape(r.code)})</strong><p>${escape(r.broker)} · ${escape(r.date)}<br>목표주가 <b>${Number(r.price).toLocaleString('ko-KR')}원</b></p><p>${escape(r.title)}</p><details><summary>리포트 요약 펼쳐보기</summary><p>${escape(r.summary)}</p></details></article>`).join('')||'<p>해당 조건의 리포트가 없어요.</p>'}</section>`;
    }).join('');
  }
  fetch('daily-reports/latest.json?v='+Date.now(),{cache:'no-store'}).then(r=>{if(!r.ok)throw Error('HTTP '+r.status);return r.json()}).then(value=>{
    data=value;
    const today=new Intl.DateTimeFormat('sv-SE',{timeZone:'Asia/Seoul'}).format(new Date());
    el('dailyReportMeta').textContent=`최신 자료 ${data.latest_date} · 수집 ${data.collected_at.replace('T',' ').slice(0,19)} KST${data.latest_date!==today?' · 오늘 자료 미수집 (아래는 최신 확보일 자료)':''}`;
    el('dailyReportDate').innerHTML=Object.keys(data.days).sort().reverse().map(d=>`<option value="${escape(d)}">${escape(d)}</option>`).join('');
    el('dailyReportDate').addEventListener('change',render);
    el('dailyReportSearch').addEventListener('input',render);
    render();
  }).catch(()=>{el('dailyReportMeta').textContent='당일 리포트 자료를 불러오지 못했어요. 새로고침 후 다시 확인해 주세요.';});
})();
