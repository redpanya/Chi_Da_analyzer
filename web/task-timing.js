import {timecode} from './player.js';

export function elapsedText(state, now = Date.now()) {
  const timer = state?.timing;
  if (!timer) return !state || ['idle', 'queued'].includes(state.state) ? '작업을 시작하면 소요 시간을 기록합니다.' : '소요 시간 기록 없음 · 이전 작업';
  const running = Number.isFinite(timer.since_ms);
  const milliseconds = timer.elapsed_ms + (running ? Math.max(0, now - timer.since_ms) : 0);
  const label = running ? '경과 시간' : ['complete', 'empty', 'unavailable', 'review'].includes(state.state) ? '완료까지 소요 시간' : '중단까지 실행 시간';
  return `${label} ${timecode(milliseconds)}${timer.partial ? ' 이상 · 미기록 시간 제외' : ''} · 중단 대기 제외`;
}
