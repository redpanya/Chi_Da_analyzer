import test from 'node:test';
import assert from 'node:assert/strict';
import {createJobDetail,jobDetailKey} from '../web/job-detail.js';

// 패널 조회와 이벤트만 검사하며 네트워크, 작업 실행, 실제 파일은 사용하지 않는다.
class Element {
 constructor(tag,root){Object.assign(this,{tagName:tag.toUpperCase(),root,children:[],listeners:{},dataset:{},attributes:{},hidden:false,open:false,disabled:false,scrollTop:0,isConnected:true,_text:''});}
 set textContent(value){this._text=String(value);this.children=[];}
 get textContent(){return this._text+this.children.map(child=>child.textContent).join('');}
 setAttribute(name,value){this.attributes[name]=String(value);}
 append(...items){for(const item of items){item.parentElement=this;this.children.push(item);}}
 replaceChildren(...items){for(const old of this.children)old.isConnected=false;this.children=[];this._text='';this.append(...items);}
 addEventListener(name,fn){(this.listeners[name]||=[]).push(fn);}
 dispatchEvent(event){for(const fn of this.listeners[event.type]||[])fn(event);}
 focus(){this.root.activeElement=this;}
 show(){this.open=true;}
 close(){this.open=false;this.dispatchEvent({type:'close'});}
}
const deferred=()=>{let resolve,reject;const promise=new Promise((yes,no)=>{resolve=yes;reject=no;});return {promise,resolve,reject};};
const flush=()=>new Promise(resolve=>setImmediate(resolve));
const walk=element=>[element,...element.children.flatMap(walk)];
const request={root:'/보관함/.download-ranges/구간',vod_id:'123',kind:'context',run:'실행-a'};
const snapshot=(options={})=>({title:'검증 방송',label:'AI 문맥',state:'complete',message:'완료',fields:[{label:'분석 모드',value:'빠른 타임스탬프'}],progress:{fraction:1,label:'10 / 10'},timing:{elapsed_ms:123000},records:[{at:'2026-11-13T03:10:00Z',message:'처리 완료'}],result:{step:6,mode:'timestamps',run:'실행-a'},...options});
function fixture(t,api,onResult=async()=>{}){
 const root={activeElement:null,createElement(tag){return new Element(tag,this);},addEventListener(...args){this.body.addEventListener(...args);},querySelector(){return walk(this.body).find(el=>el.tagName==='DIALOG'&&el.open&&el.id!=='job-detail')||null;}};root.body=new Element('body',root);
 const timers=new Map();let timerId=0; t.mock.method(globalThis,'setInterval',fn=>{timers.set(++timerId,fn);return timerId;});t.mock.method(globalThis,'clearInterval',id=>timers.delete(id));
 const calls=[],results=[],selections=[];let changed=0;
 const panel=createJobDetail({root,api:async(action,data)=>{calls.push({action,data});return api(action,data);},onResult:async(...args)=>{results.push(args);return onResult(...args);},onChanged:()=>changed++,onSelection:key=>selections.push(key)});
 const byClass=name=>walk(root.body).find(el=>(el.className||'').split(' ').includes(name)),action=name=>walk(root.body).find(el=>el.dataset.jobAction===name);
 const dialog=byClass('job-detail'),body=byClass('result-drawer-body'),error=byClass('job-detail-error');
 t.after(()=>panel.close());return {root,panel,calls,results,selections,timers,dialog,body,error,byClass,action,get changed(){return changed;}};
}

