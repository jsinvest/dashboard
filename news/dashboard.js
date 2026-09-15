(() => {
  'use strict';
  const panel = document.querySelector('[data-tab-panel="news"]');
  const latest = document.getElementById('newsLatest');
  const list = document.getElementById('newsList');
  const status = document.getElementById('newsStatus');
  const filter = document.getElementById('newsEdition');
  const labels = {morning:'아침판', evening:'저녁판', special:'특별판'};
  let reports = [];
  const node = (tag, text, cls) => {
    const el = document.createElement(tag);
    if (text) el.textContent = text;
    if (cls) el.className = cls;
    return el;
  };
  const timestamp = r => r.cutoff.slice(0,16).replace('T',' ') + ' KST 기준';
  const link = (r,text) => {
    const el = node('a',text);
    el.href = r.url; el.target = '_blank'; el.rel = 'noopener';
    return el;
  };
  function renderList() {
    list.replaceChildren();
    const selected = reports.filter(r => filter.value === 'all' || r.edition === filter.value);
    selected.forEach(r => {
      const row = node('li',null,'news-row');
      const time = node('time',timestamp(r)); time.dateTime = r.cutoff;
      row.append(time,link(r,`[${labels[r.edition]}] ${r.title}`)); list.append(row);
    });
    status.textContent = selected.length ? `게시된 보고서 ${selected.length}건 · 한국시간 기준` : '이 분류에 게시된 보고서가 없습니다.';
  }
  function selectHash() {
    if (location.hash === '#news' && typeof showDashboardTab === 'function') showDashboardTab('news');
  }
  window.addEventListener('hashchange',selectHash);
  selectHash();
  filter.addEventListener('change',renderList);
  fetch('news/index.json?v='+Date.now(),{cache:'no-store'})
    .then(r => {if (!r.ok) throw Error('목록 응답 실패');return r.json();})
    .then(data => {
      if (data.schema_version !== 1 || !Array.isArray(data.reports)) throw Error('목록 형식 오류');
      const ids = new Set();
      reports = data.reports.map(r => {
        if (!/^\d{4}-\d{2}-\d{2}-\d{4}$/.test(r.id) || r.url !== `news/${r.id}/` || !labels[r.edition] || !r.title || !Number.isFinite(Date.parse(r.cutoff)) || ids.has(r.id)) throw Error('보고서 항목 오류');
        ids.add(r.id); return r;
      }).sort((a,b) => b.cutoff.localeCompare(a.cutoff));
      latest.replaceChildren();
      ['morning','evening'].forEach(edition => {
        const r = reports.find(r => r.edition === edition);
        const card = node('article',null,'news-card');
        card.append(node('div',`최근 ${labels[edition]}`,'news-badge'));
        if (r) {
          const time = node('time',timestamp(r)); time.dateTime = r.cutoff;
          card.append(node('h3',r.title),time,document.createElement('br'),link(r,'전체 보고서 열기 ↗'));
        } else card.append(node('p','아직 게시된 보고서가 없습니다.'));
        latest.append(card);
      });
      renderList(); panel.dataset.newsLoaded = 'true';
    })
    .catch(() => {status.textContent = '뉴스 목록을 불러오지 못했어요. 잠시 후 새로고침해 주세요.';panel.dataset.newsLoaded = 'error';});
})();
