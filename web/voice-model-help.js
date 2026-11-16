// 모델 파일·실행 도구 상태만 사용하며 HF 로그인 상태를 추정하지 않는다.
export function voiceModelHelp(backend, model) {
  const paragraphs=['실행 도구와 모델은 설정에서 선택한 모델 폴더에 저장합니다. 처음 분석할 때 필요한 파일을 준비하고 같은 작업을 이어갑니다. 미리 설치하려면 설정의 저장 폴더에서 모델을 선택하세요.'];
  const links=[];
  let status=model.ready?'모델 준비 완료':'모델 준비 전';
  if(model.supported===false)status+=' / 현재 장치 미지원';
  else if(!model.engine)status+=' / 첫 사용 시 실행 도구 설치';
  else if(model.ready)status+=' / 바로 사용 가능 (오프라인)';
  if(!model.ready&&backend==='pyannote'&&model.supported!==false)status+=' / 최초 다운로드 시 HF 로그인과 이용 동의 필요';
  if(model.ready)paragraphs.push('검증을 마친 모델은 다시 받지 않습니다.');
  if(model.supported===false)paragraphs.push('현재 장치에서 실행할 수 있는 다른 엔진을 선택하세요.');
  if(!model.ready&&backend==='pyannote') {
    paragraphs.push(
      '1. 아래 Community-1 모델 페이지에서 본인의 Hugging Face 계정으로 로그인하세요. 이용 조건을 확인한 뒤 ‘Agree and access repository’로 접근에 동의하세요. 이미 동의했다면 반복할 필요가 없습니다.',
      '2. 이 컴퓨터의 터미널에서 hf auth login을 실행하고 공식 CLI의 인증 안내를 따르세요. 명령이 없으면 아래 CLI 안내에서 설치 방법을 확인하세요.',
      '사이트 로그인만으로 앱의 로컬 인증이 완료되지는 않습니다. 같은 컴퓨터의 사용자 환경에서 인증했다면 재사용합니다. 토큰 방식은 모델을 읽을 수 있는 권한만 사용하고 토큰을 앱이나 댓글, 공유 로그에 입력하지 마세요.',
      '3. 앱으로 돌아와 ‘선택 모델 준비 및 검사’를 실행하세요. 접근 거부 오류가 나면 이용 조건 동의 계정과 로컬 인증 계정과 권한을 확인하세요. 이 안내는 로그인 실패를 판정한 결과가 아닙니다.'
    );
    links.push(
      {label:'Community-1 이용 동의 페이지',url:'https://huggingface.co/pyannote/speaker-diarization-community-1'},
      {label:'Hugging Face CLI 설치 및 로그인 안내',url:'https://huggingface.co/docs/huggingface_hub/guides/cli'}
    );
  }
  return {status,paragraphs,links};
}
