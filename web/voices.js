import {createVoiceTabs} from './voice-tabs.js';
import {timecode} from './player.js';
import {createAudioPreview} from './audio-preview.js';
import {createVoiceReview} from './voice-review.js';
import {createVoiceSuggestions} from './voice-suggestions.js';
import {voiceModelHelp} from './voice-model-help.js';
import {voiceToolStatus} from './voice-tool-status.js';

export function createVoices({api, player, showVideo, showExplore, onProject}) {
  const $ = id => document.getElementById(id);
  let project=null, result=null, generation=0, requestGeneration=0, key='', cursor=0, busy=false, playingStem=null;
  const backend=()=>$('voices-backend').value||'sherpa';
  const diarizationInfo=()=>result?.diarization_models?.[backend()]||result?.model;
  const selected=()=>({root:project.root,vod_id:project.vod_id});
  const notice=text=>{$('voices-notice').textContent=text;};
  const previewAudio=$('voice-preview');
  let previewStatus=$('voice-preview-status');
  const preview=createAudioPreview(previewAudio,text=>{previewStatus.textContent=text;});
  const suggestions=createVoiceSuggestions({listen,jump,start:(action,options)=>start(action,options),edit:(action,options)=>edit(action,options)});
  const failedReview=createVoiceReview({listen,search:()=>load(),jump,suggest:row=>suggestions.choose(row),
    save:(selection,target,snapshot)=>edit(target==='__new__'?'split':'assign',
      {...snapshot,...selection,...(target==='__new__'?{}:{speaker:target})})});
  const tabs=createVoiceTabs();
  let previewKey='',setupKey='';
  function stopPreview(text='미리듣기를 멈췄습니다.'){preview.stop();previewStatus.textContent=text;}
  function listen(speaker,status=$('voice-preview-status')){
    if(project.voices.stale||project.speech.stale||!project.speech.audio)return notice('현재 전사와 연결된 추출 음성이 필요합니다.');
    stopPreview();previewStatus=status;
    for(const media of document.querySelectorAll('audio,video'))media.pause();
    const url=`file?${new URLSearchParams({...selected(),kind:'speech',key:'audio',revision:project.speech.audio.file})}`;
    preview.play(url,speaker.sample,speaker.name);
  }
  const fileURL=key=>`file?${new URLSearchParams({...selected(),kind:'voices',key,revision:project.voices.updated_at||''})}`;
  const button=(text, action, style='subtle')=>{const b=document.createElement('button');b.textContent=text;b.className=style;b.onclick=action;return b;};
  const range=prefix=>({start_ms:Math.round(Number($(prefix+'-start').value)*1000),end_ms:Math.round(Number($(prefix+'-end').value)*1000)});
  function tab(stem) {
    $('voice-review').hidden=stem; $('voice-separation').hidden=!stem;
    for(const [id,chosen] of [['voice-tab',!stem],['stem-tab',stem]]){$(id).className=chosen?'primary':'secondary';$(id).setAttribute('aria-pressed',String(chosen));}
  }
  function chooseRange(row, stem=false) {
    tab(stem);tabs.select('assigned');
    for(const prefix of ['voice']) {$(prefix+'-start').value=row.start_ms/1000;$(prefix+'-end').value=row.end_ms/1000;}
    $('voice-target').value=row.speaker||'';
  }
  function jump(ms) {for(const a of document.querySelectorAll('audio'))a.pause();showVideo();player.seek(ms);}
  function options(select, values, selectedValue) {
    const control=$(select); control.replaceChildren();
    for(const [value,text] of values){const option=document.createElement('option');option.value=value;option.textContent=text;control.append(option);}
    if(selectedValue!==undefined)control.value=selectedValue;
  }
  function controls() {
    if(!project)return;
    const s=project.voices, disabled=busy||project.locked, ready=project.speech.transcript?.complete&&!project.speech.stale;
    $('voices-title').textContent=project.metadata.title;
    $('voices-status').textContent=(s.message||'')+(s.stale?' · 현재 전사와 다른 입력입니다. 이 버전은 이전 자료로 보존됩니다.':'');
    const progress=$('voices-progress'),p=s.progress||{};
    if((s.owned||(project.locked&&s.state==='running'))&&!p.total_bytes&&!p.duration_ms)progress.removeAttribute('value');else progress.value=p.total_bytes?100*p.bytes/p.total_bytes:p.duration_ms?100*p.processed_ms/p.duration_ms:s.state==='complete'?100:0;
    $('voices-stop').disabled=busy||!s.owned||s.state==='stopping';
    const d=diarizationInfo();
    const tool=voiceToolStatus(d,s);
    $('voices-tool-install').disabled=disabled||!d||!tool.canInstall;
    $('voices-tool-check').disabled=disabled||!tool.canCheck;
    $('voices-tool-install').textContent=tool.install;
    $('voices-tool-status').textContent=tool.status;
    $('voices-prepare').disabled=disabled||!d?.engine||d?.supported===false;
    $('voices-run').disabled=disabled||!ready||!d?.ready||!d?.engine||d?.supported===false;
    $('voices-select').disabled=disabled||!s.runs?.length;
    $('voices-delete').disabled=disabled||!s.runs?.length;
    $('voices-version').disabled=disabled;
    $('stem-select').disabled=disabled||!s.stems?.length;
    $('voices-export').disabled=disabled||!result?.run||s.stale;
    for(const id of ['voice-assign','voice-split','voice-merge','voice-undo'])$(id).disabled=disabled||!result?.run||s.stale||(id==='voice-undo'&&!result?.undo);
    for(const b of document.querySelectorAll('.voice-edit'))b.disabled=disabled||!result?.run||s.stale;
    $('voice-failed-undo').disabled=disabled||!result?.run||s.stale||!result?.undo;
    failedReview.setDisabled(disabled||!result?.run||s.stale, !s.stale&&!project.speech.stale&&!!project.speech.audio);
    suggestions.setDisabled(disabled||!result?.run||s.stale);
    $('voices-backend').disabled=disabled;
    $('stem-tab').hidden=!s.stems?.length;
    $('voices-number').disabled=disabled||d?.manual_speakers===false;
  }
  function render() {
    if(!project||!result)return;
    const s=project.voices,m=diarizationInfo();
    $('voices-model').textContent=`${voiceModelHelp(backend(),m).status} · 여유 ${(m.free_bytes/1e9).toFixed(1)}GB`;
    Object.assign($('voices-model').dataset,{ready:String(!!m.ready),engine:String(!!m.engine),supported:String(m.supported!==false)});
    $('voices-backend-hint').textContent=m.hint||'기존 CPU 화자 구분';
    $('voices-install-hint').textContent='모델 경로: '+(m.path||project.model_root);
    $('voices-tool-hint').textContent=voiceToolStatus(m,s).hint;
    $('voices-resume-hint').textContent=m.resume===false?'중단 시 처음부터 재실행 · 완료 결과 보존':'30분 조각 처리 · 완료 조각부터 이어받기';
    $('voices-run').textContent=m.resume===false?'전체 화자 분석':'화자 분석·이어받기';
    const versionKey=JSON.stringify([s.versions,s.runs,s.run]);
    if($('voices-version').dataset.key!==versionKey){
      options('voices-version',s.versions?.map(r=>[r.id,r.label])||(s.runs||[]).map(id=>[id,`이전 화자 분석 · ${id.slice(0,8)}`]),s.run);
      $('voices-version').dataset.key=versionKey;
    }
    options('stem-version',(s.stems||[]).map(v=>[v.id,`${timecode(v.start_ms)}~${timecode(v.end_ms)} · ${v.profile_label || '이전 설정'} · ${v.id.slice(0,8)}`]),s.stem);
    $('voices-summary').textContent=result.run?`${result.backend_label||'기존 화자 분석'} · ${result.speakers.length}개 화자 묶음 · ${result.total_rows}개 발언 중 화자인식 실패 ${result.failed}개 · 자동 배정도 오분류 가능 · 변경 ${result.revision}회${result.speakers.length>20?' · 묶음이 많아 과분할 검토가 필요합니다. 실제 화자 수를 아는 경우 지정 후 다시 분석하세요.':''}`:'화자 분석을 완료하면 이름과 대표 발언이 표시됩니다.';
    const target=$('voice-target').value, merge=$('voice-merge-source').value;
    const speakers=result.speakers.map(s=>[s.id,`${s.name} · ${s.default}`]);
    options('voice-target',[['','화자인식 실패'],...speakers],target);options('voice-merge-source',speakers,merge||speakers[0]?.[0]);
    const drafts=new Map([...$('voice-cards').children].filter(card=>card.querySelector('input')?.dataset.dirty==='true').map(card=>[card.dataset.speaker,card.querySelector('input').value]));
    $('voice-cards').replaceChildren();
    for(const speaker of [...result.speakers].sort((a,b)=>b.count-a.count)){
      const card=document.createElement('article');card.className='voice-card';card.dataset.speaker=speaker.id;
      const title=document.createElement('h4');title.textContent=`${speaker.name} · 배정된 전사 ${speaker.count}개`;
      const hint=document.createElement('p');hint.className='hint';hint.textContent=`${speaker.default} · 감지된 음성 ${speaker.turn_count}구간${speaker.count?'':' · 전사 배정 없음'} · ID ${speaker.id.slice(-8)}`;
      const input=document.createElement('input');input.value=drafts.get(speaker.id)??(speaker.name===speaker.default?'':speaker.name);input.placeholder=speaker.default;input.maxLength=80;input.className='voice-edit';input.setAttribute('aria-label',speaker.default+' 이름');
      input.dataset.dirty=String(drafts.has(speaker.id));input.oninput=()=>{input.dataset.dirty='true';};
      card.append(title,hint,input,button('이름 일괄 저장',()=>edit('rename',{speaker:speaker.id,name:input.value}),'secondary voice-edit'));
      if(speaker.sample){const listenButton=button(speaker.sample_kind==='detected'?'감지된 음성 듣기':'대표 음성 듣기',()=>listen(speaker),'secondary');listenButton.disabled=s.stale||project.speech.stale||!project.speech.audio;listenButton.title=`원음 ${timecode(speaker.sample.start_ms)} ~ ${timecode(speaker.sample.end_ms)} · 배경음과 다른 목소리가 포함될 수 있습니다`;card.append(listenButton);}
      $('voice-cards').append(card);
    }
    $('voice-rows').replaceChildren();
    failedReview.render(result);tabs.counts(result);
    const setupNext=project.path+':'+backend()+':'+m.ready+':'+m.engine;
    if(setupNext!==setupKey){$('voices-setup').open=true;setupKey=setupNext;}
    suggestions.render(result,s);
    for(const row of result.items){
      const card=document.createElement('article');card.className='transcript-row';
      const actions=document.createElement('div');actions.className='play-actions';
      actions.append(button(`${timecode(row.start_ms)} → ${timecode(row.end_ms)} · 영상`,()=>jump(row.start_ms),'candidate-jump'),button('이 발언 범위 선택',()=>{chooseRange(row,false);$('voice-start').closest('details').open=true;$('voice-start').focus();}));
      const status=document.createElement('p');status.className='voice-status'+(row.status==='failed'?' failed':'');status.textContent=`${row.speaker_name} · ${row.status==='confirmed'?'사용자 확인':row.status==='failed'?result.reasons[row.reason]:'자동 추정 · 미확정'}`;
      const text=document.createElement('p');text.textContent=row.text;
      actions.append(button('음성 듣기',()=>listen({sample:row,name:row.speaker_name}),'secondary'));
      if(row.status!=='confirmed')actions.append(button('음향·문맥 검토 범위 선택',()=>suggestions.choose(row)));
      card.append(actions,status,text);$('voice-rows').append(card);
    }
    $('voices-count').textContent=`배정된 전사 ${result.total}개`+(result.total?` · ${Math.floor(cursor/100)+1}쪽`:'');
    $('voices-empty').textContent=result.total?'':!result.run?'화자 분석을 완료하면 배정된 전사가 표시됩니다.':$('voices-query').value?'검색 조건에 맞는 배정된 전사가 없습니다.':'아직 화자가 배정된 전사가 없습니다.';
    $('voices-prev').disabled=cursor===0;$('voices-next').disabled=result.next_cursor===null;
    $('voices-exports').replaceChildren();
    for(const k of Object.keys(s.exports||{})){const a=document.createElement('a');a.href=fileURL(k);a.textContent=k.toUpperCase()+' 저장';a.className='text-link';$('voices-exports').append(a);}
    const stem=result.stem;$('stem-result').hidden=!stem;
    if(stem){
      $('stem-info').textContent=`영상 ${timecode(stem.start_ms)}~${timecode(stem.end_ms)} · ${((stem.end_ms-stem.start_ms)/1000).toFixed(3)}초 · 플레이어 0초 = 영상 ${timecode(stem.start_ms)} · ${stem.model || '이전 분리 모델'} · ${stem.profile_label || (stem.contract?.ode === 'midpoint/16' ? '표준' : '이전 설정')} · 분리 음성은 들어서 확인하세요`;
      for(const name of ['original','vocals','background']){
        const audio=$('stem-'+name),identity=project.path+stem.id;
        if(audio.dataset.file!==identity){audio.pause();audio.src=fileURL(name);audio.dataset.file=identity;playingStem=null;}
        $('stem-save-'+name).href=fileURL(name);
      }
      $('stem-comparison').replaceChildren();
      if(stem.comparison)for(const kind of ['original','vocals']){
        const column=document.createElement('article'),heading=document.createElement('h3');heading.textContent=kind==='original'?'원음 재전사':'보컬 재전사';column.append(heading);
        for(const row of stem.comparison.segments[kind]){const p=document.createElement('p');p.append(button(timecode(row.start_ms),()=>jump(row.start_ms)),document.createTextNode(' '+row.text));column.append(p);}
        if(!stem.comparison.segments[kind].length){const p=document.createElement('p');p.textContent='인식한 문장 없음';column.append(p);}
        $('stem-comparison').append(column);
      }
    }
    controls();
  }
  async function load(reset=false){
    if(!project)return;
    if(reset)cursor=0;
    const token=generation, req=++requestGeneration, query=$('voices-query').value, review=failedReview.request();
    try{const value=await api('voices-result',{...selected(),query,cursor,...review});if(token!==generation||req!==requestGeneration||query!==$('voices-query').value||review.failed_query!==failedReview.request().failed_query||review.failed_group!==failedReview.request().failed_group)return;result=value;cursor=value.cursor??cursor;render();}
    catch(error){if(token===generation)notice(error.message);}
  }
  async function request(action,values){
    if(!project||busy)return;
    const token=generation;busy=true;notice('');controls();
    try{const fresh=await api(action,{...selected(),...values});if(token===generation){
      if(action==='voices-edit'&&values.action==='rename')for(const card of $('voice-cards').children)if(card.dataset.speaker===values.options.speaker)card.querySelector('input').dataset.dirty='false';
      onProject(fresh);await load();
    }}
    catch(error){if(token===generation){notice(error.message);await load();}}
    finally{busy=false;controls();}
  }
  const edit=(action,options={})=>request('voices-edit',{action,options:{run:result?.run,revision:result?.revision,...options}});
  const start=(action,options={})=>request('voices-start',{action,options});
  $('voice-tab').onclick=()=>tab(false); $('stem-tab').onclick=()=>tab(true);
  $('voices-backend').onchange=()=>{render();controls();};
  $('voices-tool-install').onclick=()=>start('install-engine',{backend:backend()});
  $('voices-tool-check').onclick=()=>start('check-engine',{backend:backend()});
  $('voices-prepare').onclick=()=>start('prepare',{backend:backend()});
  $('voices-run').onclick=()=>start('diarize',{backend:backend(),speakers:diarizationInfo()?.manual_speakers===false?-1:Number($('voices-number').value)||-1});
  $('voices-stop').onclick=()=>request('voices-stop',{});
  $('voices-select').onclick=()=>edit('select',{run:$('voices-version').value});
  $('voices-delete').onclick=()=>{
    const run=$('voices-version').value;
    if(!run||project?.locked||!confirm('선택한 화자 분석과 그 버전의 이름·수동 배정을 휴지통으로 이동할까요?\n영상·오디오·전사·다른 화자 분석·내보낸 파일·기존 요약은 유지됩니다.'))return;
    stopPreview();return edit('delete',{run});
  };
  $('voices-export').onclick=()=>edit('export');
  $('voice-assign').onclick=()=>edit('assign',{...range('voice'),speaker:$('voice-target').value||null,reason:$('voice-reason').value});
  $('voice-split').onclick=()=>edit('split',range('voice'));
  $('voice-merge').onclick=()=>edit('merge',{source:$('voice-merge-source').value,speaker:$('voice-target').value||null});
  $('voice-undo').onclick=()=>edit('undo');
  $('voice-failed-undo').onclick=()=>edit('undo');
  $('voices-search').onsubmit=e=>{e.preventDefault();load(true);};
  $('voices-prev').onclick=()=>{cursor=Math.max(0,cursor-100);load();};
  $('voices-next').onclick=()=>{if(result.next_cursor!==null){cursor=result.next_cursor;load();}};
  $('stem-select').onclick=()=>edit('select',{stem:$('stem-version').value});
  for(const name of ['original','vocals','background']){
    const audio=$('stem-'+name);
    audio.onplay=()=>{
      if(playingStem&&playingStem!==audio&&Number.isFinite(audio.duration))audio.currentTime=Math.min(playingStem.currentTime,audio.duration);
      for(const other of document.querySelectorAll('audio,video'))if(other!==audio)other.pause();
      playingStem=audio;
    };
    audio.onerror=()=>{if(audio.getAttribute('src'))notice('분리 음원을 읽지 못했습니다. 저장 파일을 확인하세요.');};
  }
  for(const id of ['player','speech-audio'])$(id).addEventListener('play',()=>{for(const name of ['original','vocals','background'])$('stem-'+name).pause();});
  for(const media of document.querySelectorAll('audio,video'))if(media!==previewAudio)media.addEventListener('play',()=>stopPreview());
  $('voice-preview-stop').onclick=$('voice-failed-stop').onclick=()=>stopPreview();
  return {chooseRange,stopPreview,setProject(value){
    const changed=value?.path!==project?.path;
    if(value?.voices.run!==project?.voices.run){failedReview.reset();suggestions.reset();$('voice-cards').replaceChildren();cursor=0;generation++;key='';result=null;}
    if(changed){$('voices-number').value='0';suggestions.reset();$('voices-backend').value=['sherpa','pyannote','fluid'].includes(value?.voices.backend)?value.voices.backend:'sherpa';}
    project=value;
    const nextPreviewKey=value?`${value.path}:${value.voices.run}:${value.voices.revision}:${value.voices.stale}:${value.speech.audio?.file}:${value.speech.stale}`:'';
    if(nextPreviewKey!==previewKey){stopPreview();previewAudio.removeAttribute('src');previewAudio.load();previewKey=nextPreviewKey;$('voice-preview-status').textContent='이름 카드의 듣기 버튼으로 목소리를 확인하세요.';}
    if(changed){tabs.reset();failedReview.reset();tab(false);generation++;key='';result=null;cursor=0;notice('');$('voices-query').value='';$('voice-rows').replaceChildren();$('voice-cards').replaceChildren();playingStem=null;
      for(const name of ['original','vocals','background']){const audio=$('stem-'+name);audio.pause();audio.removeAttribute('src');audio.load();audio.dataset.file='';}
      for(const prefix of ['voice']){$(prefix+'-start').value=0;$(prefix+'-end').value=10;}
    }
    if(!project)return;
    controls();
    const next=`${project.path}:${project.model_root}:${project.voices.updated_at}:${project.voices.revision}:${project.speech.run}:${project.speech.updated_at}`;
    if(next!==key){key=next;load(changed);}
  }};
}
