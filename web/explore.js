import {timecode} from './player.js';
import {createTimeline, selectedRange, speakerColor} from './timeline.js';
const $ = id => document.getElementById(id);
const labels = {chat: '채팅', speech: '발언', reaction: '반응'};
const statuses = {automatic: '자동 추정', confirmed: '사용자 확인', failed: '화자인식 실패'};

export function createExplorer({api, player}) {
  let project = null, key = '', active = false, info = null, serial = 0, contextSerial = 0, infoSerial = 0;
  let appliedOffset = 0;
  let center = 0, selection = null, cursor = 0, total = 0, lastBucket = -1, searchMode = false, contextPage = {chat: 0, speech: 0};
  const video = $('player');
  const identity = () => ({root: project.root, vod_id: project.vod_id, chat_offset_ms: Math.round(appliedOffset * 1000)});
  const message = value => { $('explore-message').textContent = value; };
  const timeline = createTimeline({canvas: $('unified-graph'), onSeek: jump, onRange: choose});
  function node(tag, text, className = '') { const el = document.createElement(tag); el.textContent = text; el.className = className; return el; }
  function remember() {
    if (project) sessionStorage.setItem('explore:' + project.path, JSON.stringify({selection, offset: appliedOffset}));
  }
  function draw() {
    timeline.set(info, center, selection);
    $('explore-position').max = info?.duration_ms || 1;
    $('explore-position').value = center;
    $('explore-clock').textContent = `${timecode(center)} / ${timecode(info?.duration_ms || 0)}`;
  }
  function pauseFollow() { $('explore-follow').checked = false; }
  function rangeLimit() { return Number.isFinite(video.duration) && video.getAttribute('src') ? Math.round(video.duration * 1000) : info?.video_ms || info?.duration_ms || 0; }
  function choose(start, end) {
    try {
      selection = selectedRange(start, end, rangeLimit());
      $('explore-start').value = selection.start_ms / 1000; $('explore-end').value = selection.end_ms / 1000;
      $('explore-range-note').textContent = `${timecode(start)} ~ ${timecode(end)} · 이번 탭에 선택 보존 · 7단계 목록에 추가해 영상으로 저장`;
      message(''); remember(); draw();
    } catch (error) { message(error.message); }
  }
  function jump(ms, playing = false) {
    center = ms; pauseFollow(); lastBucket = -1; draw(); contextPage = {chat: 0, speech: 0}; contexts();
    if (project?.tasks.video.state === 'complete') player.seek(ms, playing);
    else message('영상 준비 전입니다. 선택한 시각의 자료를 먼저 보여드립니다.');
  }
  function rowView(row, actions = true) {
    const article = node('article', '', 'unified-row'); article.dataset.start = row.start_ms; article.dataset.end = row.end_ms;
    const jumpButton = node('button', `${timecode(row.at_ms)} · ${labels[row.kind]}${row.kind === 'speech' ? ' ~ ' + timecode(row.end_ms) : ''}`, 'candidate-jump');
    jumpButton.dataset.time = row.at_ms; jumpButton.onclick = () => jump(row.at_ms);
    article.append(jumpButton);
    if (row.kind === 'speech') {
      const name = node('p', `${row.speaker_name || '화자 미분석'}${row.status === 'failed' ? '' : ' · ' + (statuses[row.status] || '배정 없음')}${row.speaker_reason ? ' · ' + row.speaker_reason : ''}`, 'hint');
      name.style.borderLeft = `3px solid ${speakerColor(row.speaker)}`; name.style.paddingLeft = '8px'; article.append(name);
    } else if (row.nickname) article.append(node('strong', row.nickname, 'hint'));
    article.append(node('p', row.text));
    if (row.kind === 'reaction') article.append(node('p', row.detail, 'hint'));
    if (row.kind === 'speech' && (row.corrected || row.repeat_review || row.boundary_review || row.encoding_review)) article.append(node('p', [row.corrected && '교정문', row.repeat_review && '반복 인식 검토', row.boundary_review && '조각 경계 검토', row.encoding_review && (row.corrected ? '원출력 문자 오류 · 교정 반영' : '문자 인식 오류 · 원음 확인 필요')].filter(Boolean).join(' · '), 'hint'));
    if (row.kind !== 'speech' && appliedOffset) article.append(node('p', `원본 ${timecode(row.raw_start_ms)} · 채팅 보정 ${appliedOffset}초`, 'hint'));
    if (actions) {
      const bar = node('div', '', 'play-actions');
      const play = node('button', '앞뒤 문맥 재생', 'subtle'); play.disabled = project?.tasks.video.state !== 'complete';
      play.onclick = () => jump(Math.max(0, row.at_ms - Number($('explore-context').value) * 1000), true);
      const range = node('button', '이 구간 선택', 'subtle');
      range.onclick = () => choose(Math.min(row.start_ms, Math.max(0, rangeLimit() - 1000)), Math.min(rangeLimit(), Math.max(row.end_ms, row.start_ms + 1000)));
      bar.append(play, range); article.append(bar);
    }
    return article;
  }
  async function results() {
    if (!project || !active) return;
    const request = ++serial, selected = project.path;
    $('explore-count').textContent = '조회 중…'; $('explore-next').disabled = true;
    try {
      const data = await api('explore-search', {...identity(), source: searchMode ? $('explore-source').value : 'reaction',
        query: searchMode ? $('explore-query').value : '', speaker: $('explore-speaker').value, cursor});
      if (request !== serial || selected !== project?.path || !active) return;
      total = data.total; $('explore-results').replaceChildren(...data.items.map(row => rowView(row)));
      if (!data.items.length) $('explore-results').append(node('p', '현재 조건에 해당하는 저장 결과가 없습니다.', 'empty'));
      $('explore-count').textContent = `${searchMode ? '검색 결과' : '반응 후보'} ${total}건 · ${Math.floor(cursor / 100) + 1}쪽`;
      $('explore-prev').disabled = cursor === 0; $('explore-next').disabled = data.next_cursor === null;
      $('explore-notes').textContent = data.notes.join(' · ');
    } catch (error) { if (request === serial) { message(error.message); $('explore-count').textContent = '조회 실패'; } }
  }
  async function contexts() {
    if (!project || !active) return;
    const request = ++contextSerial, selected = project.path, seconds = Number($('explore-context').value);
    const start = Math.max(0, center - seconds * 1000), end = Math.min(605400000, center + seconds * 1000 + 1);
    $('explore-window').textContent = `${timecode(start)} ~ ${timecode(end)} · 반응과 발언의 인과관계를 판정하지 않습니다.`;
    const filter = $('explore-speaker'); $('explore-filter-note').textContent = filter.value ? `발언 필터: ${filter.selectedOptions[0].textContent} · 채팅과 반응은 유지` : '모든 화자 · 채팅과 발언을 같은 범위에서 표시';
    await Promise.all(['chat', 'speech'].map(async source => {
      try {
        const data = await api('explore-search', {...identity(), source, start_ms: start, end_ms: end,
          speaker: $('explore-speaker').value, cursor: contextPage[source]});
        if (request !== contextSerial || selected !== project?.path || !active) return;
        $(`unified-${source}`).replaceChildren(...data.items.map(row => rowView(row, false)));
        if (!data.items.length) $(`unified-${source}`).append(node('p', '이 범위·필터에 표시할 자료가 없습니다. 위 자료 상태를 확인하세요.', 'empty'));
        $(`unified-${source}-count`).textContent = `${data.total}건 · ${Math.floor(contextPage[source] / 100) + 1}쪽`;
        $(`unified-${source}-prev`).disabled = !contextPage[source]; $(`unified-${source}-next`).disabled = data.next_cursor === null;
        const issues = data.notes.filter(note => note.includes('못했습니다'));
        if (issues.length) message(issues.join(' · '));
        highlight();
      } catch (error) { if (request === contextSerial) message(error.message); }
    }));
  }
  function highlight() {
    for (const el of $('unified-speech').children) {
      const current = Number(el.dataset.start) <= center && center < Number(el.dataset.end);
      el.classList.toggle('now', current);
      if (current && $('explore-follow').checked) {const list = $('unified-speech'); list.scrollTop += el.getBoundingClientRect().top - list.getBoundingClientRect().top;}
    }
  }
  async function refresh() {
    if (!active || !project) return;
    const request = ++infoSerial, selected = project.path;
    try {
      const data = await api('explore-info', identity());
      if (request !== infoSerial || selected !== project?.path || !active) return;
      info = data; $('explore-notes').textContent = data.notes.join(' · ');
      const filter = $('explore-speaker'), previous = filter.value;
      filter.replaceChildren(...[['', '모든 화자'], ['failed', '화자인식 실패'], ['unassigned', '화자 미분석'], ...Object.entries(data.speakers)].map(([id, name]) => { const option = node('option', name); option.value = id; return option; }));
      if ([...filter.options].some(option => option.value === previous)) filter.value = previous;
      draw(); results(); contexts();
    } catch (error) { if (request === infoSerial) message(error.message); }
  }
  function reset(value) {
    info = null; center = 0; selection = null; cursor = 0; contextPage = {chat: 0, speech: 0}; searchMode = false; lastBucket = -1;
    $('explore-query').value = ''; $('explore-source').value = 'all'; $('explore-speaker').replaceChildren(new Option('모든 화자', ''));
    appliedOffset = 0; $('explore-offset').value = '0'; $('explore-start').value = '0'; $('explore-end').value = '10'; $('explore-range-note').textContent = '시작·끝 버튼 또는 시간축 드래그로 범위를 선택하세요.';
    $('explore-title').textContent = value?.metadata.title || ''; $('explore-notes').textContent = ''; message(''); pauseFollow();
    for (const id of ['explore-results', 'unified-chat', 'unified-speech']) $(id).replaceChildren();
    if (value) {
      try {
        const saved = JSON.parse(sessionStorage.getItem('explore:' + value.path) || 'null');
        if (saved && Number.isFinite(saved.offset) && Math.abs(saved.offset) <= 600) {appliedOffset = saved.offset; $('explore-offset').value = saved.offset;}
        if (saved?.selection) { selection = selectedRange(saved.selection.start_ms, saved.selection.end_ms, 605400000); $('explore-start').value = selection.start_ms / 1000; $('explore-end').value = selection.end_ms / 1000; $('explore-range-note').textContent = '이번 탭의 이전 선택 범위를 복원했습니다. 7단계 목록에 추가하면 영상으로 저장할 수 있습니다.'; }
      } catch { /* 손상된 브라우저 선택만 무시한다. */ }
    }
    draw();
  }
  $('explore-search').onsubmit = event => { event.preventDefault(); searchMode = true; cursor = 0; results(); };
  $('explore-candidates').onclick = () => { searchMode = false; cursor = 0; results(); };
  $('explore-source').onchange = () => { searchMode = true; cursor = 0; results(); };
  $('explore-speaker').onchange = () => { cursor = 0; contextPage.speech = 0; results(); contexts(); };
  $('explore-prev').onclick = () => { cursor = Math.max(0, cursor - 100); pauseFollow(); results(); };
  $('explore-next').onclick = () => { if (cursor + 100 < total) { cursor += 100; pauseFollow(); results(); } };
  $('explore-refresh').onclick = refresh;
  $('explore-context').onchange = () => { contextPage = {chat: 0, speech: 0}; contexts(); };
  $('explore-position').onchange = () => jump(Number($('explore-position').value));
  $('explore-follow').onchange = () => { if ($('explore-follow').checked) { center = video.getAttribute('src') ? video.currentTime * 1000 : center; lastBucket = -1; contextPage = {chat: 0, speech: 0}; contexts(); draw(); } };
  $('explore-offset-form').onsubmit = event => { event.preventDefault(); const value = $('explore-offset').valueAsNumber; if (!Number.isFinite(value) || Math.abs(value) > 600) return message('채팅 보정은 -600~600초로 입력하세요.'); appliedOffset = value; remember(); cursor = 0; refresh(); };
  $('explore-range-form').onsubmit = event => { event.preventDefault(); choose($('explore-start').valueAsNumber * 1000, $('explore-end').valueAsNumber * 1000); };
  $('explore-set-start').onclick = () => { $('explore-start').value = (center / 1000).toFixed(3); };
  $('explore-set-end').onclick = () => { $('explore-end').value = (center / 1000).toFixed(3); };
  for (const source of ['chat', 'speech']) {
    for (const direction of ['prev', 'next']) $(`unified-${source}-${direction}`).onclick = () => { pauseFollow(); contextPage[source] = Math.max(0, contextPage[source] + (direction === 'next' ? 100 : -100)); contexts(); };
    const list = $(`unified-${source}`);
    for (const name of ['wheel', 'pointerdown', 'touchstart', 'keydown']) list.addEventListener(name, pauseFollow, {passive: true});
  }
  for (const name of ['wheel', 'pointerdown', 'touchstart', 'keydown']) $('explore-results').addEventListener(name, pauseFollow, {passive: true});
  video.addEventListener('seeked', () => { if (active) { center = Math.round(video.currentTime * 1000); contextPage = {chat: 0, speech: 0}; draw(); contexts(); } });
  video.addEventListener('timeupdate', () => {
    if (!active) return;
    center = Math.round(video.currentTime * 1000); draw(); highlight();
    const bucket = Math.floor(center / 10000);
    if ($('explore-follow').checked && bucket !== lastBucket) { lastBucket = bucket; contextPage = {chat: 0, speech: 0}; contexts(); }
  });
  return {
    refresh,
    setProject(value) {
      const changed = value?.path !== project?.path;
      const next = value ? JSON.stringify([value.path, value.tasks, value.speech?.updated_at, value.speech?.stale, value.voices?.run, value.voices?.revision, value.voices?.stale, value.analysis_running]) : '';
      project = value;
      if (next === key) return;
      key = next; serial++; contextSerial++; infoSerial++;
      if (changed) reset(value);
      if (active) refresh();
    },
    open(enabled) { active = enabled; serial++; contextSerial++; infoSerial++; if (enabled) { center = video.getAttribute('src') ? Math.round(video.currentTime * 1000) : center; refresh(); } },
    focus(row) { const at = row.peak_ms ?? row.at_ms ?? row.start_ms; jump(Math.max(0, at + (row.peak_ms != null ? appliedOffset * 1000 : 0))); }
  };
}
