export function fastConflicts(o,selection){
  if(o.speed!=='fast')return [];
  const values=[[o.mode!=='separate','구간별 저장'],[o.ratio!=='original'||o.layout!=='single','한 화면·원본 비율'],[o.size!=='source','원본 크기'],[o.caption,'자막 합성 끄기'],[o.sidecar&&selection,'편집용 자막 끄기'],[o.volume!==100,'음량 100%'],[o.brightness!==0||o.contrast!==1||o.saturation!==1||o.fade!==0,'화면 효과·페이드 해제']];
  if(o.image)values.push([true,'PNG 이미지 제거']);
  return values.filter(([bad])=>bad).map(([,label])=>label);
}
