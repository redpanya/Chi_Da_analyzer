// Windows 설정만 노출한다. 실행 중 변경은 서버에서도 차단한다.
export function createCompute({api, onApplying = () => {}}) {
  const $ = id => document.getElementById(id);
  let busy = false, saving = false, applied = 'cpu';
  function controls() {
    $('compute-mode').disabled = busy || saving;
    $('compute-apply').disabled = busy || saving || $('compute-mode').value === applied;
    $('compute-refresh').disabled = busy || saving;
  }
  function set(value, running = false, ownResponse = false) {
    if (saving && !ownResponse) return;
    $('compute-settings').hidden = !value?.visible;
    if (!value?.visible) return;
    if ($('compute-mode').value === applied) $('compute-mode').value = value.mode;
    applied = value.mode; busy = running;
    $('compute-status').textContent = value.note + (busy ? ' 작업 완료 또는 중단 후 변경할 수 있습니다.' : '');
    controls();
  }
  async function save(refresh) {
    if (busy || saving) return;
    saving = true; onApplying(); controls();
    $('compute-notice').textContent = refresh ? 'GPU를 확인하고 있습니다…' : '처리 장치를 적용하고 있습니다…';
    try {
      const value = await api('compute', refresh ? {refresh: true} : {mode: $('compute-mode').value});
      $('compute-mode').value = value.compute.mode; set(value.compute, value.busy, true);
      $('compute-notice').textContent = refresh ? 'GPU 확인을 마쳤습니다.' : '다음 작업부터 적용하며 앱을 다시 실행해도 유지됩니다.';
    } catch (error) { $('compute-notice').textContent = error.message; }
    finally { saving = false; controls(); }
  }
  $('compute-mode').onchange = controls;
  $('compute-form').onsubmit = event => {event.preventDefault(); return save(false);};
  $('compute-refresh').onclick = () => save(true);
  return {set, isSaving: () => saving};
}
