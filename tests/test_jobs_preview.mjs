import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {groupedJobs} from '../web/product-workspace.js';

const project={root:'/fixture',vod_id:'3',metadata:{title:'<img src=x onerror=bad> 방송'},tasks:{video:{state:'complete'},chat:{state:'running',message:'채팅 정리 중'}},summaries:{speech:{state:'complete'},context:{state:'error',message:'모델 준비 필요'}}};
const library={projects:[project]},heavy={items:[{id:'heavy-1',root:'/fixture',vod_id:'3',label:'클립 영상 저장',title:project.metadata.title,state:'queued',message:'앞 작업 대기'}]},queue={root:'/fixture',items:[{id:'automation-1',vod:'3',title:project.metadata.title,state:'paused',stage:'download',message:'일시정지'}]};

test('한 VOD의 영상·채팅·전사·AI·무거운 작업·순차 목록을 한 행으로 모은다',()=>{
 const before=JSON.stringify([library,heavy,queue]),rows=groupedJobs(library,heavy,queue);
 assert.equal(rows.length,1);assert.equal(rows[0].project,project);assert.equal(rows[0].title,project.metadata.title);
 assert.deepEqual(rows[0].items.map(item=>item.label),['영상','채팅','전사','AI 문맥','클립 영상 저장','순차 작업']);
 assert.equal(rows[0].items.find(item=>item.label==='AI 문맥').message,'모델 준비 필요');
 assert.equal(rows[0].items.at(-1).stage,'영상·채팅');assert.equal(rows[0].items.at(-2).cancelId,'heavy-1');
 assert.equal(JSON.stringify([library,heavy,queue]),before);
});

test('상태 필터는 VOD를 고르며 해당 VOD의 완료 단계도 함께 남긴다',()=>{
 for(const filter of ['active','review','complete']){const rows=groupedJobs(library,heavy,queue,filter);assert.equal(rows.length,1);assert.equal(rows[0].items.length,6);}
 assert.equal(groupedJobs({projects:[{...project,tasks:{video:{state:'complete'}},summaries:{}}]}, {}, {}, 'review').length,0);
 assert.equal(groupedJobs({projects:[{...project,tasks:{video:{state:'idle'}},summaries:{}}]}).length,0);
});

test('같은 VOD 번호라도 다른 보관함·다운로드 구간의 루트는 별개다',()=>{
 const projects=[project,{...project,root:'/other'},{...project,root:'/fixture/.download-ranges/abc'}];
 const result=groupedJobs({projects},heavy,{root:'/fixture',items:[{id:'r',vod:'3',project_root:'/fixture/.download-ranges/abc',state:'queued'}]});
 assert.equal(result.length,3);assert.equal(result[0].items.length,5);assert.equal(result[2].items.length,5);
 assert.notEqual(result[0].key,result[2].key);
});

test('Windows 경로 표기 차이만 있는 작업을 같은 VOD로 묶는다',()=>{
 const rows=groupedJobs({projects:[{...project,root:'C:\\다시보기'}]},{items:[{id:'w',root:'c:/다시보기/',vod_id:3,state:'queued'}]});
 assert.equal(rows.length,1);assert.equal(rows[0].items.length,5);
});

test('VOD와 무관한 영상 나누기 대기는 독립 행에 두고 취소를 유지한다',()=>{
 const rows=groupedJobs({}, {items:[{id:'split-a',label:'영상 나누기',state:'queued'},{id:'split-b',label:'분할 경계 검사',state:'running'}]});
 assert.equal(rows.length,2);assert.equal(rows[0].project,null);assert.equal(rows[0].items[0].cancelId,'split-a');assert.equal(rows[1].items[0].cancelId,null);
});

test('영상 교체 상태와 부분 처리·취소·확인 필요 상태를 잃지 않는다',()=>{
 const rows=groupedJobs({projects:[{...project,video_replacement:{task:{state:'error',message:'기존 영상 보존'}},summaries:{speech:{state:'partial'}}}]}, {items:[{id:'cancelled',root:'/fixture',vod_id:'3',state:'cancelled'}]});
 assert.equal(rows[0].items[0].message,'기존 영상 보존');assert.equal(rows[0].items[0].group,'review');assert.equal(rows[0].items.find(item=>item.label==='전사').group,'review');assert.equal(rows[0].items.at(-1).group,'review');
});

test('상세는 작업 종류와 순차 목록의 상위 루트를 구분한다',()=>{
 const rows=groupedJobs({projects:[{...project,summaries:{speech:{state:'complete',run:'speech-run'}}}]},heavy,{root:'/fixture',items:[{id:'range-item',vod:'3',project_root:'/fixture/.download-ranges/abc',state:'queued'}]});
 assert.deepEqual(rows[0].items.find(item=>item.id==='speech').detail,{root:'/fixture',vod_id:'3',kind:'speech'});
 assert.deepEqual(rows[0].items.at(-1).detail,{kind:'heavy',id:'heavy-1'});
 assert.deepEqual(rows[1].items[0].detail,{kind:'queue',root:'/fixture',id:'range-item'});
});

test('진행 상태 진입은 메인 페이지이며 다른 자료 조회 오류에도 대기 상태 조회를 유지한다',()=>{
 const source=readFileSync(new URL('../web/product-workspace.js',import.meta.url),'utf8');
 assert.match(source,/jobButton\.onclick=\(\)=>navigate\(10\)/);assert.doesNotMatch(source,/createJobsPreview|jobs-preview|jobs-heavy|jobs-automation|jobs-errors/);assert.match(source,/Promise\.allSettled/);
 assert.match(source,/if\(page!==10\|\|requested!==getRoot\(\)\)return/);
 assert.match(source,/card\.append\(open,remove\)/);assert.doesNotMatch(source,/libraryThumbnail|library-thumbnail|node\('img'/);
});

test('외부 AI 완료와 부분 결과를 이전 Gemma 작업과 분리해 같은 VOD에 표시한다',()=>{
 const p={...project,external_results:[{export_id:'external-a',mode:'clips',state:'complete'},{export_id:'external-b',mode:'timestamps',state:'partial'}]};
 const before=JSON.stringify(p),rows=groupedJobs({projects:[p]});
 assert.equal(rows.length,1);
 const external=rows[0].items.filter(item=>item.detail.kind==='external');
 assert.deepEqual(external.map(item=>[item.label,item.group]),[['외부 AI 클립 후보','complete'],['외부 AI 타임스탬프','review']]);
 assert.deepEqual(external[0].detail,{root:p.root,vod_id:p.vod_id,kind:'external',id:'external-a'});
 assert.equal(rows[0].items.find(item=>item.id==='context').state,'error');
 assert.equal(JSON.stringify(p),before);
});
