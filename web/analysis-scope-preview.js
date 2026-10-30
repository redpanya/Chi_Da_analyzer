import {pagePolling} from './page-lifecycle.js';
import {createSettingsPanel} from './settings-panel.js';
import {commentTimeText} from './context-comment-model.js';
import {editRange} from './clip-studio-model.js';
import {timecode} from './player.js';
const el=(tag,text='')=>{const e=document.createElement(tag);e.textContent=text;return e;};
export function createAnalysisScopePreview({api,onOpen}){
  const $=id=>document.getElementById(id),fields=$('analysis-scope-fields'),open=$('analysis-scope-open');
  const action=el('button','선택 범위로 처리 시작');action.className='primary';
  const panel=createSettingsPanel('analysis-scope-settings','가져오기 다음 · 분석 범위 설정',[fields],[action]);
  fields.hidden=false;panel.note.textContent='원본은 유지하고 범위별 독립 프로젝트로 처리합니다. 새 전사를 선택하면 범위 원음도 준비합니다. 모델은 기존 설정을 사용합니다.';
  open.setAttribute('aria-haspopup','dialog');open.setAttribute('aria-controls',panel.dialog.id);
  let project=null,origin=0,duration=0,catalog=[],loading=0,running=false,refreshing=false;
  const identity=()=>({root:project.root,vod_id:project.vod_id});
  function request(){
    const partial=fields.querySelector('[name=analysis-scope-mode]:checked').value==='range';
    const range=partial?editRange($('analysis-scope-start').value,$('analysis-scope-end').value,origin,duration):{start_ms:origin,end_ms:origin+duration};
    const mapping={audio:'audio',speech:'transcribe',voices:'diarize',context:'context'};
    const stages=[...fields.querySelectorAll('#analysis-scope-stages input:checked')].map(i=>mapping[i.value]);
    if(!stages.length&&!$('scope-remote').checked)throw Error('진행할 작업을 1개 이상 선택하세요.');
    const modes=[...fields.querySelectorAll('[name=scope-ai-mode]:checked')].map(i=>i.value);
    if(stages.includes('context')&&!modes.length)throw Error('AI 모드를 1개 이상 선택하세요.');
    const id=$('scope-transcript').value;
    return {...range,settings:{steps:stages,summary_modes:modes,backend:$('scope-backend').value,thinking:$('scope-thinking').checked,allow_partial_chat:$('scope-partial-chat').checked,height:Number($('scope-quality').value)},
      selection:id?{transcript_run:id,speaker_run:$('scope-speaker').value||null}:null};
  }
  function render(clearError=true){
    const partial=fields.querySelector('[name=analysis-scope-mode]:checked').value==='range',remote=$('scope-remote').checked;
    $('analysis-scope-range').hidden=!partial;$('scope-quality-label').hidden=!remote;$('scope-transcript').disabled=remote;
    if(clearError)$('analysis-scope-error').textContent='';action.disabled=running||!project;
    try{const r=request();$('analysis-scope-summary').textContent=`${partial?'선택 구간':'전체 영상'} ${timecode(r.end_ms-r.start_ms)} · ${r.settings.steps.length}개 작업 · 별도 결과 보관`;
      if(remote&&r.selection)throw Error('서버 구간 다운로드에서는 기존 전사 재사용을 해제하세요.');
      if(!remote&&project?.tasks?.video?.state!=='complete')throw Error('저장 영상이 없으면 서버에서 구간만 받기를 선택하세요.');
    }catch(error){$('analysis-scope-error').textContent=error.message;action.disabled=true;}
  }
  function speakers(){const choices=catalog.filter(r=>r.transcript_run===$('scope-transcript').value);$('scope-speaker').replaceChildren(new Option('화자 배정 사용 안 함',''),...choices.map(r=>new Option(r.label,r.id)));}
  $('scope-transcript').onchange=speakers;
  for(const control of fields.querySelectorAll('input,select'))control.addEventListener('input',render);
  function error(e){$('analysis-scope-error').textContent=e.message;}
  async function refresh(){
    if(refreshing||!project||!panel.dialog.open)return;refreshing=true;const selected=project.path;
    try{const result=await api('studio-status',identity());if(project?.path!==selected)return;
      running=result.runs.some(r=>r.state==='running');const list=$('scope-history');list.replaceChildren();
      for(const r of result.runs.filter(r=>r.kind!=='start')){
        const title=(r.kind==='remote'?'서버 구간 받기':'범위 분석')+(r.range_ms?' · '+r.range_ms.map(timecode).join(' ~ '):'');
        const card=el('article');card.append(el('strong',title),el('p',new Date(r.created_at).toLocaleString('ko-KR')),el('p',r.message||r.state),el('p','소요 시간 '+timecode((r.elapsed_seconds||0)*1000)));
        const bar=el('progress');bar.max=1;if(r.state==='complete'||r.progress>0)bar.value=r.progress||1;card.append(bar);
        if(r.project){const b=el('button','이 범위 결과 열기');b.onclick=()=>{panel.close();onOpen(r.project.root,r.project.vod_id);};card.append(b);}
        if(r.state==='running'){const b=el('button','중단');b.onclick=()=>api('studio-stop',identity()).then(refresh).catch(error);card.append(b);}
        else if(r.state!=='complete'){const b=el('button','완료 자료에서 이어하기');b.onclick=()=>api('studio-resume',{...identity(),run:r.id}).then(refresh).catch(error);card.append(b);}
        list.append(card);
      }
      render(false);
    }catch(e){error(e);}finally{refreshing=false;}
  }
  open.onclick=async()=>{
    if(!project||open.disabled)return;render();panel.open(open);const token=++loading;
    try{const info=await api('studio-info',identity());if(token!==loading)return;
      const previous=$('scope-transcript').value;catalog=info.inputs.speakers;
      $('scope-transcript').replaceChildren(new Option('새 전사 또는 이미 생성한 범위 전사 사용',''),...info.inputs.transcripts.filter(r=>r.complete).map(r=>new Option(r.label,r.id)));
      if([...$('scope-transcript').options].some(o=>o.value===previous))$('scope-transcript').value=previous;
      speakers();await refresh();
    }catch(e){error(e);}
  };
  action.onclick=async()=>{try{action.disabled=true;await api($('scope-remote').checked?'studio-remote':'studio-scope',{...identity(),request:request()});await refresh();}catch(e){error(e);action.disabled=false;}};
  $('scope-help').onclick=()=>{
    const box=el('div');box.append(el('h3','원본 VOD와 별개의 분석 범위'));
    for(const text of ['범위를 정하면 그 구간의 영상과 저장 채팅을 별도 폴더로 준비합니다. 전체 범위는 같은 디스크에서 원본을 참조하므로 추가 영상 용량을 줄입니다. 기존 전사·수동 교정·화자 배정은 선택한 버전에서 복사하며 부모 결과는 바꾸지 않습니다.','새 전사는 원음 추출을 함께 진행합니다. 새 전사를 끄고 기존 전사를 선택하면 그 범위의 발언만 재사용합니다. AI 모드는 여러 개 선택할 수 있습니다.','서버에서 구간만 받기는 공개 VOD를 선택 범위만 새 파일로 받습니다. 실제 수신량은 서버와 키프레임에 따라 더 클 수 있습니다. 채팅은 이미 저장한 자료 중 해당 범위만 복사하며, 없으면 채팅 없이 분석합니다.','모델·도구가 준비되지 않은 단계는 오류로 남습니다. 도구 준비 후 이어하기를 누르면 완료 단계를 재사용합니다. 범위 결과의 미디어 시각은 해당 구간의 시작부터 계산하고 원본 VOD 시작 시각도 보존합니다.'])box.append(el('p',text));
    panel.dialog.dispatchEvent(new CustomEvent('settings-help',{detail:box}));
  };
  pagePolling(refresh,2000);
  return {setProject(value){
    const changed=project?.path!==value?.path;project=value;
    origin=Number(value?.input?.start_vod_ms)||0;duration=Math.round((value?.tasks?.video?.verification?.duration||value?.metadata?.duration||0)*1000);
    open.disabled=!project||duration<=0;
    if(changed){loading++;panel.reset();fields.querySelector('[name=analysis-scope-mode][value=full]').checked=true;$('analysis-scope-start').value=commentTimeText(origin);$('analysis-scope-end').value=commentTimeText(origin+duration);$('scope-remote').checked=!!value&&value.tasks?.video?.state!=='complete';$('scope-transcript').replaceChildren(new Option('새 전사 또는 이미 생성한 범위 전사 사용',''));running=false;}
    if(open.disabled&&panel.dialog.open)panel.close();$('scope-project-title').textContent=value?.metadata?.title||'';
    $('analysis-scope-bounds').textContent=duration?`원본 VOD 범위 ${commentTimeText(origin)} ~ ${commentTimeText(origin+duration)}`:'영상 길이를 확인할 수 없습니다.';
    if(!panel.dialog.open)render();
  }};
}
