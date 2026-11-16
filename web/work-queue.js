// 대기 상태의 변경만 전달한다. 목록·취소 조작은 진행 상태 페이지에서 제공한다.
import {showToast} from './ui-feedback.js';
export function createWorkQueue(){
  const opened=Date.now();let seen=new Set();
  let busy=false,states=new Map();
  async function refresh(){
    if(busy)return;busy=true;
    try{
      const response=await fetch('api/work-queue',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});
      const value=await response.json();if(!response.ok)throw Error(value.error||'대기열을 읽지 못했습니다.');
      for(const item of value.items){
        if(states.get(item.id)!==item.state)document.dispatchEvent(new CustomEvent('work-queue-change',{detail:item}));
        states.set(item.id,item.state);
      }
      const events=value.completions||[];
      for(const event of events)if(event.time>=opened&&!seen.has(event.id)){
        showToast([event.title,event.label+' 완료'].filter(Boolean).join(' / '),{key:'done:'+event.id,persistent:true});
      }
      seen=new Set(events.map(event=>event.id));
    }catch{
      // 일시적인 조회 실패는 다음 갱신에서 재시도한다. 오류 표시는 진행 상태 페이지가 담당한다.
    }finally{busy=false;}
  }
  setInterval(refresh,1500);refresh();
  return {accept(value){
    if(value?.queued){
      refresh();
      const error=Error(`${value.queued.label} · 대기열에 등록했습니다. ‘진행 상태’에서 확인·취소할 수 있습니다.`);
      error.queued=true;throw error;
    }
    return value;
  }};
}
