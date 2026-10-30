import {timecode} from './player.js';

// 기존 재생기 노드를 잠시 이동한다. 별도 video나 음원을 만들지 않는다.
export function createMiniPlayer({player, onExplore}) {
  const $ = id => document.getElementById(id);
  const panel = document.createElement('section');
  panel.id = 'speech-preview'; panel.className = 'mini-player'; panel.hidden = true;
  panel.setAttribute('role', 'region'); panel.setAttribute('aria-labelledby', 'speech-preview-heading');
  const header = document.createElement('div'); header.className = 'mini-player-header';
  const title = document.createElement('strong'); title.id = 'speech-preview-heading'; title.textContent = '전사 영상 미리보기';
  const closeButton = document.createElement('button'); closeButton.type = 'button'; closeButton.className = 'subtle'; closeButton.textContent = '닫기 ×'; closeButton.setAttribute('aria-label', '미니 플레이어 닫기');
  header.append(title, closeButton);
  const caption = document.createElement('p'); caption.className = 'mini-player-caption'; caption.setAttribute('aria-live', 'polite');
  const media = document.createElement('div'); media.id = 'speech-preview-media';
  const explore = document.createElement('button'); explore.type = 'button'; explore.className = 'subtle'; explore.textContent = '분석·재생으로 이동';
  panel.append(header, caption, media, explore); document.body.append(panel);
  let slots = [], opener = null, row = null, projectKey = null;
  function close(restoreFocus = true) {
    if (panel.hidden) return;
    player.reset();
    for (const [node, slot] of slots) slot.replaceWith(node);
    slots = []; panel.hidden = true; row = null; player.previewMode(false);
    if (restoreFocus && opener?.isConnected && opener.getClientRects().length) opener.focus({preventScroll:true});
    opener = null;
  }
  closeButton.onclick = () => close();
  panel.addEventListener('keydown', event => { if (event.key === 'Escape') { event.preventDefault(); event.stopPropagation(); close(); } });
  explore.onclick = () => { const selected = row; close(false); if (selected) onExplore(selected); };
  return {
    close,
    setProject(value) { if (projectKey !== value?.path) { close(false); projectKey = value?.path; } },
    open(value, button = document.activeElement) {
      if (!Number.isFinite(value.start_ms)) return;
      row = value; opener = button;
      if (panel.hidden) {
        slots = ['video-result', 'video-unready'].map(id => {
          const node = $(id), slot = document.createComment('영상 원래 위치');
          node.before(slot); media.append(node); return [node, slot];
        });
      }
      for (const audio of document.querySelectorAll('audio')) audio.pause();
      caption.textContent = `${timecode(value.start_ms)} ~ ${timecode(value.end_ms ?? value.start_ms)} · ${value.text || '선택한 전사 구간'}`;
      panel.hidden = false; player.previewMode(true);
      player.seek(value.start_ms, true, value.end_ms);
      closeButton.focus({preventScroll:true});
    },
  };
}
