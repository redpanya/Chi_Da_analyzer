// 문서가 열릴 때 한 번만 고르고, 작업 단계나 VOD 전환 중에는 유지한다.
(() => {
  document.documentElement.dataset.pattern = String(1 + Math.floor(Math.random() * 8));
  // 그림 크기와 반복 간격을 분리해, 절반 크기로 줄여도 과밀하게 반복하지 않는다.
  const layer = document.createElement('div');
  layer.className = 'pattern-background';
  layer.setAttribute('aria-hidden', 'true');
  document.body.prepend(layer);
  const style = getComputedStyle(layer);
  const pitch = (parseFloat(style.getPropertyValue('--pattern-size')) || 256)
    + (parseFloat(style.getPropertyValue('--pattern-gap')) || 96);
  const layout = () => {
    const count = Math.max(1, Math.ceil(layer.clientWidth / pitch))
      * Math.max(1, Math.ceil(layer.clientHeight / pitch));
    if (layer.childElementCount !== count) {
      layer.replaceChildren(...Array.from({length: count}, () => document.createElement('span')));
    }
  };
  layout();
  window.addEventListener('resize', layout, {passive: true});
})();
