import assert from 'node:assert/strict';
import {createSpeech} from '../web/speech.js';

const nodes = new Map();
function node() {
  return {value:'', dataset:{}, children:[], textContent:'', disabled:false,
    append(...items){this.children.push(...items);if(this.value==='')this.value=String(items[0]?.value ?? '');},
    replaceChildren(...items){this.children=[];this.value='';this.append(...items);},
    pause(){},load(){},addEventListener(){},removeAttribute(){},setAttribute(){}};
}
globalThis.document = {
  getElementById(id){if(!nodes.has(id))nodes.set(id,node());return nodes.get(id);},
  createElement:node,querySelectorAll:()=>[],
};
const $=id=>document.getElementById(id);
const settle=()=>new Promise(resolve=>setImmediate(resolve));
const pending=()=>{let resolve,reject;const promise=new Promise((yes,no)=>{resolve=yes;reject=no;});return {promise,resolve,reject};};
const details=(index=1)=>({tracks:[{index,channels:1,codec:'aac',language:'ko'}],duration_ms:10000,estimated_bytes:320000,
  model:{name:'검증 모델',ready:true,engine:true,bytes:1,free_bytes:1}});
let current, infoCalls=0;
const responses=[],actions=[];
const project=(state='downloading',extra={})=>({path:'/검증/vod-1',root:'/검증',vod_id:'1',model_root:'/모델',
  metadata:{title:'검증'},locked:false,voices:{},tasks:{video:{state,assets:{playback:'media/original.mp4'}}},
  speech:{state:'idle',message:'',versions:[],options:{}},...extra});
const view=createSpeech({player:{reset(){}},onProject:value=>select(value),api:async(action,data)=>{
  if(action==='speech-info'){
    infoCalls++;
    if(current.tasks.video.state!=='complete')throw Error('영상 다운로드와 검사를 먼저 완료하세요');
    return responses.length ? await responses.shift() : details();
  }
  if(action==='speech-result')return {items:[],total:0,next_cursor:null};
  actions.push({action,data});return current;
}});
function select(value){current=value;view.setProject(value);}

// 다운로드 중 열었던 같은 VOD가 완료되면 새로고침 없이 음성 추출을 시작할 수 있다.
select(project());await settle();
assert.equal($('extract-audio').disabled,true);
$('speech-vad').value='sensitive';$('speech-prompt').value='사용자 용어';
select(project('verifying'));await settle();
select(project('complete'));await settle();
assert.equal($('extract-audio').disabled,false,'영상 검증 완료 후 음성 추출이 자동 활성화되어야 함');
assert.equal(infoCalls,1,'다운로드·검증 중에는 영상 정보 조회를 보내지 않아야 함');
assert.equal($('speech-vad').value,'sensitive');assert.equal($('speech-prompt').value,'사용자 용어');
await $('extract-audio').onclick();
assert.deepEqual(actions.at(-1),{action:'speech-start',data:{root:'/검증',vod_id:'1',action:'audio',track:1}});
for(let n=0;n<5;n++)select({...current,tasks:{...current.tasks,chat:{state:'running',progress:{messages:n}}}});
await settle();assert.equal(infoCalls,1,'채팅 진행 폴링으로 영상 정보를 반복 조회하면 안 됨');

// 영상 완료 뒤 채팅 등 다른 작업의 잠금이 풀려야 시작 가능하다.
select(project('verifying',{locked:true}));
select(project('complete',{locked:true}));await settle();
assert.equal($('extract-audio').disabled,true);
select({...current,locked:false});assert.equal($('extract-audio').disabled,false);
assert.equal(infoCalls,2);

// 동일 VOD 재검증/파일 교체 시 이전 요청의 실패·성공 모두 최신 정보를 덮어쓰면 안 된다.
const oldFailure=pending();responses.push(oldFailure.promise);
select(project('complete',{model_root:'/다른 모델'}));
assert.equal($('extract-audio').disabled,true);
select(project('verifying',{model_root:'/다른 모델'}));
select(project('complete',{model_root:'/다른 모델'}));await settle();
oldFailure.reject(Error('이전 조회 실패'));await settle();
assert.equal($('extract-audio').disabled,false);assert.doesNotMatch($('speech-source').textContent,/이전 조회 실패/);
const oldSuccess=pending();responses.push(oldSuccess.promise);
select(project('complete'));
responses.push(Promise.resolve(details(3)));
select({...current,tasks:{video:{state:'complete',assets:{playback:'media/playback-v2.mp4'}}}});await settle();
oldSuccess.resolve(details(8));await settle();
assert.deepEqual($('speech-track').children.map(x=>x.value),[3]);

// 다른 VOD 및 선택 해제 이후에 도착하는 응답도 무시한다.
const other=pending();responses.push(other.promise);
select(project('complete',{model_root:'/새 모델'}));
select(project('complete',{path:'/검증/vod-2',vod_id:'2'}));await settle();
other.resolve(details(9));await settle();
assert.deepEqual($('speech-track').children.map(x=>x.value),[1]);
const cleared=pending();responses.push(cleared.promise);
select({...current,model_root:'/변경 모델'});select(null);
const textBefore=$('speech-source').textContent;
cleared.resolve(details(7));await settle();
assert.equal($('speech-source').textContent,textBefore);

// 오디오 없음·실제 조회 실패는 완료 상태를 허위로 표시하지 않는다.
responses.push(Promise.resolve({...details(),tracks:[]}));select(project('complete'));await settle();
assert.equal($('extract-audio').disabled,true);assert.match($('speech-source').textContent,/오디오 트랙이 없는/);
const failed=pending();responses.push(failed.promise);select({...current,model_root:'/오류 모델'});
failed.reject(Error('영상 파일을 읽지 못했습니다'));await settle();
assert.equal($('extract-audio').disabled,true);assert.match($('speech-source').textContent,/영상 파일을 읽지 못했습니다/);
console.log('다운로드·검증 완료 자동 인식, 잠금 해제, 요청 순서, VOD 전환, 입력 보존, 오류 차단 검사 통과');
