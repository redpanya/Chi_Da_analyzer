// 기록된 상태만 분류한다. 근거가 부족한 결과를 처리 오류나 정확한 요약으로 추정하지 않는다.
export function resultQuality(item){
  if(item.gap)return {kind:'gap',title:'사용 가능한 전사 없음',label:'전사 없음 · 전사 범위 확인'};
  if(item.failed){
    if(typeof item.error==='string'&&item.error.trim())return {kind:'error',title:'요약 실패',label:'처리 오류 · 이어하기로 다시 시도'};
    return {kind:'review',title:'확인 필요 · 이전 결과',label:'확인 필요 · 이전 결과의 원문·작업 기록 확인'};
  }
  if(item.grounding_state==='review'||item.evidence_review||item.review_needed||item.review||item.time_review)
    return {kind:'review',title:'원문 확인 필요',label:'원문 확인 필요 · 재생·근거 확인'};
  if(item.chat_state==='failed')return {kind:'chat-error',title:null,label:item.summary?.context?.length?'채팅 정리만 실패 · 대화 요약은 확인 가능':'채팅 정리 실패 · 대화 원문 확인'};
  return null;
}
