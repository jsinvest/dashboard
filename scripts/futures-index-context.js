/* Futures remain primary. Cash-index analysis is a dated, folded supplement. */
async function renderFuturesIndexContext(data) {
  if (data.schema_version !== 'futures-options-review-v1' ||
      !['F202609','F202612'].includes(data.futures_contract) ||
      data.contract_code !== ({F202609:'A0169000',F202612:'A016C000'}[data.futures_contract]) ||
      !data.data_validation?.ready_for_editorial_review || !Array.isArray(data.overall_assessment?.levels) ||
      !Array.isArray(data.charts) || !data.hts_0791_position_inference || !data.derivatives_evidence?.all_expiry_flow) {
    throw new Error('선물 분석 필수 형식 또는 검증 결과 누락');
  }
  const esc = value => escapeHtml(String(value ?? ''));
  const num = value => value == null || value === '' ? '확인 불가' : Number(value).toLocaleString('ko-KR', {maximumFractionDigits:2});
  const signed = value => value == null || value === '' ? '확인 불가' : (Number(value)>0?'+':'')+num(value);
  const provisional = data.data_status === 'PROVISIONAL_PRE_CLOSE';
  const mixedTiming = data.data_status === 'CLOSE_PRICE_WITH_PRE_CLOSE_FLOW';
  const referenceLabel = provisional ? '마감 전 잠정 기준가' : '정규장 종가';
  const asset = file => {
    if (!/^[a-zA-Z0-9_.-]+$/.test(file)) throw new Error('선물 자료 파일명 오류');
    return 'supply-zone/'+file+'?v='+encodeURIComponent(data.generated_at);
  };
  const panel = document.querySelector('[data-tab-panel="supply"]');
  const flow = data.derivatives_evidence.all_expiry_flow;
  const chart = item => `<article class="chart-card cash-card"><div class="card-header"><h3>${esc(item.title)}</h3></div><p>${esc(item.brief?.result || item.interpretation)}</p>${item.brief?`<p><strong>${esc(item.brief.check)}</strong></p>`:''}<a href="${asset(item.file)}" target="_blank" rel="noopener"><img class="cash-chart" src="${asset(item.file)}" alt="${esc(item.title)}" /></a><small class="cash-note">${esc(item.source_note)}</small></article>`;
  const sourceCharts = data.charts.filter(x=>x.kind!=='price' && x.kind!=='gamma_research');
  const gamma = data.gamma_research;
  const gammaSection = gamma && gamma.status === 'RESEARCH_ONLY_PARTIAL_CHAIN' && Array.isArray(gamma.notes) ?
    `<section class="chart-card cash-card" id="futuresGammaResearch"><h3>옵션 감마 추정 구간</h3><p><strong>${esc(gamma.headline)}</strong></p>${Array.isArray(gamma.zones)?`<div class="cash-table-wrap"><table class="cash-table" style="min-width:0;width:100%"><thead><tr><th>12월물 선물 가격</th><th>모형 구간</th></tr></thead><tbody>${gamma.zones.map(z=>`<tr><td>${num(z.low)}~${num(z.high)}</td><td><strong>${esc(z.label)}</strong></td></tr>`).join('')}<tr><td>${num(gamma.flip)}</td><td>감마플립 (0 경계)</td></tr></tbody></table></div>`:`<p>감마플립 후보 ${num(gamma.flip)}</p>`}<small class="cash-note">${esc(gamma.compact_note || '부분자료 기반 연구용 추정')} · 양끝 200·2,000은 계산 범위</small>${data.charts.filter(x=>x.kind==='gamma_research').map(chart).join('')}<details><summary>가정·민감도·자료 범위</summary><p>${esc(gamma.method)}</p><p>IV 민감도 플립 ${num(gamma.iv_band[0])}~${num(gamma.iv_band[1])}</p><ul>${gamma.notes.map(x=>`<li>${esc(x)}</li>`).join('')}</ul></details></section>` : '';
  const inference=data.hts_0791_position_inference;
  const positions=Array.isArray(inference.display_cards)?`<section class="chart-card cash-card"><h3>0790 누적 추정 포지션</h3><div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px">${inference.display_cards.map(p=>`<article style="padding:14px;border:1px solid var(--border);border-radius:8px"><b>${esc(p.name)}</b><p><strong>${esc(p.direction)}</strong></p><small>${esc(p.detail)}</small></article>`).join('')}</div><small class="cash-note">${esc(inference.display_note)}</small></section>`:render0791PositionInference(inference);
  const flowCell=(row,key)=>row.complete===false&&row.partial_totals ? `${signed(row.partial_totals[key])}<small>부분 합계</small>`:signed(row[key]);
  panel.innerHTML = `<div class="futures-review cash-review">
    <div class="section-title">선물옵션 매물대 · 선물 가격구조와 누적 포지션 중심</div>
    <div id="supplyMeta" class="report-meta">기준일 ${esc(data.as_of)} · ${esc(data.futures_contract)} / ${esc(data.contract_code)} · ${referenceLabel} ${num(data.current_price)}${provisional ? ` · ${esc(data.capture_window)} 수집 · 종가 미확정` : mixedTiming ? ' · 가격 확정 / 수급·OI는 마감 전 잠정' : ''} · ${data.session_references.overnight?.snapshot_price != null ? `야간 보관 화면 ${num(data.session_references.overnight.snapshot_price)} (${esc(data.session_references.overnight.snapshot_time)})` : '이후 야간 시세 미반영'} · 실시간 아님</div>
    <section class="chart-card cash-card" id="supplyOverallAssessment">${renderSupplyAssessment(data.overall_assessment, data.current_price, data.display_reference_basis)}</section>
    <div id="supplyPositionInference">${positions}</div>
    <section class="chart-card cash-card" id="futuresFlow"><h3>외국인·기관 선물 순매매 · 최신 → 3일 → 5일 → 누적</h3>
      <p>${esc(data.flow_interpretation)}</p><div class="cash-table-wrap"><table class="cash-table"><thead><tr><th>기간</th><th>실제 날짜</th><th>외국인</th><th>기관계</th><th>금융투자</th><th>투신</th></tr></thead><tbody>${['1','3','5','15'].map(n=>`<tr><th>${n}거래일${flow[n].complete===false?`<small>${num(flow[n].observations)}/${n}일 집계</small>`:''}</th><td>${esc(flow[n].start)} ~ ${esc(flow[n].end)}${flow[n].missing_sessions?.length?`<small>누락 ${flow[n].missing_sessions.map(esc).join(', ')}</small>`:''}</td>${['foreign','institution','financial','trust'].map(k=>`<td>${flowCell(flow[n],k)}</td>`).join('')}</tr>`).join('')}</tbody></table></div>
      <p class="cash-note">${esc(data.derivatives_evidence.scope_note)}</p>
      <h3>콜·풋 당일 순매매 · 계약수와 금액을 구분</h3><div class="cash-table-wrap"><table class="cash-table"><thead><tr><th>주체</th><th>상품</th><th>순매매 계약</th><th>순매매 금액(억원)</th></tr></thead><tbody>${data.derivatives_evidence.daily_options.map(x=>`<tr><th>${esc(x.investor)}</th><td>${esc(x.market)}</td><td>${signed(x.quantity)}</td><td>${signed(x.amount_100m_krw)}</td></tr>`).join('')}</tbody></table></div><p>${esc(data.options_interpretation)}</p>
    </section>
    <section class="chart-card cash-card" id="futuresOi"><h3>거래량·미결제약정 · 월물별 분리</h3><div class="cash-table-wrap"><table class="cash-table"><thead><tr><th>월물 / 코드</th><th>관측가격 · 기준시각</th><th>거래량</th><th>미결제약정</th><th>OI 전일 대비</th><th>대조 상태</th></tr></thead><tbody>${data.contract_observations.map(x=>`<tr><th>${esc(x.contract)}<small>${esc(x.code)}</small></th><td>${num(x.is_final === false ? x.snapshot_price : x.close)}<small>${esc(x.captured_at || (x.is_final === false ? '잠정' : '정규장 종가'))}</small></td><td>${num(x.volume)}</td><td>${num(x.oi)}</td><td>${signed(x.oi_change)}</td><td>${esc(x.status)}</td></tr>`).join('')}</tbody></table></div><p>${esc(data.oi_interpretation)}</p></section>
    <section class="chart-card cash-card" id="futuresStructure"><h3>시간대별 결론</h3>${data.structure_briefs?['weekly','daily','minute'].map(k=>{const b=data.structure_briefs[k];return `<article style="margin:16px 0"><strong>${esc(b.title)}</strong><p>${esc(b.result)}<br>${esc(b.check)}</p><small class="cash-note">${esc(b.note)}</small></article>`}).join(''): `<p>${esc(data.futures_structure.weekly)}</p><p>${esc(data.futures_structure.daily)}</p><p>${esc(data.futures_structure.intraday)}</p>`}<details><summary>지표·파동 근거</summary>${['monthly','weekly','daily','intraday','wave_limit'].map(k=>`<p class="cash-note">${esc(data.futures_structure[k])}</p>`).join('')}</details></section>
    ${data.charts.filter(x=>x.kind==='price').map(chart).join('')}
    ${gammaSection}
    <section class="chart-card cash-card"><h3>지수 보조 확인 · 선물 뷰를 대체하지 않음</h3><p>${esc(data.index_confirmation)}</p><p class="cash-note">코스피는 KOSPI200 선물의 숫자 환산표가 아닙니다. 해외 현물 지수와 해외 선물도 구분해요.</p></section>
    <details class="chart-card cash-card cash-details" id="supplyIndexContext"><summary>코스피·나스닥·필반·니케이·다우 · 월봉 / 주봉 / 일봉 / 10분봉 보조 분석 펼치기</summary><div id="supplyIndexContextBody"><p>보조 자료 확인 중…</p></div></details>
    <details class="chart-card cash-card cash-details" id="futuresSourceCharts"><summary>0790·0791 누적 / 0441 월물별 OI / 0471 원본 화면</summary>${sourceCharts.map(chart).join('')}</details>
    <details class="chart-card cash-card cash-details" id="futuresValidation"><summary>자료 검증·판단 범위·다운로드</summary><p>${esc(data.recovery_note || '기준일별 원본 검토 결과와 실행 상태는 아래 검증 파일에 기록했습니다.')}</p><ul>${data.limitations.map(x=>`<li>${esc(x)}</li>`).join('')}</ul><div class="cash-downloads">${data.downloads.map(x=>`<a href="${asset(x.file)}" download>${esc(x.label)}</a>`).join('')}</div><p>추정 포지션과 미결제약정의 의미: <a href="https://download.kiwoom.com/hero4_help_new/0791.htm" target="_blank" rel="noopener">키움 0791 설명</a> · <a href="https://download.kiwoom.com/hero4_help_new/0441.htm" target="_blank" rel="noopener">키움 0441 설명</a></p><p class="cash-note">${esc(data.generated_at)} 작성 · 자동 주문 신호가 아닌 조건부 분석 · 도달·수익·승률 보장 없음</p></details>
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
