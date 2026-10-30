import assert from 'node:assert/strict';
import {createContext} from '../web/context.js';
const created=[];
class Element{
  constructor(){created.push(this);}
  after(...values){this.afterNodes=values;}
  before(value){this.beforeNode=value;}
  addEventListener(k,v){(this.listeners??={})[k]=v;}
  dataset={};classList={add(){},toggle(){}};
  children=[];attributes={};value='';textContent='';hidden=false;disabled=false;checked=false;scrollTop=0;
  append(...values){for(const child of values){child.remove?.();if(typeof child==='object')child.parentElement=this;this.children.push(child);}}
  remove(){if(this.parentElement)this.parentElement.children=this.parentElement.children.filter(c=>c!==this);this.parentElement=null;}
  replaceChildren(...values){for(const c of this.children)if(typeof c==='object')c.parentElement=null;this.children=[];this.append(...values);}
  setAttribute(k,v){this.attributes[k]=v;} removeAttribute(k){delete this.attributes[k];}
  querySelectorAll(){return [];} focus(){this.focused=true;} pause(){this.paused=true;}
}
const elements=new Map();globalThis.document={addEventListener(){},createElement:()=>new Element(),querySelectorAll:()=>created.filter(n=>n.commentSource),getElementById(id){if(!elements.has(id))elements.set(id,new Element());return elements.get(id);}};
globalThis.Option=class extends Element{constructor(text,value){super();this.textContent=text;this.value=value;}};
const $=id=>document.getElementById(id),calls=[],flush=()=>new Promise(resolve=>setImmediate(resolve));
let delay=null,external=false,clears=0,deleteFailure=false,lastProject;const drafts=new Map();
const clip={id:'clip-1',title:'클립 제목',summary:'대화 내용',reason:'반전',start_ms:1000,peak_ms:2000,end_ms:3000,video_checks:[],uncertainties:[],evidence:[],chat_evidence:[],review_needed:true};
const api=async(action,args)=>{
  calls.push({action,args});
  if(action==='context-delete'){if(deleteFailure)throw Error('휴지통 사용 불가');return {...lastProject,context:{...lastProject.context,run:lastProject.context.run===args.run?null:lastProject.context.run,clip_run:lastProject.context.clip_run===args.run?null:lastProject.context.clip_run,runs:lastProject.context.runs.filter(r=>r.id!==args.run)}};}
  if(action==='context-background')return {text:''};
  if(action==='analysis')return null;
  if(action==='context-comment')return structuredClone(drafts.get(args.run)||{revision:0,rows:[],format:2,legacy_text:''});
  if(action==='context-comment-save'){const value={...structuredClone(args.draft),revision:args.draft.revision+1};drafts.set(args.run,value);return value;}
  if(action==='context-result'){
    if(delay&&args.run==='detail')await new Promise(resolve=>delay.resolve=resolve);
    return {id:args.run,mode:args.run,version:11,scope:'full',origin:'external',complete:true,items:args.run==='clips'?[clip]:[],notes:[],done:1,total:1,input_label:'가상 전사'};
  }
  throw Error('예상하지 않은 쓰기 요청: '+action);
};
const view=createContext({api,player:{clearRange(){clears++;}},onProject(value){lastProject=value;view.setProject(value);},onExternal(){external=true;}});
const project={path:'/test/vod-1',root:'/test',vod_id:'1',metadata:{title:'가상 VOD'},tasks:{video:{state:'complete'},chat:{state:'complete'}},context:{state:'complete',run:'detail',clip_run:'clips',runs:['detail','timestamps','clips'].map(mode=>({id:mode,mode,label:mode,title:'검증'}))}};
lastProject=project;view.setProject(project);await flush();
assert.equal($('context-view-panel').hidden,false);assert.equal($('context-clips-panel').hidden,true);
assert.equal($('context-version').value,'detail');assert.equal($('context-clips-version').value,'clips');
assert.equal($('video-result').parentElement,$('context-video'));
$('context-tab-detail').onkeydown({key:'End',preventDefault(){}});await flush();
assert.equal($('context-tab-clips').attributes['aria-selected'],'true');assert($('context-tab-clips').focused);
assert.equal($('context-view-panel').hidden,true);assert.equal($('context-clips-panel').hidden,false);
assert.equal(view.videoTarget(),'context-clips-video');assert.equal($('video-result').parentElement,$('context-clips-video'));
assert.equal($('context-comment-panel').parentElement,$('context-clips-preview'));
const check=$('context-clips-result').children[0].children.find(e=>e.className==='inline-check context-check').children[0];
assert.equal(check.disabled,false);check.checked=true;check.onchange();
const line=$('context-comment-list').children[0];assert.equal(line.children[0].textContent,'00:00:01');assert.equal(line.children[1].value,'클립 제목');
line.children[1].value='편집한 클립 제목';line.children[1].oninput();
assert.equal($('player').paused,true);assert.equal($('context-generate').disabled,true);
view.setProject(structuredClone(project));await flush();assert.equal($('context-clips-panel').hidden,false);
$('context-clips-external').onclick();assert(external);
$('context-tab-clips').onkeydown({key:'ArrowLeft',preventDefault(){}});await flush();
assert.equal($('context-tab-timestamps').attributes['aria-selected'],'true');assert.equal($('context-version').value,'timestamps');
assert.equal($('context-comment-panel').parentElement,$('context-preview'));assert.equal($('context-comment-list').children.length,0);
assert.equal(drafts.get('clips').rows[0].title,'편집한 클립 제목');
view.setProject({...project,context:{...project.context,action:'clips',updated_at:'후보 갱신'}});await flush();
assert.equal($('context-comment-list').children.length,0); // 숨긴 클립 응답이 타임스탬프 목록을 덮지 않음
await view.openRun('clips','clips');assert.equal($('context-clips-panel').hidden,false);
assert.equal($('context-comment-list').children[0].children[1].value,'편집한 클립 제목');
assert.equal($('context-clips-result').children[0].children.find(e=>e.className==='inline-check context-check').children[0].checked,true);
$('context-tab-clips').onkeydown({key:'Home',preventDefault(){}});await flush();assert.equal($('context-version').value,'detail');
delay={};view.refresh();await flush();const waiting=delay;
$('context-tab-clips').onclick();waiting.resolve();delay=null;await flush();
assert.equal($('context-view-panel').hidden,true);assert.equal($('video-result').parentElement,$('context-clips-video'));
globalThis.confirm=()=>false;const requestsBefore=calls.length;
await $('context-clips-delete').onclick();assert.equal(calls.length,requestsBefore);
globalThis.confirm=()=>true;deleteFailure=true;
await $('context-clips-delete').onclick();assert.match($('context-delete-notice').textContent,/휴지통 사용 불가/);
assert.equal($('context-clips-version').value,'clips');assert.equal($('context-clips-delete').disabled,false);
deleteFailure=false;await $('context-clips-delete').onclick();await flush();
assert.equal($('context-clips-version').disabled,true);assert.equal($('context-clips-delete').disabled,true);
assert.equal($('context-clips-result').children.length,0);assert.equal($('context-comment-list').children.length,0);
$('context-tab-timestamps').onclick();await flush();assert.equal($('context-delete').disabled,false);
await $('context-delete').onclick();await flush();assert.equal($('context-version').value,'');assert.equal($('context-delete').disabled,true);
$('context-tab-detail').onclick();await flush();assert.equal($('context-version').value,'detail');
view.setProject({...lastProject,locked:true});assert.equal($('context-delete').disabled,true);
view.setProject(lastProject);await flush();await $('context-delete').onclick();await flush();
assert.equal($('context-version').value,'');assert.equal($('context-delete').disabled,true);
assert.deepEqual(calls.filter(r=>r.action==='context-delete').slice(-3).map(r=>r.args.run),['clips','timestamps','detail']);
console.log('세 모드 선택 버전 삭제·취소·잠금·실패 재시도·빈 목록 갱신 검사 통과');
view.setProject({...project,path:'/test/vod-2',vod_id:'2',context:{state:'idle',runs:[]}});await flush();
assert.equal($('context-clips-version').disabled,true);assert.equal($('context-clips-result').children.length,0);
assert.equal($('context-comment-list').children.length,0);assert.equal(clip.title,'클립 제목');
assert.equal($('context-view-panel').hidden,false);assert.ok(clears>=5);
console.log('문맥 3개 탭: 키보드 이동·플레이어 배치·이전 선택 복원·숨긴 응답 무시·프로젝트 전환·외부 분석 연결 통과');
