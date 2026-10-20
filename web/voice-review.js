import {timecode} from './player.js';

// 실패 발언의 검색·페이지·대상 선택은 배정된 전사 목록과 독립적으로 유지한다.
export function createVoiceReview({listen, save, search, jump, suggest}) {
  const $=id=>document.getElementById(id), drafts=new Map();
  let cursor=0, next=null, run=null, controls=[], disabled=true, playable=false;
  const empty={items:[],total:0,cursor:0,next_cursor:null};
  function setDisabled(locked, canListen) {
    disabled=locked;playable=canListen;
    for(const c of controls){c.select.disabled=disabled;c.save.disabled=disabled||!c.select.value;if(c.listen)c.listen.disabled=!playable;}
    for(const button of $('voice-failed-group-samples').children)button.disabled=!playable;
  }
  function targets(select, speakers, value=''){
    select.replaceChildren();
    for(const [id,name] of [['','화자를 선택하세요'],...speakers.map(s=>[s.id,`${s.name} · ${s.default}`]),['__new__','새 화자 만들고 배정']]){
      const option=document.createElement('option');option.value=id;option.textContent=name;select.append(option);
    }
    select.value=value;
  }
  function reset(){
    cursor=0;next=null;run=null;drafts.clear();controls=[];
    $('voice-failed-query').value='';$('voice-failed-rows').replaceChildren();
    $('voice-failed-count').textContent='';$('voice-failed-empty').textContent='화자 분석을 완료하면 실패 발언을 검토할 수 있습니다.';
    $('voice-failed-prev').disabled=$('voice-failed-next').disabled=true;
    $('voice-failed-status').textContent='발언의 음성을 듣고 대상 화자를 선택하세요.';
    $('voice-failed-group').replaceChildren();$('voice-failed-group').value='';$('voice-failed-group-review').hidden=true;
  }
  $('voice-failed-search').onsubmit=e=>{e.preventDefault();cursor=0;search();};
  $('voice-failed-prev').onclick=()=>{cursor=Math.max(0,cursor-100);search();};
  $('voice-failed-next').onclick=()=>{if(next!==null){cursor=next;search();}};
  $('voice-failed-group').onchange=()=>{cursor=0;drafts.clear();search();};
  return {
    reset, setDisabled,
    request:()=>({review:true,failed_query:$('voice-failed-query').value,failed_cursor:cursor,failed_group:$('voice-failed-group').value||''}),
    render(result) {
      const page=result.failed_review||empty;
      if(run!==result.run){drafts.clear();run=result.run;}
      cursor=page.cursor;next=page.next_cursor;controls=[];
      const ids=new Set(page.items.map(row=>row.id));for(const id of drafts.keys())if(!ids.has(id)&&id!=='group:'+page.group)drafts.delete(id);
      $('voice-failed-rows').replaceChildren();
      $('voice-failed-count').textContent=`남은 실패 ${result.failed||0}개 · 검색 결과 ${page.total}개`+(page.total?` · ${Math.floor(cursor/100)+1}쪽`:'');
      $('voice-failed-prev').disabled=cursor===0;$('voice-failed-next').disabled=next===null;
      $('voice-failed-empty').textContent=page.total?'':!result.run?'화자 분석을 완료하면 실패 발언을 검토할 수 있습니다.':
        result.failed?'검색 조건에 맞는 실패 발언이 없습니다.':'검토할 화자인식 실패 발언이 없습니다.';
      const groupSelect=$('voice-failed-group');groupSelect.replaceChildren();
      for(const [id,name] of [['','실패 발언 전체'],...(page.groups||[]).map(g=>[g.id,`${g.name} 자동 후보 · ${g.count}개`]),['__ungrouped__','묶음 근거 부족 · 개별 검토']]){
        const option=document.createElement('option');option.value=id;option.textContent=name;groupSelect.append(option);
      }
      groupSelect.value=page.group||'';
      $('voice-failed-group-note').textContent=page.groups?.length?'같은 자동 화자 ID가 단독으로 겹친 발언을 모았습니다. 동일인 확률은 아니며 잘못 묶일 수 있습니다. 대표 음성과 목록을 확인한 뒤 배정하세요.':'기존 분석 결과에서 묶을 수 있는 단일 화자 근거가 부족합니다. 동일인 확률을 임의로 만들지 않습니다.';
      const group=(page.groups||[]).find(g=>g.id===page.group);
      $('voice-failed-group-review').hidden=!group||!page.total;
      const samples=$('voice-failed-group-samples');samples.replaceChildren();
      if(group&&page.total){
        for(const [index,row] of (page.samples||[]).entries()){
          const audio=document.createElement('button');audio.className='secondary';audio.textContent=`대표 ${index+1} 듣기 · ${timecode(row.start_ms)}`;
          audio.onclick=()=>listen({sample:row,name:group.name+' 후보 · '+timecode(row.start_ms)},$('voice-failed-status'));samples.append(audio);
        }
        const select=$('voice-failed-group-target'),assign=$('voice-failed-group-assign');
        targets(select,result.speakers,drafts.get('group:'+group.id)||'');
        assign.textContent=`검색된 후보 ${page.total}개 일괄 배정`;
        assign.onclick=()=>{if(!disabled&&select.value)return save({candidate_speaker:group.id,query:page.query},select.value,{run:result.run,revision:result.revision});};
        select.onchange=()=>{drafts.set('group:'+group.id,select.value);assign.disabled=disabled||!select.value;};
        controls.push({select,save:assign});
      }
      for(const row of page.items){
        const card=document.createElement('article');card.className='transcript-row voice-failed-row';
        const time=`${timecode(row.start_ms)} ~ ${timecode(row.end_ms)}`;
        const title=document.createElement('h4');title.textContent=time;
        const reason=document.createElement('p');reason.className='voice-status failed';reason.textContent='화자인식 실패 · '+(result.reasons[row.reason]||'이유 미확인');
        const text=document.createElement('p');text.textContent=row.text;
        const actions=document.createElement('div');actions.className='play-actions';
        const audio=document.createElement('button');audio.className='secondary';audio.textContent='이 발언 음성 듣기';
        audio.setAttribute('aria-label',time+' 음성 듣기');audio.onclick=()=>listen({sample:row,name:time+' · 화자인식 실패'},$('voice-failed-status'));
        const video=document.createElement('button');video.className='subtle';video.textContent='영상에서 확인';video.onclick=()=>jump(row.start_ms);
        const label=document.createElement('label');label.className='inline-control';label.append(document.createTextNode('배정할 화자'));
        const select=document.createElement('select');select.setAttribute('aria-label',time+' 배정할 화자');
        targets(select,result.speakers,drafts.get(row.id)||'');
        const assign=document.createElement('button');assign.className='primary';assign.textContent='화자 배정';assign.setAttribute('aria-label',time+' 화자 배정');
        assign.onclick=()=>{if(!disabled&&select.value)return save({segment_id:row.id},select.value,{run:result.run,revision:result.revision});};
        select.onchange=()=>{drafts.set(row.id,select.value);assign.disabled=disabled||!select.value;};
        const editor=document.createElement('details'),summary=document.createElement('summary');
        summary.textContent='화자 배정';editor.open=drafts.has(row.id);editor.append(summary,label,assign);
        label.append(select);actions.append(audio,video);card.append(title,reason,text,actions,editor);$('voice-failed-rows').append(card);
        if(suggest){const review=document.createElement('button');review.className='secondary';review.textContent='음향·문맥 검토 범위 선택';review.onclick=()=>suggest(row);actions.append(review);}
        controls.push({select,save:assign,listen:audio});
      }
      setDisabled(disabled,playable);
    },
  };
}
