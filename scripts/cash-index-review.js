/* Optional cash-index view; the legacy futures renderer remains unchanged. */
function renderCashIndexReview(data) {
  const required = ['KOSPI', 'NASDAQ', 'SOX', 'NIKKEI', 'DOW'];
  const tfs = ['monthly', 'weekly', 'daily', 'intraday_10m'];
  if (data.schema_version !== 'cash-index-review-v1' || !data.review ||
      !Array.isArray(data.indices) || data.indices.length !== 5 ||
      !required.every(key => data.indices.some(i => i.key === key && i.review && tfs.every(tf => typeof i.review[tf] === 'string'))) ||
      !Array.isArray(data.review.levels) || !data.data_validation?.ready_for_editorial_review) {
    throw new Error('현물 분석 필수 형식 또는 검증 결과 누락');
  }
  const panel = document.querySelector('[data-tab-panel="supply"]');
  const esc = value => escapeHtml(String(value ?? ''));
  const number = value => Number(value).toLocaleString('ko-KR', {maximumFractionDigits: 2, minimumFractionDigits: 2});
  const signed = value => (Number(value) > 0 ? '+' : '') + Number(value).toLocaleString('ko-KR');
  const asset = file => {
    if (!/^[a-zA-Z0-9_.-]+$/.test(file)) throw new Error('현물 자료 파일명 오류');
    return 'supply-zone/' + file + '?v=' + encodeURIComponent(data.generated_at);
  };
  const labels = {monthly: '월봉', weekly: '주봉', daily: '일봉', intraday_10m: '10분봉'};
  const review = data.review;
  const rows = data.indices.map(index => {
    const r = index.review;
    const returns = index.timeframes.daily.returns_pct;
    return `<tr><th>${esc(index.name)}<small>${esc(index.source_session_date)} · ${esc(index.symbol)}</small></th><td>${number(index.latest_daily_ohlc.close)}</td><td>${esc(r.view)}</td><td>${signed(returns['1'])}% / ${signed(returns['3'])}% / ${signed(returns['5'])}% / ${signed(returns['20'])}%</td></tr>`;
  }).join('');
  const levels = review.levels.map(level => `<article class="cash-level ${level.side === 'support' ? 'support' : 'resistance'}">
    <div class="cash-level-head"><b>${esc(level.label)}</b><strong>${number(level.low)}${level.high !== level.low ? ' ~ ' + number(level.high) : ''}</strong></div>
    <span class="cash-strength">${esc(level.strength)}</span><p>${esc(level.evidence)}</p><p><b>판단 전환:</b> ${esc(level.condition)}</p></article>`).join('');
  const indices = data.indices.map(index => {
    const r = index.review;
    const daily = index.daily_source, intra = index.intraday_source;
    return `<article class="chart-card cash-index" data-cash-index="${esc(index.key)}">
      <h3>${esc(index.name)} <small>${esc(index.symbol)} · ${esc(index.source_session_date)} 완료 세션</small></h3>
      <p class="cash-index-view">${esc(r.view)} · 종가 ${number(index.latest_daily_ohlc.close)}</p>
      <div class="cash-timeframes">${tfs.map(tf => `<div><b>${labels[tf]}</b><p>${esc(r[tf])}</p></div>`).join('')}</div>
      <p class="cash-hold"><b>유지·회복 조건</b> ${esc(r.hold)}</p><p class="cash-fail"><b>훼손·전환 조건</b> ${esc(r.failure)}</p>
      <details class="cash-details"><summary>실제 차트 보기 · 월봉 / 주봉 / 일봉 / 10분봉</summary>
        <a href="${asset(index.chart)}" target="_blank" rel="noopener"><img class="cash-chart" src="${asset(index.chart)}" alt="${esc(index.name)} 실제 월봉 주봉 일봉 10분봉 차트" /></a>
        <p class="cash-note">차트는 해당 거래소 현지 시각입니다. 진행 중 월·주봉은 표시하되 확정 판단에서 제외했어요. 점선은 최근 확인된 가격 고저점이며 체결 매물대가 아닙니다.</p></details>
      <details class="cash-details"><summary>원본 기간·계산값 확인</summary><p class="cash-note">일봉 ${esc(daily.start)} ~ ${esc(daily.end)} (${esc(daily.rows)}개) · 5분봉 ${esc(intra.start)} ~ ${esc(intra.end)} (${esc(intra.rows)}개). 10분봉은 이 원본을 재표본화했습니다.</p>
        <div class="cash-table-wrap"><table class="cash-table"><thead><tr><th>시간대</th><th>마지막 확정 봉</th><th>확정 봉 수</th><th>원신호 점수</th><th>RSI14</th></tr></thead><tbody>${tfs.map(tf => {const v=index.timeframes[tf]; return `<tr><th>${labels[tf]}</th><td>${esc(v.latest_bar)}</td><td>${esc(v.bar_count)}</td><td>${esc(v.score)} · ${esc(v.state)}</td><td>${number(v.rsi14)}</td></tr>`;}).join('')}</tbody></table></div><p class="cash-note">원신호 점수는 확률·승률이 아니며 위의 AI 종합 판단과 구별합니다.</p></details>
    </article>`;
  }).join('');
  const flow = data.derivatives_evidence.all_expiry_flow;
  panel.innerHTML = `<div class="cash-review">
    <div class="section-title">현물 다중 시간대 분석 · 선옵 누적 수급은 보조 근거</div>
    <div class="report-meta" id="supplyMeta">분석 기준일 ${esc(data.as_of)} · 코스피·니케이 9/7 / 미국 9/4 · 선물 차트 분석 아님</div>
    <section class="chart-card cash-conclusion" id="supplyOverallAssessment"><h2>${esc(review.headline)}</h2><p>${esc(review.summary)}</p><p>${esc(review.cross_market)}</p></section>
    <section class="chart-card cash-card"><h3>다섯 지수 비교 · 각 지수의 포인트를 따로 사용</h3><div class="cash-table-wrap"><table class="cash-table"><thead><tr><th>현물 지수 · 기준일</th><th>종가</th><th>종합 판단</th><th>1 / 3 / 5 / 20거래일 변화</th></tr></thead><tbody>${rows}</tbody></table></div></section>
    <section class="chart-card cash-card"><h3>코스피 현물 · 지지 강도와 뷰 전환</h3><p class="cash-note">파랑은 지지, 빨강은 저항입니다. 5·10포인트 간격이 아니라 실제 고저점과 이평을 근거로 선택했어요. 현재 코스피 6,995.39와 과거 선물 1,0xx 가격은 섞지 않습니다.</p>
      <a href="${asset(data.primary_chart)}" target="_blank" rel="noopener"><img class="cash-chart" src="${asset(data.primary_chart)}" alt="코스피 현물 일봉 지지 저항과 유지 이탈 조건" /></a>
      <div class="cash-levels">${levels}</div><p class="cash-note">${esc(review.confirmation_rule)}</p></section>
    <section class="chart-card cash-card"><h3>코스피 파동 · 선호 가설과 대안</h3><p><b>선호:</b> ${esc(review.elliott.preferred)}</p><p><b>대안:</b> ${esc(review.elliott.alternative)}</p><p><b>회복 확인:</b> ${esc(review.elliott.confirmation)}</p><p><b>큰 무효화:</b> ${esc(review.elliott.invalidation)}</p><p class="cash-note">${esc(review.elliott.rule_check)}</p></section>
    ${indices}
    <details class="chart-card cash-card cash-details" id="cashDerivatives"><summary>선물옵션 누적 수급 · 차트 판단의 보조 자료</summary><p>${esc(review.flow_interpretation)}</p><div class="cash-table-wrap"><table class="cash-table"><thead><tr><th>기간</th><th>실제 날짜</th><th>외국인 계약</th><th>기관계 계약</th></tr></thead><tbody>${['1','3','5','15'].map(n=>`<tr><th>${n}거래일</th><td>${esc(flow[n].start)} ~ ${esc(flow[n].end)}</td><td>${signed(flow[n].foreign)}</td><td>${signed(flow[n].institution)}</td></tr>`).join('')}</tbody></table></div><p class="cash-note">${esc(data.derivatives_evidence.scope_note)}</p><p class="cash-note">0441 사용자 제공 화면 직접 판독: 9월물 OI 134,903 / 전일 대비 -12,540 / 거래량 124,035. OCR의 열 밀림을 정정했고 원본과 수정 기록을 보존했습니다. 선물 가격 파동과 만기별 잔존 포지션은 이번 분석에서 계산하지 않았습니다.</p></details>
    <details class="chart-card cash-card cash-details" id="cashValidation"><summary>복구 결과·원천·제한사항·다운로드</summary><p>전체 EOD 재실행 없이 저장된 캡처의 수급 추출, 화면 대조 정정, 수급 누적, 현물 5개 지수의 4개 시간대 후처리를 완료했습니다. 최초 수집 실패 기록은 그대로 보존했습니다.</p><ul>${review.limitations.map(x=>`<li>${esc(x)}</li>`).join('')}</ul><div class="cash-downloads">${data.downloads.map(x=>`<a href="${asset(x.file)}" download>${esc(x.label)}</a>`).join('')}</div><p>${review.sources.map(x=>`<a href="${esc(x.url)}" target="_blank" rel="noopener">${esc(x.title)}</a>`).join(' · ')}</p><p class="cash-note">생성 ${esc(data.generated_at)} · 이 분석은 조건부 시나리오이며 수익·도달·승률을 보장하지 않습니다.</p></details>
    </div>`;
}
