// 기존 폼 노드를 이동해 이벤트·입력값을 유지한다. 닫기는 실행 중 작업을 중단하지 않는다.
export function createSettingsPanel(id, title, nodes, actions = []) {
  const make = (tag, text, cls) => { const n = document.createElement(tag); n.textContent = text || ''; if (cls) n.className = cls; return n; };
  const dialog = make('dialog', '', 'settings-panel'); dialog.id = id;
  dialog.setAttribute('aria-labelledby', id + '-title');
  const header = make('div', '', 'settings-heading'), heading = make('h2', title);
  heading.id = id + '-title'; heading.tabIndex = -1;
  const close = make('button', '닫기 ×', 'subtle'); close.type = 'button'; close.setAttribute('aria-label', title + ' 닫기');
  header.append(heading, close);
  const body = make('div', '', 'settings-body'), footer = make('div', '', 'settings-footer');
  const note = make('p', '새 실행에 사용할 설정입니다. 열람 중인 기존 결과는 바뀌지 않습니다.', 'hint');
  body.append(note, ...nodes);
  const cancel = make('button', '변경 취소', 'secondary'); cancel.type = 'button';
  const status = make('p', '', 'settings-notice'); status.setAttribute('role', 'status');
  footer.append(cancel, ...actions);
  dialog.append(header, body, status, footer); document.body.append(dialog);
  let opener = null, snapshot = [], help = null;
  const fields = () => [...dialog.querySelectorAll('input:not([type=file]),select,textarea:not([readonly])')];
  function remember() { snapshot = fields().filter(el => !el.disabled).map(el => [el, el.value, el.checked]); }
  function dismiss() { if (help) { help.remove(); help = null; body.hidden = false; footer.hidden = false; close.textContent = '닫기 ×'; close.setAttribute('aria-label', title + ' 닫기'); } else dialog.close(); }
  close.onclick = dismiss;
  dialog.addEventListener('cancel', e => { e.preventDefault(); dismiss(); });
  dialog.addEventListener('close', () => {
    if (help) { help.remove(); help = null; body.hidden = false; footer.hidden = false; close.textContent = '닫기 ×'; close.setAttribute('aria-label', title + ' 닫기'); }
    if (opener?.isConnected && opener.getClientRects().length) opener.focus({preventScroll:true});
  });
  cancel.onclick = () => {
    for (const [el, value, checked] of snapshot) if (!el.disabled && (el.value !== value || el.checked !== checked)) {
      el.value = value; el.checked = checked;
      el.dispatchEvent(new Event('input', {bubbles:true})); el.dispatchEvent(new Event('change', {bubbles:true}));
    }
    dialog.close();
  };
  // 도움말은 같은 패널 안에서 열어 중첩 모달을 만들지 않는다.
  dialog.addEventListener('settings-help', e => {
    help?.remove(); help = make('div', '', 'settings-body settings-help'); help.tabIndex = -1;
    help.append(e.detail); body.hidden = true; footer.hidden = true; footer.before(help); close.textContent = '설정으로 돌아가기'; close.setAttribute('aria-label', '설정으로 돌아가기'); help.focus();
  });
  return {
    dialog, body, footer, note, status,
    open(button) { if (document.querySelector('dialog[open]')) return; opener = button; remember(); dialog.showModal(); body.scrollTop = 0; heading.focus(); },
    close() { if (dialog.open) dialog.close(); },
    reset() { snapshot = []; this.close(); },
    accepted() { remember(); },
    mirror(ids) {
      const update = () => { status.textContent = ids.map(id => document.getElementById(id)?.textContent).filter(Boolean).join('\n'); };
      const observer = new MutationObserver(update);
      for (const id of ids) { const el = document.getElementById(id); if (el) observer.observe(el, {childList:true,characterData:true,subtree:true}); }
      update();
    },
  };
}
