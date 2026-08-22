#!/usr/bin/env python3
import json, re
from pathlib import Path
from collections import defaultdict
from datetime import datetime, timezone, timedelta

ROOT=Path(__file__).resolve().parents[1]
REPORT=ROOT/'report_data.json'
UPDATE=ROOT/'report_update_20260821.json'
SIGNALS=ROOT/'report_signal_data.json'
INDEX=ROOT/'index.html'
KST=timezone(timedelta(hours=9))

def num(v):
    try: return int(float(str(v).replace(',','').strip()))
    except: return 0

def s(v): return '' if v is None else str(v)

def dedupe_key(r):
    return (s(r.get('날짜')),s(r.get('종목코드')).zfill(6),s(r.get('종목명')),num(r.get('목표주가')),s(r.get('제목')),s(r.get('기관')))

def rebuild_summary(details):
    groups=defaultdict(list)
    for r in details:
        code=s(r.get('종목코드')).zfill(6) if s(r.get('종목코드')) else ''
        name=s(r.get('종목명'))
        groups[(code,name)].append(r)
    out=[]
    for (code,name),rows in groups.items():
        high=max(rows,key=lambda r:(num(r.get('목표주가')),s(r.get('날짜'))))
        latest_date=max(s(r.get('날짜')) for r in rows)
        latest_rows=[r for r in rows if s(r.get('날짜'))==latest_date]
        latest=max(latest_rows,key=lambda r:num(r.get('목표주가')))
        out.append({
            '종목명':name,'종목코드':code,
            '최고가날짜':s(high.get('날짜')),'최고목표주가':num(high.get('목표주가')),
            '최근날짜':latest_date,'최근목표주가':num(latest.get('목표주가')),
            '언급횟수':len(rows),
            '제목(최고가기준)':s(high.get('제목')),
            '내용(최고가기준)':s(high.get('내용')),
            '기관(최고가기준)':s(high.get('기관'))
        })
    out.sort(key=lambda r:(num(r['최고목표주가']),r['최근날짜'],r['종목명']),reverse=True)
    return out

def merge_report_data():
    data=json.loads(REPORT.read_text(encoding='utf-8'))
    upd=json.loads(UPDATE.read_text(encoding='utf-8'))
    details=list(data.get('details') or [])
    seen={dedupe_key(r) for r in details}
    added=0
    for r in upd.get('report_append',[]):
        k=dedupe_key(r)
        if k in seen: continue
        clean={key:r.get(key) for key in ['날짜','종목명','목표주가','상향건수','전체건수','종목코드','제목','내용','기관']}
        details.append(clean); seen.add(k); added+=1
    details.sort(key=lambda r:(s(r.get('날짜')),s(r.get('종목명')),num(r.get('목표주가'))))
    summary=rebuild_summary(details)
    now=datetime.now(KST).isoformat(timespec='seconds')
    meta=dict(data.get('meta') or {})
    meta.update({'created_at':now,'generated_at':now,'summary_count':len(summary),'detail_count':len(details),'last_merge_source':'report_update_20260821.json','last_merge_added':added,'last_merge_through':'2026-08-21'})
    REPORT.write_text(json.dumps({'meta':meta,'summary':summary,'details':details},ensure_ascii=False,separators=(',',':')),encoding='utf-8')
    SIGNALS.write_text(json.dumps({'meta':upd.get('meta',{}),**upd.get('signals',{})},ensure_ascii=False,separators=(',',':')),encoding='utf-8')
    return added,len(details),len(summary)

