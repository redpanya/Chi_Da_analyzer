import assert from 'node:assert/strict';
import {selectedRange, speakerColor, viewport, timeAt, createTimeline} from '../web/timeline.js';
assert.deepEqual(selectedRange(1234, 3500, 5000), {start_ms:1234, end_ms:3500});
for (const [a,b,d] of [[-1,1,10],[2,2,10],[3,1,10],[0,11,10],[NaN,1,10],[0,1,Infinity]]) assert.throws(()=>selectedRange(a,b,d));
assert.equal(speakerColor('A'), speakerColor('A'));
assert.notEqual(speakerColor('A'), speakerColor('B'));
const duration=20*3600000;
assert.deepEqual(viewport(duration,0,600000),{start:0,end:600000});
assert.deepEqual(viewport(duration,duration,120000),{start:duration-120000,end:duration});
assert.deepEqual(viewport(5000,0,120000),{start:0,end:5000});
assert.deepEqual(viewport(duration,0,0),{start:0,end:duration});
assert.equal(timeAt(.5,viewport(duration,36000000,600000)),36000000);
assert.equal(timeAt(-1,{start:100,end:200}),100);
assert.equal(timeAt(2,{start:100,end:200}),200);
let seek,pan,zoom;
globalThis.ResizeObserver=class{observe(){}};
const canvas={clientWidth:0,setPointerCapture(){},getBoundingClientRect(){return {left:0,width:1086};}};
const timeline=createTimeline({canvas,onSeek:v=>seek=v,onPan:v=>pan=v,onZoom:v=>zoom=v});
timeline.set({duration_ms:duration,video_ms:duration},5000,{start:100000,end:200000});canvas.clientWidth=1086;
canvas.onpointerdown({button:0,clientX:586});canvas.onpointerup({clientX:586});assert.equal(seek,150000);
canvas.onpointerdown({button:0,clientX:586});canvas.onpointerup({clientX:686});assert.equal(pan,140000);
canvas.onkeydown({key:'ArrowRight',preventDefault(){}});assert.equal(seek,10000);
canvas.onkeydown({key:'ArrowUp',preventDefault(){}});assert.equal(zoom,1);
for(const length of [1800000,3600000,36000000,72000000])for(const center of [0,length/2,length]){
  const view=viewport(length,center,120000);
  assert(view.start>=0&&view.end<=length);
  assert.equal(timeAt(0,view),view.start);assert.equal(timeAt(1,view),view.end);
}
let strokes=0;
const ctx={scale(){},fillRect(){},fillText(){},save(){},restore(){},beginPath(){},rect(){},clip(){},moveTo(){},lineTo(){},stroke(){strokes++;}};
globalThis.devicePixelRatio=1;canvas.setAttribute=()=>{};canvas.getContext=()=>ctx;
const longInfo={duration_ms:duration,chat_offset_ms:0,tracks:[],reactions:[],boundary_unverified:true,
  graph:Array.from({length:7200},(_,i)=>({start_ms:i*10000,end_ms:(i+1)*10000,messages:i%12,coverage:'known'}))};
timeline.set(longInfo,0,viewport(duration,duration/2,120000));
assert(strokes<400);
strokes=0;timeline.set(longInfo,0,viewport(duration,0,0));assert(strokes<50000);
console.log('20시간 시간축의 확대 경계·클릭·가로 이동·키보드 탐색·화자 색 검사 통과');
