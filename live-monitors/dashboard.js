'use strict';
(()=>{
  const cacheTtlMs=15000;
  let manifestPromise,manifestConfig,manifestExpiresAt=0;
  const requests=new Map();
  const known={'program-live':'program','cvd-live':'cvd','investor-live':'investor'};
  const validate=config=>{
    if(!config||typeof config!=='object'||Array.isArray(config)||config.mode!=='readonly'||typeof config.url!=='string')throw new Error('Invalid connection manifest');
    const url=new URL(config.url);
    if(url.protocol!=='https:'||!/^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.trycloudflare\.com$/.test(url.hostname)||url.username||url.password||url.port||url.search||url.hash||url.pathname!=='/')throw new Error('Invalid connection URL');
    return {url:url.origin,mode:'readonly'};
  };
  const getManifest=force=>{
    if(manifestPromise)return manifestPromise;
    if(!force&&manifestConfig&&Date.now()<manifestExpiresAt)return Promise.resolve(manifestConfig);
    const controller=new AbortController();let timeout;
    const read=Promise.resolve().then(()=>fetch('live-monitors/connection.json?checked='+Date.now(),{cache:'no-store',signal:controller.signal}))
      .then(response=>{if(!response.ok)throw new Error('Connection manifest unavailable');return response.json();})
      .then(validate);
    const pending=Promise.race([read,new Promise((resolve,reject)=>{timeout=setTimeout(()=>{controller.abort();reject(new Error('Connection manifest timed out'));},10000);})])
      .then(config=>{manifestConfig=config;manifestExpiresAt=Date.now()+cacheTtlMs;return config;})
      .catch(error=>{manifestConfig=null;manifestExpiresAt=0;throw error;})
      .finally(()=>{clearTimeout(timeout);if(manifestPromise===pending)manifestPromise=null;});
    manifestPromise=pending;return pending;
  };
  window.loadLiveMonitor=async(tab,options={})=>{
    const kind=known[tab];if(!kind)return;
    const prefix=kind==='program'?'programLive':kind==='investor'?'investorLive':'cvdLive';
    const frame=document.getElementById(prefix+'Frame'),status=document.getElementById(prefix+'Status'),link=document.getElementById(prefix+'Open');
    if(!frame||!status||!link)return;
    let retry=document.getElementById(prefix+'Retry');
    if(!retry){retry=document.createElement('button');retry.id=prefix+'Retry';retry.type='button';retry.textContent='연결 정보 다시 확인';retry.hidden=true;retry.onclick=()=>window.loadLiveMonitor(tab,{force:true});status.parentNode.insertBefore(retry,status.nextSibling);}
    const request=(requests.get(tab)||0)+1;requests.set(tab,request);
    retry.hidden=true;
    status.textContent='보호된 실시간 화면 연결 중…';
    try{
      const config=await getManifest(options.force===true);
      if(requests.get(tab)!==request)return;
      const target=new URL('/'+kind+'/',config.url).href;
      if(frame.dataset.target!==target){frame.src=target;frame.dataset.target=target;}
      frame.hidden=false;frame.dataset.loaded='1';link.href=target;link.hidden=false;
      status.textContent='연결 정보를 확인했어요. 비밀번호로 보호된 화면이며 PC 수집 프로그램과 공유 연결이 켜져 있어야 갱신돼요. 화면이 열리지 않으면 연결 정보를 다시 확인하고, 이전 숫자를 최신값으로 읽지 마세요.';
      retry.hidden=false;
    }catch{
      if(requests.get(tab)!==request)return;
      frame.hidden=true;frame.src='about:blank';delete frame.dataset.loaded;delete frame.dataset.target;
      link.hidden=true;link.removeAttribute('href');retry.hidden=false;
      status.textContent='공유 연결 정보를 확인하지 못했어요. 다시 확인 버튼을 누르거나 PC 공유 연결 상태를 확인해주세요.';
    }
  };
})();
