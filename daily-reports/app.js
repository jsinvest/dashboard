(()=>{
  const el=id=>document.getElementById(id);
  const escape=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  let data;
  function render(){
    const day=data.days[el('dailyReportDate').value];
    const query=el('dailyReportSearch').value.trim().toLowerCase();
    const rows=day.reports.filter(r=>[r.name,r.code,r.broker,r.title,r.summary].join(' ').toLowerCase().includes(query));
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
