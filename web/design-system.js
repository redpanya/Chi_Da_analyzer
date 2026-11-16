// Core의 버튼·배지만 로컬 도입합니다. 기존 폼/위임 이벤트의 DOM 계약은 유지합니다.
import { setBasePath, setIconPath } from './vendor/webawesome/utilities/base-path.js';
import './vendor/webawesome/components/button/button.js';
import './vendor/webawesome/components/badge/badge.js';
import {exposeDetails, showToast} from './ui-feedback.js';
import {bindDocumentMotion} from './workspace-motion.js';
import './pattern-background.js';

setBasePath(new URL('./vendor/webawesome/', import.meta.url).href);
// 사용자가 새 아이콘을 추가해도 CDN으로 요청하지 않습니다. 내부 시스템 아이콘은 번들에 있습니다.
setIconPath(new URL('./vendor/webawesome/icons/', import.meta.url).href);
bindDocumentMotion();
function connectThemeControls() {
  document.querySelectorAll('[data-theme-select]').forEach(select => window.ChidaTheme?.connect(select));
  exposeDetails();
  const notice = document.getElementById('notice');
  if (notice) new MutationObserver(() => {
    if (notice.textContent.trim() && !notice.hidden) {showToast(notice.textContent); notice.hidden = true;}
  }).observe(notice, {subtree:true,childList:true,characterData:true,attributes:true,attributeFilter:['hidden']});
}
if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', connectThemeControls, { once: true });
else connectThemeControls();
