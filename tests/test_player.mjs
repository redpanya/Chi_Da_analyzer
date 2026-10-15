import assert from 'node:assert/strict';
import {parseTime, clampTime, timecode} from '../web/player.js';

assert.equal(parseTime('01:02:03'), 3723000);
assert.equal(parseTime('35:52'), 2152000);
assert.throws(() => parseTime('10:60'));
assert.throws(() => parseTime('1.5'));
assert.equal(clampTime(-1000, 20), 0);
assert.equal(clampTime(2152487, 2150.741), 2150.741);
assert.equal(clampTime(11682, 2152.751666), 11.682);
assert.equal(clampTime(1000, NaN), null);
assert.equal(timecode(3600000), '01:00:00');
console.log('시각 해석·범위 제한 검사 9개 통과');
