/* Supplementary source charts, kept under the existing folded source section. */
(()=>{
  async function load(){
    const parent=document.getElementById('marketSourceDetails');if(!parent)return;
    const block=document.createElement('details');block.className='chart-card';block.id='usContextDetails';
    block.style.cssText='margin-top:14px;padding:14px;line-height:1.7';
    const title=document.createElement('summary');title.textContent='미국·니케이225 보조 차트 · 월·주·일·10분';block.append(title);parent.append(block);
    try{
      const response=await fetch('market-analysis/us_context_public.json?v='+Date.now(),{cache:'no-store'});
      if(!response.ok)throw Error('HTTP '+response.status);
      const d=await response.json();
      if(d.status!=='OK'||d.can_use_for_context!==true||!Array.isArray(d.indices)||d.indices.length!==4)throw Error('자료 검증 미완료');
      const p=text=>{const e=document.createElement('p');e.textContent=text;block.append(e);};
      p(`한국 기준 ${d.trade_date} · 미국 완료장 ${d.source_session_date} · Yahoo 지연 보조 원천 · 거래소 공식 가격 독립 검증과 구분`);
      p(`니케이 10분 계산 구간: ${d.nikkei_window.start.slice(0,10)} ~ ${d.nikkei_window.end.slice(0,10)} · ${d.nikkei_window.complete_sessions}개 완료 세션 · ${d.nikkei_window.bars_10m}봉. 과거 누락일과 이전 구간은 지표 계산에서 제외하고 이 구간에서 새로 계산했어요.`);
      for(const gap of d.retained_source_gaps||[])p(`보존된 원천 누락: ${(gap.missing_timestamps||[]).join(', ')} · 실제 값 복원·보간 없음`);
      p('아래 방향 표시는 스크립트의 완료봉 원신호예요. 현재 진행 중 월·주봉은 판단에서 제외하며 AI 최종 뷰·현금비중·주문에 자동 반영하지 않아요.');
      const notice=document.createElement('p');notice.id='usContextUpdateNotice';notice.style.cssText='font-size:12px;color:var(--text-dim);line-height:1.6';
      notice.textContent=`별도 보조자료 갱신: 한국 ${d.trade_date} / 미국 ${d.source_session_date}. 니케이 10분은 ${d.nikkei_window.start.slice(0,10)} 이후 완전 구간만 사용해요. 아래 원본 자료의 미국·니케이 보조 차트에서 확인할 수 있어요.`;
      document.getElementById('marketAIMeta')?.after(notice);
      for(const item of d.indices){
        const card=document.createElement('details');card.style.cssText='margin:14px 0;border-top:1px solid var(--border);padding-top:10px';
        const summary=document.createElement('summary');summary.textContent=`${item.name} · ${item.source_session_date} 완료장`;
        const states=document.createElement('p');states.textContent=[['monthly','월'],['weekly','주'],['daily','일'],['intraday_10m','10분']].map(([key,label])=>`${label}: ${item.timeframes[key].state}`).join(' / ');
        const img=document.createElement('img');
        if(!/^us-context\/[A-Z0-9_]+_mtf\.png$/.test(item.chart))throw Error('차트 경로 오류');
        img.src='market-analysis/'+item.chart+'?v='+encodeURIComponent(d.generated_at);img.alt=item.name+' 월·주·일·10분 원천 차트';img.loading='lazy';img.style.cssText='width:100%;height:auto';
        card.append(summary,states,img);block.append(card);
      }
      const link=document.createElement('a');link.className='quick-btn';link.href='market-analysis/'+d.evidence_zip.file;link.download=d.evidence_zip.file;link.textContent='원본·계산값·검증·원천 누락 기록 ZIP';block.append(link);
      block.dataset.status='OK';window.usContextReady=true;
    }catch(error){const message=document.createElement('p');message.textContent='미국·니케이 보조 자료 확인 불가: '+error.message;block.append(message);block.dataset.status='UNAVAILABLE';}
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',load);else load();
})();
