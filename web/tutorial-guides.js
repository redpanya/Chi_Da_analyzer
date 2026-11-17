const hasResults=()=>Boolean(document.querySelector('.result-mode-tabs button:enabled'));
const s=(selector,title,text,options={})=>({selector,title,text,...options});
const clipStep=(tab,panel,selector,title,text)=>s(selector,title,text,{tab,panel});
export const names={
  welcome:'첫 사용 안내',register:'VOD 등록',library:'보관함',jobs:'진행 상태',prepare:'자료 준비',
  download:'영상과 채팅',audio:'원음 추출',speech:'음성 전사',voices:'화자 구분',context:'AI 문맥 설정',
  analysis:'분석',explore:'공통 시간축',voiceReview:'화자 검토',work:'작업',clip:'클립 만들기',mix:'믹스클립',
  split:'영상 나누기',external:'외부 AI 파일 분석',report:'결과 리포트',settings:'설정'
};
export const guides={
  welcome:[
    s('#load-library','VOD 보관함 폴더','폴더 선택을 눌러 영상과 채팅을 저장할 보관함을 지정하세요. 이미 사용할 폴더가 표시되어 있으면 다음으로 넘어가세요.'),
    s('#apply-model-folder','공용 AI 모델 폴더','전사와 분석 모델을 저장할 위치입니다. 이미 받은 모델이 있으면 그 폴더를 선택하세요.'),
    s('#model-library-heading','모델 및 실행 도구','영상 다운로드는 모델 없이 시작할 수 있습니다. 나중에 전사나 분석이 필요하면 여기서 모델을 준비하세요.'),
    s('#new','등록, 보관함, 진행 상태','VOD 등록에서 주소를 넣고, 보관함에서 저장한 방송을 엽니다. 진행 상태에서는 작업을 확인하거나 이어갈 수 있습니다.'),
    s('#open-video-split','영상 나누기와 믹스클립','영상 나누기는 내 컴퓨터의 영상 파일을 나눕니다. 믹스클립은 여러 방송에서 담은 장면을 한 영상으로 합칩니다.'),
    s('.rail-bottom','테마와 설정','테마에서 화면 밝기를 바꾸고 설정에서 저장 위치와 모델을 관리하세요. 이제 첫 방송을 등록해 보세요.',{label:'첫 VOD 등록하기'})
  ],
  library:[
    s('#library-search','방송 찾기','제목, 채널, VOD 번호로 검색하고 상태별로 목록을 좁힐 수 있습니다.'),
    s('.library-open','방송 열기','방송을 열면 자료 준비, 분석, 작업으로 이동할 수 있습니다. 일부 확인이 남은 방송도 완료된 결과를 사용할 수 있습니다.'),
    s('#new','첫 방송 등록','보관함에 표시할 방송이 없으면 VOD 등록에서 다시보기 주소를 추가하세요.',{when:()=>!document.querySelector('.library-open')})
  ],
  jobs:[s('#jobs-filter','작업 확인','실행, 대기, 중단, 완료 상태로 목록을 좁힐 수 있습니다. 작업이 생기면 상세에서 대기 사유와 최근 기록을 확인하세요.'),
    s('#jobs-rows [aria-controls="job-detail"]','작업 상세','상세 패널에서 중단된 작업을 이어가거나 완료된 결과를 열 수 있습니다.')],
  prepare:[s('.preparation-list','자료 준비 순서','영상과 채팅, 원음 추출, 음성 전사, 화자 구분, AI 문맥 순으로 상태를 확인하세요. 각 단계의 확인 버튼에서 자료와 설정을 엽니다.'),
    s('#prepare-overview .primary','분석 결과 열기','준비한 자막과 문맥 결과가 있으면 분석 화면에서 장면을 확인할 수 있습니다.')],
  download:[s('#download-settings .settings-heading','영상과 채팅','영상과 채팅의 수신 상태를 각각 확인하세요. 중단된 자료는 이어받을 수 있고 영상은 다른 화질로 다시 받을 수 있습니다.')],
  audio:[s('#extract-audio','원음 추출','오디오 트랙을 골라 원음을 추출하세요. 완료하면 아래에서 추출한 음성을 듣거나 WAV 파일로 저장할 수 있습니다.')],
  speech:[s('#speech-settings .settings-heading','자막 만들기','모델과 방송 언어를 고르고 발화 검출 옵션을 확인하세요. 전사를 시작하면 완료된 구간부터 확인할 수 있습니다.')],
  voices:[s('#voice-settings .settings-heading','화자 구분','엔진과 모델을 준비한 다음 화자 분석을 시작하세요. 이미 처리한 구간은 이어받을 수 있습니다.')],
  context:[s('#context-settings .settings-heading, #clip-settings .settings-heading','AI 문맥 설정','결과 종류와 입력 전사를 고르고 방송 배경이나 추가 요청을 적으세요. 준비된 자료로 분석을 시작할 수 있습니다.')],
  explore:[s('#timeline-span','공통 시간축','표시할 시간 범위를 선택하세요. 영상, 채팅 반응과 클립 후보를 같은 위치에서 비교할 수 있습니다.')],
  voiceReview:[s('#purpose-tabs','화자 검토','화자별 구간과 전사를 함께 확인하세요. 화자 구분 자료는 준비 단계에서 생성할 수 있습니다.')],
  analysis:[s('.result-navigation-empty','첫 분석 결과 준비','아직 이 방송에 표시할 분석 결과가 없습니다. 자료 준비에서 음성 전사나 AI 문맥을 실행하거나 작업에서 외부 결과를 가져오세요.',{when:()=>!hasResults()}),
    s('.result-mode-tabs','분석 결과 선택','전사 자막, 상세 문맥, 타임스탬프와 클립 후보를 전환하세요. 목록에서 구간을 고르면 영상 위치를 확인할 수 있습니다.',{when:hasResults}),
    s('.scene-usage .review-tabs','댓글이나 클립에 담기','댓글 목록에서는 댓글 담기를 사용하세요. 여러 방송을 섞으려면 담은 클립 탭을 열고 원하는 장면에서 클립 담기를 누른 뒤 믹스클립 보내기를 누르세요.',{when:hasResults}),
    s('.result-primary-actions button','근거와 처리 기록','장면별 세부 정보는 내용근거에서, 선택한 결과의 버전과 처리 기록은 결과 설정에서 확인하세요.',{when:hasResults})],
  work:[s('#use-page .flow-card','결과 활용','클립 만들기에서 영상을 편집하고, 외부 AI 파일 분석에서 자료를 주고받거나 결과 리포트에서 처리 기록을 확인하세요.')],
  clip:[
    clipStep('range','','#assembly-add','편집할 장면 고르기','분석에서 담은 클립이 미리보기 아래에 표시됩니다. 장면을 더 넣으려면 구간 추가를 여세요.'),
    clipStep('range','sources','#source-version','분석에서 구간 가져오기','오른쪽에서 저장된 분석 결과를 고르고, 목록에서 원하는 장면을 체크하세요. 찾는 장면이 없으면 아래의 직접 구간 추가를 사용하세요.'),
    clipStep('range','','#range-form .range-fields','시작과 끝 다듬기','구간 카드를 선택하고 오른쪽에서 제목과 시작, 끝을 수정하세요. 영상을 멈춘 위치는 현재 시각으로 가져올 수 있습니다. 구간 변경 적용을 눌러 반영하세요.'),
    clipStep('range','','#play-sequence','순서와 연결 확인','미리보기 아래의 카드를 끌어 재생 순서를 정하세요. 담은 구간 이어 보기로 장면 사이의 연결을 확인할 수 있습니다.'),
    clipStep('preset','','#profile-target','프리셋을 적용할 구간 정하기','현재 구간, 여러 구간 선택, 담은 구간 전체 중 하나를 고르세요. 여러 구간을 선택할 때는 미리보기 아래에서 체크하고 오른쪽에 나온 제목과 개수를 확인하세요.'),
    clipStep('preset','','#studio-preset-list','저장해 둔 설정 적용하기','프리셋을 고른 뒤 적용 버튼을 누르면 선택한 구간이 바뀝니다. 처음이라 프리셋이 없다면 화면과 자막부터 꾸미세요. 나중에 여기서 현재 구간 설정에 이름을 붙여 저장할 수 있습니다.'),
    clipStep('frame','','#overview-frame .inspector-cards','현재 구간의 화면 꾸미기','화면 비율에서 영상 배치와 효과를, PNG 이미지에서 로고나 그림을 설정하세요. 왼쪽 미리보기에서 현재 구간에 적용될 모습을 확인할 수 있습니다.'),
    clipStep('frame','layout','#frame-layout','비율과 화면 배치 고르기','위에서 원본, 가로, 세로 등의 비율을 고르세요. 한 화면에 영상을 맞추거나 세로 2단으로 나눠 게임과 얼굴을 따로 배치할 수 있습니다.'),
    clipStep('frame','effects','#brightness','색감과 페이드 조절하기','밝기, 대비, 채도를 조절하세요. 구간의 시작과 끝을 서서히 밝아지거나 어두워지게 하려면 페이드 시간을 지정하세요.'),
    clipStep('frame','volume','#volume','구간 음량 맞추기','현재 구간의 소리를 줄이려면 음량을 낮추세요. 소리를 없애려면 0%로 맞추세요.'),
    clipStep('frame','image','#image-file','PNG 이미지 얹기','로고나 그림을 넣을 때는 PNG 파일을 선택하세요. 오른쪽에서 위치, 너비, 불투명도를 조정할 수 있습니다.'),
    clipStep('caption','','#overview-caption .inspector-cards','자막 넣기','먼저 자막 내용을 확인하고 글꼴과 색상, 크기와 위치 순서로 조정하세요.'),
    clipStep('caption','caption-content','#caption-version','전사 선택과 문장 확인','전사를 영상에 자막으로 입히려면 위의 체크를 켜세요. 이 전사 버전은 모든 구간이 함께 사용합니다. 아래에서 문장을 검색하고 시각을 눌러 들어 본 뒤 자막 문구를 고치세요.'),
    clipStep('caption','caption-appearance','#caption-style','글꼴과 색상 고르기','자막 스타일과 글자 색을 고르고 설치된 글꼴을 검색하세요. 테두리, 그림자, 배경 박스를 조정하면서 예시 자막을 확인하세요.'),
    clipStep('caption','caption-position','#caption-size','자막 크기와 위치 맞추기','글자 크기와 기본 위치를 정하고 가로와 세로 위치를 미세 조정하세요. 미리보기에서 자막이 화면 밖으로 잘리지 않는지 확인하세요.'),
    clipStep('export','','#panel-export fieldset','파일 구성 정하기','구간별 파일로 저장하거나 한 영상으로 이어 붙일 수 있습니다. 이어 붙일 때는 컷이나 디졸브를 고르고, 아래에서 해상도와 편집용 자막 파일 포함 여부를 확인하세요.'),
    clipStep('export','','#render-speed','저장 방식과 공간 확인','화면과 자막 설정을 반영하려면 정확한 저장을 선택하세요. 빠른 저장은 원본 비율의 개별 구간에 사용합니다. 저장 공간 확인으로 예상 용량과 남은 공간을 비교하세요.'),
    clipStep('export','','#render-start','초안 보관과 영상 생성','편집을 나중에 이어가려면 편집 초안 저장을 누르세요. 완성할 준비가 되면 영상 생성 시작을 누르세요. 완료 후 저장 폴더에서 결과를 확인할 수 있습니다.')
  ],
  mix:[s('#mix-assembly-panel .panel-title, #mix-heading','믹스클립에 장면 보내기','각 VOD의 분석에서 담은 클립 탭을 열고 원하는 장면에 클립 담기를 누르세요. 믹스클립 보내기를 누르면 여러 방송의 구간이 이곳에 모입니다. 편집과 저장 방법은 클립 만들기와 같습니다.')],
  split:[s('#split-load','영상 파일 열기','컴퓨터에서 나눌 영상을 고르세요. 파일을 열면 재생 위치나 시간 간격으로 분할 경계를 정하고 출력 폴더를 고를 수 있습니다.'),
    s('#split-start','나눈 영상 저장','구간 목록과 출력 폴더를 확인한 뒤 영상 나누기를 시작하세요.')],
  external:[s('#external-task-tab-export','자료 내보내기','전사와 필요한 채팅을 선택해 분석 자료를 내보내고, 외부 AI에서 함께 제공된 요청문을 사용하세요.'),
    s('#external-task-tab-import','결과 가져오기','외부 AI 결과를 검사한 뒤 새 버전으로 가져오세요. 일부 묶음이 빠졌다면 보완 자료를 확인하세요.')],
  report:[s('#report-task-tab-runs','실행 리포트','선택한 방송의 실행 기록에서 단계별 처리 시간과 결과를 확인하세요.'),
    s('#report-task-tab-errors','오류 기록','이 방송의 오류를 확인하고 보낼 내용을 미리본 뒤 첨부할 파일을 직접 저장하세요.')],
  settings:[s('#task-rail','설정 둘러보기','저장 폴더에서 경로와 모델을 관리하고 화면과 안내에서 튜토리얼을 다시 볼 수 있습니다. 데스크톱 앱에서는 업데이트도 확인할 수 있습니다.')]
};
export const registration={
  address:[s('#register-address .form-section','등록할 방송','치지직 다시보기 주소나 짧은 주소를 붙여 넣으세요. 이미 저장한 방송은 저장한 VOD 선택에서 고를 수 있습니다.'),
    s('#registration-next','처리할 작업 선택','주소를 하나 이상 입력하거나 저장한 VOD를 고르면 이 버튼을 누를 수 있습니다. 방송 순서와 배경을 확인한 뒤 진행하세요.',{wait:true})],
  options:[s('#queue-steps','처리할 작업','영상과 채팅을 받으려면 다운로드를 선택하세요. 오디오 파일, 자막, 화자 또는 장면 요약이 필요하면 해당 단계도 선택하세요.'),
    s('#queue-height','최대 화질','480p, 720p, 1080p 중 받을 화질의 상한을 고르세요. 높은 화질은 더 많은 저장 공간을 사용합니다.'),
    s('#queue-download-scope','다운로드 범위','전체 방송이나 지정 구간을 고르세요. 지정 구간은 원본 VOD의 시작과 끝 시각을 입력합니다.'),
    s('#queue-download-range','시작과 끝','원본 방송을 기준으로 받을 시작 시각과 끝 시각을 입력하세요.'),
    s('#queue-fragments','동시 다운로드 개수','한 방송을 동시에 받을 조각 수입니다. 기본 1개, 최대 32개이며 서버가 분할 수신을 지원할 때 적용됩니다.'),
    s('#queue-audio','원음 추출','선택한 영상의 오디오를 별도 파일로 만듭니다. 추출한 소리는 자료 준비에서 듣거나 저장할 수 있습니다.',{when:()=>document.querySelector('#queue-audio').checked}),
    s('#queue-transcribe-options','전사 언어와 발화 검출','방송 언어를 고르세요. 발화 검출은 말소리를 찾습니다. 작은 말소리를 놓치면 민감을 사용하고 인물 이름은 용어 힌트에 적으세요.'),
    s('#queue-voice-options','화자 구분 도구','엔진을 선택하세요. 실패 시 계속을 켜면 구분하지 못한 화자를 불명으로 남기고 요약을 이어갑니다.'),
    s('#queue-ai-options','AI 문맥 결과','시간순 제목, 대화 요약, 클립 후보를 필요한 만큼 선택하세요. Gemma 사고를 켜면 분석 시간이 늘어날 수 있습니다.'),
    s('#queue-chat-options','검증이 필요한 채팅','수집 범위를 더 확인해야 하는 채팅도 분석에 포함할지 정합니다. 처음에는 꺼 두어도 됩니다.'),
    s('#queue-options .task-next','등록 내용 확인','원하는 설정을 골랐다면 등록 내용을 확인하세요.',{wait:true})],
  confirm:[s('#queue-add','목록에 등록','방송과 작업 설정을 확인한 뒤 이 버튼을 누르세요. 등록된 항목은 대기 목록에 들어갑니다.',{wait:true})],
  queued:[s('#queue-start','대기 목록 시작','등록된 방송과 함께 처리할 대기 항목을 확인하세요. 시작 준비를 확인하려면 목록 시작 또는 이어가기를 누르세요.',{wait:true})],
  preflight:[s('#preflight-start','실제 작업 시작','준비 상태와 실행할 VOD를 확인하세요. 이 설정으로 시작을 누르면 선택한 작업이 실행됩니다.',{wait:true})],
  started:[s('#nav-jobs','작업 시작 요청 완료','진행 상태에서 수신 중인지, 대기 중인지 또는 기존 자료를 재사용했는지 확인하세요.',{label:'진행 상태 보기'})]
};