REPORT_PANEL="""  <!-- 리포트 검색 -->
  <div class=\"tab-panel\" data-tab-panel=\"report\">
    <div class=\"section-title\">리포트 검색 · TARGET PRICE & EARNINGS SIGNALS</div>
    <div class=\"report-card\">
      <div class=\"report-section-tabs\">
        <button class=\"report-section-btn active\" id=\"reportSectionSearchBtn\" onclick=\"setReportSection('search')\">리포트검색</button>
        <button class=\"report-section-btn report-up-btn\" id=\"reportSectionUpBtn\" onclick=\"setReportSection('up')\">목표주가 상향</button>
        <button class=\"report-section-btn report-down-btn\" id=\"reportSectionDownBtn\" onclick=\"setReportSection('down')\">목표주가 하향</button>
      </div>
      <div class=\"report-section-pane active\" id=\"reportSectionSearch\">
        <div class=\"report-search-row\"><input id=\"reportSearchInput\" type=\"text\" placeholder=\"종목명/종목코드/제목/내용/기관 검색 (예: 삼성전자, 005930, 반도체)\" /><button onclick=\"searchReports()\">검색</button></div>
        <div class=\"report-meta\" id=\"reportMeta\">report_data.json 로딩중...</div>
        <div class=\"report-tabs\"><button class=\"report-mini-btn active\" id=\"reportSummaryBtn\" onclick=\"setReportMode('summary')\">요약</button><button class=\"report-mini-btn\" id=\"reportDetailBtn\" onclick=\"setReportMode('detail')\">전체 리포트</button></div>
        <div class=\"report-result-box\"><div id=\"reportResults\" class=\"report-empty\">검색어를 입력하세요.</div></div>
      </div>
      <div class=\"report-section-pane\" id=\"reportSectionUp\">
        <div class=\"signal-headline\"><div><b>상향 시그널</b><span>6월 18일 이후 · 목표주가 상향 + 어닝서프라이즈 + 컨센서스/이익추정 상향</span></div><div id=\"reportUpCount\" class=\"signal-count\"></div></div>
        <div class=\"signal-filter-row\"><input id=\"reportUpSearch\" type=\"text\" placeholder=\"상향 시그널 검색\" oninput=\"renderSignalList('up')\"/><select id=\"reportUpCategory\" onchange=\"renderSignalList('up')\"></select></div>
        <div class=\"signal-stat-grid\" id=\"reportUpStats\"></div><div class=\"report-result-box\"><div id=\"reportUpResults\" class=\"report-empty\">상향 시그널 로딩중...</div></div>
      </div>
      <div class=\"report-section-pane\" id=\"reportSectionDown\">
        <div class=\"signal-headline down\"><div><b>하향 시그널</b><span>6월 18일 이후 · 목표주가 하향 + 어닝쇼크 + 컨센서스/이익추정 하향</span></div><div id=\"reportDownCount\" class=\"signal-count\"></div></div>
        <div class=\"signal-note\" id=\"reportDownNote\"></div>
        <div class=\"signal-filter-row\"><input id=\"reportDownSearch\" type=\"text\" placeholder=\"하향 시그널 검색\" oninput=\"renderSignalList('down')\"/><select id=\"reportDownCategory\" onchange=\"renderSignalList('down')\"></select></div>
        <div class=\"signal-stat-grid\" id=\"reportDownStats\"></div><div class=\"report-result-box\"><div id=\"reportDownResults\" class=\"report-empty\">하향 시그널 로딩중...</div></div>
      </div>
    </div>
  </div>

"""

