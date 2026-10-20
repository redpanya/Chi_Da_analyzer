import {timecode} from './player.js';
export function speakerColor(id) {
  if (!id) return '#81968a';
  let value=0; for(const char of id)value=(value*31+char.charCodeAt(0))>>>0;
  return `hsl(${value%360} 48% 66%)`;
}
// 기존 저장 범위 판독과 테스트의 호환을 유지한다. 새 UI는 범위 저장을 하지 않는다.
export function selectedRange(start,end,duration){
  if(![start,end,duration].every(Number.isFinite)||start<0||end<=start||end>duration)throw Error('선택 범위는 영상 안에서 시작 < 끝이어야 합니다.');
  return {start_ms:Math.round(start),end_ms:Math.round(end)};
}
export function viewport(duration,center,span){
  const size=Math.min(Math.max(1,duration),span>0?span:duration||1);
  const start=Math.max(0,Math.min(Math.max(0,duration-size),center-size/2));
  return {start,end:start+size};
}
export function timeAt(fraction,view){return Math.round(view.start+Math.max(0,Math.min(1,fraction))*(view.end-view.start));}
export function createTimeline({canvas,onSeek,onPan,onZoom}){
  let info=null,position=0,view={start:0,end:1},down=null;
  const left=86,height=214;
  function draw(){
    if(!info){canvas.getContext('2d').clearRect(0,0,canvas.width,canvas.height);return;}
    if(canvas.clientWidth<=left)return;
    const width=canvas.clientWidth,ratio=devicePixelRatio||1,area=width-left;
    canvas.width=width*ratio;canvas.height=height*ratio;
    const ctx=canvas.getContext('2d');ctx.scale(ratio,ratio);ctx.fillStyle='#FAFAFA';ctx.fillRect(0,0,width,height);
    const x=ms=>left+(ms-view.start)/(view.end-view.start)*area;
    const block=(start,end,y,h,color)=>{if(end<view.start||start>view.end)return;ctx.fillStyle=color;ctx.fillRect(Math.max(left,x(start)),y,Math.max(1,Math.min(width,x(end))-Math.max(left,x(start))),h);};
    const stripe=(start,end,y,h)=>{const a=Math.max(left,x(start)),b=Math.min(width,x(end));if(b<=a)return;block(start,end,y,h,'#E5E2DE');ctx.strokeStyle='#99938D';ctx.save();ctx.beginPath();ctx.rect(a,y,b-a,h);ctx.clip();for(let at=Math.floor((a-h)/10)*10;at<b;at+=10){ctx.beginPath();ctx.moveTo(at,y+h);ctx.lineTo(at+h,y);ctx.stroke();}ctx.restore();};
    for(const [label,y] of [['채팅 / 10초',25],['반응 후보',87],['발언·화자',125],['인식 실패',165]]){ctx.fillStyle='#54504A';ctx.font='11px sans-serif';ctx.fillText(label,5,y);block(view.start,view.end,y+7,1,'#D5D1CC');}
    const graph=info.graph||[],max=Math.max(1,...graph.map(r=>r.messages||0));
    if(!graph.length)stripe(view.start,view.end,12,42);
    // 같은 화면 열의 최대값을 보존하여 전체 보기에서도 짧은 급증이 사라지지 않게 한다.
    const columns=new Map();
    for(const bin of graph){const start=bin.start_ms+info.chat_offset_ms,end=bin.end_ms+info.chat_offset_ms;if(end<view.start||start>view.end)continue;
      if(bin.coverage!=='known'||info.boundary_unverified)stripe(start,end,12,42);
      if(bin.messages!=null){const key=Math.floor(x(start));const old=columns.get(key);if(!old||old.messages<bin.messages)columns.set(key,{start,end,messages:bin.messages});}}
    for(const bin of columns.values()){const h=bin.messages/max*42;block(bin.start,bin.end,54-h,h,'#86c99d');}
    for(const row of info.reactions||[])block(row.start_ms,row.end_ms,69,18,'#daba7d');
    stripe(info.processed_ms||0,info.duration_ms,105,31);
    for(const row of info.tracks||[]){block(row.start_ms,row.end_ms,105,31,speakerColor(row.speaker));if(row.status==='failed')block(row.start_ms,row.end_ms,151,18,'#f4a47d');}
    ctx.fillStyle='#54504A';ctx.font='11px monospace';
    for(let n=0;n<=4;n++){const ms=timeAt(n/4,view);ctx.textAlign=n===4?'right':n===0?'left':'center';ctx.fillText(timecode(ms),left+area*n/4,203);}ctx.textAlign='left';
    if(position>=view.start&&position<=view.end){ctx.strokeStyle='#18181B';ctx.beginPath();ctx.moveTo(x(position),0);ctx.lineTo(x(position),185);ctx.stroke();}
    canvas.setAttribute('aria-valuemin','0');canvas.setAttribute('aria-valuemax',String(Math.round(info.video_ms||info.duration_ms)));canvas.setAttribute('aria-valuenow',String(position));canvas.setAttribute('aria-valuetext',timecode(position));
  }
  const at=event=>{const r=canvas.getBoundingClientRect();return timeAt((event.clientX-r.left-left)/(r.width-left),view);};
  canvas.onpointerdown=e=>{if(!info||e.button!==0)return;down={x:e.clientX,center:(view.start+view.end)/2,span:view.end-view.start};canvas.setPointerCapture(e.pointerId);};
  canvas.onpointerup=e=>{if(!down||!info)return;const previous=down;down=null;const dx=e.clientX-previous.x;if(Math.abs(dx)>5)onPan(previous.center-dx/(canvas.clientWidth-left)*previous.span);else onSeek(at(e));};
  canvas.onpointercancel=()=>{down=null;};
  canvas.onkeydown=e=>{if(!info)return;const limit=info.video_ms||info.duration_ms;if(['ArrowLeft','ArrowRight','Home','End'].includes(e.key)){e.preventDefault();onSeek(e.key==='Home'?0:e.key==='End'?limit:Math.max(0,Math.min(limit,position+(e.key==='ArrowLeft'?-5000:5000))));}else if(['ArrowUp','ArrowDown'].includes(e.key)){e.preventDefault();onZoom(e.key==='ArrowUp'?1:-1);}};
  new ResizeObserver(draw).observe(canvas);
  return {set(value,ms,range){info=value;position=ms;view=range||view;draw();}};
}
