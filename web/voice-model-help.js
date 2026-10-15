// 모델 파일·실행 도구 상태만 사용하며 HF 로그인 상태를 추정하지 않는다.
export function voiceModelHelp(backend, model) {
  const paragraphs=['모델은 앱 밖의 지정한 AI 폴더에 저장합니다. 무료 모델에도 이용 조건이 있습니다.'];
  const links=[];
  let status=model.ready?'모델 준비 완료':'모델 준비·검사 필요';
  if(model.supported===false)status+=' · 현재 환경은 실행 지원 안 됨';
  else if(!model.engine)status+=' · 실행 도구 설치 필요';
  else if(model.ready)status+=' · 바로 사용 가능 (오프라인)';
  else if(backend==='pyannote')status+=' · 최초 다운로드 시 HF 로그인·이용 동의 필요 · 💡에서 방법 확인';
  else status+=' · 선택 모델 준비·검사를 실행하세요';

  if(model.ready)paragraphs.push('현재 폴더의 모델 준비가 완료됐습니다. 분석할 때 HF 로그인이나 재다운로드가 필요하지 않습니다. 전사 준비 후 전체 화자 분석을 실행하세요.');
  else paragraphs.push('현재 폴더에서 준비 완료를 확인하지 못했습니다. 처음 사용하거나 모델 경로·파일이 바뀐 경우 ‘선택 모델 준비·검사’를 실행하세요. 기존 결과는 유지합니다.');
  if(model.supported===false)paragraphs.push('이 엔진은 현재 운영체제·장치에서 실행을 지원하지 않습니다. 지원하는 엔진을 선택하세요.');
  else if(!model.engine)paragraphs.push('모델과 별도로 실행 도구가 필요합니다. 화면의 도구 설치 안내를 먼저 확인하세요. 모델이 있어도 실행 도구 설치 전에는 분석할 수 없습니다.');
  if(!model.ready&&backend==='pyannote') {
    paragraphs.push(
      '1. 아래 Community-1 모델 페이지에서 본인의 Hugging Face 계정으로 로그인하세요. 이용 조건을 확인한 뒤 ‘Agree and access repository’로 접근에 동의하세요. 이미 동의했다면 반복할 필요가 없습니다.',
      '2. 이 컴퓨터의 터미널에서 hf auth login을 실행하고 공식 CLI의 인증 안내를 따르세요. 명령이 없으면 아래 CLI 안내에서 설치 방법을 확인하세요. 소스로 실행할 때는 프로젝트 폴더에서 .diarization-tools/pyannote/venv/bin/hf auth login도 사용할 수 있습니다.',
      '사이트 로그인만으로 앱의 로컬 인증이 완료되지는 않습니다. 같은 컴퓨터·사용자 환경에서 인증했다면 재사용합니다. 토큰 방식은 모델을 읽을 수 있는 권한만 사용하고 토큰을 앱·댓글·공유 로그에 입력하지 마세요.',
      '3. 앱으로 돌아와 ‘선택 모델 준비·검사’를 실행하세요. 접근 거부 오류가 나면 이용 조건 동의 계정과 로컬 인증 계정·권한을 확인하세요. 이 안내는 로그인 실패를 판정한 결과가 아닙니다.'
    );
    links.push(
      {label:'Community-1 이용 동의 페이지',url:'https://huggingface.co/pyannote/speaker-diarization-community-1'},
      {label:'Hugging Face CLI 설치·로그인 안내',url:'https://huggingface.co/docs/huggingface_hub/guides/cli'}
    );
  }
  return {status,paragraphs,links};
}
