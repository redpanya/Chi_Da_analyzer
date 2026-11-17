import {createCompute} from './compute.js';
import {createModelLibrary} from './model-library.js';
export function createFolders({api, onApplied, onPicking, onLibrary}) {
  const $ = id => document.getElementById(id);
  let applied = '', busy = false, saving = false, serial = 0;
  const compute = createCompute({api, onApplying: () => {serial++;}});
  const library = createModelLibrary(api);
  function controls() {
    $('model-root').disabled = saving || busy;
    $('apply-model-folder').disabled = saving || busy;
  }
  function set(value) {
    onLibrary?.(value.library);
    compute.set(value.compute, value.busy);
    if (!applied || $('model-root').value === applied) $('model-root').value = value.models;
    applied = value.models; busy = value.busy;
    library.rootChanged(applied);
    $('model-folder-current').textContent = `현재 적용: ${applied}`;
    $('model-folder-state').textContent = value.problem || (busy ? '진행 중인 작업을 마치면 저장 폴더를 변경할 수 있습니다.' : '');
    controls();
  }
  $('model-folder-form').onsubmit = async event => {
    event.preventDefault();
    if (saving || busy) return;
    let failed = false;
    saving = true; serial++; controls(); onPicking?.('apply-model-folder', true);
    $('model-folder-notice').textContent = '';
    try {
      const selected = await api('pick-path', {kind:'folder'});
      if (!selected.path || selected.path === applied) return;
      $('model-folder-notice').textContent = '폴더의 접근 권한과 저장 상태를 확인하고 있습니다…';
      const value = await api('model-folder', {path: selected.path});
      $('model-root').value = value.models; set(value);
      await library.refresh();
      $('model-folder-notice').textContent = '경로를 적용했습니다. 다음 앱 실행에도 유지됩니다. 기존 파일은 그대로 보존했습니다.';
      await onApplied();
    } catch (error) { failed = true; $('model-folder-notice').textContent = error.message; }
    finally { saving = false; controls(); onPicking?.('apply-model-folder', false, failed); }
  };
  return {set, async refresh() {
    if (saving || compute.isSaving()) return;
    const request = ++serial;
    try { const value = await api('folders', {}); if (request === serial) {set(value); await library.refresh();} }
    catch (error) { if (request === serial) $('model-folder-state').textContent = error.message; }
  }};
}
