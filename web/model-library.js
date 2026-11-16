const catalog = {
  '음성 전사': {
    whisper: '방송에서 말한 내용을 시간대별 자막으로 옮깁니다.',
    vad: '말소리가 있는 구간을 찾아 Whisper가 전사할 범위를 정합니다.',
  },
  '화자 구분': {
    sherpa: '목소리를 구분해 같은 사람이 말한 구간을 묶습니다. 중단한 분석은 조각 단위로 이어갈 수 있습니다.',
    'tool-sherpa': 'sherpa 화자 구분과 전사의 Silero VAD 발화 검출에 함께 쓰는 실행 도구입니다.',
    pyannote: '누가 언제 말했는지 구분합니다. 처음 받을 때 Hugging Face에서 모델 이용에 동의해야 합니다.',
    'tool-pyannote': '이 컴퓨터에서 Community-1 모델로 화자를 구분할 때 사용합니다.',
    fluid: 'Apple Silicon Mac에서 화자의 목소리를 구분하는 모델입니다.',
    'tool-fluid': 'Mac의 Core ML로 FluidAudio 화자 모델을 실행합니다.',
  },
  'AI 문맥 분석': {
    gemma: '전사 내용을 바탕으로 장면을 요약하고 타임스탬프와 클립 후보를 만듭니다.',
  },
};

function groupedLists(items, renderRow) {
  const remaining = new Map(items.map(item => [item.id, item]));
  const groups = new Map();
  function append(group, item, description) {
    if (!groups.has(group)) {
      const section = document.createElement('section');
      const heading = document.createElement('h4');
      heading.textContent = group;
      const list = document.createElement('ul');
      section.append(heading, list);
      groups.set(group, {section, list});
    }
    groups.get(group).list.append(renderRow(item, description));
  }
  for (const [group, entries] of Object.entries(catalog)) {
    for (const [id, description] of Object.entries(entries)) {
      const item = remaining.get(id);
      if (item) {
        append(group, item, description);
        remaining.delete(id);
      }
    }
  }
  for (const item of remaining.values()) {
    if (item.id.startsWith('legacy-')) append('AI 문맥 분석', item, '이전 버전의 AI 문맥 분석에서 사용한 모델입니다.');
    else append('기타', item, '');
  }
  return Array.from(groups.values(), group => group.section);
}

function size(bytes) {
  if (!bytes) return '';
  if (bytes >= 1024 ** 3) return (bytes / 1024 ** 3).toFixed(2) + ' GiB';
  if (bytes >= 1024 ** 2) return (bytes / 1024 ** 2).toFixed(1) + ' MiB';
  return Math.ceil(bytes / 1024) + ' KiB';
}

export function createModelLibrary(api) {
  const el = id => document.getElementById(id);
  const list = el('model-library-items'), notice = el('model-library-notice');
  const dialog = el('model-delete-dialog');
  let root = '', snapshot, signature = '', pending = false, reading = false, revision = 0, deleteItem, nextRefresh = 0;

  function button(text, label, action, item, busy = false) {
    const control = document.createElement('button');
    control.type = 'button';
    control.className = action === 'delete' ? 'danger' : 'secondary';
    control.textContent = text;
    control.setAttribute('aria-label', label + ' ' + text);
    control.disabled = pending || busy;
    control.onclick = () => {
      if (action !== 'delete') return submit(action, item);
      deleteItem = item;
      el('model-delete-title').textContent = label + ' 삭제';
      el('model-delete-description').textContent = '공용 AI 모델 폴더에서 이 항목을 삭제합니다. 여러 VOD가 함께 쓰는 항목으로, 다음에 필요할 때 다시 설치할 수 있습니다.';
      dialog.showModal();
    };
    return control;
  }

  function render(value) {
    if (value.root !== root) return;
    snapshot = value;
    const job = value.job;
    const active = job.state === 'running' || job.state === 'stopping';
    const next = JSON.stringify([value.items, active && job.id, job.state, pending]);
    if (signature !== next) {
      signature = next;
      const sections = groupedLists(value.items, (item, description) => {
        const row = document.createElement('li');
        const info = document.createElement('div'), label = document.createElement('strong');
        const name = ['whisper', 'gemma'].includes(item.id) ? '(필수) ' + item.label : item.label;
        label.textContent = name;
        const status = document.createElement('small');
        let state = item.problem || (item.ready ? '설치됨' : item.present ? '일부 파일 있음' : '미설치');
        if (!item.supported) state += ' / 현재 기기 미지원';
        if (active && job.id === item.id) state = job.state === 'stopping' ? '중단 중' : job.action === 'delete' ? '삭제 중' : '설치 중';
        const disk = item.bytes ? '저장 ' + size(item.bytes) : item.expected_bytes ? '모델 크기 ' + size(item.expected_bytes) : '';
        status.textContent = [item.type === 'tool' ? '실행 도구' : '모델', state, disk].filter(Boolean).join(' / ');
        info.append(label);
        if (description) {
          const detail = document.createElement('p');
          detail.textContent = description;
          info.append(detail);
        }
        info.append(status);
        const actions = document.createElement('div');
        actions.className = 'model-library-actions';
        if (active && job.id === item.id && job.action === 'install' && job.state === 'running') {
          actions.append(button('중단', name, 'cancel', item));
        } else {
          if (item.can_install && !item.ready) actions.append(button('설치', name, 'install', item, active));
          if (item.can_delete) actions.append(button('삭제', name, 'delete', item, active));
        }
        row.append(info, actions);
        return row;
      });
      list.replaceChildren(...sections);
    }
    const progress = job.progress || {};
    const amount = active && progress.total_bytes ? [size(progress.bytes) || '0 B', size(progress.total_bytes)].join(' / ') : '';
    notice.textContent = [job.message, amount].filter(Boolean).join('  ');
    nextRefresh = Date.now() + (active ? 500 : 8000);
  }

  async function submit(action, item) {
    if (pending || !item || !root) return;
    const request = ++revision;
    pending = true;
    if (snapshot) render(snapshot);
    try {
      const result = await api('model-library', {action, id:item.id, root});
      if (revision === request) { pending = false; render(result); }
    } catch (error) {
      if (revision === request) {
        pending = false;
        if (snapshot) render(snapshot);
        notice.textContent = error.message;
      }
    }
  }

  el('model-delete-cancel').onclick = () => dialog.close();
  el('model-delete-confirm').onclick = () => { const item = deleteItem; dialog.close(); return submit('delete', item); };
  return {
    rootChanged(path) {
      if (root === path) return;
      root = path; snapshot = undefined; signature = ''; pending = false; nextRefresh = 0; revision++;
      if (dialog.open) dialog.close();
      deleteItem = null; list.replaceChildren(); notice.textContent = '';
    },
    async refresh() {
      if (!root || pending || reading || Date.now() < nextRefresh || !list.getClientRects().length) return;
      const request = revision;
      reading = true;
      try {
        const value = await api('model-library', {});
        if (request === revision) render(value);
      } catch (error) { if (request === revision) notice.textContent = error.message; }
      finally { reading = false; }
    }
  };
}
