/* Recompute age in KST on every visit; a newly generated audit never freshens old data. */
(()=>{
  const dateKey=value=>{
    const match=String(value||'').match(/^(\d{4})-?(\d{2})-?(\d{2})/);
    if(!match)return null;
    const [y,m,d]=match.slice(1).map(Number),time=Date.UTC(y,m-1,d),date=new Date(time);
    return date.getUTCFullYear()===y&&date.getUTCMonth()===m-1&&date.getUTCDate()===d?time:null;
  };
  window.dashboardFreshnessAge=(value,now=new Date())=>{
    const parts=new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Seoul',year:'numeric',month:'2-digit',day:'2-digit'}).formatToParts(now);
    const get=type=>parts.find(p=>p.type===type).value;
    const observed=dateKey(value),today=dateKey(`${get('year')}-${get('month')}-${get('day')}`);
    return observed===null?null:Math.floor((today-observed)/86400000);
  };
  async function run(){
    const panel=document.createElement('details');panel.id='dashboardFreshness';panel.className='chart-card';
    panel.style.cssText='margin:12px 0;padding:12px 16px;border-left:3px solid #f59e0b;line-height:1.6';
    const summary=document.createElement('summary');summary.textContent='자료 갱신 상태 확인 중…';panel.append(summary);
    const host=document.querySelector('.main');if(!host)return;host.prepend(panel);
    try{
      const response=await fetch('dashboard-health/latest.json?v='+Date.now(),{cache:'no-store'});
      if(!response.ok)throw Error('HTTP '+response.status);
      const data=await response.json(),rows=data.items;
      if(!Array.isArray(rows))throw Error('자료 목록 누락');
      const problems=rows.filter(row=>{
        const age=window.dashboardFreshnessAge(row.data_date);
        return age!==null&&(age>=5||age<0)||['EXCLUDED','HISTORICAL_ONLY'].includes(row.availability);
      });
      summary.textContent=`자료 갱신 상태 · 5일 이상 지난 자료 ${rows.filter(row=>window.dashboardFreshnessAge(row.data_date)>=5).length}개 · 사용 제한 ${rows.filter(row=>['EXCLUDED','HISTORICAL_ONLY'].includes(row.availability)).length}개`;
      const note=document.createElement('p');note.style.cssText='font-size:12px;color:var(--text-dim)';
      note.textContent=`점검 ${data.as_of} · 한국 달력일 기준. 아래 경과일은 접속 시 다시 계산해요. 외부 차트·실시간 수급의 최신 관측은 각 화면에서 확인하며 설정파일 날짜로 판정하지 않아요.`;panel.append(note);
      for(const row of problems){
        const line=document.createElement('p'),button=document.createElement('button'),age=window.dashboardFreshnessAge(row.data_date);
        button.type='button';button.className='quick-btn';button.textContent=row.label;
        button.addEventListener('click',()=>document.querySelector(`.tab-btn[data-tab="${row.tab}"]`)?.click());
        line.append(button,document.createTextNode(` · ${row.data_date||'기준일 미확인'}${age===null?'':` · ${age}일 경과`} · ${row.note||'원천 갱신 필요'}`));
        line.style.cssText='font-size:12px;overflow-wrap:anywhere';panel.append(line);
      }
      if(!problems.length){const p=document.createElement('p');p.textContent='저장 자료 중 5일 이상 지난 항목이 없어요.';panel.append(p);}
      window.dashboardFreshnessReady=true;
    }catch(error){summary.textContent='자료 갱신 상태 확인 불가';const p=document.createElement('p');p.textContent=String(error.message);panel.append(p);}
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',run);else run();
})();
