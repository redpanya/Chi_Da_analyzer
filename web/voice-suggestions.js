import {timecode} from './player.js';

export function createVoiceSuggestions({listen,jump,start,edit}) {
  const $=id=>document.getElementById(id);
  let locked=true, result=null, segment=null;
  const button=(text,action)=>{const b=document.createElement('button');b.className='secondary';b.textContent=text;b.onclick=action;return b;};
  const range=()=>({start_ms:Math.round(Number($('suggest-start').value)*1000),end_ms:Math.round(Number($('suggest-end').value)*1000)});
  function choose(row){
    segment=row.id; $('suggest-start').value=row.start_ms/1000;$('suggest-end').value=row.end_ms/1000;
    $('voice-suggestions').open=true;$('suggest-start').focus();
  }
  $('suggest-start').oninput=$('suggest-end').oninput=()=>{segment=null;};
  $('suggest-run').onclick=()=>{if(!locked&&result?.run)return start('suggest',{
    ...range(),run:result.run,revision:result.revision,...(segment?{segment_id:segment}:{})});};
  $('suggest-original').onclick=()=>{if(!locked)return start('retranscribe-original',range());};
  $('suggest-open').onclick=()=>{if(!locked&&$('suggest-version').value)return edit('select-suggestion',{id:$('suggest-version').value});};
  $('retranscription-open').onclick=()=>{if(!locked&&$('retranscription-version').value)return edit('select-retranscription',{id:$('retranscription-version').value});};
  function options(id,rows,selected){
    $(id).replaceChildren();for(const row of rows||[]){const o=document.createElement('option');o.value=row.id;o.textContent=`${timecode(row.start_ms)}~${timecode(row.end_ms)} · ${row.id.slice(0,8)}`;$(id).append(o);}$(id).value=selected||'';
  }
  return {choose,reset(){segment=null;$('suggest-start').value=0;$('suggest-end').value=10;$('suggest-results').replaceChildren();$('retranscription-results').replaceChildren();},
    setDisabled(value){locked=value;for(const id of ['suggest-run','suggest-original','suggest-open','retranscription-open'])$(id).disabled=locked;
      for(const b of $('suggest-results').querySelectorAll?.('[data-apply]')||[])b.disabled=locked||!!result?.suggestion?.stale;},
    render(value,state){
      result=value;
      options('suggest-version',state.suggestions,state.suggestion);options('retranscription-version',state.retranscriptions,state.retranscription);
      const s=value.suggestion, host=$('suggest-results');host.replaceChildren();
      $('suggest-notice').textContent=!s?'아직 후보 검토 결과가 없습니다. 최대 5분·20개 발언을 선택하세요.':
        `${s.complete?'검토 완료':'부분 결과'} · ${s.items.length}/${s.input.rows.length}개${s.stale?' · 입력이 변경된 이전 후보입니다. 새 검토가 필요합니다.':''}`;
      for(const row of s?.items||[]){
        const card=document.createElement('article');card.className='transcript-row';
        const title=document.createElement('h4');title.textContent=`${timecode(row.start_ms)} ~ ${timecode(row.end_ms)} · ${row.candidate?'후보: '+s.input.names[row.candidate]:'배정 보류'}`;
        const text=document.createElement('p');text.textContent=row.text;
        const reason=document.createElement('p');reason.textContent=row.reason;
        const hint=document.createElement('p');hint.className='hint';hint.textContent=row.acoustic.note;
        const actions=document.createElement('div');actions.className='play-actions';
        actions.append(button('대상 음성 듣기',()=>listen({sample:row,name:'후보 검토 대상'})),button('영상에서 확인',()=>jump(row.start_ms)),button('이 구간 추가 확인',()=>choose(row)));
        if(row.candidate){const b=button('듣고 이 후보로 배정',()=>{if(!locked&&!s.stale)return edit('accept-suggestion',{suggestion:s.id,segment_id:row.id,speaker:row.candidate});});
          b.dataset.apply='true';b.disabled=locked||s.stale;actions.append(b);}
        card.append(title,text,reason,hint,actions);
        for(const a of row.acoustic.candidates){
          const line=document.createElement('p');line.className='hint';line.textContent=`${s.input.names[a.speaker]} · 음향 유사도 ${a.similarity.toFixed(3)} (확률 아님) `;
          for(const [i,sample] of a.samples.entries())line.append(button(`대표 ${i+1} 듣기 · ${sample.status==='confirmed'?'사용자 확인':'자동 추정'}`,()=>listen({sample,name:s.input.names[a.speaker]+' 대표 음성'})));
          card.append(line);
        }
        if(row.evidence.length){const refs=document.createElement('details'),label=document.createElement('summary');label.textContent='참고한 앞뒤 대화';refs.append(label);
          for(const id of row.evidence){const source=s.input.context.find(r=>r.id===id);if(source){const p=document.createElement('p');p.textContent=`${timecode(source.start_ms)} · ${source.speaker_name}: ${source.text}`;refs.append(p);}}card.append(refs);}
        host.append(card);
      }
      const t=value.retranscription, target=$('retranscription-results');target.replaceChildren();
      if(t){const title=document.createElement('p');title.className='hint';title.textContent=`원음 재전사 비교본 · 기존 전사에 적용하지 않았습니다${t.stale?' · 이전 입력의 결과':''}`;target.append(title);
        for(const row of t.segments){const p=document.createElement('p');p.append(button(timecode(row.start_ms),()=>jump(row.start_ms)));const text=document.createElement('span');text.textContent=' '+row.text;p.append(text);target.append(p);}
        if(!t.segments.length){const p=document.createElement('p');p.textContent='인식한 문장 없음';target.append(p);}}
    },
  };
}
