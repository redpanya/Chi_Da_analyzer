import assert from 'node:assert/strict';
import {createSpeech} from '../web/speech.js';
import {getHelpContent} from '../web/help-content.js';

const nodes = new Map();
function node() {
  return {value:'', dataset:{}, children:[], textContent:'', disabled:false,
    append(...items){this.children.push(...items);}, replaceChildren(...items){this.children=items;},
    before(){},querySelectorAll(){return [];},pause(){}, load(){}, addEventListener(){}, removeAttribute(){}, setAttribute(){}};
}
globalThis.document = {
  getElementById(id){if(!nodes.has(id))nodes.set(id,node());return nodes.get(id);},
  createElement:tag=>({...node(),tagName:tag.toUpperCase()}), querySelectorAll:()=>[],
};
const $ = id=>document.getElementById(id), calls=[],seeks=[];let rowsRequests=0, items=[], preview=null;
const sources=[],selections=[];
const sceneUsage={
  setTranscript(result,project){sources.push({result,project});},
  transcriptCheckbox(item,run,segment){const button=document.createElement('button');button.className='secondary scene-selection-button';button.textContent='클립 담기';button.onclick=()=>selections.push({item,run,segment});return button;},
};
let project={path:'/검증/vod-1',root:'/검증',vod_id:'1',metadata:{title:'검증'},locked:false,voices:{},
  tasks:{video:{state:'complete',assets:{playback:'media/original.mp4'}}},
  speech:{state:'idle',message:'',raw_audio:{track:1},options:{input_kind:'sam',sam_profile:'standard'},versions:[]}};
const details={tracks:[{index:1,channels:1}],duration_ms:10000,estimated_bytes:320000,
  model:{ready:true,engine:true,bytes:1,free_bytes:1},
  sam:{ready:false,engine:false,profiles:[
    {id:'standard',label:'표준',description:'기존 설정'},
    {id:'balanced',label:'균형',description:'계산 절반'},
    {id:'fast',label:'빠름',description:'발음 손상 주의'}],speed_note:'10초 실측, 로딩 제외'}};
