// 같은 음원에서 범위만 재생한다. 새 파일이나 음원 분리 작업은 만들지 않는다.
export function createAudioPreview(audio, status) {
  let range = null, pending = null, serial = 0, frame = null;
  function stop() {
    serial++; pending = null; range = null;
    cancelAnimationFrame(frame); frame = null; audio.pause();
  }
  function checkEnd() {
    if (range && audio.currentTime >= range.end) {
      const end = range.end; stop(); audio.currentTime = end; status('음성 재생을 마쳤습니다.');
    }
  }
  function tick() {
    checkEnd();
    if (range && !audio.paused) frame = requestAnimationFrame(tick);
  }
  async function apply() {
    if (!pending || !Number.isFinite(audio.duration)) return;
    const request = pending; pending = null;
    if (request.start >= audio.duration) { stop(); status('음성 시각이 추출 음성 범위를 벗어났습니다.'); return; }
    range = {start: request.start, end: Math.min(request.end, audio.duration)};
    audio.currentTime = range.start;
    try { await audio.play(); if (request.serial === serial) status(request.label+' · 원음 재생 중 · 구간 끝에서 멈춥니다.'); }
    catch { if (request.serial === serial) { stop(); status('음성 재생을 시작하지 못했습니다. 듣기 버튼을 다시 눌러주세요.'); } }
  }
  audio.addEventListener('loadedmetadata', apply);
  audio.addEventListener('timeupdate', checkEnd);
  audio.addEventListener('play', () => { cancelAnimationFrame(frame); frame = requestAnimationFrame(tick); });
  audio.addEventListener('pause', () => { cancelAnimationFrame(frame); frame = null; });
  audio.addEventListener('ended', () => { stop(); status('음성 재생을 마쳤습니다.'); });
  audio.addEventListener('error', () => { stop(); status('음성을 읽을 수 없습니다. 추출 음성과 저장 경로를 확인하세요.'); });
  return {stop, play(url, sample, label) {
    stop();
    if (!Number.isFinite(sample?.start_ms) || !Number.isFinite(sample?.end_ms) || sample.start_ms < 0 || sample.end_ms <= sample.start_ms) {
      status('재생할 음성 구간이 없습니다.'); return;
    }
    pending = {start: sample.start_ms/1000, end: sample.end_ms/1000, label, serial};
    status(label+' · 음성을 불러오는 중…');
    if (audio.getAttribute('src') !== url) { audio.src = url; audio.load(); }
    else apply();
  }};
}
