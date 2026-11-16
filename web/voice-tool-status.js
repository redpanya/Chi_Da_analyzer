// 실행 도구와 모델 준비는 서로 다른 단계다. 상태 조회만으로 다운로드하지 않는다.
export function voiceToolStatus(model, state={}) {
  const tool=model?.tool||{}, supported=model?.supported!==false;
  const active=state.backend===model?.id&&['install-engine','check-engine'].includes(state.action)&&['running','stopping'].includes(state.state);
  return {
    status:!supported?'실행 도구: 현재 장치 미지원':active?(state.message||'실행 도구 준비 중'):model?.engine?'실행 도구: 설치됨':'실행 도구: 첫 사용 시 자동 설치',
    install:active&&state.action==='install-engine'?'실행 도구 설치 중…':tool.managed?'실행 도구 다시 설치':'실행 도구 다운로드',
    hint:!supported?'현재 장치에서 지원하는 엔진을 선택하세요.':'',
    canInstall:supported, canCheck:supported&&!!model?.engine,
  };
}
