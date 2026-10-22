// 새 요약의 입력 선택은 전사·화자 검토 페이지의 현재 버전과 별도로 보관한다.
export function createContextInputs(onChange, prefix="context") {
  const $=id=>document.getElementById(id.replace(/^context-/, prefix+"-"));
  let path=null, catalog={}, transcript='', speaker='', key='', locked=true;
  const voices=()=> (catalog.speakers||[]).filter(r=>r.transcript_run===transcript);
  function options(id,items,placeholder,value) {
    const select=$(id), option=(value,label,disabled=false)=>{
      const el=document.createElement('option');el.value=value;el.textContent=label;el.disabled=disabled;return el;
    };
    select.replaceChildren(option('',placeholder),...items.map(r=>option(r.id,r.label,r.complete===false)));
    select.value=value;
    select.title=items.find(r=>r.id===value)?.label||placeholder;
  }
  function render(){
    options('context-transcript',catalog.transcripts||[],'분석할 전사 선택',transcript);
    options('context-speaker',voices(),'사용 안 함 · 전사 내용만 분석',speaker);
    $('context-transcript').disabled=locked;
    $('context-speaker').disabled=locked||!transcript||!voices().length;
    $('context-input-status').textContent=transcript
      ?'선택한 전사의 수동 교정을 반영합니다. 화자 정보는 이 전사와 연결된 분석만 선택할 수 있습니다.'
      :'전체 처리가 완료된 전사 데이터를 선택하세요.';
  }
  $('context-transcript').onchange=()=>{
    transcript=$('context-transcript').value;speaker='';render();onChange();
  };
  $('context-speaker').onchange=()=>{speaker=$('context-speaker').value;render();onChange();};
  return {
    ready(){return !!(catalog.transcripts||[]).find(r=>r.id===transcript&&r.complete);},
    selection(){return {transcript_run:transcript,speaker_run:speaker||null};},
    setProject(project){
      const changed=path!==project?.path;
      path=project?.path;catalog=project?.context?.inputs||{};locked=!project||project.locked;
      if(changed){
        transcript=(catalog.transcripts||[]).find(r=>r.id===catalog.transcript_run&&r.complete)?.id
          ||(catalog.transcripts||[]).find(r=>r.complete)?.id||'';
        speaker=voices().find(r=>r.id===catalog.speaker_run)?.id||'';
      }else{
        if(!(catalog.transcripts||[]).some(r=>r.id===transcript))transcript='';
        // 삭제한 입력 대신 다른 화자를 자동으로 넣지 않는다.
        if(!voices().some(r=>r.id===speaker))speaker='';
      }
      const next=JSON.stringify([path,catalog,locked,transcript,speaker]);
      if(key!==next){key=next;render();}
    }
  };
}
