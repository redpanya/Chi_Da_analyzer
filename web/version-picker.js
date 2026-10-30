export function shortVersion(label) {
  const parts = label.split(' · ').map(s => s.trim()).filter(Boolean);
  // 존재하는 설명만 축약한다. 과거 결과의 모델·완료 상태를 추정하지 않는다.
  const date = label.match(/20\d{2}-\d{2}-\d{2}[T ]\d{2}:\d{2}/)?.[0];
  const names = parts.filter(p => !/^20\d{2}-/.test(p) && !/^[a-f\d]{12,}$/i.test(p));
  return [date?.slice(5).replace('T', ' '), ...names.slice(0, 2).map(s => s.length > 28 ? s.slice(0, 27) + '…' : s)].filter(Boolean).join(' · ') || label;
}

export function compactVersionPicker(select) {
  const details = document.createElement('details'); details.className = 'version-details';
  const summary = document.createElement('summary'); summary.textContent = '버전 정보';
  const text = document.createElement('p'); details.append(summary, text);
  details.addEventListener('keydown', event => {if(event.key==='Escape'){details.open=false;summary.focus();}});
  // 실제 ID와 option 값은 그대로 두고 전체 설명을 별도로 보존한다.
  function update() {
    const options = [...select.options];
    const labels = options.map(o => shortVersion(o.dataset.fullLabel || o.textContent));
    for (const [i, option] of options.entries()) {
      option.dataset.fullLabel ||= option.textContent;
      const label = labels[i] + (option.value && labels.filter(s => s === labels[i]).length > 1 ? ' · ' + option.value.slice(0, 8) : '');
      if (option.textContent !== label) option.textContent = label;
      option.title = option.dataset.fullLabel;
    }
    const selected = select.selectedOptions[0];
    const full = selected?.dataset.fullLabel || '저장된 결과 없음';
    select.title = full;
    text.textContent = full + (selected?.value ? '\nID: ' + selected.value : '');
  }
  new MutationObserver(update).observe(select, {childList:true,subtree:true});
  select.addEventListener('change', update); update();
  return {details, update};
}
