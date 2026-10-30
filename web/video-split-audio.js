// 저장할 트랙 선택과 브라우저 공통 미리듣기. 원본 영상에는 쓰지 않는다.
export function connectSplitAudio({video, api, changed, error}) {
  const $=id=>document.getElementById(id), audio=new Audio();
  audio.id='split-preview-audio';audio.hidden=true;video.after(audio);
  const mode=$('split-audio-mode'), list=$('split-audio-tracks'), listen=$('split-audio-listen');
  const toggle=$('split-audio-toggle'), status=$('split-audio-status');
  let source=null, sourceId=null, selected=[], enabled=false, busy=false, waiting=false;
  let serial=0, chunk=null, intent=false, originalMuted=false;
  const tracks=()=>source?.streams.filter(s=>s.codec_type==='audio')||[];
  const kept=()=>mode.value==='all'?tracks().map(s=>s.index):selected;
  const label=(s,i)=>`트랙 ${i+1} · ${s.tags?.title||s.tags?.handler_name||'AAC'} · ${s.channels}채널${s.tags?.language&&s.tags.language!=='und'?' · '+s.tags.language:''}`;
  function controls() {
    mode.disabled=busy||!tracks().length;
    list.hidden=mode.value!=='selected';
    for(const input of list.querySelectorAll('input'))input.disabled=busy;
    listen.disabled=toggle.disabled=!kept().length;
    toggle.textContent=enabled?'선택 트랙 듣기 종료':'선택 트랙으로 미리보기';
    toggle.setAttribute('aria-pressed',String(enabled));
    $('split-audio-volume-row').hidden=!enabled;
    $('split-audio-summary').textContent=tracks().length
      ? (kept().length?`저장할 오디오 ${kept().length}/${tracks().length}개 · 원본 순서 유지 · 재인코딩 없음`:'유지할 오디오를 하나 이상 선택하세요.')
      : '오디오가 없는 영상입니다. 영상만 그대로 나눕니다.';
    $('split-preview-note').textContent=enabled
      ? '선택한 트랙 하나만 영상에 맞춰 듣습니다. 원본 소리는 끄고 아래 음량으로 조절합니다.'
      : '기본 재생은 브라우저의 기본 트랙을 사용합니다. 저장할 트랙은 아래에서 고르세요.';
  }
  function stop() {
    serial++;intent=false;waiting=false;chunk=null;audio.pause();audio.removeAttribute('src');audio.load();
    if(enabled){enabled=false;video.muted=originalMuted;}
    status.textContent='';controls();
  }
  function refreshList() {
    const before=listen.value;listen.replaceChildren();
    tracks().forEach((s,i)=>{if(kept().includes(s.index)){const o=document.createElement('option');o.value=s.index;o.textContent=label(s,i);listen.append(o);}});
    if([...listen.options].some(o=>o.value===before))listen.value=before;
    if(!kept().length){video.pause();stop();}
    else if(enabled&&listen.value!==before)prepare(video.currentTime,!video.paused||intent);
    controls();
  }
  function fail(e, token=serial) {
    if(token!==serial)return;
    video.pause();stop();status.textContent='선택 트랙을 재생하지 못했습니다. 다시 시도하세요.';error(e);
  }
  function sync() {
    if(!chunk)return;
    const at=Math.max(0,video.currentTime-chunk.start);
    if(Number.isFinite(audio.duration)&&at<audio.duration&&Math.abs(audio.currentTime-at)>.15)audio.currentTime=at;
    audio.playbackRate=video.playbackRate;
  }
  async function playPair(token) {
    sync();
    try {await audio.play();if(token!==serial||!intent){audio.pause();return;}await video.play();}
    catch(e){fail(e,token);}
  }
  async function prepare(at, resume) {
    if(!enabled||!source)return;
    const token=++serial;intent=resume;waiting=true;audio.pause();video.pause();
    status.textContent='선택한 오디오를 재인코딩 없이 준비하는 중…';
    try {
      const value=await api('audio-preview',{source_id:sourceId,track:Number(listen.value),at:Math.min(at,source.duration-.001)});
      if(token!==serial)return;
      await new Promise((resolve,reject)=>{
        const timer=setTimeout(()=>finish(Error('미리듣기 파일을 읽는 시간이 초과됐습니다.')),15000);
        const done=()=>finish(),bad=()=>finish(Error('브라우저에서 선택 트랙을 재생하지 못했습니다.'));
        function finish(e){clearTimeout(timer);audio.removeEventListener('loadedmetadata',done);audio.removeEventListener('error',bad);e?reject(e):resolve();}
        audio.addEventListener('loadedmetadata',done);audio.addEventListener('error',bad);
        audio.src='split-audio?'+new URLSearchParams({id:value.id});audio.load();
      });
      if(token!==serial)return;
      chunk=value;waiting=false;sync();status.textContent=`${listen.selectedOptions[0]?.textContent} · 미리듣기`;
      if(intent)await playPair(token);
    }catch(e){fail(e,token);}
  }
  mode.onchange=()=>{refreshList();changed();};
  listen.onchange=()=>{if(enabled)prepare(video.currentTime,!video.paused||intent);};
  toggle.onclick=()=>{
    if(enabled){video.pause();stop();return;}
    originalMuted=video.muted;enabled=true;video.muted=true;controls();prepare(video.currentTime,true);
  };
  $('split-audio-volume').oninput=e=>{audio.volume=Number(e.target.value)/100;};
  video.addEventListener('volumechange',()=>{if(enabled&&!video.muted)video.muted=true;});
  video.addEventListener('play',()=>{
    if(!enabled||waiting)return;
    intent=true;
    if(!chunk||video.currentTime<chunk.start||video.currentTime>=chunk.end)prepare(video.currentTime,true);
    else {sync();audio.play().catch(e=>fail(e));}
  });
  video.addEventListener('pause',()=>{if(!waiting){intent=false;audio.pause();}});
  video.addEventListener('waiting',()=>audio.pause());
  video.addEventListener('playing',()=>{if(enabled&&!waiting&&intent){sync();audio.play().catch(e=>fail(e));}});
  video.addEventListener('seeking',()=>{if(enabled)prepare(video.currentTime,!video.paused||intent);});
  video.addEventListener('ratechange',sync);
  video.addEventListener('timeupdate',()=>{
    if(!enabled||waiting||video.paused||!chunk)return;
    if(video.currentTime>=chunk.end&&chunk.end<source.duration)prepare(video.currentTime,true);
    else sync();
  });
  video.addEventListener('ended',()=>{intent=false;audio.pause();});
  audio.addEventListener('error',()=>{if(enabled&&!waiting)fail(Error('선택 오디오를 읽지 못했습니다.'));});
  window.addEventListener('pagehide',()=>{video.pause();stop();});
  return {
    selection:()=>({mode:mode.value,tracks:[...kept()]}),
    valid:()=>mode.value==='all'||kept().length>0,
    lock(value){busy=value;controls();},
    reset(id,value,saved=null){
      stop();sourceId=id;source=value;mode.value=saved?.mode||'all';selected=saved?.tracks?[...saved.tracks]:tracks().map(s=>s.index);
      list.replaceChildren();
      tracks().forEach((s,i)=>{
        const row=document.createElement('label'),input=document.createElement('input');input.type='checkbox';input.checked=selected.includes(s.index);
        input.onchange=()=>{selected=tracks().map(s=>s.index).filter(n=>n===s.index?input.checked:selected.includes(n));refreshList();changed();};
        row.append(input,document.createTextNode(label(s,i)));list.append(row);
      });refreshList();
    },stop
  };
}
