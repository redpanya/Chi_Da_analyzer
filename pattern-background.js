// 문서가 열릴 때 한 번만 고르고, 작업 단계나 VOD 전환 중에는 유지한다.
(() => {
  // 기존 512px 이미지에서 소품 하나씩 표시할 영역 [x, y, 너비, 높이]. 원본은 변경하지 않는다.
  const motifs = [
    [[24, 24, 104, 128], [155, 54, 120, 200]], // 뿔, 꽃가지
    [[16, 28, 112, 120], [130, 8, 74, 114], [206, 26, 104, 116], [400, 8, 106, 142], [205, 143, 82, 132]], // 나비, 체인, 하트, 가방, 십자가
    [[40, 34, 108, 126], [201, 12, 85, 152]], // 고양이, 넥타이
    [[54, 74, 188, 126], [84, 228, 128, 106], [84, 362, 132, 98]], // 모자, 갈색 리본, 하늘색 리본
    [[42, 22, 151, 160], [210, 37, 101, 149]], // 검정·노랑 리본, 스페이드
    [[30, 4, 194, 156], [368, 20, 126, 136]], // 토끼 머리띠, 다이아몬드
    [[44, 13, 150, 156], [218, 42, 170, 147]], // 나비, 초커
    [[0, 0, 167, 169], [168, 0, 146, 130]], // 하늘색 리본, 레이스 초커
  ];
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