test('닫기 모션 도중 다른 작업을 열어도 늦은 콜백이 새 패널을 닫지 않는다',async t=>{
 const f=fixture(t,()=>snapshot()),animations=[];
 f.dialog.animate=()=>{const animation={cancelled:false,cancel(){this.cancelled=true;}};animations.push(animation);return animation;};
 f.panel.open(request);await flush();
 f.byClass('result-drawer-close').onclick();const closing=animations.at(-1);
 assert.equal(f.dialog.open,true);assert.equal(f.dialog.inert,true);
 f.panel.open({...request,run:'실행-b'});await flush();closing.onfinish();
 assert.equal(closing.cancelled,true);assert.equal(f.dialog.inert,false);assert.equal(f.dialog.open,true);
 f.byClass('result-drawer-close').onclick();animations.at(-1).onfinish();
 assert.equal(f.dialog.open,false);assert.equal(f.timers.size,0);
});

test('상세 열기는 정확한 실행 조회만 하고 최근 5개 기록을 원문 텍스트로 표시한다',async t=>{
 const title='<img src=x onerror=bad> 방송',events=Array.from({length:7},(_,index)=>({at:'2026-11-13T03:10:00Z',message:'기록 '+index}));
 const f=fixture(t,()=>snapshot({title,fields:[{label:'실패 수',value:0}],records:events})),opener=f.root.createElement('button');
 f.panel.open(request,{opener});await flush();
 assert.deepEqual(f.calls,[{action:'job-detail',data:request}]);assert.equal(f.results.length,0);assert.equal(f.changed,0);
 assert.equal(f.byClass('job-detail-title').textContent,title);assert.equal(f.byClass('job-detail-title').children.length,0);
 assert.equal(f.byClass('job-detail-fields').children[1].textContent,'0');assert.equal(f.byClass('job-detail-records').children.length,5);
 assert.match(f.byClass('job-detail-records').children[0].textContent,/기록 2$/);assert.equal(f.timers.size,1);
 f.dialog.dispatchEvent({type:'cancel',preventDefault(){}});
 assert.equal(f.dialog.open,false);assert.equal(f.root.activeElement,opener);assert.equal(f.timers.size,0);assert.equal(f.calls.length,1);assert.equal(f.panel.key(),null);
});

test('다른 작업을 빠르게 선택하면 늦은 응답을 버리고 같은 패널만 사용한다',async t=>{
 const a=deferred(),b=deferred();let index=0;const f=fixture(t,()=>++index===1?a.promise:b.promise);
 f.panel.open(request);const next={...request,run:'실행-b'};f.panel.open(next);
 b.resolve(snapshot({title:'두 번째 방송'}));await flush();a.resolve(snapshot({title:'첫 번째 방송'}));await flush();
 assert.equal(f.byClass('job-detail-title').textContent,'두 번째 방송');assert.equal(f.panel.key(),jobDetailKey(next));
 assert.equal(walk(f.root.body).filter(el=>el.tagName==='DIALOG').length,1);assert.equal(f.timers.size,1);assert.equal(f.calls.length,2);
});

test('닫은 패널의 늦은 응답은 적용하지 않으며 닫기는 작업 취소를 호출하지 않는다',async t=>{
 const pending=deferred(),f=fixture(t,()=>pending.promise);f.panel.open(request);f.panel.close();pending.resolve(snapshot());await flush();
 assert.equal(f.dialog.open,false);assert.equal(f.panel.key(),null);assert.equal(f.timers.size,0);assert.equal(f.byClass('job-detail-title').textContent,'불러오는 중…');
 assert.deepEqual(f.calls.map(call=>call.action),['job-detail']);assert.equal(f.results.length,0);
});

test('자동 갱신은 스크롤과 버튼 포커스를 유지하고 진행 수치를 갱신한다',async t=>{
 let value=snapshot();const f=fixture(t,()=>value);f.panel.open(request);await flush();f.body.scrollTop=240;
 const button=f.action('result');button.focus();value=snapshot({message:'새 기록',progress:{fraction:.7,label:'7 / 10'},records:[{at:'2026-11-13T03:11:00Z',message:'갱신'}]});
 await [...f.timers.values()][0]();
 assert.equal(f.body.scrollTop,240);assert.equal(f.root.activeElement,button);assert.equal(f.action('result'),button);
 assert.equal(walk(f.root.body).find(el=>el.tagName==='PROGRESS').value,.7);assert.match(f.byClass('job-detail-records').textContent,/갱신/);
});

