import {playbackRanges} from './player-sequence.js';
export function timecode(milliseconds) {
  const seconds = Math.floor(Math.max(0, milliseconds) / 1000);
  return [Math.floor(seconds / 3600), Math.floor(seconds / 60) % 60, seconds % 60]
    .map(value => String(value).padStart(2, '0')).join(':');
}

export function parseTime(value) {
  if (!/^\d{1,3}:\d{2}(:\d{2})?$/.test(value)) throw Error('시각을 분:초 또는 시:분:초로 입력하세요');
  const parts = value.split(':').map(Number);
  if (parts.slice(1).some(part => part > 59)) throw Error('분·초는 0~59로 입력하세요');
  return parts.reduce((sum, part) => sum * 60 + part, 0) * 1000;
}

export function clampTime(milliseconds, duration) {
  if (!Number.isFinite(milliseconds) || !Number.isFinite(duration) || duration <= 0) return null;
  return Math.max(0, Math.min(milliseconds / 1000, duration));
}

export function createPlayer() {
  const $ = id => document.getElementById(id);
  const video = $('player');
  let pending = null, range = null, sequence = null, playRequest = 0;
  const pause=()=>{playRequest++;video.pause();};
  const listeners=new Set();
  const sequenceState=()=>({active:!!sequence,paused:video.paused,index:sequence?.index??0,total:sequence?.ranges.length??0});
  const emit=()=>{for(const listener of listeners)listener(sequenceState());};
  function stopSequence(pause=true){if(!sequence)return;sequence=null;range=null;pending=null;if(pause){playRequest++;video.pause();}emit();}
  const status = text => { $('player-status').textContent = text; };
  function showTime() {
    if (!video.error && Number.isFinite(video.duration)) {
      $('player-clock').textContent = `${timecode(video.currentTime * 1000)} / ${timecode(video.duration * 1000)}`;
    }
    $('play-toggle').textContent = video.paused ? '재생' : '일시정지';
  }
  async function play() {
    const request=++playRequest;
    try { await video.play(); } catch { if(request!==playRequest)return;stopSequence(); status('재생을 시작하지 못했습니다. 재생 버튼 또는 원본 파일을 확인하세요.'); }
  }
  function apply() {
    if (!pending || !Number.isFinite(video.duration)) return;
    const {milliseconds, playing} = pending;
    pending = null;
    const target = clampTime(milliseconds, video.duration);
    if (target === null) return;
    pause();
    video.currentTime = target;
    status(milliseconds < 0 || milliseconds > video.duration * 1000 ? '영상 범위를 벗어나 재생 가능한 시각으로 이동했습니다.' : '선택한 시각으로 이동했습니다.');
    if (playing) play();
    if(sequence)status(`목록 구간 ${sequence.index+1}/${sequence.ranges.length} 재생 중 · 선택하지 않은 시간은 건너뜁니다.`);
  }
  function seek(milliseconds, playing = false, end = null, keepSequence = false) {
    if(!keepSequence)stopSequence(false);
    range = Number.isFinite(end) && end > milliseconds ? {start: milliseconds, end} : null;
    if (!Number.isFinite(milliseconds)) return;
    if (!video.getAttribute('src') || video.error) {
      status('영상 파일을 재생할 수 없습니다. 다운로드 상태와 파일 경로를 확인하세요.');
      return;
    }
    pending = {milliseconds, playing};
    apply();
  }
  function nextRange(){
    if(!sequence)return;
    if(++sequence.index>=sequence.ranges.length){const end=sequence.ranges.at(-1).end;stopSequence();video.currentTime=Math.min(video.duration,end/1000);status('선택한 목록의 재생을 모두 마쳤습니다.');return;}
    const next=sequence.ranges[sequence.index];seek(next.start,true,next.end,true);emit();
  }
  video.addEventListener('timeupdate', () => {
    if(video.seeking||pending)return;
    if(sequence){const part=sequence.ranges[sequence.index];if(video.currentTime*1000>=part.end)nextRange();return;}
    if (range && video.currentTime * 1000 >= range.end) { const end = range.end; range = null; pause(); video.currentTime = Math.min(video.duration, end / 1000); status('선택한 문맥 구간 재생을 마쳤습니다.'); }
    else if (range && video.currentTime * 1000 < range.start - 500) range = null;
  });
  video.addEventListener('loadedmetadata', () => {
    if(sequence){sequence.ranges=playbackRanges(sequence.ranges.map(r=>({start_ms:r.start,end_ms:r.end})),video.duration*1000);if(!sequence.ranges.length){stopSequence();status('선택한 구간이 영상 범위 밖입니다.');return;}}
    apply();showTime();
  });
  // WebKit은 연속 seek의 이전 이벤트를 늦게 전달할 수 있다. 완료된 위치로 판단한다.
  video.addEventListener('seeked',()=>{
    if(!sequence)return;const part=sequence.ranges[sequence.index],now=video.currentTime*1000;
    if(now<part.start-500||now>part.end+500){stopSequence(false);status('선택 범위 밖으로 이동해 목록 재생을 종료했습니다.');}
  });
  video.addEventListener('ended',()=>{if(sequence)nextRange();});
  for(const event of ['play','pause'])video.addEventListener(event,emit);
  for (const event of ['timeupdate', 'pause', 'play', 'ended']) video.addEventListener(event, showTime);
  video.addEventListener('error', () => { stopSequence(); pending = null; status('영상 파일을 불러오지 못했습니다. 원본을 보존하고 다운로드 상태와 파일 경로를 확인하세요.'); });
  $('play-toggle').onclick = () => video.paused ? play() : pause();
  $('playback-speed').onchange = () => { video.defaultPlaybackRate = video.playbackRate = Number($('playback-speed').value); };
  for(const [id,seconds] of [['play-back',-3],['play-forward',3]])$(id).onclick=()=>seek((video.currentTime+seconds)*1000,!video.paused);
  return {
    seek,
    playSequence(rows){
      const ranges=playbackRanges(rows,Number.isFinite(video.duration)?video.duration*1000:Infinity);
      if(!ranges.length){status('재생할 수 있는 구간이 없습니다.');return false;}
      if(!video.getAttribute('src')||video.error){status('영상 파일을 먼저 준비하세요.');return false;}
      stopSequence();sequence={ranges,index:0};seek(ranges[0].start,true,ranges[0].end,true);emit();return true;
    },
    toggleSequence(){if(!sequence)return;video.paused?play():pause();emit();},
    stopSequence, sequenceState,
    onSequence(listener){listeners.add(listener);return()=>listeners.delete(listener);},
    previewMode(enabled){$('playback-speed-control').hidden=enabled;$('play-back').hidden=$('play-forward').hidden=!enabled;if(enabled){video.defaultPlaybackRate=video.playbackRate=1;$('playback-speed').value='1';}},
    clearRange(){stopSequence();range=null;},
    reset(){stopSequence();range=null;pending=null;pause();status('');}
  };
}
