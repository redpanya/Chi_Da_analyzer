// 같은 로컬 앱에서 발생한 오류만 모은다. 로그 전송 자체의 실패는 재전송하지 않는다.
export function installErrorCapture(host=window){
  const original=host.fetch.bind(host),recent=new Map();
  const here=new URL(host.location.href),page=here.pathname.endsWith('clip-studio.html')?'clip-studio':here.pathname.endsWith('video-split.html')?'video-split':'index';
  const endpoint=new URL('api/error-log-client',here).href;
  let sent=0,started=Date.now();
  function report(kind,message){
    const text=String(message||'상세 정보 없는 화면 오류').slice(0,2000),key=kind+text,now=Date.now();
    if(now-started>60000){sent=0;started=now;recent.clear();}
    if(sent>=20||now-(recent.get(key)||0)<10000)return;
    recent.set(key,now);sent++;
    const vod=here.searchParams.get('vod_id');
    original(endpoint,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({page,kind,message:text,vod_id:vod})}).catch(()=>{});
  }
  host.addEventListener('error',event=>{
    const media=event.target;
    if(media?.tagName==='VIDEO'||media?.tagName==='AUDIO'){
      // 소스 교체·이탈 취소는 오류로 남기지 않는다.
      if(media.error&&media.error.code!==1)report('media','미디어 재생 오류 코드 '+media.error.code);
    }else if(event.message)report('script',event.message);
  },true);
  host.addEventListener('unhandledrejection',event=>{if(event.reason?.name!=='AbortError')report('promise',event.reason?.message||event.reason);});
  host.fetch=async(input,init)=>{
    let local=false;
    try{const url=new URL(typeof input==='string'||input instanceof URL?input:input.url,here);local=url.origin===here.origin&&url.pathname.includes('/api/')&&!url.pathname.includes('/api/error-log-');}catch{}
    try{
      const response=await original(input,init);
      // HTTP 오류의 상세 내용은 서버가 기록한다. 비 JSON 응답만 별도로 기록한다.
      if(local&&response.ok&&!response.headers.get('content-type')?.includes('application/json'))report('response','서버 응답이 JSON 형식이 아닙니다');
      return response;
    }catch(error){if(local&&error.name!=='AbortError')report('network',error.message);throw error;}
  };
  return {report};
}
if(typeof window!=='undefined')installErrorCapture();
