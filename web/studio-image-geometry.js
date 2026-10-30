// 위치는 화면 중심 백분율, 크기는 화면 너비 백분율이다. 기존 저장 형식과 동일하다.
const clamp=(v,lo,hi)=>Math.max(lo,Math.min(hi,v));
const step=v=>Math.round(v*2)/2;
export function imageRect(value,frame,aspect){
  const width=frame.width*value.width/100,height=width/aspect;
  return {x:frame.width*value.x/100-width/2,y:frame.height*value.y/100-height/2,width,height};
}
export function imageGesture(start,frame,aspect,handle,dx,dy){
  if(!handle)return {...start,x:clamp(step(start.x+dx/frame.width*100),0,100),y:clamp(step(start.y+dy/frame.height*100),0,100)};
  const sx=handle.includes('e')?1:-1,sy=handle.includes('s')?1:-1,r=imageRect(start,frame,aspect);
  const anchorX=r.x+(sx<0?r.width:0),anchorY=r.y+(sy<0?r.height:0);
  // 대각선에 포인터 이동량을 투영해 비율을 유지하고 반대 모서리를 고정한다.
  const projected=r.width+(sx*dx+sy*dy/aspect)/(1+1/aspect**2);
  const maxWidth=Math.min(frame.width,2*(sx>0?frame.width-anchorX:anchorX),2*(sy>0?frame.height-anchorY:anchorY)*aspect);
  const width=clamp(step(clamp(projected,frame.width*.01,maxWidth)/frame.width*100),1,100);
  return {...start,width,x:clamp(step((anchorX+sx*frame.width*width/200)/frame.width*100),0,100),y:clamp(step((anchorY+sy*frame.width*width/(200*aspect))/frame.height*100),0,100)};
}
