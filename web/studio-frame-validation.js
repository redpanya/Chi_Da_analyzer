// 숨겨진 영역 값은 보존하고 실제 사용하는 세로 2단만 검사한다.
export function frameErrors(options,width=0,height=0){
  if(options.layout!=='split')return {};
  const errors={};
  for(const [key,label] of [['game','게임 영역'],['face','얼굴 영역']]){
    const r=options[key];
    if(!Array.isArray(r)||r.length!==4||r.some((v,i)=>!Number.isFinite(v)||v<(i<2?0:1)||v>100))errors[key]=`${label}의 위치는 0~100%, 너비·높이는 1~100%로 입력하세요.`;
    else if(r[0]+r[2]>100.001)errors[key]=`${label}의 가로 위치 + 너비가 100%를 넘습니다.`;
    else if(r[1]+r[3]>100.001)errors[key]=`${label}의 세로 위치 + 높이가 100%를 넘습니다.`;
    else if((width>0&&r[2]*width/100<2)||(height>0&&r[3]*height/100<2))errors[key]=`${label}의 너비·높이는 원본 기준 최소 2픽셀이어야 합니다.`;
  }
  return errors;
}
export function showFrameErrors(errors){
  for(const key of ['game','face']){
    document.getElementById(key+'-error').textContent=errors[key]?errors[key]+' 자막은 계속 표시되며, 화면 미리보기만 전체 영역을 대신 보여줍니다.':'';
    for(const field of ['x','y','w','h']){
      const input=document.getElementById(key+'-'+field);
      input.setAttribute('aria-invalid',String(!!errors[key]));
      input.setAttribute('aria-describedby',key+'-error');
    }
  }
}
