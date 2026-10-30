import {createSettingsPanel} from './settings-panel.js';
import {compactVersionPicker} from './version-picker.js';
const $ = id => document.getElementById(id);
const make = (tag, text = '', cls = '') => {const n = document.createElement(tag); n.textContent = text; n.className = cls; return n;};
function range(first, last) {
  const nodes = []; let node = first;
  while (node) { nodes.push(node); if (node === last) return nodes; node = node.nextElementSibling; }
  throw Error('화면 구성 범위를 찾지 못했습니다.');
}
function group(nodes, cls) { const box = make('div', '', cls); nodes[0].before(box); box.append(...nodes); return box; }
function fold(title, nodes) { const box = make('details', '', 'workspace-details'); nodes[0].before(box); box.append(make('summary', title), ...nodes); return box; }
function launcher(panel, id, text) { const b = make('button', text, 'primary'); b.id = id; b.type = 'button'; b.setAttribute('aria-haspopup', 'dialog'); b.setAttribute('aria-controls', panel.dialog.id); b.onclick = () => panel.open(b); return b; }
function version(selectId, toolbar, versions) { $(selectId).setAttribute('aria-label', ({'speech-version':'저장된 전사 버전','voices-version':'화자 분석 버전','context-version':'문맥 결과 버전','context-clips-version':'클립 결과 버전'})[selectId]); const picker = compactVersionPicker($(selectId)); toolbar.append(picker.details); versions.push(picker); }