test('조회 실패 시 마지막 정보를 유지하고 정상 재조회하면 오류를 지운다',async t=>{
 let fail=false;const f=fixture(t,()=>{if(fail)throw new Error('외장 디스크 연결 없음');return snapshot();});f.panel.open(request);await flush();
 fail=true;await f.panel.refresh();assert.equal(f.byClass('job-detail-title').textContent,'검증 방송');assert.match(f.error.textContent,/마지막 조회.*외장 디스크/);assert.equal(f.error.hidden,false);
 fail=false;await f.panel.refresh();assert.equal(f.error.hidden,true);assert.equal(f.results.length,0);
});

test('대기 취소는 명시적 클릭으로만 실행하고 중복 클릭을 막는다',async t=>{
 const cancel=deferred(),data={id:'대기-작업'};const f=fixture(t,(action)=>action==='work-cancel'?cancel.promise:snapshot({state:'queued',result:null,records:[],actions:[{label:'대기 취소',action:'work-cancel',data}]}));
 const mutable={...request};f.panel.open(mutable);mutable.run='바뀐 외부 값';await flush();assert.equal(f.calls[0].data.run,'실행-a');
 const button=f.action('work-cancel'),first=button.onclick();button.onclick();assert.equal(button.disabled,true);assert.equal(f.calls.filter(call=>call.action==='work-cancel').length,1);
 assert.deepEqual(f.calls.at(-1),{action:'work-cancel',data});cancel.resolve({});await first;
 assert.equal(f.changed,1);assert.equal(button.disabled,false);assert.equal(f.results.length,0);
});

test('이어서 처리는 정확한 요청을 한 번 보내고 대기 등록 안내와 현재 화면을 유지한다',async t=>{
 const resume=deferred(),data={...request,kind:'speech',run:'전사-실행'};
 let resumed=false;
 const f=fixture(t,action=>{
  if(action==='job-resume')return resume.promise;
  return snapshot({state:resumed?'queued':'paused',result:null,actions:resumed?[{label:'대기 취소',action:'work-cancel',data:{id:'대기-1'}}]:[{label:'이어서 처리',action:'job-resume',data}]});
 });
 f.panel.open(data);await flush();assert.deepEqual(f.calls.map(call=>call.action),['job-detail']);
 f.body.scrollTop=170;const button=f.action('job-resume');button.focus();const waiting=button.onclick();button.onclick();
 assert.equal(button.disabled,true);assert.deepEqual(f.calls.at(-1),{action:'job-resume',data});assert.equal(f.calls.filter(call=>call.action==='job-resume').length,1);
 resumed=true;resume.resolve({queued:{id:'대기-1'},message:'앞 작업 뒤에 이어서 처리하도록 대기열에 등록했습니다.'});await waiting;
 assert.equal(f.byClass('job-detail-feedback').textContent,'앞 작업 뒤에 이어서 처리하도록 대기열에 등록했습니다.');assert.equal(f.byClass('job-detail-feedback').hidden,false);
 assert.equal(f.error.hidden,true);assert.equal(f.byClass('job-detail-state').dataset.state,'queued');assert.equal(f.action('work-cancel').disabled,false);
 assert.equal(f.body.scrollTop,170);assert.equal(f.dialog.open,true);assert.equal(f.panel.key(),jobDetailKey(data));assert.equal(f.results.length,0);assert.equal(f.changed,1);
});

