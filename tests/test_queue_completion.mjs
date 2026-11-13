import assert from 'node:assert/strict';
import {registrationItems,registrationSummary} from '../web/queue.js';

const items=['complete','partial','error','paused','queued','running'].map((state,index)=>({id:String(index),state,report:'report-'+index}));
const data={items,state:'running',message:'순차 작업 진행 중'};
const before=JSON.stringify(data);
assert.deepEqual(registrationItems(data).map(item=>item.state),['partial','error','paused','queued','running']);
assert.equal(registrationSummary(data),'전체 5개 / 5번째 처리 중 / 순차 작업 진행 중');
assert.equal(JSON.stringify(data),before,'진행 상태와 리포트에 사용하는 원본 목록은 보존');

const loaded=JSON.parse(before);
assert.deepEqual(registrationItems(loaded).map(item=>item.id),['1','2','3','4','5'],'다시 불러와도 완료 항목은 등록 목록에서 제외');
loaded.items[5].state='complete';
assert.deepEqual(registrationItems(loaded).map(item=>item.id),['1','2','3','4'],'실행 완료 후 다음 새로고침에서 자동 제외');
assert.equal(registrationSummary({...loaded,state:'complete',message:'목록 처리 종료 완료 2개'}),'전체 4개 / 목록 처리 종료');

const finished={state:'complete',items:[items[0]],message:'목록 처리 종료 완료 1개'};
assert.deepEqual(registrationItems(finished),[]);
assert.match(registrationSummary(finished),/등록된 VOD가 없습니다/);
assert.match(registrationSummary(finished),/완료 자료는 보관함에 유지/);
assert.match(registrationSummary({items:[],state:'idle'}),/자료를 등록/);
console.log('완료 자동 제외, 미완료 보존, 표시 순서, 새로고침과 기록 보존 검사 통과');
