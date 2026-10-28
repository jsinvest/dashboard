/* Dated ETF holdings comparison. No trade or capital-flow inference. */
(() => {
  'use strict';
  const root = document.getElementById('etfWeightsPanel');
  if (!root) return;
  const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const n = (x, digits=2) => Number(x).toLocaleString('ko-KR',{minimumFractionDigits:digits,maximumFractionDigits:digits});
  const signed = (x,digits=2) => `${x>0?'+':''}${n(x,digits)}`;
  const labels = {NEW:'신규 편입',EXIT:'편출',UP:'비중 확대',DOWN:'비중 축소',SAME:'비중 동일'};
  const assetLabels={STOCK:'주식',ETF:'ETF',CASH:'현금',DERIVATIVE:'파생상품',OTHER:'기타'};
  const q=x=>Number(x).toLocaleString('ko-KR',{maximumFractionDigits:6});
  let report, filtered=[], portfolioRows=[], activeView='increase';
  const link = u => /^https:\/\/www\.funetf\.co\.kr\/product\/etf\/view\/KR[A-Z0-9]+$/.test(u) ? u : 'https://www.funetf.co.kr/';
  function renderRows(){
    const fund=root.querySelector('#ewFund').value, kind=root.querySelector('#ewKind').value;
    const threshold=Number(root.querySelector('#ewThreshold').value), qty=root.querySelector('#ewQuantity').value;
    const query=root.querySelector('#ewSearch').value.trim().toLowerCase();
    const allowed=activeView==='decrease'?['EXIT','DOWN']:['NEW','UP'];
    filtered=report.events.filter(e => allowed.includes(e.event) && (!fund||e.etf_code===fund) && (!kind||e.event===kind) && (['NEW','EXIT'].includes(e.event)||Math.abs(e.delta_pp)>=threshold) && (!qty||(qty==='changed'?e.quantity_delta!==0:e.quantity_delta===0)) && (!query||`${e.stock_name} ${e.stock_code} ${e.etf_name}`.toLowerCase().includes(query)));
    root.querySelector('#ewResultCount').textContent=`${filtered.length.toLocaleString()}건 · ETF–종목 쌍 기준 · 신규/편출에는 최소변화 필터를 적용하지 않아요.`;
    root.querySelector('#ewRows').innerHTML=filtered.map(e=>`<tr><td>${esc(e.stock_name)}<span class="ew-code">${esc(e.stock_code)}</span></td><td>${esc(e.etf_name)}<span class="ew-code">${esc(e.etf_code)}</span></td><td><span class="ew-tag">${labels[e.event]}</span></td><td>${n(e.old_weight)}%</td><td>${n(e.new_weight)}%</td><td class="${e.delta_pp>0?'ew-up':'ew-down'}">${signed(e.delta_pp)}%p</td><td>${n(e.old_quantity_per_cu,0)} → ${n(e.new_quantity_per_cu,0)}</td><td>${signed(e.quantity_delta,0)}</td></tr>`).join('') || '<tr><td colspan="8" class="ew-empty">조건에 맞는 변화가 없어요.</td></tr>';
  }
  function selectView(view){
    activeView=view;
    root.querySelectorAll('[data-ew-tab]').forEach(b=>{const on=b.dataset.ewTab===view;b.setAttribute('aria-pressed',String(on));b.classList.toggle('active',on);});
    root.querySelector('#ewChanges').hidden=view==='portfolio';
    root.querySelector('#ewPortfolio').hidden=view!=='portfolio';
    root.querySelector('#ewOverlap').hidden=view!=='increase';
    if(view==='portfolio'){renderPortfolio();return;}
    const down=view==='decrease', kinds=down?['EXIT','DOWN']:['NEW','UP'];
    root.querySelector('#ewKind').innerHTML=`<option value="">${down?'감소 전체':'증가 전체'}</option>`+kinds.map(k=>`<option value="${k}">${labels[k]}</option>`).join('');
    root.querySelector('#ewChangeTitle').textContent=down?'감소 · 편출 및 비중 축소':'증가 · 신규 편입 및 비중 확대';
    const count=report.events.filter(e=>e.event===kinds[1]&&Math.abs(e.delta_pp)>=.1).length;
    root.querySelector('#ewSummary').innerHTML=[[report.counts[kinds[0]]||0,labels[kinds[0]]],[count,`0.10%p 이상 ${down?'축소':'확대'}`]].map(([v,t])=>`<div class="ew-card"><span>${t}</span><strong>${n(v,0)}</strong></div>`).join('');
    renderRows();
  }
  function renderPortfolio(){
    const fund=report.funds.find(f=>f.code===root.querySelector('#ewPortfolioFund').value);
    const p=fund?.portfolio, body=root.querySelector('#ewPortfolioRows');
    if(!p){root.querySelector('#ewPortfolioMeta').textContent='이 ETF의 전체 구성자료가 없어요.';body.innerHTML='';portfolioRows=[];return;}
    const query=root.querySelector('#ewPortfolioSearch').value.trim().toLowerCase();
    const kind=root.querySelector('#ewAssetType').value;
    portfolioRows=p.holdings.filter(r=>(!kind||r.asset_type===kind)&&(!query||`${r.name} ${r.code}`.toLowerCase().includes(query)));
    root.querySelector('#ewPortfolioName').textContent=fund.name;
    root.querySelector('#ewPortfolioMeta').textContent=`최근 수집 구성내역: ${p.date} 날짜 지정 조회 · ${p.date_status==='OFFICIAL_CROSS_CHECKED'?'TIME 운용사 원문 대조 완료':'API 응답에 기준일 미표기'} · 순자산 NAV 참고일 ${fund.nav_reference_date} · 실시간 보유내역이 아니에요.`;
    root.querySelector('#ewPortfolioStats').innerHTML=[[p.total_count,'전체 구성항목'],[`${n(p.total_weight)}%`,'제공 비중 합계'],[`${n(fund.aum_eok,0)}억`,'선정 시 순자산']].map(([v,t])=>`<div class="ew-card"><span>${t}</span><strong>${esc(v)}</strong></div>`).join('');
    root.querySelector('#ewPortfolioCount').textContent=`${portfolioRows.length} / ${p.total_count}개 표시 · 비중 높은 순 · 현금·파생상품·다른 ETF도 포함`;
    body.innerHTML=portfolioRows.map((r,i)=>`<tr><td>${i+1}</td><td>${esc(r.name)}<span class="ew-code">${esc(r.code)}</span></td><td>${assetLabels[r.asset_type]}</td><td title="${r.weight}%">${n(r.weight)}%<span class="ew-weight-track"><span style="width:${Math.min(100,Math.max(0,r.weight))}%"></span></span></td><td>${q(r.quantity_per_cu)}</td><td>${n(r.value_krw,0)}</td></tr>`).join('')||'<tr><td colspan="6" class="ew-empty">조건에 맞는 구성항목이 없어요.</td></tr>';
  }
  function download(){
    const cell=v=>'"'+String(v).replace(/^[=+@-]/,'\t$&').replaceAll('"','""')+'"';
    const fund=report.funds.find(f=>f.code===root.querySelector('#ewPortfolioFund').value);
    const rows=activeView==='portfolio'?[['조회기준일','ETF코드','ETF','종목코드','종목','구분','비중%','1CU공개수량','1CU평가금액원'],...portfolioRows.map(r=>[fund.portfolio.date,fund.code,fund.name,r.code,r.name,assetLabels[r.asset_type],r.weight,r.quantity_per_cu,r.value_krw])]:[['이전일','현재일','ETF코드','ETF','종목코드','종목','변화','이전비중%','현재비중%','증감%p','이전1CU수량','현재1CU수량','수량증감'],...filtered.map(e=>[report.start_date,report.end_date,e.etf_code,e.etf_name,e.stock_code,e.stock_name,labels[e.event],e.old_weight,e.new_weight,e.delta_pp,e.old_quantity_per_cu,e.new_quantity_per_cu,e.quantity_delta])];
    const url=URL.createObjectURL(new Blob(['\uFEFF'+rows.map(r=>r.map(cell).join(',')).join('\r\n')],{type:'text/csv;charset=utf-8'}));
    const a=document.createElement('a');a.href=url;a.download=activeView==='portfolio'?`ETF포트폴리오_${fund.code}_${fund.portfolio.date}.csv`:`ETF비중_${activeView==='decrease'?'감소':'증가'}_${report.start_date}_${report.end_date}.csv`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
  }
  function draw(d){
    if(d.schema_version!==1||d.status!=='COMPARED'||!Array.isArray(d.funds)||d.funds.length!==20||!Array.isArray(d.events)||d.errors.length) throw Error('20개 ETF의 비교 검증이 완료되지 않았어요.');
    const ids=new Set(d.funds.map(f=>f.code));
    if(ids.size!==20||d.events.some(e=>!ids.has(e.etf_code)||!labels[e.event]||![e.old_weight,e.new_weight,e.delta_pp,e.old_quantity_per_cu,e.new_quantity_per_cu,e.quantity_delta].every(Number.isFinite))) throw Error('구성자료 형식 오류');
    for(const fund of d.funds){
      const p=fund.portfolio;
      if(!p||p.date!==d.end_date||!Array.isArray(p.holdings)||p.holdings.length!==p.total_count||p.total_count!==fund.new_rows||new Set(p.holdings.map(r=>r.isin)).size!==p.total_count||p.holdings.some(r=>!assetLabels[r.asset_type]||![r.weight,r.quantity_per_cu,r.value_krw].every(Number.isFinite))||!Number.isFinite(p.total_weight)||Math.abs(p.holdings.reduce((sum,r)=>sum+r.weight,0)-p.total_weight)>.001||Math.abs(p.total_weight-100)>.1)throw Error('현재 포트폴리오 완결성 검증 실패');
    }
    report=d;
    const age=(Date.now()-Date.parse(d.end_date+'T00:00:00+09:00'))/86400000;
    const grouped=new Map();
    for(const e of d.events){
      if(!(['NEW','UP'].includes(e.event)&&(e.event==='NEW'||e.delta_pp>=.1)))continue;
      if(!grouped.has(e.stock_code))grouped.set(e.stock_code,{name:e.stock_name,code:e.stock_code,items:[]});
      grouped.get(e.stock_code).items.push(e);
    }
    const overlap=[...grouped.values()].filter(s=>s.items.length>=2).sort((a,b)=>b.items.length-a.items.length||a.code.localeCompare(b.code));
    root.innerHTML=`<h2>ETF비중</h2><p class="ew-muted">국내 주식 액티브 ETF 순자산 상위 20개 · ${esc(d.start_date)} → ${esc(d.end_date)}${d.partial_week?' · 이번주 진행 중':''}</p>
      <div class="ew-subnav" role="group" aria-label="ETF비중 하위 메뉴"><button type="button" data-ew-tab="increase" aria-pressed="true" aria-controls="ewChanges">증가</button><button type="button" data-ew-tab="decrease" aria-pressed="false" aria-controls="ewChanges">감소</button><button type="button" data-ew-tab="portfolio" aria-pressed="false" aria-controls="ewPortfolio">현재 포트폴리오</button></div>
      ${age>10?'<p class="ew-note">업데이트 확인 필요: 10일 이상 지난 자료예요.</p>':''}
      <section id="ewChanges" aria-labelledby="ewChangeTitle"><h3 id="ewChangeTitle"></h3><div class="ew-cards ew-change-cards" id="ewSummary"></div>
      <p class="ew-muted">전체 20개 요약 · 건수는 ETF–종목 쌍 기준 · 비중 변화에는 주가 등락도 포함돼요.</p>
      <div class="ew-box"><div class="ew-controls">
      <label>ETF<select id="ewFund"><option value="">전체 20개</option>${d.funds.map(f=>`<option value="${esc(f.code)}">${f.rank}. ${esc(f.name)}</option>`).join('')}</select></label>
      <label>변화 유형<select id="ewKind"></select></label>
      <label>최소 비중변화<select id="ewThreshold"><option value="0.1">0.10%p</option><option value="0.5">0.50%p</option><option value="1">1.00%p</option><option value="0">미세변화 포함</option></select></label>
      <label>공개수량<select id="ewQuantity"><option value="">전체</option><option value="changed">수량도 변함</option><option value="same">수량 동일</option></select></label>
      <label class="ew-search">종목명 · 코드 검색<input id="ewSearch" type="search" placeholder="예: 삼성전자, 005930"></label></div>
      <p id="ewResultCount" class="ew-muted" aria-live="polite"></p><p class="ew-muted">작은 화면에서는 표를 좌우로 밀어 비중과 수량을 볼 수 있어요.</p>
      <div class="ew-scroll" tabindex="0" role="region" aria-label="ETF 구성종목 변화 표"><table><thead><tr><th>종목</th><th>ETF</th><th>구분</th><th>이전 비중</th><th>현재 비중</th><th>변화</th><th>공개수량 / 1CU</th><th>수량 증감</th></tr></thead><tbody id="ewRows"></tbody></table></div>
      <div class="ew-actions"><button id="ewDownload" type="button">현재 결과 CSV 저장</button></div><p class="ew-muted">수량은 1CU 공개값이에요. CU 크기 변경·기업행사를 확인하지 않아 실제 매매량으로 사용할 수 없어요.</p></div>
      </section>
      <section id="ewPortfolio" hidden aria-label="현재 포트폴리오"><div class="ew-box"><h3>현재 포트폴리오</h3><p class="ew-muted">ETF 하나를 선택해 전체 구성내역을 확인하세요. 최근 수집자료 기준으로 표시해요.</p><div class="ew-controls"><label>ETF 선택<select id="ewPortfolioFund">${d.funds.map(f=>`<option value="${esc(f.code)}">${f.rank}. ${esc(f.name)}</option>`).join('')}</select></label><label>자산 구분<select id="ewAssetType"><option value="">전체 구성항목</option>${Object.entries(assetLabels).map(([k,v])=>`<option value="${k}">${v}</option>`).join('')}</select></label><label class="ew-search">종목명 · 코드 검색<input id="ewPortfolioSearch" type="search" placeholder="예: 삼성전자, 005930"></label></div><h3 id="ewPortfolioName"></h3><p id="ewPortfolioMeta" class="ew-muted"></p><div id="ewPortfolioStats" class="ew-cards ew-portfolio-cards"></div><p id="ewPortfolioCount" class="ew-muted" aria-live="polite"></p><p class="ew-muted">작은 화면에서는 표를 좌우로 밀어 보세요.</p><div class="ew-scroll" tabindex="0" role="region" aria-label="ETF 전체 포트폴리오 표"><table><thead><tr><th>순서</th><th>구성항목</th><th>구분</th><th>비중</th><th>공개수량 / 1CU</th><th>평가금액 / 1CU (원)</th></tr></thead><tbody id="ewPortfolioRows"></tbody></table></div><div class="ew-actions"><button type="button" id="ewPortfolioDownload">이 포트폴리오 CSV 저장</button></div><p class="ew-muted">비중·평가금액은 제공처 원값이에요. 수량 단위는 자산별로 다르며 펀드 전체 보유수량이 아니에요. 순자산은 ETF 선정 시점의 표시값이에요.</p></div></section>
      <details class="ew-box" id="ewOverlap"><summary>여러 ETF에서 함께 편입·확대한 종목 (${overlap.length}개)</summary><p class="ew-muted">신규 또는 0.10%p 이상 확대 ETF 수예요. 가격 상승만으로도 여러 ETF의 비중이 함께 늘 수 있어요.</p><div class="ew-scroll"><table><thead><tr><th>종목</th><th>편입·확대 ETF</th><th>ETF 수</th></tr></thead><tbody>${overlap.map(s=>`<tr><td>${esc(s.name)}<span class="ew-code">${s.code}</span></td><td>${s.items.map(e=>`${esc(e.etf_name)} (${signed(e.delta_pp)}%p)`).join('<br>')}</td><td>${s.items.length}</td></tr>`).join('')}</tbody></table></div></details>
      <details class="ew-box"><summary>추적 대상 20개 · 순자산 및 검증 상태</summary><p class="ew-muted">선정 조회일 ${d.ranking_observed_date} · 순자산 단위 억원 · NAV 참고일은 순자산 자체의 별도 기준일과 구분해요.</p><div class="ew-scroll"><table><thead><tr><th>순위 · ETF</th><th>순자산 / NAV 참고일</th><th>신규 / 편출</th><th>원문 추가 대조</th></tr></thead><tbody>${d.funds.map(f=>`<tr><td>${f.rank}. <a href="${link(f.source_url)}" target="_blank" rel="noopener">${esc(f.name)}</a><span class="ew-code">${f.code}</span></td><td>${n(f.aum_eok,0)}억원<br>${esc(f.nav_reference_date)}</td><td>${f.counts.NEW||0} / ${f.counts.EXIT||0}</td><td>${f.official_checked?'TIME 운용사 양일 일치':'날짜 지정 API · 원문 미대조'}</td></tr>`).join('')}</tbody></table></div></details>
      <details class="ew-box"><summary>출처와 비교 기준</summary><p>${esc(d.source)}</p><ul>${d.limitations.map(s=>`<li>${esc(s)}</li>`).join('')}</ul><p class="ew-muted">수집 ${esc(d.generated_at)} · 자동 주문이나 매수 추천이 아니에요.</p></details>`;
    for(const id of ['ewFund','ewKind','ewThreshold','ewQuantity'])root.querySelector('#'+id).addEventListener('change',renderRows);
    root.querySelector('#ewSearch').addEventListener('input',renderRows);
    root.querySelector('#ewDownload').addEventListener('click',download);
    root.querySelectorAll('[data-ew-tab]').forEach(b=>b.addEventListener('click',()=>{selectView(b.dataset.ewTab);history.replaceState(null,'',`#etf-weights/${b.dataset.ewTab}`);}));
    for(const id of ['ewPortfolioFund','ewAssetType'])root.querySelector('#'+id).addEventListener('change',renderPortfolio);
    root.querySelector('#ewPortfolioSearch').addEventListener('input',renderPortfolio);
    root.querySelector('#ewPortfolioDownload').addEventListener('click',download);
    selectView(location.hash.match(/^#etf-weights\/(increase|decrease|portfolio)$/)?.[1]||'increase');root.dataset.state='ready';
  }
  async function load(){
    try{
      const embedded=document.getElementById('etfWeightsData');
      if(embedded)draw(JSON.parse(embedded.textContent));
      else {const response=await fetch('etf-weights/latest.json?t='+Date.now(),{cache:'no-store'});if(!response.ok)throw Error(`자료 요청 실패 (${response.status})`);draw(await response.json());}
    }catch(e){root.dataset.state='error';root.innerHTML=`<h2>ETF비중</h2><p class="ew-note">비교자료를 표시할 수 없어요: ${esc(e.message)}. 자료 누락을 무변동으로 처리하지 않아요.</p>`;}
  }
  const activate=()=>{const match=location.hash.match(/^#etf-weights(?:\/(increase|decrease|portfolio))?$/);if(match){if(typeof window.showDashboardTab==='function')window.showDashboardTab('etf-weights');if(report)selectView(match[1]||'increase');}};
  window.addEventListener('hashchange',activate);activate();load();
})();