// 시작할 때 한 번만 배치한다. 폴링 때 폼·결과 노드를 복제하거나 재구성하지 않는다.
export function createWorkspaceLayout() {
  const panels = [], versions = [];
  document.body.classList.add('result-first');
  const contextToolbar = group([$('context-version').parentElement.parentElement], 'result-toolbar');
  $('context-view-panel').prepend(contextToolbar);
  const contextDelete=make('button','선택 버전 삭제','secondary danger');contextDelete.id='context-delete';contextDelete.disabled=true;contextToolbar.append(contextDelete);
  contextToolbar.append(document.querySelector('.context-list-toolbar'));
  const resultState = make('p', '', 'hint'); resultState.id = 'context-result-state'; contextToolbar.after(resultState);
  const contextJob = group(range($('context-task-kind'), $('context-log')), 'job-status');
  contextJob.id = 'context-job'; contextToolbar.after(contextJob);
  contextJob.append($('context-stop'));
  fold('다른 결과의 이전 작업 상태', [contextJob]).id='context-job-history';
  contextToolbar.append($('context-resume'));
  const contextSettings = createSettingsPanel('context-settings', '새 문맥 분석 설정',
    [$('context-mode-note'), ...range($('context-background-form'), $('context-offset').closest('details'))], [$('context-generate')]);
  contextSettings.mirror(['context-notice', 'context-status']); panels.push(contextSettings);
  contextToolbar.append(launcher(contextSettings, 'context-new', '새 분석'));
  const external = make('button', '외부 AI로 작업', 'secondary'); external.id = 'context-external-open'; contextToolbar.append(external);
  version('context-version', contextToolbar, versions);
  $('context-version').addEventListener('change', () => $('context-open').click()); $('context-open').hidden = true;
  const contextReady = make('p', '', 'readiness'); contextReady.id = 'context-readiness'; contextToolbar.after(contextReady);

  const clipPanel = $('context-clips-panel');
  const clipToolbar = group([$('context-clips-version').parentElement], 'result-toolbar'); clipPanel.prepend(clipToolbar);
  const clipDelete=make('button','선택 버전 삭제','secondary danger');clipDelete.id='context-clips-delete';clipDelete.disabled=true;clipToolbar.append(clipDelete);
  const deletionNotice=make('p');deletionNotice.id='context-delete-notice';deletionNotice.setAttribute('role','status');$('context-view-panel').before(deletionNotice);
  const clipJob = group(range($('context-clips-progress-status'), $('context-clips-elapsed')), 'job-status'); clipJob.id = 'clips-job'; clipToolbar.after(clipJob);
  clipJob.append($('context-clips-stop')); fold('다른 결과의 이전 작업 상태', [clipJob]).id='clips-job-history'; clipToolbar.append($('context-clips-resume'));
  const clipSettings = createSettingsPanel('clip-settings', '새 클립 후보 설정',
    range(clipPanel.querySelector('.context-inputs'), $('context-clips-offset').closest('details')), [$('context-clips-generate')]);
  clipSettings.mirror(['context-clips-notice', 'context-clips-progress-status']); panels.push(clipSettings);
  clipToolbar.append(launcher(clipSettings, 'clips-new', '새 클립 후보'), $('context-clips-external'));
  $('context-clips-external').textContent = '외부 AI로 작업';
  version('context-clips-version', clipToolbar, versions);
  document.querySelector('label[for=context-clips-version]').hidden = true;
  const clipReady = make('p', '', 'readiness'); clipReady.id = 'clips-readiness'; clipToolbar.after(clipReady);
  // 기본 설명은 새 작업 패널에서만 표시한다.
  const clipIntro = $('context-clips-heading').nextElementSibling;
  clipSettings.body.prepend(clipIntro);

  const speech = $('speech-panel');
  const speechToolbar = group([$('speech-version').parentElement], 'result-toolbar'); speech.prepend(speechToolbar);
  const speechSettings = createSettingsPanel('speech-settings', '새 음성 전사 설정', [speech.querySelector('.speech-steps')], [$('transcribe')]);
  panels.push(speechSettings); speechSettings.mirror(['speech-notice', 'speech-status']);
  speechToolbar.append(launcher(speechSettings, 'speech-new', '새 전사·이어하기')); version('speech-version', speechToolbar, versions);
  const speechReady = make('p', '', 'readiness'); speechReady.id = 'speech-readiness'; speechToolbar.after(speechReady);
  const speechJob = group(range($('speech-status'), $('speech-stop').parentElement), 'job-status'); speechJob.id = 'speech-job';
  speechReady.after(speechJob, $('speech-notice'), $('speech-search'));
  fold('추출한 음성·저장 자료', [$('speech-audio-box'), $('sam-audio-box')]);
  fold('전사 범위·인식이 어려운 구간', [$('speech-coverage'), $('speech-gaps')]);
  speech.querySelector('.exports').before($('speech-next-step').parentElement);

  const voices = $('voices-panel');
  const versionArticle = $('voices-version').closest('article');
  const voiceToolbar = group([versionArticle], 'result-toolbar'); voices.prepend(voiceToolbar);
  versionArticle.querySelector('h3').hidden = true;
  const voiceSettings = createSettingsPanel('voice-settings', '새 화자 분석 설정', [$('voices-setup')], [$('voices-run')]);
  panels.push(voiceSettings); voiceSettings.mirror(['voices-notice', 'voices-status']);
  voiceToolbar.append(launcher(voiceSettings, 'voices-new', '새 화자 분석')); version('voices-version', voiceToolbar, versions);
  const voiceReady = make('p', '', 'readiness'); voiceReady.id = 'voices-readiness'; voiceToolbar.after(voiceReady);
  const voiceJob = group(range($('voices-status'), $('voices-stop')), 'job-status'); voiceJob.id = 'voices-job'; voiceReady.after(voiceJob, $('voices-notice'));
  voices.append($('voices-next-step'));

  const reactionSettings = createSettingsPanel('reaction-settings', '채팅 반응 분석 기준', [$('analysis-settings')]);
  reactionSettings.note.textContent = '분석 기준 변경 후 화면의 채팅 반응 분석 버튼을 눌러 적용하세요.';
  panels.push(reactionSettings);
  for(const input of $('analysis-settings').querySelectorAll('input,select'))input.setAttribute('form', 'analysis-form');
  $('analysis-form').append(launcher(reactionSettings, 'reaction-options', '분석 기준'));

  // 5개 기본 목적과 보조 화면. 기존 내부 단계 ID는 연결 호환성을 위해 유지한다.
  const nav = document.querySelector('main > nav'); nav.setAttribute('aria-label', '작업 화면');
  for (const [id, text] of [[1,'가져오기'],[3,'음성 전사'],[4,'화자 구분 · 선택'],[5,'분석·재생'],[6,'AI 문맥']]) $('step'+id).textContent = text;
  const utilities = make('div', '', 'workspace-utilities'); document.querySelector('main > header > .play-actions').prepend(utilities);
  utilities.append($('step7'), $('step8')); $('step7').textContent = '작업 기록'; $('step8').textContent = '외부 AI';
  for (const id of ['step7','step8']) $(id).className = 'subtle';
  external.onclick = () => $('step8').click();
  const downloadDetails = make('section', '', 'download-details'); downloadDetails.id = 'download-details';
  downloadDetails.append($('download-panel')); $('import-panel').append(downloadDetails);
  $('step2').textContent = '선택 VOD 진행'; $('step2').className = 'subtle'; $('step2').hidden = true; utilities.append($('step2'));
  $('download-panel').classList.add('download-content');
  const assets = make('details', '', 'workspace-details'); assets.id = 'project-assets';
  assets.append(make('summary', '선택 VOD의 저장 경로·자료 링크'), $('project-path'), $('download-panel').querySelector('.exports'));

  const queueSettings = createSettingsPanel('queue-options', '등록할 VOD의 작업 설정',
    [$('queue-work-options')], [$('queue-apply')]);
  queueSettings.note.textContent = '새로 등록할 항목에 적용됩니다. 기존 대기 항목은 선택 후 ‘설정 적용’을 눌러주세요.';
  queueSettings.mirror(['queue-notice']); panels.push(queueSettings);
  $('queue-settings-launcher').prepend(launcher(queueSettings, 'queue-options-open', '작업 설정'));
  $('settings-page').append(document.querySelector('.folder-settings'), $('compute-settings'), assets);
  // 리포트와 외부 AI는 독립 화면을 유지하되 결과 확인 동선부터 보여준다.
  fold('현재 PC 사양', [$('report-hardware').previousElementSibling, $('report-hardware')]);
  fold('실행 당시 PC 사양', [$('report-run-hardware')]);
  fold('성능 리포트 JSON·이메일 안내', [document.querySelector('.report-export-box')]);
  const externalPanel = $('external-panel');
  const exportCard = group(range(externalPanel.querySelector('fieldset'), $('external-prompt').closest('details')), 'external-task');
  exportCard.prepend(make('h3', '자료 내보내기'));
  const importCard = group(range($('external-file').previousElementSibling.previousElementSibling, $('external-preview-result')), 'external-task');
  group([exportCard, importCard], 'external-workspace');
  externalPanel.append($('external-list').previousElementSibling, $('external-list'));
  fold('JSON 직접 붙여넣기', [$('external-json').previousElementSibling, $('external-json')]);

  // 제목은 공통 헤더 한 곳에만 표시한다. 도움말은 해당 페이지 헤더로 연결한다.
  for (const id of ['speech-title','voices-title','context-title','external-title','explore-title']) $(id).hidden = true;
  for (const panel of [speech, voices, $('context-panel'), $('external-panel'), $('report-panel'), $('explore-panel')]) {
    const title = panel.querySelector(':scope > h2, :scope > .section-heading'); if (title) title.hidden = true;
  }
  $('context-clips-heading').hidden = true; $('context-list-title').hidden = true;
  speech.querySelector('h3[data-help=transcript]').hidden = true;
  document.querySelector('label[for=speech-version]').hidden = true;
  $('queue-heading').hidden = true;
  const subtitle = make('p', '', 'workspace-subtitle'); subtitle.id = 'workspace-subtitle'; $('heading').after(subtitle);
  document.querySelector('.eyebrow').hidden = true; document.querySelector('.local-badge').hidden = true;
  const more = fold('더보기', [$('delete-project')]); more.className = 'header-more';
  const moreActions = make('div', '', 'header-more-actions');
  moreActions.append($('open-clip-studio'), $('step7'), $('step8'), $('delete-project')); more.append(moreActions);
  document.querySelector('.clip-studio-launch').remove();
  const closeMore = () => {more.open = false;};
  moreActions.addEventListener('click', event => {if (event.target.closest('button')) closeMore();});
  document.addEventListener('click', event => {if (!more.contains(event.target)) closeMore();});
  more.addEventListener('keydown', event => {if (event.key === 'Escape') {closeMore(); more.querySelector('summary').focus();}});

  const overview = make('div', '', 'global-jobs'); overview.id = 'global-jobs'; overview.hidden = true; nav.after(overview);
  const jobs = make('div'); jobs.id = 'global-job-rows'; overview.append(jobs);
  const queueStatus = make('p', '', 'hint'); queueStatus.id = 'global-queue-state'; overview.append(queueStatus);
  const queueLink = make('button', '순차 작업 열기', 'subtle'); queueLink.onclick = () => $('new').click(); overview.append(queueLink);
  return {closeMore, panels, versions, contextSettings, clipSettings, speechSettings, voiceSettings, queueSettings};
}
