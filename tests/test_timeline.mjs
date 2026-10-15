import assert from 'node:assert/strict';
import {selectedRange, speakerColor} from '../web/timeline.js';
assert.deepEqual(selectedRange(1234, 3500, 5000), {start_ms:1234, end_ms:3500});
for (const [a,b,d] of [[-1,1,10],[2,2,10],[3,1,10],[0,11,10],[NaN,1,10],[0,1,Infinity]]) assert.throws(()=>selectedRange(a,b,d));
assert.equal(speakerColor('A'), speakerColor('A'));
assert.notEqual(speakerColor('A'), speakerColor('B'));
console.log('구간 경계·고정 화자 색 검사 9개 통과');
