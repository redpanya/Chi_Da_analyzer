import {showToast} from './ui-feedback.js';

export function showPreviewToast(enabled) {
  if (enabled) showToast('개발 미리보기: 주석 호환 모드입니다. 이 실행에서만 인라인 스타일을 허용합니다.', {key: 'annotation-preview'});
}
