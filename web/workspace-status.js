import {timecode} from './player.js';
import {vodDuration} from './vod-label.js';
import {elapsedText} from './task-timing.js';
const $ = id => document.getElementById(id);
const active = new Set(['queued','running','downloading','verifying','exporting','stopping']);
const needsReview = new Set(['error','review','paused']);
const modes = {whole:'상세 문맥',timestamps:'타임스탬프',clips:'클립 후보',model:'모델 준비'};

// 화면의 작업 상태만 반영한다. 옵션·결과 선택·데이터 파일에는 쓰지 않는다.
export function createWorkspaceStatus(layout) {
  let project = null, path = null, page = 1, queue = null;
  const rows = new Map();
  const setText = (id, text) => { if ($(id).textContent !== text) $(id).textContent = text; };
  function readiness() {
    const speech = project?.speech, model = $('speech-model').dataset;
    setText('speech-readiness', !project ? '' : `${speech?.raw_audio || speech?.audio ? '원음 준비됨' : '원음 추출 필요'} · ${model.ready === 'true' && model.engine === 'true' ? '전사 모델 준비됨' : $('speech-model').textContent || '전사 모델 확인 중'}${speech?.run ? '' : ' · 아직 저장된 전사가 없습니다. 새 전사에서 시작하세요.'}`);
    setText('voices-readiness', !project ? '' : `${$('voices-model').textContent || '화자 모델 확인 중'}${project.voices?.run ? '' : ' · 선택 기능입니다. 새 화자 분석에서 준비하세요.'}`);
    const context = project?.context?.model;
    const text = !project ? '' : `Gemma 4 E4B · ${context?.ready && context?.engine ? '준비됨' : '모델·엔진 준비 필요 · 새 분석에서 준비하세요'}${project.context?.inputs?.transcripts?.some(r => r.complete) ? '' : ' · 완료된 전사가 필요합니다.'}`;
    setText('context-readiness', text); setText('clips-readiness', text);
  }
  function jobs() {
    const descriptors = [
      ['video','영상',2,'video-stop',project?.tasks?.video], ['chat','채팅',2,'chat-stop',project?.tasks?.chat],
      ['speech','음성 전사',3,'speech-stop',project?.speech], ['voices','화자 구분',4,'voices-stop',project?.voices],
      ['context','AI 문맥',6,'context-stop',project?.context],
    ];
    const shown = new Set();
    for (const [key, name, step, stopId, state] of descriptors) {
      if (!state || !(active.has(state.state) || needsReview.has(state.state)) || step === page) continue;
      shown.add(key);
      if (!rows.has(key)) {
        const row = document.createElement('div'); row.className = 'global-job-row';
        const text = document.createElement('span'), open = document.createElement('button'), stop = document.createElement('button');
        open.className = stop.className = 'subtle'; open.textContent = '작업 열기'; stop.textContent = '중단';
        open.onclick = () => $('step'+step).click(); stop.onclick = () => $(stopId).click(); row.append(text, open, stop);
        rows.set(key, row); $('global-job-rows').append(row);
      }
      const row = rows.get(key), [text, , stop] = row.children;
      text.textContent = `${name} · ${state.message || state.state} · ${elapsedText(state)}`;
      row.classList.toggle('needs-review', needsReview.has(state.state)); stop.disabled = $(stopId).disabled; stop.hidden = !active.has(state.state);
    }
    for (const [key, row] of rows) if (!shown.has(key)) {row.remove(); rows.delete(key);}
    const queueText = $('queue-status').textContent;
    const queueActive = !!(project && queue?.active && queue.items?.some(item => item.state === 'running' && (item.project_root||queue.root) === project.root && String(item.vod) === String(project.vod_id)));
    setText('global-queue-state', queueActive ? '보관함 순차 작업 · '+queueText : '');
    $('global-queue-state').hidden = !queueActive || page === 1;
    $('global-queue-state').nextElementSibling.hidden = $('global-queue-state').hidden;
    $('global-jobs').hidden = !shown.size && $('global-queue-state').hidden;
  }
  function update(value = project) {
    const changed = path !== value?.path, previous = project; project = value;
    if (changed) {layout.closeMore?.(); path = value?.path; layout.panels.forEach(panel => panel.reset());}
    for (const [key, panels] of [['context',[layout.contextSettings, layout.clipSettings]], ['speech',[layout.speechSettings]], ['voices',[layout.voiceSettings]]]) {
      const state = value?.[key];
      if (state?.owned && !previous?.[key]?.owned) panels.forEach(panel => {panel.accepted(); panel.close();});
    }
    for (const picker of layout.versions) picker.update();
    for (const id of ['context-resume','context-clips-resume']) $(id).hidden = $(id).disabled;
    readiness();
    for (const [id, state] of [['context-job',value?.context],['clips-job',value?.context],['speech-job',value?.speech],['voices-job',value?.voices]]) {
      $(id).classList.toggle('needs-review', needsReview.has(state?.state));
      // 완료 상태도 보이되 빈 작업의 큰 진행 게이지는 생략한다.
      const idle = !state?.action && (!state?.state || state.state === 'idle');
      $(id).dataset.idle = String(idle);
      $(id).hidden = idle && id !== 'context-job';
    }
    $('download-details').hidden = !value || page !== 2;
    document.querySelector('.queue-section').hidden = page !== 1;
    $('project-assets').hidden = !value;
    $('step2').hidden = true;
    $('download-panel').hidden = !value;
    $('lock-note').hidden = !value?.locked && !value?.analysis_running;
    setText('workspace-subtitle', page === 9 ? '보관함·모델 폴더와 처리 장치를 관리하세요.' : page === 1 ? '보관함 전체 · 주소를 등록하고 순서대로 작업하세요.' : value ? `${value.metadata.title} (${timecode(Math.round((vodDuration(value) ?? 0)*1000))})` : '저장한 VOD를 선택하세요.');
    const state = value?.context;
    const tab=document.querySelector('#context-panel [role=tab][aria-selected=true]')?.id?.replace('context-tab-','')||'detail';
    const jobMode=state?.action?.startsWith('clips')?'clips':state?.action?.startsWith('timestamps')?'timestamps':'detail';
    for(const [id,selected] of [['context-job-history',$('context-version').value],['clips-job-history',$('context-clips-version').value]]){
      const details=$(id);if(!details)continue;
      const ownId=jobMode==='clips'?state?.clip_run:jobMode==='detail'?state?.full_run:state?.run;
      const matching=jobMode===tab&&ownId===selected;
      const automatic=!!state?.owned||matching;
      if(details.dataset.automatic!==String(automatic)){details.open=automatic;details.dataset.automatic=String(automatic);}
      details.querySelector('summary').textContent=matching?'선택 결과의 작업 진행·기록':state?.owned?'다른 결과의 실행 중인 작업':'다른 결과의 이전 작업 상태';
    }
    if (state?.action) $('context-job').dataset.mode = modes[state.action.replace('-resume','')] || 'AI 문맥';
    jobs();
  }
  new MutationObserver(readiness).observe($('speech-model'), {childList:true,characterData:true,subtree:true});
  new MutationObserver(readiness).observe($('voices-model'), {childList:true,characterData:true,subtree:true});

  return {update, setQueue(value) {queue = value; jobs();}, navigate(step) {layout.closeMore?.();layout.panels.forEach(panel => panel.close()); page = step; update();}};
}