test('이어서 처리 실패는 마지막 상태를 보존하며 재시도 성공 후 오류를 지운다',async t=>{
 let fail=true;const data={...request,kind:'context'},f=fixture(t,action=>{
  if(action==='job-resume'){if(fail)throw Error('저장한 입력 파일을 확인하세요.');return {message:'저장한 설정으로 이어서 처리를 시작했습니다.'};}
  return snapshot({state:'paused',actions:[{label:'이어서 처리',action:'job-resume',data}]});
 });
 f.panel.open(data);await flush();f.body.scrollTop=190;const button=f.action('job-resume');button.focus();await button.onclick();
 assert.equal(f.byClass('job-detail-state').dataset.state,'paused');assert.equal(f.error.textContent,'저장한 입력 파일을 확인하세요.');assert.equal(f.byClass('job-detail-feedback').hidden,true);
 assert.equal(button.disabled,false);assert.equal(f.changed,0);assert.equal(f.results.length,0);
 fail=false;await button.onclick();assert.equal(f.error.hidden,true);assert.equal(f.byClass('job-detail-feedback').textContent,'저장한 설정으로 이어서 처리를 시작했습니다.');
 assert.equal(f.body.scrollTop,190);assert.equal(f.root.activeElement,button);assert.equal(f.dialog.open,true);assert.equal(f.changed,1);
});

test('대기 응답을 전달하는 기존 API 오류도 작업 실패와 구분한다',async t=>{
 const f=fixture(t,action=>{
  if(action==='job-resume'){const error=Error('대기 안내');error.queued=true;throw error;}
  return snapshot({state:'queued',actions:[{label:'이어서 처리',action:'job-resume',data:request}]});
 });
 f.panel.open(request);await flush();await f.action('job-resume').onclick();
 assert.equal(f.error.hidden,true);assert.match(f.byClass('job-detail-feedback').textContent,/대기열에 등록/);assert.equal(f.changed,1);assert.equal(f.results.length,0);
});

test('직접 이어갈 수 없는 중단 작업은 사유를 보이고 재개 가능하거나 완료되면 숨긴다',async t=>{
 let value=snapshot({state:'paused',resume_note:'원음 입력이 변경되었습니다. 전사 설정에서 확인하세요.'});
 const f=fixture(t,()=>value);f.panel.open(request);await flush();const note=f.byClass('job-detail-resume-note');
 assert.equal(note.hidden,false);assert.equal(note.textContent,value.resume_note);assert.equal(f.action('job-resume'),undefined);
 value={...value,actions:[{label:'이어서 처리',action:'job-resume',data:request}]};await f.panel.refresh();assert.equal(note.hidden,true);
 value={...value,state:'complete',actions:[]};await f.panel.refresh();assert.equal(note.hidden,true);
 value={...value,state:'paused',owned:true};await f.panel.refresh();assert.equal(note.hidden,true);
 f.panel.open({...request,run:'실행-b'});assert.equal(note.hidden,true);await flush();assert.equal(f.results.length,0);
});

test('이어서 처리 응답이 늦어도 새로 선택한 상세에는 성공이나 실패를 표시하지 않는다',async t=>{
 const started=deferred(),failed=deferred();let attempt=0;
 const f=fixture(t,(action,data)=>action==='job-resume'?(++attempt===1?started.promise:failed.promise):snapshot({title:data.run,actions:[{label:'이어서 처리',action:'job-resume',data}]}));
 f.panel.open(request);await flush();const a=f.action('job-resume').onclick();
 const next={...request,run:'실행-b'};f.panel.open(next);await flush();started.resolve({queued:{id:'대기-1'},message:'이전 작업 성공'});await a;
 assert.equal(f.byClass('job-detail-feedback').hidden,true);assert.equal(f.byClass('job-detail-title').textContent,'실행-b');assert.equal(f.changed,0);
 const b=f.action('job-resume').onclick();f.panel.open(request);await flush();failed.reject(Error('이전 작업 실패'));await b;
 assert.equal(f.error.hidden,true);assert.equal(f.byClass('job-detail-title').textContent,'실행-a');assert.equal(f.changed,0);assert.equal(f.results.length,0);assert.equal(f.action('job-resume').disabled,false);
});

