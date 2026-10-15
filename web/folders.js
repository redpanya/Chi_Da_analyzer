import {createCompute} from './compute.js';
export function createFolders({api, onApplied}) {
  const $ = id => document.getElementById(id);
  let applied = '', busy = false, saving = false, serial = 0;
  const compute = createCompute({api, onApplying: () => {serial++;}});
  function controls() {
    $('model-root').disabled = saving || busy;
    $('apply-model-folder').disabled = saving || busy || $('model-root').value === applied;
  }
  function set(value) {
    compute.set(value.compute, value.busy);
    if (!applied || $('model-root').value === applied) $('model-root').value = value.models;
    applied = value.models; busy = value.busy;
    $('model-folder-current').textContent = `현재 적용: ${applied}`;
    const names = {speech: '음성 전사', voices: '화자 구분', context: 'AI 문맥 정리'};
    $('model-folder-state').textContent = (busy ? '작업 완료 또는 중단 정리 후 경로를 변경할 수 있습니다. ' : '') + (value.problem || Object.entries(names).map(([key, name]) => `${name}: ${value.ready[key] ? '준비됨' : '준비 필요'}`).join(' · '));
    controls();
  }
  $('model-root').oninput = () => {
    $('model-folder-notice').textContent = $('model-root').value === applied ? '' : '입력한 경로는 ‘경로 적용’을 누른 뒤 사용합니다.';
    controls();
  };
  $('model-folder-form').onsubmit = async event => {
    event.preventDefault();
    if (saving || busy) return;
    saving = true; serial++; controls();
    $('model-folder-notice').textContent = '폴더의 접근 권한과 저장 상태를 확인하고 있습니다…';
    try {
      const value = await api('model-folder', {path: $('model-root').value});
      $('model-root').value = value.models; set(value);
      $('model-folder-notice').textContent = '경로를 적용했습니다. 다음 앱 실행에도 유지됩니다. 기존 파일은 그대로 보존했습니다.';
      await onApplied();
    } catch (error) { $('model-folder-notice').textContent = error.message; }
    finally { saving = false; controls(); }
  };
  return {set, async refresh() {
    if (saving || compute.isSaving()) return;
    const request = ++serial;
    try { const value = await api('folders', {}); if (request === serial) set(value); }
    catch (error) { if (request === serial) $('model-folder-state').textContent = error.message; }
  }};
}