let view;
view=createSpeech({sceneUsage,player:{reset(){},seek(...args){seeks.push(args);}},showPreview:row=>preview=row,api:async(action,data)=>{
  if(action==='speech-info')return details;
  if(action==='speech-result'){rowsRequests++;return {items,total:items.length,next_cursor:null,run:project.speech.run};}
  calls.push({action,data});return project;
},onProject:value=>view.setProject(value)});
const settle=async()=>{await Promise.resolve();await Promise.resolve();};
view.setProject(project);await settle();
assert.equal($('transcribe').disabled,false);
assert.equal($('speech-vad').value,'standard');
$('speech-vad').value='sensitive';$('speech-vad').onchange();
$('speech-prompt').value='사용자 용어';assert.match(getHelpContent('speech-options',id=>$(id).value).current,/sensitive/);
project={...project,speech:{...project.speech,updated_at:'폴링'}};view.setProject(project);
assert.equal($('speech-vad').value,'sensitive');assert.equal($('speech-prompt').value,'사용자 용어');
await $('transcribe').onclick();
assert.equal(calls.at(-1).data.input_kind,'original');
assert.deepEqual(calls.at(-1).data.asr_options,{vad:'sensitive',prompt:'사용자 용어'});
assert.equal(calls.at(-1).data.sam_profile,undefined);
$('speech-vad').value='off';$('speech-vad').onchange();assert.match(getHelpContent('speech-options',id=>$(id).value).current,/off/);
view.setProject({...project,locked:true});assert.equal($('speech-vad').disabled,true);assert.equal($('speech-prompt').disabled,true);
project={...project,path:'/검증/vod-2',speech:{...project.speech,options:{asr_options:{vad:'off',prompt:'다른 자료'}}}};
view.setProject(project);await settle();
assert.equal($('speech-vad').value,'off');assert.equal($('speech-prompt').value,'다른 자료');
assert.equal($('separate-speech').onclick,undefined);assert.equal($('prepare-sam').onclick,undefined);
const count=rowsRequests;view.setProject({...project,voices:{run:'새 화자 분석',revision:8,updated_at:'변경'}});await settle();
assert.equal(rowsRequests,count);
project={...project,speech:{...project.speech,run:'선택 전사',versions:[{id:'선택 전사',label:'한국어 · 원음 · 표준'}]}};
view.setProject(project);await settle();
globalThis.confirm=()=>false;
const beforeDelete=calls.length;await $('speech-delete').onclick();assert.equal(calls.length,beforeDelete);
globalThis.confirm=()=>true;
await $('speech-delete').onclick();assert.equal(calls.at(-1).data.action,'delete');assert.equal(calls.at(-1).data.run,'선택 전사');
console.log('원음 전사·옵션·폴링 보존·잠금·VOD별 설정·선택 삭제 확인 통과');
items=[{id:'발언1',start_ms:1000,end_ms:3000,text:'영상 확인',original_text:'영상 확인'}];
await $('speech-search').onsubmit({preventDefault(){}});await settle();
const card=$('transcript-rows').children[0],scene=card.children.find(n=>n.className==='scene-copy'),actions=card.children.find(n=>n.className==='play-actions scene-actions').children;
assert.equal(sources.at(-1).project,project);assert.equal(sources.at(-1).result.items,items);
const selectionButton=actions.find(n=>n.className.includes('scene-selection-button'));selectionButton.onclick();
assert.deepEqual(selections.at(-1),{item:{id:'transcript:선택 전사:발언1',start_ms:1000,end_ms:3000,summary:{title:'영상 확인'}},run:'선택 전사',segment:'발언1'});
assert.equal(scene.children[0].textContent,'00:00:01 → 00:00:03');assert.equal(scene.children[1].textContent,'영상 확인');scene.onclick();assert.deepEqual(seeks,[[1000,true,3000]]);
assert.deepEqual(actions.map(n=>n.textContent),['클립 담기','내용근거']);
const correction=card.children.find(n=>n.className==='scene-details'),reviewActions=correction.children[1].children;
assert.equal(card.children.some(n=>n.className==='hint'&&n.textContent.includes('자동 전사')),false);
assert.ok(correction.children.some(n=>n.textContent.includes('자동 전사 · 원음 확인 필요')),'일반 주의 설명은 원음·교정 패널에 보존');
assert.deepEqual(reviewActions.map(n=>n.textContent),['음성 듣기','화자 검토 (선택)','작은 창에서 영상보기']);
assert.ok(reviewActions.every(n=>typeof n.onclick==='function')); // 보조 기능은 접힌 원음/교정 영역에서 계속 사용한다.
assert.equal(correction.hidden,true,'추가 내용은 근거 패널에서 확인한다');
const together=reviewActions.find(n=>n.textContent==='작은 창에서 영상보기');
together.onclick();assert.deepEqual(preview,items[0]);
const draft=correction.children[3];
correction.open=true;correction.ontoggle();draft.value='저장하기 전 교정 내용';draft.oninput();
project={...project,speech:{...project.speech,updated_at:'진행 결과 갱신'}};view.setProject(project);await settle();
const preserved=$('transcript-rows').children[0].children.find(n=>n.className==='scene-details');
assert.equal(preserved.children[3].value,'저장하기 전 교정 내용');assert.equal(preserved.open,true);
assert.equal(items[0].text,'영상 확인'); // 폴링 동안 원문·서버 전사에는 쓰지 않는다.
items[0].video_start_ms=200;items[0].video_end_ms=2200;
together.onclick();assert.equal(preview.start_ms,200);assert.equal(preview.end_ms,2200);
assert.equal(items[0].start_ms,1000);assert.equal(items[0].end_ms,3000);
await $('speech-search').onsubmit({preventDefault(){}});await settle();
$('transcript-rows').children[0].children.find(n=>n.className==='play-actions scene-actions').children[0].onclick();
assert.equal(selections.at(-1).item.start_ms,200);assert.equal(selections.at(-1).item.end_ms,2200);
preview=null;project={...project,speech:{...project.speech,stale:true}};view.setProject(project);together.onclick();
assert.equal(preview,null);assert.match($('speech-notice').textContent,/이전 입력/);
assert.equal(calls.some(call=>call.action==='studio-transcript-add'),false);
console.log('전사 행 재생, 교정 패널, 공통 선택 및 클립 버튼 연결, 영상 시각 반영, 미저장 교정 보존, 이전 입력 재생 차단 통과');

project={...project,speech:{...project.speech,stale:false}};items[0].quality_review=true;items[0].quality_notes=['발화 근거 부족'];view.setProject(project);await settle();
await $('speech-search').onsubmit({preventDefault(){}});await settle();
const flagged=$('transcript-rows').children[0];assert.equal(flagged.children.find(n=>n.className==='scene-details').children.find(n=>n.className==='result-source-review').textContent,'원음 확인 필요 · 요약 제외');
assert.ok(flagged.children.find(n=>n.className==='scene-details').children.some(n=>n.textContent.includes('발화 근거 부족')));
console.log('일반 안내 접기·실제 품질 경고 직접 표시·상세 사유 보존 통과');
