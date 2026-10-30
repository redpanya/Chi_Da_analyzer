import {getHelpContent} from './help-content.js';

// 화면 도움말은 입력값을 읽기만 한다. 결과·미디어 DOM과 작업 상태는 건드리지 않는다.
export function connectHelp() {
  const $ = id => document.getElementById(id);
  const dialog = $('help-dialog'), body = $('help-body');
  let opener = null, backdropStart = false, project = null;
  const read = (id, kind) => {
    const input = $(id);
    if (kind === 'value') return input?.value;
    if (kind === 'dataset') return input?.dataset;
    if (kind === 'checked') return !!input?.checked;
    if (kind === 'length') return input?.value.length || 0;
    return input?.selectedOptions?.[0]?.textContent || input?.value || '미선택';
  };
  function label(button, id) {
    button.dataset.helpOpen = id;
    button.setAttribute('aria-label', getHelpContent(id, read).title + ' 도움말');
  }
  const buttons = new Map();
  for (const target of document.querySelectorAll('[data-help]')) {
    if (target.hidden || target.closest('.section-heading[hidden]')) continue;
    const wrapper = document.createElement('div'), button = document.createElement('button');
    wrapper.className = target.tagName === 'DETAILS' ? 'help-details' : 'help-heading';
    button.type = 'button'; button.className = 'help-button';
    button.setAttribute('aria-haspopup', 'dialog'); button.setAttribute('aria-controls', dialog.id);
    const icon = document.createElement('span'); icon.textContent = '💡'; icon.setAttribute('aria-hidden', 'true');
    button.append(icon); label(button, target.dataset.help);
    target.before(wrapper); wrapper.append(target, button); buttons.set(target, button);
  }
  function close() { if (dialog.open) dialog.close(); }
  document.addEventListener('click', event => {
    const origin = event.target?.nodeType === 3 ? event.target.parentElement : event.target;
    const button = origin?.closest?.('[data-help-open]');
    const settings = button?.closest('.settings-panel[open]');
    if (!button || (document.querySelector('dialog[open]') && !settings)) return;
    const content = getHelpContent(button.dataset.helpOpen, read);
    $('help-title').textContent = content.title + ' 도움말';
    const contentBody = settings ? document.createElement('section') : body;
    contentBody.replaceChildren();
    if (settings) { const title = document.createElement('h3'); title.textContent = content.title + ' 도움말'; contentBody.append(title); }
    for (const [index, text] of [content.current, ...content.paragraphs].entries()) {
      if (!text) continue;
      const p = document.createElement('p'); p.textContent = text;
      if (index === 0) p.className = 'help-current';
      contentBody.append(p);
    }
    for (const link of content.links||[]) {
      const p=document.createElement('p'),a=document.createElement('a');
      a.href=link.url;a.textContent=link.label;a.target='_blank';a.rel='noopener noreferrer';
      p.append(a);contentBody.append(p);
    }
    if (settings) {settings.dispatchEvent(new CustomEvent('settings-help', {detail:contentBody})); return;}
    opener = button; backdropStart = false; dialog.showModal();
    body.scrollTop = 0; $('help-close').focus({preventScroll:true});
  });
  $('help-close').addEventListener('click', close);
  dialog.addEventListener('cancel', event => {event.preventDefault(); close();});
  dialog.addEventListener('close', () => {
    // 다른 모달이 열린 경우 그 모달의 초점을 유지한다.
    if (document.querySelector('dialog[open]')) return;
    const target = opener?.isConnected && opener.getClientRects().length ? opener : $('heading');
    target.focus({preventScroll:true}); opener = null;
  });
  const outside = event => {
    const r = dialog.getBoundingClientRect();
    return event.clientX < r.left || event.clientX > r.right || event.clientY < r.top || event.clientY > r.bottom;
  };
  dialog.addEventListener('pointerdown', event => {backdropStart = event.target === dialog && outside(event);});
  dialog.addEventListener('pointercancel', () => {backdropStart = false;});
  dialog.addEventListener('click', event => {
    if (backdropStart && event.target === dialog && outside(event)) close();
    backdropStart = false;
  });
  return {
    close,
    setPage(step) {
      close();
      const id = ['import','download','speech','voices','explore','context','report','external','settings'][step-1];
      $('heading').dataset.help = id; label(buttons.get($('heading')), id);
    },
    setProject(path) { if (path !== project) {close(); project = path;} },
  };
}
