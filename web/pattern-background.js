// 실행 첫 화면은 치지직 마크, 사용자 메뉴 이동은 개별 소품으로 표시한다.
(() => {
  // 기존 512px 이미지에서 소품 하나씩 표시할 영역 [x, y, 너비, 높이]. 원본은 변경하지 않는다.
  const motifs = [
    [[24, 24, 104, 128], [155, 54, 120, 200]], // 뿔, 꽃가지
    [[16, 28, 112, 120], [130, 8, 74, 114], [206, 26, 104, 116], [400, 8, 106, 142], [205, 143, 82, 132]], // 나비, 체인, 하트, 가방, 십자가
    [[40, 34, 108, 126], [201, 12, 85, 152]], // 고양이, 넥타이
    [[54, 74, 188, 126], [84, 228, 128, 106], [84, 362, 132, 98]], // 모자, 갈색 리본, 하늘색 리본
    [[42, 22, 151, 160], [210, 37, 101, 149]], // 검정과 노랑 리본, 스페이드
    [[30, 4, 194, 156], [368, 20, 126, 136]], // 토끼 머리띠, 다이아몬드
    [[44, 13, 150, 156], [218, 42, 170, 147]], // 나비, 초커
    [[0, 0, 167, 169], [168, 0, 146, 130]], // 하늘색 리본, 레이스 초커
  ];
  const marks = document.querySelectorAll('.brand > img.mark, .studio-brand > img');
  if (marks.length) {
    const choices = motifs.flatMap((frames, sheet) => frames.map(frame => ({sheet, frame})));
    // 실행기별 주소로 구분하며 같은 실행의 새로고침과 문서 이동에서는 마지막 소품을 잇는다.
    const storageKey = 'chida-brand:' + new URL('.', location.href).pathname;
    let current = -1;
    try {
      const saved = sessionStorage.getItem(storageKey);
      if (saved !== null && /^\d+$/.test(saved) && Number(saved) < choices.length) current = Number(saved);
    } catch {} // 저장소가 제한되어도 로고와 메뉴는 사용할 수 있다.
    const svgNode = (tag, attributes) => {
      const node = document.createElementNS('http://www.w3.org/2000/svg', tag);
      for (const [key, value] of Object.entries(attributes)) node.setAttribute(key, String(value));
      return node;
    };
    const contents = [];
    for (const [index, mark] of [...marks].entries()) {
      const logo = svgNode('svg', {class: 'mark brand-mark', viewBox: '0 0 40 40',
        width: mark.getAttribute('width') || 32, height: mark.getAttribute('height') || 32,
        'aria-hidden': 'true', focusable: 'false'});
      logo.append(svgNode('rect', {class: 'brand-tile', x: 0, y: 0, width: 40, height: 40, rx: 9}));
      logo.append(svgNode('path', {class: 'brand-handle', d: 'M27 27L34 34'}));
      logo.append(svgNode('circle', {class: 'brand-lens', cx: 17, cy: 17, r: 12.5}));
      const clipId = `brand-lens-content-${index}`;
      const clip = svgNode('clipPath', {id: clipId, clipPathUnits: 'userSpaceOnUse'});
      clip.append(svgNode('circle', {cx: 17, cy: 17, r: 11.1}));
      const defs = svgNode('defs', {}); defs.append(clip);
      const content = svgNode('g', {'clip-path': `url(#${clipId})`});
      logo.append(defs, content); contents.push(content);
      mark.replaceWith(logo);
    }
    function paint() {
      for (const content of contents) {
        if (current < 0) {
          content.replaceChildren(svgNode('path', {class: 'brand-chzzk',
            d: 'M14 7H22L18.5 11H25L15.5 23H22V27H9L17.5 15H9Z'}));
          continue;
        }
        const {sheet, frame} = choices[current];
        // 소품만 확대하고 렌즈 경계에서 가려 돋보기와 인접 소품은 그대로 유지한다.
        const scale = 24 / Math.max(frame[2], frame[3]);
        const width = frame[2] * scale, height = frame[3] * scale;
        const art = svgNode('svg', {class: 'brand-motif', x: 17 - width / 2, y: 17 - height / 2, width, height,
          viewBox: frame.join(' '), preserveAspectRatio: 'xMidYMid meet', overflow: 'hidden'});
        art.append(svgNode('image', {href: `patterns/pattern-${String(sheet + 1).padStart(2, '0')}.webp`,
          x: 0, y: 0, width: 512, height: 512}));
        content.replaceChildren(art);
      }
    }
    function change() {
      const next = Math.floor(Math.random() * (choices.length - (current < 0 ? 0 : 1)));
      current = current >= 0 && next >= current ? next + 1 : next;
      try { sessionStorage.setItem(storageKey, String(current)); } catch {}
      paint();
    }
    paint();
    const tabs = '.result-mode-tabs > button[role="tab"], .studio-steps > button[role="tab"]';
    const menus = [
      '.step-primary :is(#new,#nav-library,#nav-jobs,#open-video-split,#step9)', '.step-primary > .brand',
      '#selected-vod-rail > .rail-back', '#purpose-tabs > button', '#task-rail > button.rail-action', tabs,
      '#library-cards .library-open', '#projects .project-item', '#use-page > button.flow-card',
      '#prepare-overview button', '#queue-options-open', '#registration-next',
      '#task-main .task-previous', '#task-main .task-next',
      'a.studio-rail-link', 'a.studio-brand', 'a.studio-rail-back', '#vod-title',
      '[data-inspector-open]', '#inspector-back', '#inspector-close', '#studio-step-prev', '#studio-step-next',
      'a.split-rail-link', '#split-primary-rail > .brand',
    ].join(',');
    // 초기 화면 복원과 폴링, 내부 .click() 호출은 메뉴 이동으로 세지 않는다.
    document.addEventListener('click', event => {
      if (!event.isTrusted) return;
      const menu = event.target.closest?.(menus);
      if (!menu || menu.matches(':disabled, [aria-disabled="true"]')) return;
      if (menu.tagName === 'BUTTON' && menu.matches('[aria-current="page"], [aria-current="step"], [aria-selected="true"], [aria-pressed="true"]')) return;
      change();
    }, true);
    document.addEventListener('keydown', event => {
      if (!event.isTrusted || !['ArrowLeft','ArrowRight','ArrowUp','ArrowDown','Home','End'].includes(event.key)) return;
      const tab = event.target.closest?.(tabs), list = tab?.closest('[role="tablist"]');
      if (!list) return;
      const selected = list.querySelector('[aria-selected="true"]');
      queueMicrotask(() => { if (list.querySelector('[aria-selected="true"]') !== selected) change(); });
    }, true);
  }

  if (!document.querySelector('link[href="pattern-background.css"]')) return;
  const theme = Math.floor(Math.random() * motifs.length);
  const frames = motifs[theme];
  const scale = .5;
  document.documentElement.dataset.pattern = String(theme + 1);
  const layer = document.createElement('div');
  layer.className = 'pattern-background';
  layer.setAttribute('aria-hidden', 'true');
  layer.style.setProperty('--pattern-sheet-size', `${512 * scale}px`);
  document.body.prepend(layer);
  const pitch = parseFloat(getComputedStyle(layer).getPropertyValue('--pattern-pitch')) || 156;
  let lastGrid = '';
  const layout = () => {
    const columns = Math.max(1, Math.floor(layer.clientWidth / pitch));
    const rows = Math.max(1, Math.ceil(layer.clientHeight / pitch));
    const grid = `${columns}:${rows}`;
    if (grid === lastGrid) return;
    lastGrid = grid;
    layer.replaceChildren(...Array.from({length: columns * rows}, (_, index) => {
      const cell = document.createElement('span');
      const sprite = document.createElement('i');
      const [x, y, width, height] = frames[(index + Math.floor(index / columns)) % frames.length];
      sprite.style.width = `${width * scale}px`;
      sprite.style.height = `${height * scale}px`;
      sprite.style.backgroundPosition = `${-x * scale}px ${-y * scale}px`;
      cell.append(sprite);
      return cell;
    }));
  };
  layout();
  window.addEventListener('resize', layout, {passive: true});
})();
