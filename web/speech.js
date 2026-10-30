import {timecode} from './player.js';


export function createSpeech({api, player, showVoices, showPreview, onProject}) {
  const $ = id => document.getElementById(id);
  let project = null, generation = 0, infoGeneration = 0, rowGeneration = 0, details = null, fingerprint = '', rowsKey = '', next = null, cursor = 0, requesting = false;
  const selected = () => ({root: project.root, vod_id: project.vod_id});
  const message = text => { $('speech-notice').textContent = text; };
  const fileURL = key => `file?${new URLSearchParams({...selected(), kind:'speech', key, revision:project.speech.updated_at||''})}`;
  function button(text, action, className = 'secondary') {
    const b = document.createElement('button'); b.textContent = text; b.className = className; b.onclick = action; return b;
  }
  async function info() {
    if (!project) return;
    const token = generation, requestId = ++infoGeneration;
    details = null;
    $('speech-model').dataset.ready='pending'; $('speech-model').dataset.engine='pending';
    $('speech-track').replaceChildren();
    const ready = project.tasks?.video?.state === 'complete';
    $('speech-source').textContent = ready ? '영상의 오디오 정보를 확인하고 있습니다…' : '영상 다운로드·검증 완료 후 오디오 정보를 확인합니다.';
    render();
    if (!ready) return;
    try {
      const value = await api('speech-info', selected());
      if (token !== generation || requestId !== infoGeneration) return;
      details = value;
      $('speech-track').replaceChildren();
      for (const track of value.tracks) {
        const option = document.createElement('option'); option.value = track.index;
        option.textContent = `트랙 ${track.index} · ${track.language} · ${track.channels}채널 · ${track.codec}${track.title ? ' · '+track.title : ''}`;
        $('speech-track').append(option);
      }
      const raw = project.speech.raw_audio || project.speech.audio;
      if (raw) $('speech-track').value = raw.track;
      $('speech-source').textContent = value.tracks.length ? `재생용 영상 기준 ${timecode(value.duration_ms)} · WAV 예상 ${(value.estimated_bytes / 1e6).toFixed(1)} MB · 16kHz 모노` : '오디오 트랙이 없는 영상입니다.';
      const m = value.model;
      Object.assign($('speech-model').dataset,{ready:String(!!m.ready),engine:String(!!m.engine)});
      $('speech-model').textContent = `${m.name} · ${(m.bytes / 1024**2).toFixed(0)} MiB · ${m.ready ? '준비됨' : '준비 필요'} · ${m.engine ? '전사 엔진 감지됨' : 'whisper-cli 설치 필요'} · 남은 공간 ${(m.free_bytes / 1e9).toFixed(1)} GB`;
      render();
    } catch (error) { if (token === generation && requestId === infoGeneration) { details = null; $('speech-source').textContent = error.message; message(error.message); render(); } }
  }
  function render() {
    if (!project) return;
    const s = project.speech, running = s.owned || (project.locked && ['running','stopping'].includes(s.state));
    $('speech-title').textContent = project.metadata.title;
    const oldSeparation=!running&&['paused','error'].includes(s.state)&&(['separate','sam-model','roformer-model'].includes(s.action)||s.action==='transcribe'&&s.options?.input_kind&&s.options.input_kind!=='original');
    $('speech-status').textContent = s.message + (s.action==='transcribe'&&s.compute?.note?' · '+s.compute.note:'') + (oldSeparation?' · 이전 분리 작업은 이어받지 않습니다. 아래 원음 전사를 시작하면 기존 결과를 보존하고 별도 작업을 만듭니다.':'') + (s.stale ? ' · 입력이 달라지거나 파일이 없어 이전 결과입니다. 추출·전사를 다시 확인하세요.' : '');
    const p = s.progress || {}, progress = $('speech-progress');
    const ratio = p.total_bytes ? p.bytes / p.total_bytes : p.duration_ms ? p.processed_ms / p.duration_ms : null;
    if (running && ratio === null) progress.removeAttribute('value'); else progress.value = ratio === null ? 0 : ratio * 100;
    $('speech-progress-text').textContent = p.duration_ms ? `보존된 범위 ${timecode(p.processed_ms || 0)} / ${timecode(p.duration_ms)}${p.current_end_ms ? ' · 현재 조각 끝 '+timecode(p.current_end_ms) : ''}` : p.total_bytes ? `모델 ${Math.floor(100 * p.bytes / p.total_bytes)}%` : '';
    $('extract-audio').disabled = requesting || project.locked || !details?.tracks.length;
    $('prepare-model').disabled = requesting || project.locked || !details;
    $('transcribe').textContent = '원음으로 전체 전사·이어받기';
    $('transcribe').disabled = requesting || project.locked || !(s.raw_audio || s.audio) || !details?.model.ready || !details?.model.engine;
    $('speech-vad').disabled = $('speech-prompt').disabled = requesting || project.locked;
    $('speech-version').disabled = requesting || project.locked;
    $('speech-delete').disabled = requesting || project.locked || !s.run;
    const versions = s.versions || [];
    const versionKey = JSON.stringify(versions);
    if ($('speech-version').dataset.key !== versionKey) {
      $('speech-version').replaceChildren(...versions.map(v => {const o=document.createElement('option');o.value=v.id;o.textContent=v.label;return o;}));
      $('speech-version').dataset.key = versionKey;
    }
    $('speech-version').value=s.run || '';
    $('sam-audio-box').hidden=!s.separated_audio;
    if (s.separated_audio && $('sam-audio').dataset.file !== project.path+s.separated_audio.file) {
      $('sam-audio').src=fileURL('sam'); $('sam-audio').dataset.file=project.path+s.separated_audio.file;
    }
    $('sam-audio-label').textContent = '이전에 저장한 분리본';
    $('sam-review').textContent = s.separation_review_chunks?.length ? `음량이 크게 줄어든 ${s.separation_review_chunks.length}개 조각이 있습니다. 음악·무음일 수도 있으므로 누락 여부를 들어 확인하세요.` : '';
    $('speech-stop').disabled = requesting || !s.owned || s.state === 'stopping';
    $('speech-export').disabled = requesting || project.locked || !s.run;
    $('speech-track').disabled = $('speech-language').disabled = requesting || project.locked;
    for (const control of document.querySelectorAll('.speech-edit-control')) control.disabled = project.locked || requesting;
    $('speech-audio-box').hidden = !s.audio;
    if (s.audio) {
      const audio = $('speech-audio'), relative = s.audio.file;
      if (audio.dataset.file !== project.path + relative) { audio.pause(); audio.src = fileURL('audio'); audio.dataset.file = project.path + relative; }
      $('speech-audio-save').href = fileURL('audio-save');
      $('speech-audio-label').textContent = `추출한 트랙 ${s.audio.track} · ${timecode(s.audio.duration_ms)} · 영상 상대 시각 유지`;
    }
    const t = s.transcript;
    $('speech-coverage').textContent = t ? `${t.quality_revision?'발화 검출·품질 점검 · ':''}${t.input_label || '이전 입력'} · ${t.complete ? '전체 범위 처리' : '일부 범위 처리'} · ${timecode(t.processed_ms)} / ${timecode(t.duration_ms)} · ${t.segment_count}개 발언 · 디지털 무음 ${t.chunks.filter(c=>c.status==='silence').length}조각 · 텍스트 인식 실패 ${t.chunks.filter(c=>c.status==='unrecognized').length}조각 · 문자 인식 오류 ${t.chunks.reduce((n,c)=>n+(c.encoding_review_count||0),0)}개 발언` : '전사를 시작하면 완료된 조각부터 확인할 수 있습니다.';
    $('speech-gaps').replaceChildren();
    for (const chunk of t?.chunks || []) if (chunk.status !== 'recognized') {
      const p = document.createElement('p'); p.className = 'hint'; p.textContent = `${timecode(chunk.start_ms)}~${timecode(chunk.end_ms)} · ${chunk.status === 'silence' ? '디지털 무음' : chunk.status === 'no_speech' ? '발화 검출 없음 · 작은 목소리 누락 여부 확인' : '소리는 있으나 텍스트 인식 실패 · 원음 확인 필요'}`; $('speech-gaps').append(p);
    }
    $('speech-exports').replaceChildren();
    for (const key of Object.keys(s.exports || {})) {
      const a = document.createElement('a'); a.href = fileURL(key); a.textContent = key.toUpperCase()+' 저장'; a.className = 'text-link'; $('speech-exports').append(a);
    }
  }
  async function loadRows(reset = false) {
    if (!project) return;
    if (reset) cursor = 0;
    const token = generation, requestId = ++rowGeneration, query = $('speech-query').value;
    try {
      const result = await api('speech-result', {...selected(), query, cursor});
      if (token !== generation || requestId !== rowGeneration || query !== $('speech-query').value) return;
      $('transcript-rows').replaceChildren(); next = result.next_cursor;
      $('speech-next').disabled = next === null;
      $('speech-prev').disabled = cursor === 0;
      $('speech-count').textContent = `${result.total}개 · ${Math.floor(cursor / 100) + 1}쪽`;
      for (const row of result.items) {
        const card = document.createElement('article'); card.className = 'transcript-row';
        const actions = document.createElement('div'); actions.className = 'play-actions';
        const time = document.createElement('span'); time.className = 'transcript-time';
        time.textContent = `${timecode(row.start_ms)} → ${timecode(row.end_ms)}`;
        actions.append(time);
        actions.append(button('음성 듣기', async () => {
          const audio = $('speech-audio');
          if (project.speech.stale || !Number.isFinite(audio.duration)) return message('추출 음성이 준비되지 않았거나 이전 입력입니다.');
          player.reset(); audio.currentTime = Math.min(row.start_ms / 1000, audio.duration);
          try { await audio.play(); } catch { message('음성 재생을 시작하지 못했습니다.'); }
        }));
        actions.append(button('화자 검토 (선택)', () => showVoices(row)), button('해당 영상보기', () => {
          if (project.speech.stale) return message('이전 입력의 전사입니다. 입력 상태를 먼저 확인하세요.');
          showPreview(row);
        }));
        const text = document.createElement('p'); text.textContent = row.text || '(교정 후 빈 텍스트)';
        const hint = document.createElement('p'); hint.className = 'hint'; hint.textContent = `${row.corrected ? '사용자 교정 · 원문 별도 보존' : '자동 전사 · 원음 확인 필요'}${row.boundary_review ? ' · 조각 경계 검토' : ''}${row.timing_adjusted ? ' · 종료 시각 범위 제한 · 시각 검토 필요' : ''}${row.repeat_review ? ' · 같은 문장 반복 · 인식 내용 검토' : ''}${row.repeat_candidate ? ' · 유사 반복 발화 · 원문·요약 입력 유지' : ''}${row.quality_review ? ' · '+row.quality_notes.join(' · ')+(row.corrected?' · 사용자 교정 반영':' · 요약에서 제외, 원음 확인 후 교정 가능') : ''}${row.encoding_review ? (row.corrected ? ' · 원출력 문자 오류 · 교정 반영' : ' · 문자 인식 오류 · 원음 확인 후 교정 필요') : ''}`;
        const edit = document.createElement('details'), summary = document.createElement('summary'); summary.textContent = '텍스트 교정';
        const original = document.createElement('p'); original.className='hint'; original.textContent = '원문: '+row.original_text;
        const input = document.createElement('textarea'); input.value = row.text; input.maxLength=5000; input.className='speech-edit-control'; input.disabled=project.locked; input.setAttribute('aria-label',timecode(row.start_ms)+' 전사 교정');
        const save = value => request('speech-edit', {action:'correct', run:result.run, segment:row.id, text:value}, () => loadRows());
        const saveButton=button('교정 저장',()=>save(input.value),'secondary speech-edit-control'), restoreButton=button('원문으로 복원',()=>save(null),'subtle speech-edit-control');
        saveButton.disabled=restoreButton.disabled=project.locked;
        edit.append(summary,original,input,saveButton,restoreButton);
        card.append(actions,text,hint,edit); $('transcript-rows').append(card);
      }
    } catch (error) { if (token === generation) message(error.message); }
  }
  async function request(action, options, after) {
    if (!project || requesting) return;
    const token = generation; requesting = true; message(''); render();
    try {
      const fresh = await api(action, {...selected(), ...options});
      if (token === generation) { onProject(fresh); if (after) await after(); }
    } catch (error) { if (token === generation) message(error.message); }
    finally { requesting = false; if (project) render(); }
  }
  $('extract-audio').onclick = () => request('speech-start', {action:'audio', track:Number($('speech-track').value)});
  $('prepare-model').onclick = () => request('speech-start', {action:'model'});
  $('speech-version').onchange = () => request('speech-edit', {action:'select',run:$('speech-version').value});
  $('speech-delete').onclick = () => {
    const run=$('speech-version').value;
    if(!run||project?.locked||!confirm('선택한 전사와 그 전사의 수동 교정을 휴지통으로 이동할까요?\n영상·오디오·채팅·다른 전사·내보낸 파일·기존 요약은 유지됩니다.\n이 전사를 사용하는 화자 분석이 있다면 먼저 삭제해야 합니다.'))return;
    return request('speech-edit',{action:'delete',run});
  };
  $('sam-audio').onplay = () => {player.reset(); $('speech-audio').pause();};
  $('transcribe').onclick = () => request('speech-start', {action:'transcribe', language:$('speech-language').value,
    input_kind:'original', asr_options:{vad:$('speech-vad').value,prompt:$('speech-prompt').value}});
  $('speech-vad').onchange = render;
  $('speech-stop').onclick = () => request('speech-stop', {});
  $('speech-export').onclick = () => request('speech-edit', {action:'export'});
  $('speech-search').onsubmit = event => {event.preventDefault(); loadRows(true);};
  $('speech-next').onclick = () => {if(next !== null){cursor=next;loadRows();}};
  $('speech-prev').onclick = () => {cursor=Math.max(0,cursor-100);loadRows();};
  $('speech-audio').onerror = () => {if(project?.speech.audio) message('추출 음성을 읽을 수 없습니다. 저장 파일을 확인하세요.');};
  $('speech-audio').onplay = () => {player.reset();$('sam-audio').pause();};
  $('player').addEventListener('play', () => {$('speech-audio').pause();$('sam-audio').pause();});
  return {setProject(value) {
    const changed = value?.path !== project?.path;
    const modelChanged = value?.model_root !== project?.model_root;
    const videoChanged = value?.tasks?.video?.state !== project?.tasks?.video?.state
      || value?.tasks?.video?.assets?.playback !== project?.tasks?.video?.assets?.playback;
    if (modelChanged && !changed) {generation++; details=null; fingerprint=''; $('speech-model').textContent='모델 상태 확인 중'; $('speech-model').dataset.ready='false'; $('speech-model').dataset.engine='false';}
    if (changed) {
      generation++; details=null; fingerprint=''; rowsKey=''; cursor=0; next=null;
      $('sam-audio').pause();$('sam-audio').removeAttribute('src');$('sam-audio').load();$('sam-audio').dataset.file='';
      $('speech-audio').pause(); $('speech-audio').removeAttribute('src'); $('speech-audio').load(); $('speech-audio').dataset.file='';
      $('transcript-rows').replaceChildren(); $('speech-query').value=''; message(''); $('speech-model').textContent='모델 상태 확인 중'; $('speech-model').dataset.ready='false'; $('speech-model').dataset.engine='false';
    }
    const previous = project?.speech;
    project=value;
    if (!project) return;
    if (changed) {
      $('speech-language').value = value.speech.transcript?.language || 'ko';
      const options=value.speech.options?.asr_options || value.speech.transcript?.asr_options || {};
      $('speech-vad').value = options.vad || 'standard';
      $('speech-prompt').value = options.prompt || '';
    }
    if (changed || modelChanged || videoChanged || (previous?.owned && !value.speech.owned) || (value.speech.action === 'model' && value.speech.state === 'complete' && previous?.updated_at !== value.speech.updated_at)) info();
    const nextFingerprint=JSON.stringify(value.speech)+value.locked;
    if (nextFingerprint !== fingerprint) {fingerprint=nextFingerprint;render();}
    const key=`${value.speech.run}:${value.speech.transcript?.processed_ms}:${value.speech.updated_at}`;
    if(key !== rowsKey){rowsKey=key;loadRows(true);}
  }};
}
