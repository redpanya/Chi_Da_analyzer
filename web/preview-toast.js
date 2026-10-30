// 부가 안내만 자동으로 닫는다. 작업 상태·오류 영역은 건드리지 않는다.
export function showPreviewToast(enabled) {
  if (!enabled) return;
  const toast = document.getElementById('preview-toast');
  let timer;
  const close = () => { clearTimeout(timer); toast.hidden = true; };
  const schedule = () => { clearTimeout(timer); timer = setTimeout(close, 6000); };
  document.getElementById('preview-toast-close').onclick = close;
  toast.onmouseenter = toast.onfocusin = () => clearTimeout(timer);
  toast.onmouseleave = toast.onfocusout = schedule;
  toast.hidden = false;
  schedule();
}
