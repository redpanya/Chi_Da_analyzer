import assert from 'node:assert/strict';
import {createMixPlayback} from '../web/mix-studio.js';

globalThis.requestAnimationFrame=()=>1;
globalThis.cancelAnimationFrame=()=>{};
const sources=[],seeks=[],active=[];
const video={
  file:null,clock:0,paused:true,seeking:false,ended:false,error:null,
  getAttribute(){return this.file;},hasAttribute(){return this.file!==null;},removeAttribute(){this.file=null;},
  set src(url){this.file=url;sources.push(url);},
  set currentTime(value){seeks.push(value);this.clock=value;},
  get currentTime(){return this.clock;},
  async play(){this.paused=false;},pause(){this.paused=true;},load(){}
};
const items=[
  {key:'a',preview_key:'a',origin:90000,start_ms:91000,end_ms:92000},
  {key:'b',preview_key:'a',origin:90000,start_ms:92000,end_ms:93000},
  {key:'c',preview_key:'a',origin:90000,start_ms:90500,end_ms:90800},
  {key:'d',preview_key:'d',origin:0,start_ms:90800,end_ms:91500}
];
let failures=0;
const playback=createMixPlayback(video,{items:()=>items,source:key=>'/'+key,
  changed:(_,index)=>active.push(index),failed:()=>failures++});
function advance(clock){video.clock=clock;video.ontimeupdate();}

playback.play(0);await Promise.resolve();
advance(2.01);
assert.deepEqual(seeks,[1]);
advance(3.01);
assert.deepEqual(seeks,[1,0.5]);
advance(0.81);
assert.deepEqual(seeks,[1,0.5,90.8]);
assert.deepEqual(sources,['/a','/d']);
assert.deepEqual(active,[0,1,2,3]);
const staleTimeUpdate=video.ontimeupdate;
advance(91.51);
assert.equal(playback.active(),false);
assert.equal(video.paused,true);

playback.play(1);
staleTimeUpdate();
assert.equal(active.at(-1),1);
video.error={};video.onerror();
assert.equal(failures,1);
assert.equal(playback.active(),false);
