const notifications = new Map();

export function showToast(message, {key = message, action, actionLabel = '작업 열기'} = {}) {
  if (!message || notifications.has(key)) return;
  let region = document.getElementById('ui-toasts');
  if (!region) {
    region = document.createElement('div'); region.id = 'ui-toasts';
    region.setAttribute('role', 'status'); region.setAttribute('aria-live', 'polite');
    document.body.append(region);
  }
  const item = document.createElement('div'); item.className = 'ui-toast';
  const text = document.createElement('span'); text.textContent = message; item.append(text);
  const countdown = document.createElement('small'); countdown.className = 'ui-toast-countdown';
  countdown.setAttribute('aria-hidden', 'true');
  const deadline = Date.now() + 15000;
  const updateCountdown = () => {countdown.textContent = `${Math.max(0, Math.ceil((deadline - Date.now()) / 1000))}초 후 닫힘`;};
  updateCountdown();
  const close = () => {
    const notification = notifications.get(key);
    clearTimeout(notification?.timer); clearInterval(notification?.ticker);
    notifications.delete(key); item.remove();
  };
  if (action) {
    const open = document.createElement('button'); open.textContent = actionLabel;
    open.onclick = () => {close(); action();}; item.append(open);
  }
  const dismiss = document.createElement('button'); dismiss.textContent = '×'; dismiss.setAttribute('aria-label', '알림 닫기 (15초 후 자동 닫힘)');
  dismiss.onclick = close; item.append(countdown, dismiss); region.append(item);
  notifications.set(key, {item, close, timer: setTimeout(close, 15000), ticker: setInterval(updateCountdown, 1000)});
  notifications.get(key).timer.unref?.();
  notifications.get(key).ticker.unref?.();
  while (notifications.size > 4) notifications.values().next().value.close();
}

export function exposeDetails(root = document) {
  const reveal = node => {
    const details = [...(node.matches?.('details') ? [node] : []), ...(node.querySelectorAll?.('details') || [])];
    for (const item of details) {
      if (!item.open) item.open = true;
      item.classList.add('always-visible');
      const summary = item.querySelector('summary');
      if (summary) summary.tabIndex = -1;
    }
  };
  reveal(root);
  root.addEventListener('click', event => {
    const summary = event.target.closest?.('summary');
    if (summary?.parentElement.classList.contains('always-visible') && !event.target.closest('button,a,input,select,textarea')) event.preventDefault();
  }, true);
  new MutationObserver(records => {
    for (const record of records) {
      if (record.type === 'attributes') reveal(record.target);
      else for (const node of record.addedNodes) reveal(node);
    }
  }).observe(root, {subtree:true, childList:true, attributes:true, attributeFilter:['open']});
}
