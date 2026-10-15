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
  let pending = null, range = null;
  const status = text => { $('player-status').textContent = text; };
  function showTime() {
    if (!video.error && Number.isFinite(video.duration)) {
      $('player-clock').textContent = `${timecode(video.currentTime * 1000)} / ${timecode(video.duration * 1000)}`;
    }
    $('play-toggle').textContent = video.paused ? '재생' : '일시정지';
  }
  async function play() {
    try { await video.play(); } catch { status('재생을 시작하지 못했습니다. 재생 버튼 또는 원본 파일을 확인하세요.'); }
  }
  function apply() {
    if (!pending || !Number.isFinite(video.duration)) return;
    const {milliseconds, playing} = pending;
    pending = null;
    const target = clampTime(milliseconds, video.duration);
    if (target === null) return;
    video.pause();
    video.currentTime = target;
    status(milliseconds < 0 || milliseconds > video.duration * 1000 ? '영상 범위를 벗어나 재생 가능한 시각으로 이동했습니다.' : '선택한 시각으로 이동했습니다.');
    if (playing) play();
  }
  function seek(milliseconds, playing = false, end = null) {
    range = Number.isFinite(end) && end > milliseconds ? {start: milliseconds, end} : null;
    if (!Number.isFinite(milliseconds)) return;
    if (!video.getAttribute('src') || video.error) {
      status('영상 파일을 재생할 수 없습니다. 다운로드 상태와 파일 경로를 확인하세요.');
      return;
    }
    pending = {milliseconds, playing};
    $('video-result').scrollIntoView({block: 'nearest'});
    apply();
  }
  video.addEventListener('timeupdate', () => {
    if (range && video.currentTime * 1000 >= range.end) { const end = range.end; range = null; video.pause(); video.currentTime = Math.min(video.duration, end / 1000); status('선택한 문맥 구간 재생을 마쳤습니다.'); }
    else if (range && video.currentTime * 1000 < range.start - 500) range = null;
  });
  video.addEventListener('loadedmetadata', () => { apply(); showTime(); });
  for (const event of ['timeupdate', 'pause', 'play', 'ended']) video.addEventListener(event, showTime);
  video.addEventListener('error', () => { pending = null; status('영상 파일을 불러오지 못했습니다. 원본을 보존하고 다운로드 상태와 파일 경로를 확인하세요.'); });
  $('seek-start').onclick = () => seek(0);
  $('seek-middle').onclick = () => seek(video.duration * 500);
  $('seek-end').onclick = () => seek(Math.max(0, video.duration - 3) * 1000);
  $('play-toggle').onclick = () => video.paused ? play() : video.pause();
  $('playback-speed').onchange = () => { video.defaultPlaybackRate = video.playbackRate = Number($('playback-speed').value); };
  $('seek-form').onsubmit = event => {
    event.preventDefault();
    try { seek(parseTime($('seek-time').value)); } catch (error) { status(error.message); }
  };
  return {seek, clearRange() { range = null; }, reset() { range = null; pending = null; video.pause(); status(''); }};
}
