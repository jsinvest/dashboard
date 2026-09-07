/* Futures remain primary. Cash-index analysis is a dated, folded supplement. */
async function renderFuturesIndexContext(data) {
  if (data.schema_version !== 'futures-options-review-v1' || data.futures_contract !== 'F202609' ||
      !data.data_validation?.ready_for_editorial_review || !Array.isArray(data.overall_assessment?.levels) ||
      !Array.isArray(data.charts) || !data.hts_0791_position_inference || !data.derivatives_evidence?.all_expiry_flow) {
    throw new Error('선물 분석 필수 형식 또는 검증 결과 누락');
  }
  const esc = value => escapeHtml(String(value ?? ''));
  const num = value => Number(value).toLocaleString('ko-KR', {maximumFractionDigits:2});
  const signed = value => (Number(value)>0?'+':'')+num(value);
  const asset = file => {
    if (!/^[a-zA-Z0-9_.-]+$/.test(file)) throw new Error('선물 자료 파일명 오류');
    return 'supply-zone/'+file+'?v='+encodeURIComponent(data.generated_at);
  };
  const panel = document.querySelector('[data-tab-panel="supply"]');
  const flow = data.derivatives_evidence.all_expiry_flow;
  const chart = item => `<article class="chart-card cash-card"><div class="card-header"><h3>${esc(item.title)}</h3></div><p>${esc(item.interpretation)}</p><a href="${asset(item.file)}" target="_blank" rel="noopener"><img class="cash-chart" src="${asset(item.file)}" alt="${esc(item.title)}" /></a><p class="cash-note">${esc(item.source_note)}</p></article>`;
  const sourceCharts = data.charts.filter(x=>x.kind!=='price');
  panel.innerHTML = `<div class="futures-review cash-review">
    <div class="section-title">선물옵션 매물대 · 선물 가격구조와 누적 포지션 중심</div>
    <div id="supplyMeta" class="report-meta">기준일 ${esc(data.as_of)} · ${esc(data.futures_contract)} / ${esc(data.contract_code)} · 정규장 종가 ${num(data.current_price)} · 야간 보관 화면 ${num(data.session_references.overnight.snapshot_price)} (${esc(data.session_references.overnight.snapshot_time)}) · 실시간 아님</div>
    <section class="chart-card cash-card" id="supplyOverallAssessment">${renderSupplyAssessment(data.overall_assessment, data.current_price, data.display_reference_basis)}</section>
    <div id="supplyPositionInference">${render0791PositionInference(data.hts_0791_position_inference)}</div>
    <section class="chart-card cash-card" id="futuresFlow"><h3>외국인·기관 선물 순매매 · 최신 → 3일 → 5일 → 누적</h3>
      <p>${esc(data.flow_interpretation)}</p><div class="cash-table-wrap"><table class="cash-table"><thead><tr><th>기간</th><th>실제 날짜</th><th>외국인 계약</th><th>기관계 계약</th></tr></thead><tbody>${['1','3','5','15'].map(n=>`<tr><th>${n}거래일</th><td>${esc(flow[n].start)} ~ ${esc(flow[n].end)}</td><td>${signed(flow[n].foreign)}</td><td>${signed(flow[n].institution)}</td></tr>`).join('')}</tbody></table></div>
      <p class="cash-note">${esc(data.derivatives_evidence.scope_note)}</p>
      <h3>콜·풋 당일 순매매 · 계약수와 금액을 구분</h3><div class="cash-table-wrap"><table class="cash-table"><thead><tr><th>주체</th><th>상품</th><th>순매매 계약</th><th>순매매 금액(억원)</th></tr></thead><tbody>${data.derivatives_evidence.daily_options.map(x=>`<tr><th>${esc(x.investor)}</th><td>${esc(x.market)}</td><td>${signed(x.quantity)}</td><td>${signed(x.amount_100m_krw)}</td></tr>`).join('')}</tbody></table></div><p>${esc(data.options_interpretation)}</p>
    </section>
    <section class="chart-card cash-card" id="futuresOi"><h3>거래량·미결제약정 · 9월물과 12월물 분리</h3><div class="cash-table-wrap"><table class="cash-table"><thead><tr><th>월물 / 코드</th><th>정규장 종가</th><th>거래량</th><th>미결제약정</th><th>OI 전일 대비</th><th>대조 상태</th></tr></thead><tbody>${data.contract_observations.map(x=>`<tr><th>${esc(x.contract)}<small>${esc(x.code)}</small></th><td>${num(x.close)}</td><td>${num(x.volume)}</td><td>${num(x.oi)}</td><td>${signed(x.oi_change)}</td><td>${esc(x.status)}</td></tr>`).join('')}</tbody></table></div><p>${esc(data.oi_interpretation)}</p></section>
    <section class="chart-card cash-card"><h3>선물 파동·매물대 해석</h3><p>${esc(data.futures_structure.daily)}</p><p>${esc(data.futures_structure.intraday)}</p><p>${esc(data.futures_structure.profile)}</p><p class="cash-note">${esc(data.futures_structure.wave_limit)}</p></section>
    ${data.charts.filter(x=>x.kind==='price').map(chart).join('')}
    <section class="chart-card cash-card"><h3>지수 보조 확인 · 선물 뷰를 대체하지 않음</h3><p>${esc(data.index_confirmation)}</p><p class="cash-note">코스피는 KOSPI200 선물의 숫자 환산표가 아닙니다. 해외 현물 지수와 해외 선물도 구분해요.</p></section>
    <details class="chart-card cash-card cash-details" id="supplyIndexContext"><summary>코스피·나스닥·필반·니케이·다우 · 월봉 / 주봉 / 일봉 / 10분봉 보조 분석 펼치기</summary><div id="supplyIndexContextBody"><p>보조 자료 확인 중…</p></div></details>
    <details class="chart-card cash-card cash-details" id="futuresSourceCharts"><summary>0790·0791 누적 / 0441 월물별 OI / 0471 원본 화면</summary>${sourceCharts.map(chart).join('')}</details>
    <details class="chart-card cash-card cash-details" id="futuresValidation"><summary>자료 검증·판단 범위·다운로드</summary><p>저장 원본을 직접 검토한 9월 7일 분석입니다. 최초 EOD 1단계 실패 기록은 보존했고, 이번에는 전체 배치나 화면 수집을 다시 실행하지 않았습니다.</p><ul>${data.limitations.map(x=>`<li>${esc(x)}</li>`).join('')}</ul><div class="cash-downloads">${data.downloads.map(x=>`<a href="${asset(x.file)}" download>${esc(x.label)}</a>`).join('')}</div><p>추정 포지션과 미결제약정의 의미: <a href="https://download.kiwoom.com/hero4_help_new/0791.htm" target="_blank" rel="noopener">키움 0791 설명</a> · <a href="https://download.kiwoom.com/hero4_help_new/0441.htm" target="_blank" rel="noopener">키움 0441 설명</a></p><p class="cash-note">${esc(data.generated_at)} 작성 · 자동 주문 신호가 아닌 조건부 분석 · 도달·수익·승률 보장 없음</p></details>
  </div>`;
  // A missing optional index appendix must not replace valid futures analysis.
  const body = document.getElementById('supplyIndexContextBody');
  try {
    const response = await fetch(asset(data.index_context_file), {cache:'no-store'});
    if (!response.ok) throw new Error('HTTP '+response.status);
    const context = await response.json();
    if (context.as_of !== data.as_of) throw new Error('보조 지수 기준일 불일치');
    renderCashIndexReview({...context, downloads:context.downloads.map(x=>({...x,file:x.file==='latest.json'?data.index_context_file:x.file}))}, body);
  } catch (error) {
    body.textContent = '지수 보조 자료 확인 불가: '+error.message+' · 위 선물 분석과 분리';
    body.dataset.loadError = 'true';
  }
}
