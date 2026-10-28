/* Dated ETF holdings comparison. No trade or capital-flow inference. */
(() => {
  'use strict';
  const root = document.getElementById('etfWeightsPanel');
  if (!root) return;
  const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const n = (x, digits=2) => Number(x).toLocaleString('ko-KR',{minimumFractionDigits:digits,maximumFractionDigits:digits});
  const signed = (x,digits=2) => `${x>0?'+':''}${n(x,digits)}`;
  const labels = {NEW:'신규 편입',EXIT:'편출',UP:'비중 확대',DOWN:'비중 축소',SAME:'비중 동일'};
  let report, filtered=[];
  const link = u => /^https:\/\/www\.funetf\.co\.kr\/product\/etf\/view\/KR[A-Z0-9]+$/.test(u) ? u : 'https://www.funetf.co.kr/';
  function renderRows(){
    const fund=root.querySelector('#ewFund').value, kind=root.querySelector('#ewKind').value;
    const threshold=Number(root.querySelector('#ewThreshold').value), qty=root.querySelector('#ewQuantity').value;
    const query=root.querySelector('#ewSearch').value.trim().toLowerCase();
    filtered=report.events.filter(e => (!fund||e.etf_code===fund) && (!kind||(kind==='ENTRY_EXIT'?['NEW','EXIT'].includes(e.event):e.event===kind)) && (['NEW','EXIT'].includes(e.event)||Math.abs(e.delta_pp)>=threshold) && (!qty||(qty==='changed'?e.quantity_delta!==0:e.quantity_delta===0)) && (!query||`${e.stock_name} ${e.stock_code} ${e.etf_name}`.toLowerCase().includes(query)));
    root.querySelector('#ewResultCount').textContent=`${filtered.length.toLocaleString()}건 · ETF–종목 쌍 기준 · 신규/편출에는 최소변화 필터를 적용하지 않아요.`;
    root.querySelector('#ewRows').innerHTML=filtered.map(e=>`<tr><td>${esc(e.stock_name)}<span class="ew-code">${esc(e.stock_code)}</span></td><td>${esc(e.etf_name)}<span class="ew-code">${esc(e.etf_code)}</span></td><td><span class="ew-tag">${labels[e.event]}</span></td><td>${n(e.old_weight)}%</td><td>${n(e.new_weight)}%</td><td class="${e.delta_pp>0?'ew-up':'ew-down'}">${signed(e.delta_pp)}%p</td><td>${n(e.old_quantity_per_cu,0)} → ${n(e.new_quantity_per_cu,0)}</td><td>${signed(e.quantity_delta,0)}</td></tr>`).join('') || '<tr><td colspan="8" class="ew-empty">조건에 맞는 변화가 없어요.</td></tr>';
  }
  function download(){
    const cell=v=>'"'+String(v).replace(/^[=+@-]/,'\t$&').replaceAll('"','""')+'"';
    const rows=[['이전일','현재일','ETF코드','ETF','종목코드','종목','변화','이전비중%','현재비중%','증감%p','이전1CU수량','현재1CU수량','수량증감'],...filtered.map(e=>[report.start_date,report.end_date,e.etf_code,e.etf_name,e.stock_code,e.stock_name,labels[e.event],e.old_weight,e.new_weight,e.delta_pp,e.old_quantity_per_cu,e.new_quantity_per_cu,e.quantity_delta])];
    const url=URL.createObjectURL(new Blob(['\uFEFF'+rows.map(r=>r.map(cell).join(',')).join('\r\n')],{type:'text/csv;charset=utf-8'}));
    const a=document.createElement('a');a.href=url;a.download=`ETF비중_${report.start_date}_${report.end_date}.csv`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
  }
  function draw(d){
    if(d.schema_version!==1||d.status!=='COMPARED'||!Array.isArray(d.funds)||d.funds.length!==20||!Array.isArray(d.events)||d.errors.length) throw Error('20개 ETF의 비교 검증이 완료되지 않았어요.');
    const ids=new Set(d.funds.map(f=>f.code));
    if(ids.size!==20||d.events.some(e=>!ids.has(e.etf_code)||!labels[e.event]||![e.old_weight,e.new_weight,e.delta_pp,e.old_quantity_per_cu,e.new_quantity_per_cu,e.quantity_delta].every(Number.isFinite))) throw Error('구성자료 형식 오류');
    report=d;
    const ups=d.events.filter(e=>e.event==='UP'&&e.delta_pp>=.1).length;
    const downs=d.events.filter(e=>e.event==='DOWN'&&e.delta_pp<=-.1).length;
    const checked=d.funds.filter(f=>f.official_checked).length;
    const age=(Date.now()-Date.parse(d.end_date+'T00:00:00+09:00'))/86400000;
    const grouped=new Map();
    for(const e of d.events){
      if(!(['NEW','UP'].includes(e.event)&&(e.event==='NEW'||e.delta_pp>=.1)))continue;
      if(!grouped.has(e.stock_code))grouped.set(e.stock_code,{name:e.stock_name,code:e.stock_code,items:[]});
      grouped.get(e.stock_code).items.push(e);
    }
    const overlap=[...grouped.values()].filter(s=>s.items.length>=2).sort((a,b)=>b.items.length-a.items.length||a.code.localeCompare(b.code));
    root.innerHTML=`<h2>ETF비중</h2><p class="ew-muted">국내 주식 액티브 ETF 순자산 상위 20개 · ${esc(d.start_date)} → ${esc(d.end_date)}${d.partial_week?' · 이번주 진행 중':''}</p>
      <div class="ew-note">${age>10?'<strong>업데이트 확인 필요: 10일 이상 지난 비교자료예요.</strong><br>':''}현재 상위 20개를 같은 두 날짜로 비교했어요. 비중 변화에는 주가 등락이 포함되며, 실제 매수·매도나 추종자금 유입을 뜻하지 않아요.<br>두 날짜를 지정한 조회이며 응답 자체에 기준일은 없어요. TIME ${checked}개는 운용사 날짜·종목·수량·비중을 별도로 대조했어요.</div>
      <div class="ew-cards">${[[d.funds.length,'ETF 비교 완료'],[d.counts.NEW||0,'신규 편입'],[d.counts.EXIT||0,'편출'],[ups,'0.10%p 이상 확대'],[downs,'0.10%p 이상 축소']].map(([v,t])=>`<div class="ew-card"><span>${t}</span><strong>${n(v,0)}</strong></div>`).join('')}</div>
      <p class="ew-muted">건수는 ETF–종목 쌍 기준이에요. 모든 미세변화 포함: 확대 ${d.counts.UP||0}건 · 축소 ${d.counts.DOWN||0}건.</p>
      <div class="ew-box"><h3>종목별 변화</h3><div class="ew-controls">
      <label>ETF<select id="ewFund"><option value="">전체 20개</option>${d.funds.map(f=>`<option value="${esc(f.code)}">${f.rank}. ${esc(f.name)}</option>`).join('')}</select></label>
      <label>변화 유형<select id="ewKind"><option value="ENTRY_EXIT">신규 편입 · 편출</option><option value="">모든 변화</option>${Object.entries(labels).map(([k,v])=>`<option value="${k}">${v}</option>`).join('')}</select></label>
      <label>최소 비중변화<select id="ewThreshold"><option value="0.1">0.10%p</option><option value="0.5">0.50%p</option><option value="1">1.00%p</option><option value="0">미세변화 포함</option></select></label>
      <label>공개수량<select id="ewQuantity"><option value="">전체</option><option value="changed">수량도 변함</option><option value="same">수량 동일</option></select></label>
      <label class="ew-search">종목명 · 코드 검색<input id="ewSearch" type="search" placeholder="예: 삼성전자, 005930"></label></div>
      <p id="ewResultCount" class="ew-muted" aria-live="polite"></p><p class="ew-muted">작은 화면에서는 표를 좌우로 밀어 비중과 수량을 볼 수 있어요.</p>
      <div class="ew-scroll" tabindex="0" role="region" aria-label="ETF 구성종목 변화 표"><table><thead><tr><th>종목</th><th>ETF</th><th>구분</th><th>이전 비중</th><th>현재 비중</th><th>변화</th><th>공개수량 / 1CU</th><th>수량 증감</th></tr></thead><tbody id="ewRows"></tbody></table></div>
      <div class="ew-actions"><button id="ewDownload" type="button">현재 결과 CSV 저장</button></div><p class="ew-muted">수량은 1CU 공개값이에요. CU 크기 변경·기업행사를 확인하지 않아 실제 매매량으로 사용할 수 없어요.</p></div>
      <details class="ew-box"><summary>여러 ETF에서 함께 편입·확대한 종목 (${overlap.length}개)</summary><p class="ew-muted">신규 또는 0.10%p 이상 확대 ETF 수예요. 가격 상승만으로도 여러 ETF의 비중이 함께 늘 수 있어요.</p><div class="ew-scroll"><table><thead><tr><th>종목</th><th>편입·확대 ETF</th><th>ETF 수</th></tr></thead><tbody>${overlap.map(s=>`<tr><td>${esc(s.name)}<span class="ew-code">${s.code}</span></td><td>${s.items.map(e=>`${esc(e.etf_name)} (${signed(e.delta_pp)}%p)`).join('<br>')}</td><td>${s.items.length}</td></tr>`).join('')}</tbody></table></div></details>
      <details class="ew-box"><summary>추적 대상 20개 · 순자산 및 검증 상태</summary><p class="ew-muted">선정 조회일 ${d.ranking_observed_date} · 순자산 단위 억원 · NAV 참고일은 순자산 자체의 별도 기준일과 구분해요.</p><div class="ew-scroll"><table><thead><tr><th>순위 · ETF</th><th>순자산 / NAV 참고일</th><th>신규 / 편출</th><th>원문 추가 대조</th></tr></thead><tbody>${d.funds.map(f=>`<tr><td>${f.rank}. <a href="${link(f.source_url)}" target="_blank" rel="noopener">${esc(f.name)}</a><span class="ew-code">${f.code}</span></td><td>${n(f.aum_eok,0)}억원<br>${esc(f.nav_reference_date)}</td><td>${f.counts.NEW||0} / ${f.counts.EXIT||0}</td><td>${f.official_checked?'TIME 운용사 양일 일치':'날짜 지정 API · 원문 미대조'}</td></tr>`).join('')}</tbody></table></div></details>
      <details class="ew-box"><summary>출처와 비교 기준</summary><p>${esc(d.source)}</p><ul>${d.limitations.map(s=>`<li>${esc(s)}</li>`).join('')}</ul><p class="ew-muted">수집 ${esc(d.generated_at)} · 자동 주문이나 매수 추천이 아니에요.</p></details>`;
    for(const id of ['ewFund','ewKind','ewThreshold','ewQuantity'])root.querySelector('#'+id).addEventListener('change',renderRows);
    root.querySelector('#ewSearch').addEventListener('input',renderRows);
    root.querySelector('#ewDownload').addEventListener('click',download);
    renderRows();root.dataset.state='ready';
  }
  async function load(){
    try{
      const embedded=document.getElementById('etfWeightsData');
      if(embedded)draw(JSON.parse(embedded.textContent));
      else {const response=await fetch('etf-weights/latest.json?t='+Date.now(),{cache:'no-store'});if(!response.ok)throw Error(`자료 요청 실패 (${response.status})`);draw(await response.json());}
    }catch(e){root.dataset.state='error';root.innerHTML=`<h2>ETF비중</h2><p class="ew-note">비교자료를 표시할 수 없어요: ${esc(e.message)}. 자료 누락을 무변동으로 처리하지 않아요.</p>`;}
  }
  const activate=()=>{if(location.hash==='#etf-weights'&&typeof window.showDashboardTab==='function')window.showDashboardTab('etf-weights');};
  window.addEventListener('hashchange',activate);activate();load();
})();
