"""Publish only the reviewed calendar entries, without private archive fields."""
import json, html, re
from pathlib import Path
from collections import defaultdict

ROOT = Path(__file__).resolve().parents[1]
source = ROOT / 'reports/news/schedule_all_20260927/calendar.json'
out = ROOT / 'news/schedules/2026-09-27'
out.mkdir(parents=True, exist_ok=True)
data = json.loads(source.read_text(encoding='utf-8'))
events = [{k: e[k] for k in ('date','text','urls','state')} for e in data['events']]
assert len(events) == data['manifest']['calendar_count'] == 168
esc = html.escape
groups = defaultdict(list)
for e in events:
    groups[e['date'] or '날짜 미정'].append(e)
def category(d):
    return 'dated' if re.fullmatch(r'\d{4}-\d{2}-\d{2}', d) else ('period' if d.startswith('20') else 'undated')
def order(d):
    return ({'dated':0,'period':1,'undated':2}[category(d)], d)

parts = ['''<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>날짜별 누적 뉴스 일정 | J’s Trading</title>
<style>*{box-sizing:border-box}body{margin:0;background:#f3f6fb;color:#22334b;font:16px/1.65 system-ui,sans-serif}main{max-width:1100px;margin:auto;padding:28px 18px}header,.controls,details{background:white;border:1px solid #dce4ee;border-radius:14px;padding:20px;margin-bottom:14px}h1{font-size:28px;margin:8px 0}h2{font-size:20px}p{margin:8px 0}a{color:#1765ad}.muted{color:#65748b;font-size:14px}.controls{position:sticky;top:0;z-index:1;box-shadow:0 3px 12px #1834510a}input,select,button{font:inherit;padding:9px;border:1px solid #bbc9da;border-radius:7px;background:white;color:inherit}input{width:100%;margin-bottom:10px}.row{display:flex;gap:8px;flex-wrap:wrap}summary{cursor:pointer;font-size:18px;font-weight:700}article{padding:16px 0;border-top:1px solid #e5ebf3}article:first-of-type{margin-top:12px}.state{display:inline-block;color:#775411;background:#fff6dc;border-radius:5px;padding:3px 8px;font-size:13px}.links a{display:inline-block;margin:8px 14px 0 0}[hidden]{display:none!important}@media(max-width:500px){main{padding:12px 8px}header,.controls,details{padding:14px}h1{font-size:23px}select{max-width:100%}.controls{position:static}}@media print{.controls{display:none}body{background:white}details{break-inside:avoid}}</style></head><body><main>
<header><a href="../../../#news">← 대시보드 뉴스</a><h1>날짜별 누적 뉴스 일정</h1><p><strong>9월 27일 보관자료 기준 · 168개 항목</strong></p>
<p>수집 범위: 2026년 9월 11일 20:00~9월 27일 19:01 KST. 원본 게시물 15,254건에서 정리한 일정입니다. 오늘 새로 검증한 뉴스가 아닌 <strong>9/27 누적 일정표의 게시본</strong>입니다.</p>
<p class="muted">날짜가 있는 88개 · 월·연도·상대 기간 45개 · 날짜 미정 35개. 날짜 표기가 행사 성사나 정책 집행 확정을 뜻하지는 않습니다. 기존 검토와 미확인·조건부 항목을 구분했습니다. 해외 현지 날짜와 한국시간은 본문을 따릅니다. 종료일까지 진행되는 일정은 시작일 그룹에 표시할 수 있습니다.</p>
<p class="muted">개별종목·IR·재공시는 주요 목록에서 제외했습니다. 접근 불가 채널·빈 본문·이미지 속 일정·삭제 자료 등으로 누락 가능성이 있습니다.</p></header>
<div class="controls"><label for="query">일정 검색</label><input id="query" type="search" placeholder="이란, 방한, FOMC 등"><div class="row"><select id="kind" aria-label="일정 구분"><option value="all">전체 구분</option value="dated">날짜가 적힌 일정</option><option value="period">월·연도·상대 기간</option><option value="undated">날짜 미정</option></select><select id="date" aria-label="날짜 선택"><option value="all">모든 날짜</option>''']
for d in sorted(groups,key=order):
    parts.append(f'<option value="{esc(d,quote=True)}">{esc(d)} ({len(groups[d])})</option>')
parts.append('''</select><button id="expand">모두 펼치기</button><button id="collapse">모두 접기</button></div><p id="count" class="muted" aria-live="polite"></p></div><div id="groups">''')
last = None
for d in sorted(groups,key=order):
    cat=category(d)
    if cat!=last:
        parts.append('<h2>'+{'dated':'날짜순 일정','period':'월·연도·상대 기간 계획','undated':'날짜 미정·조건부'}[cat]+'</h2>');last=cat
    parts.append(f'<details data-date="{esc(d,quote=True)}" data-kind="{cat}"'+(' open' if d=='2026-09-28' else '')+f'><summary>{esc(d)} · {len(groups[d])}개</summary>')
    for e in groups[d]:
        parts.append('<article><p>'+esc(e['text'])+'</p><span class="state">'+esc(e['state'])+'</span><div class="links">')
        for j,u in enumerate(e['urls']):
            assert u.startswith(('https://','http://')) and 't.me/' not in u
            parts.append(f'<a href="{esc(u,quote=True)}" target="_blank" rel="noopener noreferrer">원문 {j+1} ↗</a>')
        if not e['urls']:parts.append('<span class="muted">독립 원문 링크 미확보</span>')
        parts.append('</div></article>')
    parts.append('</details>')
parts.append('''</div><script>
const groups=[...document.querySelectorAll('details')],q=document.querySelector('#query'),kind=document.querySelector('#kind'),date=document.querySelector('#date');
function filter(){let n=0,g=0;for(const d of groups){let c=0;const allowed=(kind.value==='all'||d.dataset.kind===kind.value)&&(date.value==='all'||d.dataset.date===date.value);for(const a of d.querySelectorAll('article')){a.hidden=!allowed||!a.textContent.toLowerCase().includes(q.value.trim().toLowerCase());if(!a.hidden)c++;}d.hidden=!c;if(c){n+=c;g++;if(q.value||date.value!=='all')d.open=true;}}document.querySelector('#count').textContent=`${g}개 날짜·기간 그룹 / ${n}개 항목 표시`;}
q.addEventListener('input',filter);kind.addEventListener('change',filter);date.addEventListener('change',filter);document.querySelector('#expand').onclick=()=>groups.filter(d=>!d.hidden).forEach(d=>d.open=true);document.querySelector('#collapse').onclick=()=>groups.forEach(d=>d.open=false);filter();
</script></main></body></html>''')
(out/'index.html').write_text(''.join(parts),encoding='utf-8')
print(json.dumps({'events':len(events),'date_groups':len(groups),'path':str(out/'index.html')},ensure_ascii=False))
