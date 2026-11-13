import {resultBrowser,lazyDetails} from './result-browser.js';
import {contextKey} from './context-comment-model.js';
import {timecode} from './player.js';
import {clipEvidence,skippedChatEvidence} from './context-clip-evidence.js';
import {createCandidateReview} from './context-review.js';
import {resultPlayback} from './result-playback.js';
import {bindSceneDetails,syncSceneDrawer} from './result-flow.js';
const $=id=>document.getElementById(id);
const node=(tag,text,className='')=>{const el=document.createElement(tag);el.textContent=text;el.className=className;return el;};

// 클립 탭은 상세 문맥·타임스탬프와 결과 선택 상태를 따로 보관한다.
export function createClipResults({api,player,basket=null,onResult=()=>{},checkbox=()=>null}){
  let selectedItem=null;
  let project=null,current=null,serial=0,catalogKey='',renderedKey='',lastResult=null;
  const projectVersions=new Map();
  const browser=resultBrowser($('context-clips-result'),()=>{if(lastResult)render(lastResult);},{keyOf:contextKey});
  const review=createCandidateReview({api,host:$('context-clips-result'),onChange:reset=>{if(reset)browser.first();if(lastResult)render(lastResult);}});
  if(basket){const accepted=node('button','채택 담기','secondary');accepted.type='button';accepted.title='채택한 후보를 모두 클립에 담기';accepted.onclick=()=>{if(lastResult)basket.add(lastResult,current,lastResult.items.map((item,index)=>review.state(item)==='accepted'?index:-1).filter(index=>index>=0));};review.addAction(accepted);}
  const playback=resultPlayback({host:$('context-clips-result'),bar:browser.bar,media:$('player'),visible:()=>!$('context-panel').hidden&&!$('context-clips-panel').hidden,followPage:at=>browser.follow(at)});
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
    const box=$('context-clips-result'),guidance=$('context-clips-guidance'),scroll=box.scrollTop;
    const focusedReview=document.activeElement?.dataset?.reviewKey;
    const focusedMemo=document.activeElement?.dataset?.reviewMemo,caret=[document.activeElement?.selectionStart,document.activeElement?.selectionEnd];
    const notesOpen=guidance.querySelector?.('.candidate-result-notes')?.open||false;guidance.replaceChildren();
    const opened=new Set([...box.querySelectorAll('details.clip-evidence[open]')].map(d=>d.parentElement.dataset.key));box.replaceChildren();
    const local=result.origin==='local';
    status(`${local?'Gemma · '+(result.complete?'전체 처리 완료':'일부 처리'):(result.complete?'전체 묶음 가져오기 완료':'일부 묶음만 가져옴')} · 후보 ${result.items.length}개 · 처리 발언 ${result.done}/${result.total}개${result.stale?' · 입력이 변경된 이전 결과입니다. 새로 생성하거나 자료를 내보내세요.':''}`);
    const unanchored=result.chat_discovery?.unanchored?.length||0;
    if(result.notes?.length||unanchored){
      const notes=node('details','','candidate-result-notes');notes.open=notesOpen;
      notes.append(node('summary',`결과 안내${unanchored?' · 보류 채팅 '+unanchored+'구간':''}`));
      for(const note of result.notes||[])notes.append(node('p',note,'hint'));
      skippedChatEvidence(notes,result);guidance.append(notes);
    }
    if(!result.items.length)box.append(node('p',result.complete?'검토한 자료에서 추천 후보가 없습니다.':local?'아직 검토가 완료된 후보가 없습니다. 진행 상태와 실패 내역을 확인하세요.':'가져온 묶음에는 추천 후보가 없습니다. 나머지 결과를 추가할 수 있습니다.'));
    if(result.failure_ranges?.length){const failures=node('details','','candidate-failures');failures.append(node('summary',`처리 오류 ${result.failure_ranges.length}구간 · 완료된 후보는 아래에서 확인`));
      for(const row of result.failure_ranges){const card=node('div','','result-error');card.append(node('h4',`${timecode(row.start_ms)} ~ ${timecode(row.end_ms)} · 처리 오류`),node('p',row.error),node('p','완료 후보는 보존됩니다. 이어하기로 실패 항목을 재검토할 수 있습니다.','hint'));failures.append(card);}guidance.append(failures);}
    const visible=browser.slice(review.filtered());
    if(result.items.length&&!visible.length)box.append(node('p','이 검토 상태와 검색 조건에 맞는 후보가 없습니다.','empty'));
    for(const item of visible){
      const i=result.items.indexOf(item);
      const card=node('article','','clip-item');card.dataset.key=String(item.start_ms)+':'+item.title;card.classList.toggle('selected',card.dataset.key===selectedItem);
      card.dataset.start=item.start_ms;card.dataset.end=item.end_ms;card.dataset.review=review.state(item);
      const check=checkbox(item,i,result,current);if(check)card.append(check);
      const scene=node('button','','scene-copy');scene.type='button';scene.disabled=project?.tasks?.video?.state!=='complete';scene.onclick=()=>play(item);
      scene.append(node('time',`${timecode(item.start_ms)} ~ ${timecode(item.end_ms)}`,'scene-time'),node('h3',`${i+1}. ${item.title}`),node('p',item.summary,'scene-summary'));card.append(scene);
      const actions=node('div','','play-actions'),start=node('button','이 구간 재생','secondary'),peak=node('button',`핵심 ${timecode(item.peak_ms)}로 이동`,'subtle');
      start.onclick=()=>play(item);peak.onclick=()=>play(item,true);actions.append(start,peak);
      const refs=node('details','','clip-evidence scene-details');refs.open=opened.has(card.dataset.key);refs.append(node('summary','추천 이유·채팅·영상 확인'),review.control(item),node('h4','추천 이유'),node('p',item.reason));
      clipEvidence(refs,item,at=>{
        if(project?.tasks?.video?.state!=='complete'){status('저장한 영상이 준비된 뒤 재생할 수 있습니다.');return;}
        // 구간 밖의 늦은 반응도 이동 가능하도록 현재 클립의 종료 제한을 해제한다.
        player.clearRange();player.seek(at,true);
        $('context-clips-playing').textContent=`${item.title} · 채팅 반응 ${timecode(at)}`;
      });
      refs.append(review.memo(item));
      refs.append(node('h4','장면 요약'),node('p',item.summary));
      if(item.context_note)refs.append(node('h4','알아두면 좋은 맥락'),node('p',item.context_note));
      refs.append(node('h4','영상 확인 사항'));const checks=node('ul','');
      for(const check of item.video_checks)checks.append(node('li',check));refs.append(checks);
      if(item.review_needed){refs.append(node('p','원문 확인 필요','result-source-review'));refs.append(node('p','후보 생성은 완료됐지만 내용의 확인이 필요합니다.','hint'));}
      for(const text of item.uncertainties)refs.append(node('p',text,'clip-review'));
      if(item.chat_summary)refs.append(node('h4','관측된 채팅 반응'),node('p',item.chat_summary));

      lazyDetails(refs,()=>{evidence(refs,'대사 근거',item.evidence);evidence(refs,'채팅 근거',item.chat_evidence);});
      refs.append(actions);bindSceneDetails(card,refs,{title:item.title,subtitle:`${timecode(item.start_ms)} ~ ${timecode(item.end_ms)}`,key:JSON.stringify([project.path,current,card.dataset.key])});box.append(card);
    }
    box.scrollTop=scroll;playback.refresh();syncSceneDrawer();
    if(focusedReview)[...box.querySelectorAll('select[data-review-key]')].find(el=>el.dataset.reviewKey===focusedReview)?.focus({preventScroll:true});
    if(focusedMemo){const field=[...box.querySelectorAll('textarea[data-review-memo]')].find(el=>el.dataset.reviewMemo===focusedMemo);field?.focus({preventScroll:true});if(field&&Number.isInteger(caret[0]))field.setSelectionRange(...caret);}
  }
  async function openRun(id,refresh=false){
    if(!project||!runs().some(r=>r.id===id))return;
    const request=++serial,path=project.path;current=id;projectVersions.set(path,id);versions();
    if(!refresh){browser.setScope(JSON.stringify([path,id]));selectedItem=null;renderedKey='';lastResult=null;review.reset();onResult(null);player?.clearRange();$('context-clips-playing').textContent='';$('context-clips-playing').title='후보를 누르면 해당 구간을 재생합니다.';$('context-clips-result').replaceChildren();$('context-clips-guidance').replaceChildren();status('클립 후보를 불러오는 중…');}
    try{
      const result=await api('context-result',{root:project.root,vod_id:project.vod_id,run:id});
      if(request!==serial||project?.path!==path)return;
      if(result?.mode!=='clips')throw Error('클립 후보 결과가 아닙니다.');
      lastResult=result;review.setSource(project,id,result.items);onResult(result);
      const key=JSON.stringify(result);if(key!==renderedKey){render(result);renderedKey=key;}
    }catch(e){if(request===serial&&project?.path===path)status(e.message);}
  }
  $('context-clips-version').onchange=()=>openRun($('context-clips-version').value);
  $('context-clips-refresh').onclick=()=>openRun(current,true);
  return {openRun,redraw(){onResult(lastResult);if(lastResult)render(lastResult);},setProject(value){
    const changed=project?.path!==value?.path;project=value;
    if(changed){serial++;current=null;catalogKey='';renderedKey='';lastResult=null;review.reset();playback.reset();onResult(null);$('context-clips-result').replaceChildren();$('context-clips-guidance').replaceChildren();$('context-clips-playing').textContent='';$('context-clips-playing').title='후보를 누르면 해당 구간을 재생합니다.';}
    const state=project?.context,localTask=state?.action?.startsWith('clips');
    const key=JSON.stringify([project?.path,runs(),state?.clip_run,localTask?state.updated_at:null]);
    if(key===catalogKey)return;catalogKey=key;
    if(changed||!runs().some(r=>r.id===current)){
      current=runs().find(r=>r.id===projectVersions.get(project?.path))?.id||runs().find(r=>r.id===project?.context?.clip_run)?.id||runs().at(-1)?.id||null;
      if(current)openRun(current);
      else{serial++;lastResult=null;renderedKey='';onResult(null);$('context-clips-result').replaceChildren();$('context-clips-guidance').replaceChildren();versions();status('Gemma로 생성하거나 외부 AI 결과를 가져오면 여기에 표시됩니다.');}
    }else{versions();if(localTask&&current===state.clip_run)openRun(current,true);}
  }};
}
