import assert from 'node:assert/strict';
import {elapsedText} from '../web/task-timing.js';
import {contextReactions} from '../web/context-reactions.js';
import {createAudioPreview} from '../web/audio-preview.js';

assert.match(elapsedText({state:'running',timing:{elapsed_ms:3000,since_ms:1000}},4000), /경과 시간 00:00:06/);
assert.match(elapsedText({state:'complete',timing:{elapsed_ms:3661000,since_ms:null}},99999), /완료까지 소요 시간 01:01:01/);
assert.match(elapsedText({state:'paused',timing:{elapsed_ms:3000,since_ms:null,partial:true}},99999), /00:00:03 이상/);
assert.match(elapsedText({state:'complete'}), /기록 없음/);
assert.match(elapsedText(null), /작업을 시작/);

const items=[{start_ms:1000,end_ms:2000},{start_ms:2000,end_ms:3000},{start_ms:3000,end_ms:4000,gap:true}];
const analysis={complete_source:true,candidates:[{kind:'burst',start_ms:0,end_ms:1000},{kind:'consonant',start_ms:1500,end_ms:2000},{kind:'word',start_ms:3000,end_ms:3500}]};
const before=JSON.stringify({items,analysis});
assert.deepEqual(contextReactions(items,analysis).items.map(r=>r.reaction_count),[1,0,0]);
assert.deepEqual(contextReactions(items,analysis,1000).items.map(r=>r.reaction_count),[1,1,0]);
assert.deepEqual(contextReactions(items,analysis,-1000).items.map(r=>r.reaction_count),[0,1,0]);
for(const value of [null,{unreadable:true},{...analysis,stale:true}])assert.equal(contextReactions(items,value).items[0].reaction_count,0);
assert.equal(contextReactions(items,analysis,0,true).items[0].reaction_count,0);
assert.match(contextReactions(items,{...analysis,complete_source:false}).note,/일부 채팅/);
assert.equal(JSON.stringify({items,analysis}),before);
const hierarchy=[{id:'parent',kind:'topic',start_ms:0,end_ms:4000},
  {id:'child',kind:'story',start_ms:1000,end_ms:2000,reactions:[{id:'event',start_ms:1500,end_ms:1700}]},
  {id:'quiet',kind:'story',start_ms:2000,end_ms:3000}];
const hierarchyBefore=JSON.stringify(hierarchy),marked=contextReactions(hierarchy,analysis).items;
assert.deepEqual(marked.map(r=>r.reaction_count),[3,1,0]);
assert.equal(marked[1].reactions[0].reaction_count,1);
assert.equal(contextReactions(hierarchy,{...analysis,stale:true}).items[1].reactions[0].reaction_count,0);
const peaksAnalysis={complete_source:true,candidates:[
  {kind:'burst',start_ms:0,end_ms:5000,peak_ms:1000},
  {kind:'word',start_ms:0,end_ms:5000,peak_ms:1000},
  {kind:'consonant',start_ms:4000,end_ms:8000,peak_ms:6000},
  {kind:'word',start_ms:0,end_ms:5000,peak_ms:9999}
]};
const peakItems=[{start_ms:2000,end_ms:6000},{start_ms:0,end_ms:6000,failed:true}];
assert.deepEqual(contextReactions(peakItems,peaksAnalysis,1000,false,7000).items.map(r=>r.reaction_peaks),[[2000],[]]);
assert.deepEqual(contextReactions(peakItems,peaksAnalysis,0,false,10000).items[0].reaction_peaks,[1000,6000]);
assert.deepEqual(contextReactions(peakItems,peaksAnalysis,0,true).items[0].reaction_peaks,[]);
assert.equal(JSON.stringify(hierarchy),hierarchyBefore);

let status='',nextFrame=0;const frames=new Map(),handlers=new Map();
globalThis.requestAnimationFrame=fn=>{frames.set(++nextFrame,fn);return nextFrame;};
globalThis.cancelAnimationFrame=id=>frames.delete(id);
const emit=async event=>{for(const fn of handlers.get(event)||[])await fn();};
const audio={duration:NaN,currentTime:0,paused:true,src:'',reject:false,
  getAttribute(){return this.src;},addEventListener(event,fn){handlers.set(event,[...(handlers.get(event)||[]),fn]);},
  load(){this.duration=NaN;},pause(){this.paused=true;emit('pause');},
  async play(){if(this.reject)throw Error('재생 차단');this.paused=false;await emit('play');}};
const preview=createAudioPreview(audio,value=>status=value);
preview.play('음성.wav',{start_ms:1000,end_ms:1800},'A화자');assert.equal(audio.paused,true);
audio.duration=10;await emit('loadedmetadata');assert.equal(audio.currentTime,1);assert.equal(audio.paused,false);
audio.currentTime=1.81;await emit('timeupdate');assert.equal(audio.currentTime,1.8);assert.equal(audio.paused,true);assert.equal(frames.size,0);
preview.play('음성.wav',{start_ms:2000,end_ms:3000},'B화자');await Promise.resolve();assert.equal(audio.currentTime,2);
preview.play('음성.wav',{start_ms:4000,end_ms:5000},'C화자');await Promise.resolve();assert.equal(audio.currentTime,4);
audio.currentTime=5.1;for(const fn of [...frames.values()])fn();assert.equal(audio.paused,true);assert.equal(audio.currentTime,5);
preview.play('다른 음성.wav',{start_ms:0,end_ms:1000},'D화자');preview.stop();audio.duration=10;await emit('loadedmetadata');assert.equal(audio.paused,true);
preview.play('다른 음성.wav',{start_ms:11000,end_ms:12000},'D화자');assert.match(status,/벗어났습니다/);
audio.reject=true;preview.play('다른 음성.wav',{start_ms:0,end_ms:1000},'D화자');await Promise.resolve();await Promise.resolve();assert.match(status,/시작하지 못했습니다/);
await emit('error');assert.match(status,/읽을 수 없습니다/);
preview.play('다른 음성.wav',{start_ms:1000,end_ms:500},'D화자');assert.match(status,/구간이 없습니다/);
console.log('경과 시간·문맥 반응 경계/보정·원음 미리듣기 중단/오류 검사 통과');

const scores={...analysis,reaction_index:{comparable:true,points:[{at_ms:1500,index:1},{at_ms:2500,index:10},{at_ms:2600,index:5}]}};
assert.deepEqual(contextReactions(items,scores).items.map(r=>r.reaction_index),[1,10,0]);
assert.equal(contextReactions([{start_ms:1000,end_ms:5000}],scores).items[0].reaction_index,10);
assert.equal(contextReactions([{start_ms:2500,end_ms:2600}],scores).items[0].reaction_index,10);
assert.equal(contextReactions([{start_ms:2600,end_ms:3000}],scores).items[0].reaction_index,5);
assert.equal(contextReactions([{start_ms:0,end_ms:1000}],scores).items[0].reaction_index,0);
assert.equal(contextReactions(items,scores,1000).items[0].reaction_index,0);
assert(contextReactions(items,{...scores,unavailable:true}).items.every(x=>x.reaction_index===0));
