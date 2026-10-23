// 문서가 열릴 때 한 번만 고르고, 작업 단계나 VOD 전환 중에는 유지한다.
(() => {
  document.documentElement.dataset.pattern = String(1 + Math.floor(Math.random() * 8));
})();
