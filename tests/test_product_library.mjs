import test from 'node:test';
import assert from 'node:assert/strict';
import {libraryStatus,projectPageKey,createProjectPageMemory,broadcastTime,sortLibraryProjects} from '../web/product-workspace.js';
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
