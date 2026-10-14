'use strict';
(()=>{
  let manifestPromise;
  const known={'program-live':'program','cvd-live':'cvd'};
  window.loadLiveMonitor=async tab=>{
    const kind=known[tab];if(!kind)return;
    const prefix=kind==='program'?'programLive':'cvdLive';
    const frame=document.getElementById(prefix+'Frame'),status=document.getElementById(prefix+'Status'),link=document.getElementById(prefix+'Open');
    if(frame.dataset.loaded==='1')return;
    status.textContent='보호된 실시간 화면 연결 중…';
    try{
      if(!manifestPromise)manifestPromise=fetch('live-monitors/connection.json?checked='+Date.now(),{cache:'no-store'}).then(response=>{if(!response.ok)throw new Error();return response.json();}).catch(error=>{manifestPromise=null;throw error;});
      const config=await manifestPromise,url=new URL(config.url);
      if(url.protocol!=='https:'||!url.hostname.endsWith('.trycloudflare.com')||config.mode!=='readonly')throw new Error();
      const target=new URL('/'+kind+'/',url).href;
      frame.src=target;frame.hidden=false;frame.dataset.loaded='1';link.href=target;link.hidden=false;
      status.textContent='비밀번호로 보호된 화면이에요. PC 수집 프로그램과 공유 연결이 켜져 있어야 갱신돼요. 연결이 끊기면 이전 숫자를 최신값으로 읽지 마세요.';
    }catch{status.textContent='공유 연결 정보를 확인할 수 없어요. PC 공유 연결 상태를 확인해주세요.';}
  };
})();
