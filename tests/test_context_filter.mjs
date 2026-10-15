import assert from 'node:assert/strict';
import {contextReactionRows} from '../web/context-tree.js';

const row=(id,score,start_ms=0)=>({id,start_ms,end_ms:start_ms+1000,...(score===undefined?{}:{reaction_index:score})});
const items=[row('미계산'),row('최저',1,1000),row('중간',5,2000),row('최고',10,3000),{...row('실패'),failed:true},row('범위 초과',11)];
const before=JSON.stringify(items);
assert.equal(contextReactionRows(items).length,6);
assert.deepEqual(contextReactionRows(items,1).map(r=>r.item.id),['최저','중간','최고']);
assert.deepEqual(contextReactionRows(items,5).map(r=>r.item.id),['중간','최고']);
assert.deepEqual(contextReactionRows(items,10).map(r=>r.item.id),['최고']);
assert.equal(contextReactionRows(items,5)[0].index,2); // 필터 전 목록 번호 유지
assert.equal(JSON.stringify(items),before);
assert.deepEqual(contextReactionRows([],10),[]);
assert.deepEqual(contextReactionRows([row('지수 없음')],1),[]);

// 과거 결과: 낮은 지수의 부모가 높은 지수의 하위 반응을 가리지 않는다.
const legacy=[{...row('낮은 부모',1),kind:'story',reactions:[row('하위 반응',9,1500)]},row('나중 문맥',10,3000)];
const legacyBefore=JSON.stringify(legacy);
assert.deepEqual(contextReactionRows(legacy,9).map(r=>r.item.id),['하위 반응','나중 문맥']);
assert.equal(JSON.stringify(legacy),legacyBefore);
console.log('반응지수 하한·경계·미계산·실패·원본 번호·과거 하위 반응·자료 불변 확인 통과');
