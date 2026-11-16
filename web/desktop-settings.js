// 데스크톱 앱의 설정을 열었을 때만 로컬 업데이트 상태를 읽는다.
export function bindDesktopSettings(panel, bridge = globalThis.window?.chidaDesktop) {
  if (!panel || !bridge) return () => {};
  const find = id => panel.querySelector('#' + id);
  const button = action => find('desktop-update-' + action);
  const status = find('desktop-update-status'), progress = find('desktop-update-progress');
  const notices = find('desktop-licenses');
  find('web-licenses').hidden = true;
  find('web-latest-release').hidden = true;
  find('desktop-update').hidden = false;
  notices.hidden = false;
  let visible = false, timer, revision = 0, reading = false;
  function render(state) {
    const {phase, currentVersion, version, platform, received, size, message} = state;
    const mac = platform === 'darwin';
    find('desktop-update-version').textContent = '현재 버전 ' + currentVersion +
      (version && version !== currentVersion ? ' / 배포 버전 ' + version : '');
    find('desktop-update-guide').textContent = mac
      ? 'DMG를 원하는 폴더에 받은 뒤 앱을 종료하고, DMG 안의 앱을 기존 앱 위치에 복사해 교체하세요.'
      : '포터블 업데이트를 받은 뒤 교체 후 재실행을 누르면 현재 앱 폴더에서 새 버전으로 바뀝니다.';
    button('check').hidden = ['downloading', 'downloaded', 'ready', 'applying'].includes(phase);
    button('check').disabled = phase === 'checking';
    button('download').hidden = phase !== 'available';
    button('download').textContent = mac ? 'DMG 다운로드' : '포터블 업데이트 다운로드';
    button('cancel').hidden = phase !== 'downloading';
    button('reveal').hidden = phase !== 'downloaded';
    button('apply').hidden = phase !== 'ready';
    progress.hidden = phase !== 'downloading';
    if (!progress.hidden && size > 0) {
      progress.max = size;
      progress.value = received;
    } else {
      progress.removeAttribute('value');
    }
    const percentage = phase === 'downloading' && size > 0 ? ' (' + Math.floor(received / size * 100) + '%)' : '';
    const nextMessage = (message || (phase === 'checking' ? 'GitHub에서 새 버전을 확인하고 있습니다.' : '')) + percentage;
    if (status.textContent !== nextMessage) status.textContent = nextMessage;
  }
  async function refresh() {
    if (!visible || reading) return;
    reading = true;
    const stamp = revision;
    try {
      const result = await bridge.state();
      if (visible && stamp === revision) render(result);
    } catch (error) {
      if (visible && stamp === revision) status.textContent = error.message;
    } finally {reading = false;}
  }
  for (const action of ['check', 'download', 'cancel', 'reveal', 'apply', 'notices']) {
    const control = action === 'notices' ? notices : button(action);
    control.onclick = async () => {
      control.disabled = true;
      revision++;
      try {
        await bridge[action]();
        await refresh();
      } catch (error) {
        if (visible) status.textContent = error.message;
      } finally {control.disabled = false;}
    };
  }
  // 한 창의 페이지 전환 및 뒤로 가기 캐시에서는 이전 폴링을 종료한다.
  let selected = false, suspended = false;
  function sync() {
    const active = selected && !suspended && !document.hidden;
    if (active === visible) return;
    visible = active;
    revision++;
    clearInterval(timer);
    if (active) {refresh(); timer = setInterval(refresh, 1000);}
  }
  document.addEventListener('visibilitychange', sync);
  window.addEventListener('pagehide', () => {suspended = true; sync();});
  window.addEventListener('pageshow', () => {suspended = false; sync();});
  return active => {selected = active; sync();};
}
