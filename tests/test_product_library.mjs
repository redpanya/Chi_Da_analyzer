import test from 'node:test';
import assert from 'node:assert/strict';
import {libraryStatus,projectStatus,projectPageKey,createProjectPageMemory,broadcastTime,sortLibraryProjects} from '../web/product-workspace.js';
const project={root:'/library',vod_id:'1',metadata:{title:'방송'},tasks:{video:{state:'complete'}},speech:{run:'speech'},context:{runs:[{id:'context'}]}};

test('최근 작업·방송일 정렬은 미확인 날짜를 뒤에 두고 원본을 유지',()=>{
 const rows=[{vod_id:'1',updated_at:'2026-11-11',metadata:{}},{vod_id:'2',updated_at:'2026-11-09',metadata:{broadcast_date:'20261101'}},{vod_id:'3',updated_at:'2026-11-10',metadata:{broadcast_at:'2026-11-02T12:00:00Z'}}],before=JSON.stringify(rows);
 assert.deepEqual(sortLibraryProjects(rows).map(r=>r.vod_id),['1','3','2']);
 assert.deepEqual(sortLibraryProjects(rows,'broadcast').map(r=>r.vod_id),['3','2','1']);
 assert.equal(broadcastTime({metadata:{broadcast_date:'잘못된 날짜',upload_date:'20261103'}}),null);
 assert.equal(JSON.stringify(rows),before);
});

test('최근 작업 화면은 보관함·VOD·다운로드 구간을 구분하고 사라진 결과를 복원하지 않음',()=>{
 let saved=[];const preferences={read:()=>saved,write:rows=>{saved=structuredClone(rows);}},memory=createProjectPageMemory(preferences),before=JSON.stringify(project);
 memory.remember(project,3);assert.equal(memory.page(project),3);
 const other={...project,root:'/other'},range={...project,download_range:{start_ms:0,end_ms:60000}};
 assert.notEqual(projectPageKey(project),projectPageKey(other));assert.notEqual(projectPageKey(project),projectPageKey(range));
 assert.equal(memory.page(other),6);memory.remember(range,5);assert.equal(memory.page(project),3);assert.equal(memory.page(range),5);
 memory.remember(project,9);assert.equal(memory.page(project),3);
 assert.equal(createProjectPageMemory(preferences).page(project),3);
 assert.equal(memory.page({...project,speech:{},context:{runs:[]}}),5);
 memory.remember(project,6);assert.equal(memory.page({...project,context:{runs:[]}}),3);
 assert.equal(JSON.stringify(project),before);assert.ok(!JSON.stringify(saved).includes('/library'));
 for(let i=0;i<40;i++)memory.remember({...project,vod_id:String(i)},2);
 assert.equal(saved.length,32);
});

test('브라우저 설정은 포트와 무관한 쿠키로 복원하고 손상 값은 안전하게 무시',()=>{
 const oldDocument=globalThis.document,oldStorage=globalThis.localStorage;
 globalThis.document={cookie:''};globalThis.localStorage={getItem:()=>null,setItem(){}};
 try{const memory=createProjectPageMemory();memory.remember(project,3);assert.match(document.cookie,/SameSite=Strict/);assert.equal(createProjectPageMemory().page(project),3);
 document.cookie='chida_project_pages=%7Bbad';assert.equal(createProjectPageMemory().page(project),6);
 }finally{globalThis.document=oldDocument;globalThis.localStorage=oldStorage;}
});

test('보관함 대표 상태는 실행·문제·완료 순이며 상세 상태를 버리지 않음',()=>{
 const p={tasks:{video:{state:'complete'},chat:{state:'complete'}},summaries:{speech:{state:'complete'},context:{state:'paused'}}};
 const before=JSON.stringify(p);assert.equal(libraryStatus(p).label,'문맥 중단됨');assert.equal(libraryStatus(p).group,'review');assert.match(libraryStatus(p).detail,/채팅 완료/);
 assert.equal(libraryStatus({...p,video_replacement:{task:{state:'downloading'}}}).label,'영상 다운로드 중');
 assert.equal(libraryStatus({...p,summaries:{speech:{state:'complete'}}}).label,'전사 완료');
 assert.equal(libraryStatus({}).label,'영상 준비 전');assert.equal(JSON.stringify(p),before);
});

test('일부 요약과 이전 외부 결과는 사용 가능한 자료로 분류하되 실패 상태를 숨기지 않음',()=>{
 const p={tasks:{video:{state:'complete'},chat:{state:'complete'}},summaries:{context:{state:'review',results:{usable:true,complete:true,issues:true}}}};
 const before=JSON.stringify(p);
 assert.equal(libraryStatus(p).label,'문맥 사용 가능 (일부 확인)');
 assert.equal(projectStatus(p),'ready');
 for(const [state,label] of [['paused','일부 완료 (중단)'],['error','일부 완료 (작업 실패)'],['running','진행 중']]){
  const row={...p,summaries:{context:{...p.summaries.context,state}}};
  assert.equal(libraryStatus(row).label,'문맥 '+label);
  assert.equal(projectStatus(row),state==='running'?'working':'ready');
 }
 const previous={...p,summaries:{context:{state:'error',results:{usable:true,previous:true,origin:'external'}}}};
 assert.equal(libraryStatus(previous).label,'문맥 이전 결과 사용 가능');
 assert.match(libraryStatus(previous).detail,/최근 작업 확인 필요/);
 assert.match(libraryStatus(previous).detail,/외부 AI 결과/);
 const empty={...p,summaries:{context:{state:'error',results:{usable:false}}}};
 assert.equal(libraryStatus(empty).label,'문맥 실패 (결과 없음)');assert.equal(projectStatus(empty),'review');
 assert.equal(projectStatus({...p,tasks:{video:{state:'error'}}}),'review');
 assert.equal(libraryStatus({...p,summaries:{context:{state:'complete',results:{usable:true,complete:true}}}}).label,'문맥 완료');
 assert.equal(JSON.stringify(p),before);
});

test('원음 추출과 모델 준비 완료를 전사 완료로 표시하지 않음',()=>{
 const speech={state:'complete',action:'audio',audio_ready:true,transcript_state:'idle'};
 const row=s=>({tasks:{video:{state:'complete'}},summaries:{speech:s}});
 assert.equal(libraryStatus(row(speech)).label,'원음 추출 완료');
 assert.doesNotMatch(libraryStatus(row(speech)).detail,/전사 완료/);
 assert.equal(libraryStatus(row({...speech,action:'model',audio_ready:false})).label,'영상 완료');
 assert.equal(libraryStatus(row({...speech,action:'model',state:'running'})).label,'전사 모델 진행 중');
 const saved=libraryStatus(row({...speech,transcript_state:'complete'}));
 assert.equal(saved.label,'전사 완료');assert.match(saved.detail,/원음 추출 완료/);
 assert.equal(libraryStatus(row({...speech,state:'error'})).label,'원음 추출 확인 필요');
});
