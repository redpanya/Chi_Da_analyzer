// 실행 도구와 모델 준비는 서로 다른 단계다. 상태 조회만으로 다운로드하지 않는다.
export function voiceToolStatus(model, state={}) {
  const tool=model?.tool||{}, supported=model?.supported!==false;
  const active=state.backend===model?.id&&['install-engine','check-engine'].includes(state.action)&&['running','stopping'].includes(state.state);
  const source={installed:'별도 설치됨',bundled:'앱에 포함됨',development:'개발 환경 도구'}[tool.source]||'준비됨';
  return {
    status:!supported?'실행 도구 · 현재 장치 미지원':active?(state.message||'실행 도구 준비 중'):model?.engine?`실행 도구 · ${source}`:'실행 도구 · 설치 필요',
    install:active&&state.action==='install-engine'?'실행 도구 설치 중…':tool.managed?'실행 도구 다시 설치':model?.engine?'실행 도구 별도 설치':'실행 도구 다운로드·설치',
    hint:!supported?'FluidAudio는 Apple Silicon macOS에서 사용할 수 있습니다. 지원하는 엔진을 선택하세요.':
      `앱 밖 설치 위치: ${tool.install_path||'사용자 앱 지원 폴더'}`,
    canInstall:supported, canCheck:supported&&!!model?.engine,
  };
}