CSS="""
  .report-section-tabs{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:14px;padding-bottom:12px;border-bottom:1px solid var(--border)}
  .report-section-btn{border:1px solid var(--border);background:var(--bg3);color:var(--text-dim);padding:9px 15px;border-radius:7px;font-weight:700;cursor:pointer}
  .report-section-btn.active{border-color:var(--accent);color:var(--accent);box-shadow:0 0 0 2px rgba(0,229,255,.08)}
  .report-section-btn.report-up-btn.active{border-color:var(--up);color:var(--up)} .report-section-btn.report-down-btn.active{border-color:var(--down);color:var(--down)}
  .report-section-pane{display:none}.report-section-pane.active{display:block}
  .signal-headline{display:flex;justify-content:space-between;gap:14px;align-items:flex-end;padding:12px 14px;margin-bottom:10px;border-left:3px solid var(--up);background:rgba(46,213,115,.06);border-radius:6px}
  .signal-headline.down{border-left-color:var(--down);background:rgba(255,71,87,.06)} .signal-headline b{font-size:17px;color:var(--up)} .signal-headline.down b{color:var(--down)}
  .signal-headline span{display:block;margin-top:4px;font-size:12px;color:var(--text-dim)} .signal-count{font-family:'JetBrains Mono',monospace;font-size:13px;color:var(--text-dim);white-space:nowrap}
  .signal-note{font-size:12px;line-height:1.6;padding:9px 11px;background:rgba(255,184,0,.08);border:1px solid rgba(255,184,0,.18);border-radius:6px;color:#e6c66a;margin-bottom:10px}
  .signal-filter-row{display:flex;gap:8px;margin-bottom:10px}.signal-filter-row input,.signal-filter-row select{background:var(--bg3);border:1px solid var(--border);color:var(--text);border-radius:6px;padding:9px 12px}.signal-filter-row input{flex:1}.signal-filter-row select{min-width:190px}
  .signal-stat-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:8px;margin-bottom:12px}.signal-stat{padding:11px 12px;background:#171d27;border:1px solid #344153;border-radius:7px}.signal-stat small{display:block;color:#e7edf6;font-size:12px;font-weight:700}.signal-stat strong{display:block;margin-top:5px;font-family:'JetBrains Mono',monospace;font-size:18px}.signal-stat span{display:block;margin-top:4px;color:#aebbd0;font-size:11px;font-weight:600}.signal-stat.up strong{color:var(--up)}.signal-stat.down strong{color:var(--down)}
  .signal-tag{display:inline-block;padding:3px 7px;border-radius:999px;font-size:11px;font-weight:700;white-space:nowrap}.signal-tag.up{color:var(--up);background:rgba(46,213,115,.10);border:1px solid rgba(46,213,115,.22)}.signal-tag.down{color:var(--down);background:rgba(255,71,87,.10);border:1px solid rgba(255,71,87,.22)}
  .signal-link{color:var(--accent);text-decoration:none}.signal-link:hover{text-decoration:underline}
  .signal-latest-badge{display:inline-block;margin-left:6px;padding:2px 5px;border-radius:999px;background:rgba(0,229,255,.09);color:var(--accent);font-size:10px;font-weight:700;vertical-align:1px}
  .signal-more-btn{display:block;margin-top:6px;padding:3px 7px;border:1px solid var(--border);border-radius:5px;background:var(--bg3);color:var(--text-dim);font-size:11px;cursor:pointer;white-space:nowrap}.signal-more-btn:hover{border-color:var(--accent);color:var(--accent)}
  .signal-group-extra td{background:rgba(255,255,255,.018)}.signal-group-extra td:first-child{padding-left:20px}.signal-group-extra[hidden]{display:none}
  @media(max-width:700px){.signal-filter-row{flex-direction:column}.signal-filter-row select{min-width:0}.signal-headline{align-items:flex-start;flex-direction:column}}
"""

