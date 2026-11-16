import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {groupedJobs} from '../web/product-workspace.js';

const project={root:'/fixture',vod_id:'3',metadata:{title:'<img src=x onerror=bad> 방송'},tasks:{video:{state:'complete'},chat:{state:'running',message:'채팅 정리 중'}},summaries:{speech:{state:'complete'},context:{state:'error',message:'모델 준비 필요'}}};
const library={projects:[project]},heavy={items:[{id:'heavy-1',root:'/fixture',vod_id:'3',label:'클립 영상 저장',title:project.metadata.title,state:'queued',message:'앞 작업 대기'}]},queue={root:'/fixture',items:[{id:'automation-1',vod:'3',title:project.metadata.title,state:'paused',stage:'download',message:'일시정지'}]};

test('진행 중인 단계와 취소 가능한 대기만 먼저 보여준다',()=>{
 const before=JSON.stringify([library,heavy,queue]),rows=groupedJobs(library,heavy,queue);
 assert.equal(rows.length,1);assert.equal(rows[0].project,project);
 assert.deepEqual(rows[0].items.map(i=>i.label),['채팅','클립 영상 저장']);
 assert.equal(rows[0].items[1].cancelId,'heavy-1');
 assert.equal(JSON.stringify([library,heavy,queue]),before);
 assert.deepEqual(groupedJobs(library,heavy,queue,'review')[0].items.map(i=>i.detail.kind),['context','queue']);
 assert.equal(groupedJobs(library,heavy,queue,'complete').length,0);
});

test('같은 실행을 등록 목록과 대기열에서 함께 보고해도 실제 진행 단계만 남긴다',()=>{
 const p={...project,tasks:{},summaries:{speech:{action:'transcribe',state:'running'}}};
 const wrapper={...heavy.items[0],action:'speech-start',stage:'transcribe',state:'running'};
 const running={...queue.items[0],stage:'transcribe',state:'running'};
 assert.deepEqual(groupedJobs({projects:[p]},{items:[wrapper]},{...queue,items:[running]})[0].items.map(i=>i.id),['speech']);
});

test('완료 자료는 한 줄로 모으고 가장 최근 결과의 상세를 연결한다',()=>{
 const p={...project,tasks:{video:{state:'complete'}},summaries:{speech:{action:'transcribe',state:'complete'}}};
 const result={...queue.items[0],state:'complete',stage:'transcribe',finished_at:'2026-11-16T09:00:00Z'};
 const rows=groupedJobs({projects:[p]}, {}, {...queue,items:[],results:[result]},'complete');
 assert.equal(rows[0].items.length,1);
 assert.equal(rows[0].items[0].summary,'영상, 음성 전사');
 assert.deepEqual(rows[0].items[0].detail,{kind:'queue',root:'/fixture',id:'automation-1'});
 assert.equal(groupedJobs({projects:[{...p,tasks:{},summaries:{}}]}).length,0);
 const noChat={...p,tasks:{video:{state:'complete'},chat:{state:'unavailable',updated_at:'2026-11-16T09:15:00Z'}},summaries:{}};
 assert.equal(groupedJobs({projects:[noChat]})[0].items[0].detail.kind,'video');
});

test('삭제한 원본과 다른 보관함의 기록을 제외하고 같은 번호의 지정 구간을 유지한다',()=>{
 const range='/fixture/.download-ranges/abc',row={...project,root:range,tasks:{},summaries:{}};
 const scoped={...queue.items[0],id:'range',project_root:range,state:'queued'};
 const rows=groupedJobs({projects:[row]},heavy,{...queue,items:[...queue.items,scoped],results:[{...queue.items[0],state:'complete'}]});
 assert.equal(rows.length,1);assert.equal(rows[0].items.length,1);
 assert.deepEqual(rows[0].items[0].detail,{kind:'queue',root:'/fixture',id:'range'});
});

test('윈도우 경로의 대소문자 차이는 같은 자료이며 독립적인 영상 나누기 대기는 유지한다',()=>{
 const rows=groupedJobs({projects:[{...project,root:'C:\\다시보기'}]},{items:[{...heavy.items[0],root:'c:/다시보기/'},{id:'split-a',label:'영상 나누기',state:'queued'}]});
 assert.equal(rows.length,2);assert.equal(rows[0].items.length,2);
 assert.equal(rows[1].project,null);assert.equal(rows[1].items[0].cancelId,'split-a');
});

test('진행 상태 진입은 메인 페이지이며 다른 자료 조회 오류에도 대기 상태 조회를 유지한다',()=>{
 const source=readFileSync(new URL('../web/product-workspace.js',import.meta.url),'utf8');
 assert.match(source,/jobButton\.onclick=\(\)=>navigate\(10\)/);assert.doesNotMatch(source,/createJobsPreview|jobs-preview|jobs-heavy|jobs-automation|jobs-errors/);assert.match(source,/Promise\.allSettled/);
 assert.match(source,/if\(page!==10\|\|requested!==getRoot\(\)\)return/);
 assert.match(source,/card\.append\(open,remove\)/);assert.doesNotMatch(source,/libraryThumbnail|library-thumbnail|node\('img'/);
});

test('외부 AI 완료 결과와 재개 가능한 부분 결과의 상세를 구분한다',()=>{
 const p={...project,tasks:{},summaries:{},external_results:[{export_id:'external-a',mode:'clips',state:'complete'}]};
 const done=groupedJobs({projects:[p]})[0].items[0];
 assert.equal(done.summary,'외부 AI 클립 후보');
 assert.deepEqual(done.detail,{root:p.root,vod_id:p.vod_id,kind:'external',id:'external-a'});
 p.external_results.push({export_id:'external-b',mode:'timestamps',state:'partial'});
 assert.equal(groupedJobs({projects:[p]}, {}, {}, 'review')[0].items[0].detail.id,'external-b');
});
