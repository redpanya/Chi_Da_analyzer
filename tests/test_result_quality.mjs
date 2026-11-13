import assert from 'node:assert/strict';
import {resultQuality} from '../web/result-quality.js';

const failure={failed:true,error:'추론 프로그램 종료'},held={grounding_state:'review',summary:{context:[]}},gap={gap:true,failed:true,error:'전사 없음'};
assert.equal(resultQuality(failure).kind,'error');
assert.equal(resultQuality(held).kind,'review');assert.equal(resultQuality(held).title,'원문 확인 필요');
assert.equal(resultQuality(gap).kind,'gap');
assert.equal(resultQuality({failed:true}).title,'확인 필요 · 이전 결과');
assert.equal(resultQuality({review_needed:true}).kind,'review');
assert.equal(resultQuality({chat_state:'failed',summary:{context:[{text:'보존한 설명'}]}}).kind,'chat-error');
assert.equal(resultQuality({summary:{title:'완료'}}),null);
assert.deepEqual(failure,{failed:true,error:'추론 프로그램 종료'});assert.equal(held.grounding_state,'review');
console.log('실행 오류·근거 검토·전사 부족·채팅만 실패·원인 미기록 이전 결과 분류 및 원본 보존 통과');
