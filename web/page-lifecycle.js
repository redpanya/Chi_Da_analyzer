// 뒤로 가기 캐시에서 복귀해도 타이머는 하나만 유지한다.
export function pagePolling(task,delay,{target=globalThis,timers=globalThis}={}){
  let timer=null,busy=false,visible=true;
  async function refresh(){if(busy||!visible)return;busy=true;try{await task();}finally{busy=false;}}
  function start(){visible=true;if(timer===null)timer=timers.setInterval(refresh,delay);void refresh();}
  function stop(){visible=false;if(timer!==null)timers.clearInterval(timer);timer=null;}
  target.addEventListener('pagehide',stop);target.addEventListener('pageshow',start);start();
  return {refresh,stop,start};
}
export function latestResponse(){let generation=0;return {begin(){const id=++generation;return ()=>id===generation;},invalidate(){generation++;}};}
