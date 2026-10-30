export function parseTime(text){
  const s=String(text).trim();if(!/^\d+:\d{2}:\d{2}(\.\d{1,3})?$/.test(s))throw Error('시각은 HH:MM:SS 또는 HH:MM:SS.밀리초로 입력하세요.');
  const [h,m,v]=s.split(':').map(Number);if(m>=60||v>=60)throw Error('분과 초는 60 미만으로 입력하세요.');return h*3600+m*60+v;
}
export function clock(seconds){
  const ms=Math.max(0,Math.round((Number(seconds)||0)*1000)),s=Math.floor(ms/1000);
  return `${String(Math.floor(s/3600)).padStart(2,'0')}:${String(Math.floor(s/60)%60).padStart(2,'0')}:${String(s%60).padStart(2,'0')}.${String(ms%1000).padStart(3,'0')}`;
}
export function validPoints(values,duration){
  if(values.length>200)throw Error('분할점은 최대 200개입니다.');
  if(values.some(v=>!Number.isFinite(v)||v<=0||v>=duration))throw Error('영상 시작과 끝 사이의 시각을 입력하세요.');
  if(new Set(values).size!==values.length)throw Error('같은 분할점이 이미 있습니다.');return [...values].sort((a,b)=>a-b);
}
export function intervals(minutes,duration){
  if(!Number.isFinite(minutes)||minutes<=0)throw Error('간격은 0보다 큰 분 단위로 입력하세요.');
  const count=Math.ceil(duration/(minutes*60))-1;if(count>200)throw Error('간격을 늘려 주세요. 분할점은 최대 200개입니다.');
  return validPoints(Array.from({length:count},(_,i)=>Math.round((i+1)*minutes*60000)/1000),duration);
}