JS=r"""
// ── 리포트 하위메뉴 / 상·하향 시그널 ──
let reportSignalData={meta:{},up:[],down:[]};
let reportSection='search';
function setReportSection(section){reportSection=section;['search','up','down'].forEach(k=>{const cap=k.charAt(0).toUpperCase()+k.slice(1);document.getElementById('reportSection'+cap)?.classList.toggle('active',k===section);document.getElementById('reportSection'+cap+'Btn')?.classList.toggle('active',k===section);});if(section==='up'||section==='down')renderSignalList(section);}
function signalCategoryCounts(rows){return rows.reduce((a,r)=>{const k=r['구분']||'기타';a[k]=(a[k]||0)+1;return a;},{});}
function setupSignalCategory(direction){const rows=reportSignalData[direction]||[];const sel=document.getElementById(direction==='up'?'reportUpCategory':'reportDownCategory');if(!sel)return;const cats=Object.keys(signalCategoryCounts(rows));sel.innerHTML='<option value="">전체 구분</option>'+cats.map(c=>`<option value="${escapeHtml(c)}">${escapeHtml(c)}</option>`).join('');}
function signalUniqueStockCount(rows){return new Set(rows.map(signalStockKey)).size;}
function renderSignalStats(direction){const rows=reportSignalData[direction]||[],counts=signalCategoryCounts(rows);const box=document.getElementById(direction==='up'?'reportUpStats':'reportDownStats');if(box)box.innerHTML=Object.entries(counts).map(([k,v])=>{const uniqueStocks=signalUniqueStockCount(rows.filter(r=>(r['구분']||'기타')===k));return `<div class="signal-stat ${direction}"><small>${escapeHtml(k)}</small><strong>${v.toLocaleString()}건</strong><span>중복 제외 ${uniqueStocks.toLocaleString()}종목</span></div>`;}).join('');const countEl=document.getElementById(direction==='up'?'reportUpCount':'reportDownCount');if(countEl)countEl.textContent=`총 ${rows.length.toLocaleString()}개 시그널 · 중복 제외 ${signalUniqueStockCount(rows).toLocaleString()}종목`;}
function signalSearchMatch(r,q){if(!q)return true;return Object.values(r).map(normalizeReportText).join(' ').includes(normalizeReportText(q));}
function signalStrength(r){if(r['영업이익_컨센대비_pct']!==null&&r['영업이익_컨센대비_pct']!==undefined)return `영업 컨센대비 ${Number(r['영업이익_컨센대비_pct']).toLocaleString()}%`;if(r['목표주가변동률_pct']!==null&&r['목표주가변동률_pct']!==undefined)return `목표가 +${Number(r['목표주가변동률_pct']).toLocaleString()}%`;return escapeHtml(r['근거키워드']||'');}
function signalStockKey(r){return normalizeReportText(r['종목코드']||r['종목명']||'종목정보없음');}
function renderSignalRow(r,direction,{groupId='',extraCount=0,isExtra=false}={}){const tagClass=direction==='up'?'up':'down',groupAttrs=isExtra?` class="signal-group-extra" data-signal-group="${groupId}" hidden`:'';const groupControl=extraCount?`<span class="signal-latest-badge">최신</span><button type="button" class="signal-more-btn" data-count="${extraCount}" aria-expanded="false" aria-controls="${groupId}" onclick="toggleSignalGroup('${groupId}',this)">나머지 ${extraCount}건 펼쳐보기</button>`:'';return `<tr${groupAttrs}><td>${escapeHtml(r['날짜'])}</td><td><strong>${escapeHtml(r['종목명'])}</strong>${groupControl}</td><td class="code">${escapeHtml(r['종목코드'])}</td><td><span class="signal-tag ${tagClass}">${escapeHtml(r['구분'])}</span></td><td>${signalStrength(r)}</td><td class="num">${r['목표주가']?formatReportNumber(r['목표주가']):''}</td><td class="title">${escapeHtml(r['제목']||(r['영업이익']?`영업이익 ${r['영업이익']}`:''))}</td><td>${escapeHtml(r['내용']||([r['영업_QoQ']&&`QoQ ${r['영업_QoQ']}`,r['영업_YoY']&&`YoY ${r['영업_YoY']}`].filter(Boolean).join(' · ')))}</td><td>${escapeHtml(r['기관']||r['연계_기관']||'')}</td><td>${r['텔레그램URL']?`<a class="signal-link" href="${escapeHtml(r['텔레그램URL'])}" target="_blank" rel="noopener">보기</a>`:''}</td></tr>`;}
function renderSignalTable(rows,direction){const groups=new Map();rows.map((r,index)=>({r,index})).sort((a,b)=>String(b.r['날짜']||'').localeCompare(String(a.r['날짜']||''))||a.index-b.index).forEach(({r})=>{const key=signalStockKey(r);if(!groups.has(key))groups.set(key,[]);groups.get(key).push(r);});const bodies=[...groups.values()].map((group,index)=>{const groupId=`signal-${direction}-group-${index}`,latest=group[0],older=group.slice(1);return `<tbody id="${groupId}">${renderSignalRow(latest,direction,{groupId,extraCount:older.length})}${older.map(r=>renderSignalRow(r,direction,{groupId,isExtra:true})).join('')}</tbody>`;}).join('');return `<table class="report-table"><thead><tr><th>날짜</th><th>종목</th><th>코드</th><th>구분</th><th>강도/수치</th><th>목표주가</th><th>제목·실적</th><th>내용</th><th>기관</th><th>원문</th></tr></thead>${bodies}</table>`;}
function toggleSignalGroup(groupId,button){const extras=document.querySelectorAll(`[data-signal-group="${groupId}"]`),willExpand=button.getAttribute('aria-expanded')!=='true',count=Number(button.dataset.count||extras.length);extras.forEach(row=>{row.hidden=!willExpand;});button.setAttribute('aria-expanded',String(willExpand));button.textContent=willExpand?`나머지 ${count}건 접기`:`나머지 ${count}건 펼쳐보기`;}
function renderSignalList(direction){const isUp=direction==='up',input=document.getElementById(isUp?'reportUpSearch':'reportDownSearch'),sel=document.getElementById(isUp?'reportUpCategory':'reportDownCategory'),box=document.getElementById(isUp?'reportUpResults':'reportDownResults');if(!box)return;const q=input?.value.trim()||'',cat=sel?.value||'';const rows=(reportSignalData[direction]||[]).filter(r=>(!cat||r['구분']===cat)&&signalSearchMatch(r,q));if(!rows.length){box.className='report-empty';box.textContent='조건에 맞는 시그널이 없습니다.';return;}box.className='';box.innerHTML=renderSignalTable(rows,direction);}
async function loadReportSignalData(){try{const res=await fetch('report_signal_data.json?v='+Date.now(),{cache:'no-store'});if(!res.ok)throw new Error('HTTP '+res.status);reportSignalData=await res.json();setupSignalCategory('up');setupSignalCategory('down');renderSignalStats('up');renderSignalStats('down');renderSignalList('up');renderSignalList('down');const note=document.getElementById('reportDownNote');if(note)note.textContent=reportSignalData.meta?.note||'';}catch(e){console.error('report_signal_data load failed',e);['reportUpResults','reportDownResults'].forEach(id=>{const el=document.getElementById(id);if(el){el.className='report-empty';el.textContent='report_signal_data.json 로딩 실패';}});}}
loadReportSignalData();
"""

def patch_index():
    html=INDEX.read_text(encoding='utf-8')
    pattern=r'  <!-- 리포트 검색 -->\n.*?(?=  <!-- 당일 주도주:)'
    html,n=re.subn(pattern,REPORT_PANEL,html,flags=re.S)
    if n!=1: raise RuntimeError(f'report panel replace count={n}')
    head=html.split('</style>',1)[0]
    if '.report-section-tabs{' not in head: html=html.replace('</style>',CSS+'\n</style>',1)
    marker='// ── run_all 시장분석: market-analysis/latest.json ──'
    if marker not in html: raise RuntimeError('market analysis JS marker not found')
    if '// ── 리포트 하위메뉴 / 상·하향 시그널 ──' not in html: html=html.replace(marker,JS+'\n\n'+marker,1)
    INDEX.write_text(html,encoding='utf-8')

if __name__=='__main__':
    added,total,summary=merge_report_data();patch_index();print(json.dumps({'added':added,'detail_count':total,'summary_count':summary,'index_patched':True},ensure_ascii=False))
