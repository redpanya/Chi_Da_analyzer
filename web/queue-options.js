import {parseTime,timecode} from './player.js';
const names={download:'영상·채팅 다운로드',audio:'원음 오디오 추출',transcribe:'전사 진행',diarize:'화자 구분',context:'AI 문맥'};
const modes={timestamps:'빠른 타임스탬프',detail:'상세 문맥 정리',clips:'클립 후보'};

export function selectedSteps(options){
  return options.steps??(options.mode==='analysis'?['download','audio','transcribe',...(options.speakers_enabled?['diarize']:[]),'context']:['download']);
}
export function selectionLabel(options){
  return selectedSteps(options).map(step=>step==='context'?`AI 문맥 (${(options.summary_modes??['detail']).map(mode=>modes[mode]).join(' · ')||'모드 선택 필요'})`:step==='download'&&options.download_range?`${names[step]} (${timecode(options.download_range.start_ms)} ~ ${timecode(options.download_range.end_ms)})`:names[step]).join(' → ')||'진행할 단계를 선택하세요';
}
export function createQueueOptions($){
  const checked=id=>[...$(id).querySelectorAll('input:checked')].map(input=>input.value);
  function scope(steps){
    if(!steps.includes('download')||$('queue-download-scope').value!=='range')return null;
    const start_ms=parseTime($('queue-range-start').value.trim()),end_ms=parseTime($('queue-range-end').value.trim());
    if(end_ms-start_ms<1000||end_ms-start_ms>20*3600000)throw Error('다운로드 구간은 시작보다 끝이 늦어야 하며 1초 이상, 최대 20시간입니다');
    return {start_ms,end_ms};
  }
  function read(){
    const steps=checked('queue-steps'),summary_modes=checked('queue-summary-modes');
    if(!steps.length)throw Error('진행할 단계를 하나 이상 선택하세요');
    if(steps.includes('context')&&!summary_modes.length)throw Error('AI 문맥 모드를 하나 이상 선택하세요');
    return {steps,summary_modes,download_range:scope(steps),height:Number($('queue-height').value),language:$('queue-language').value,
      asr_options:{vad:$('queue-vad').value,prompt:$('queue-prompt').value},backend:$('queue-backend').value,
      thinking:$('queue-thinking').checked,allow_partial_chat:$('queue-partial-chat').checked,continue_voice_error:$('queue-continue-voice').checked};
  }
  function refresh(){
    const steps=checked('queue-steps'),has=step=>steps.includes(step);
    for(const [id,visible] of [['download',has('download')],['transcribe',has('transcribe')],['voice',has('diarize')],['ai',has('context')],['chat',has('download')||has('context')]])$('queue-'+id+'-options').hidden=!visible;
    // 비활성 세부 값도 유지해 단계 재선택·변경 취소 때 같은 설정으로 돌아온다.
    $('queue-download-range').hidden=$('queue-download-scope').value!=='range';
    try{$('queue-selection-summary').textContent=selectionLabel({steps,summary_modes:checked('queue-summary-modes'),download_range:scope(steps)});}
    catch{$('queue-selection-summary').textContent=selectionLabel({steps,summary_modes:checked('queue-summary-modes')})+' · 다운로드 시각 확인 필요';}
  }
  for(const id of ['queue-steps','queue-summary-modes'])for(const input of $(id).querySelectorAll('input'))input.addEventListener('change',refresh);
  for(const id of ['queue-download-scope','queue-range-start','queue-range-end'])$(id).addEventListener('input',refresh);
  refresh();return {read};
}