test('재개 요청 중 패널을 닫아도 취소를 실행하지 않으며 늦은 응답은 무시한다',async t=>{
 const pending=deferred(),f=fixture(t,action=>action==='job-resume'?pending.promise:snapshot({actions:[{label:'이어서 처리',action:'job-resume',data:request}]}));
 f.panel.open(request);await flush();const resume=f.action('job-resume').onclick();f.panel.close();pending.resolve({message:'시작했습니다.'});await resume;
 assert.deepEqual(f.calls.map(call=>call.action),['job-detail','job-resume']);assert.equal(f.dialog.open,false);assert.equal(f.changed,0);assert.equal(f.results.length,0);assert.equal(f.timers.size,0);
});

test('외부 결과는 측정하지 않은 소요 시간을 숨기고 선택한 결과 버전을 전달한다',async t=>{
 const external={root:'/보관함',vod_id:'123',kind:'external',id:'외부-묶음'},result={root:'/보관함',vod_id:'123',step:6,run:'외부-완료본',mode:'clips'};
 const f=fixture(t,()=>snapshot({label:'외부 AI',timing:null,progress:{label:'3 / 4개 결과 수신'},result}));
 f.panel.open(external);await flush();
 const hints=walk(f.body).filter(el=>el.className==='hint');assert.equal(hints[1].hidden,true);assert.equal(hints[1].textContent,'');assert.equal(f.results.length,0);
 await f.action('result').onclick();assert.deepEqual(f.results[0].slice(0,2),[external,result]);
});

test('결과 보기는 선택한 모드와 버전을 전달하고 명시적 클릭 뒤에만 이동한다',async t=>{
 const value=snapshot(),f=fixture(t,()=>value);f.panel.open(request);await flush();assert.equal(f.results.length,0);
 await f.action('result').onclick();assert.equal(f.results.length,1);assert.deepEqual(f.results[0].slice(0,2),[request,value.result]);assert.equal(typeof f.results[0][2],'function');assert.equal(f.dialog.open,false);assert.equal(f.timers.size,0);
});

test('작업 화면 확인도 상세 조회 중에는 이동하지 않고 해당 버튼으로만 이동한다',async t=>{
 const workspace={step:3},f=fixture(t,()=>snapshot({result:null,workspace,records:[]}));f.panel.open(request);await flush();
 assert.equal(f.results.length,0);assert.equal(f.action('result'),undefined);await f.action('workspace').onclick();assert.equal(f.results.length,1);assert.deepEqual(f.results[0].slice(0,2),[request,workspace]);assert.equal(typeof f.results[0][2],'function');
});

test('결과 이동 준비 중 다른 작업을 열면 이전 이동과 새 패널 닫기를 막는다',async t=>{
 const pending=deferred(),validity=[];let navigations=0;
 const f=fixture(t,(_action,data)=>snapshot({title:data.run}),async(_request,_destination,isCurrent)=>{
  validity.push(isCurrent());await pending.promise;validity.push(isCurrent());if(isCurrent())navigations++;
 });
 f.panel.open(request);await flush();const visiting=f.action('result').onclick();
 const next={...request,run:'실행-b'};f.panel.open(next);await flush();pending.resolve();await visiting;
 assert.deepEqual(validity,[true,false]);assert.equal(navigations,0);assert.equal(f.dialog.open,true);assert.equal(f.panel.key(),jobDetailKey(next));
 assert.equal(f.byClass('job-detail-title').textContent,'실행-b');assert.equal(f.timers.size,1);assert.equal(f.action('result').disabled,false);
});

test('다른 대화상자가 열려 있으면 상세 패널을 중첩하지 않는다',async t=>{
 const f=fixture(t,()=>snapshot()),other=f.root.createElement('dialog');other.open=true;f.root.body.append(other);
 f.panel.open(request);await flush();assert.equal(f.calls.length,0);assert.equal(f.dialog.open,false);assert.equal(f.timers.size,0);
});
