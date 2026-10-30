import {resultBrowser,lazyDetails} from './result-browser.js';
import {contextKey} from './context-comment-model.js';
import {timecode} from './player.js';
import {clipEvidence,skippedChatEvidence} from './context-clip-evidence.js';
const $=id=>document.getElementById(id);
const node=(tag,text,className='')=>{const el=document.createElement(tag);el.textContent=text;el.className=className;return el;};

// 클립 탭은 상세 문맥·타임스탬프와 결과 선택 상태를 따로 보관한다.
export function createClipResults({api,player,onResult=()=>{},checkbox=()=>null}){
  let selectedItem=null;
  let project=null,current=null,serial=0,catalogKey='',renderedKey='',lastResult=null;
  const browser=resultBrowser($('context-clips-result'),()=>{if(lastResult)render(lastResult);},{keyOf:contextKey});
  document.addEventListener('context-comment-source',e=>{if(!$('context-clips-panel').hidden)browser.locate(e.detail);});
  const runs=()=> (project?.context?.runs||[]).filter(r=>r.mode==='clips');
  function status(text){$('context-clips-status').textContent=text;}
  function versions(){
    const options=runs().map(r=>{const el=node('option',`${r.label} · ${r.title||''}`);el.value=r.id;return el;});
    $('context-clips-version').replaceChildren(...options);$('context-clips-version').value=current||'';
    $('context-clips-version').disabled=!options.length;$('context-clips-refresh').disabled=!current;
  }
  function play(item,peak=false){
    if(project?.tasks?.video?.state!=='complete'){status('저장한 영상이 준비된 뒤 재생할 수 있습니다.');return;}
    selectedItem=String(item.start_ms)+':'+item.title;
    for(const card of $('context-clips-result').querySelectorAll('.clip-item'))card.classList.toggle('selected',card.dataset.key===selectedItem);
    player.seek(peak?item.peak_ms:item.start_ms,true,item.end_ms);
    $('context-clips-playing').textContent=`${item.title} · ${peak?'핵심 ':''}${timecode(peak?item.peak_ms:item.start_ms)} ~ ${timecode(item.end_ms)}`;
  }
  function evidence(card,label,rows){
    if(!rows.length)return;
    card.append(node('h4',label));
    for(const r of rows)card.append(node('p',`${timecode(r.start_ms)} · ${r.text}`));
  }
  function render(result){
    const box=$('context-clips-result'),scroll=box.scrollTop;
    const opened=new Set([...box.querySelectorAll('details[open]')].map(d=>d.parentElement.dataset.key));box.replaceChildren();
    const local=result.origin==='local';
    status(`${local?'Gemma · '+(result.complete?'전체 처리 완료':'일부 처리'):(result.complete?'전체 묶음 가져오기 완료':'일부 묶음만 가져옴')} · 후보 ${result.items.length}개 · 처리 발언 ${result.done}/${result.total}개${result.stale?' · 입력이 변경된 이전 결과입니다. 새로 생성하거나 자료를 내보내세요.':''}`);
    for(const note of result.notes||[])box.append(node('p',note,'hint'));
    skippedChatEvidence(box,result);
    if(!result.items.length)box.append(node('p',result.complete?'검토한 자료에서 추천 후보가 없습니다.':local?'아직 검토가 완료된 후보가 없습니다. 진행 상태와 실패 내역을 확인하세요.':'가져온 묶음에는 추천 후보가 없습니다. 나머지 결과를 추가할 수 있습니다.'));
    for(const row of result.failure_ranges||[]){const card=node('article','','clip-item');card.append(node('h4',`${timecode(row.start_ms)} ~ ${timecode(row.end_ms)} · 클립 처리 실패`,'context-failed'),node('p',row.error),node('p','같은 범위의 완료 후보는 보존됩니다. 이어하기로 실패 항목을 재검토할 수 있습니다.','hint'));box.append(card);}
    for(const item of browser.slice(result.items)){
      const i=result.items.indexOf(item);
      const card=node('article','','clip-item');card.dataset.key=String(item.start_ms)+':'+item.title;card.classList.toggle('selected',card.dataset.key===selectedItem);
      const check=checkbox(item);if(check)card.append(check);
      card.append(node('p',`${timecode(item.start_ms)} ~ ${timecode(item.end_ms)}`,'hint'),node('h3',`${i+1}. ${item.title}`));
      const actions=node('div','','play-actions'),start=node('button','이 구간 재생','secondary'),peak=node('button',`핵심 ${timecode(item.peak_ms)}로 이동`,'subtle');
      start.onclick=()=>play(item);peak.onclick=()=>play(item,true);actions.append(start,peak);card.append(actions);
      card.append(node('p',item.summary),node('h4','추천 이유'),node('p',item.reason));
      clipEvidence(card,item,at=>{
        if(project?.tasks?.video?.state!=='complete'){status('저장한 영상이 준비된 뒤 재생할 수 있습니다.');return;}
        // 구간 밖의 늦은 반응도 이동 가능하도록 현재 클립의 종료 제한을 해제한다.
        player.clearRange();player.seek(at,true);
        $('context-clips-playing').textContent=`${item.title} · 채팅 반응 ${timecode(at)}`;
      });
      const refs=node('details','');refs.open=opened.has(card.dataset.key);refs.append(node('summary','영상 확인 사항·대사·채팅 근거'));
      if(item.context_note)refs.append(node('h4','알아두면 좋은 맥락'),node('p',item.context_note));
      refs.append(node('h4','영상 확인 사항'));const checks=node('ul','');
      for(const check of item.video_checks)checks.append(node('li',check));refs.append(checks);
      if(item.review_needed)card.append(node('p','불확실한 내용 · 원음과 장면 확인 필요','clip-review'));
      for(const text of item.uncertainties)refs.append(node('p',text,'clip-review'));
      if(item.chat_summary)card.append(node('h4','관측된 채팅 반응'),node('p',item.chat_summary));

      lazyDetails(refs,()=>{evidence(refs,'대사 근거',item.evidence);evidence(refs,'채팅 근거',item.chat_evidence);});card.append(refs);box.append(card);
    }
    box.scrollTop=scroll;
  }
  async function openRun(id,refresh=false){
    if(!project||!runs().some(r=>r.id===id))return;
    const request=++serial,path=project.path;current=id;versions();
    if(!refresh){browser.reset();selectedItem=null;renderedKey='';lastResult=null;onResult(null);player?.clearRange();$('context-clips-playing').textContent='후보의 구간 또는 핵심 시각을 눌러 확인하세요.';$('context-clips-result').replaceChildren();status('클립 후보를 불러오는 중…');}
    try{
      const result=await api('context-result',{root:project.root,vod_id:project.vod_id,run:id});
      if(request!==serial||project?.path!==path)return;
      if(result?.mode!=='clips')throw Error('클립 후보 결과가 아닙니다.');
      lastResult=result;onResult(result);
      const key=JSON.stringify(result);if(key!==renderedKey){render(result);renderedKey=key;}
    }catch(e){if(request===serial&&project?.path===path)status(e.message);}
  }
  $('context-clips-version').onchange=()=>openRun($('context-clips-version').value);
  $('context-clips-refresh').onclick=()=>openRun(current);
  return {openRun,redraw(){onResult(lastResult);if(lastResult)render(lastResult);},setProject(value){
    const changed=project?.path!==value?.path,previous=project?.context?.clip_run;project=value;
    if(changed){serial++;current=null;catalogKey='';renderedKey='';lastResult=null;onResult(null);$('context-clips-result').replaceChildren();$('context-clips-playing').textContent='후보의 구간 또는 핵심 시각을 눌러 확인하세요.';}
    const state=project?.context,localTask=state?.action?.startsWith('clips');
    const key=JSON.stringify([project?.path,runs(),state?.clip_run,localTask?state.updated_at:null]);
    if(key===catalogKey)return;catalogKey=key;
    if(changed||previous!==project?.context?.clip_run||!runs().some(r=>r.id===current)){
      current=runs().find(r=>r.id===project?.context?.clip_run)?.id||runs().at(-1)?.id||null;
      if(current)openRun(current);
      else{serial++;lastResult=null;renderedKey='';onResult(null);$('context-clips-result').replaceChildren();versions();status('Gemma로 생성하거나 외부 AI 결과를 가져오면 여기에 표시됩니다.');}
    }else{versions();if(localTask&&current===state.clip_run)openRun(current,true);}
  }};
}
