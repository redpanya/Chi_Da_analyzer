'use strict';
const path = require('node:path');
function readyAddress(record, pid) {
  if (record?.pid !== pid || typeof record.url !== 'string') throw Error('실행 중인 처리기를 확인할 수 없습니다.');
  const u = new URL(record.url);
  if (u.protocol !== 'http:' || u.hostname !== '127.0.0.1' || !u.port || !/^\/[a-zA-Z0-9_-]{32}\/$/.test(u.pathname) ||
      u.username || u.password || u.search || u.hash) throw Error('처리기가 올바르지 않은 주소를 반환했습니다.');
  return u;
}
function trustedPage(base, url) {
  if (!base) return false;
  try {
    const u = new URL(url);
    return !u.username && !u.password && u.origin === base.origin &&
      ['', 'clip-studio.html', 'mix-studio.html', 'video-split.html'].some(name => u.pathname === base.pathname + name);
  } catch { return false; }
}
const externalLinks = new Set([
  'https://github.com/redpanya/Chi_Da_analyzer/blob/main/THIRD-PARTY-NOTICES.md',
  'https://github.com/redpanya/Chi_Da_analyzer/releases/latest',
  'https://redpanya.github.io/Chi_Da_analyzer/',
  'https://huggingface.co/docs/huggingface_hub/guides/cli',
  'https://huggingface.co/pyannote/speaker-diarization-community-1'
]);
function handoff(base, value) {
  try {
    const url = new URL(value);
    if (url.username || url.password) return;
    if (url.origin === base.origin && ['file','split-file','mix-file'].some(name => url.pathname === base.pathname + name)) return 'download';
    if (externalLinks.has(value)) return 'external';
    if (url.protocol === 'mailto:' && url.pathname === 'redpanyaday@gmail.com' && !url.hash &&
        value.length < 1200 && ['치다 분석기 성능 리포트','치다 분석기 오류 제보'].includes(url.searchParams.get('subject')) &&
        [...url.searchParams.keys()].every(k => k === 'subject' || k === 'body')) return 'external';
  } catch {}
}
function inside(parent, file) {
  const rel = path.relative(parent, file);
  return rel === '' || (rel !== '..' && !rel.startsWith('..' + path.sep) && !path.isAbsolute(rel));
}
module.exports = { readyAddress, trustedPage, handoff, inside };
