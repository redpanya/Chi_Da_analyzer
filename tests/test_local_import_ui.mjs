import assert from 'node:assert/strict';
import {readFileSync,existsSync} from 'node:fs';
const html=readFileSync(new URL('../web/index.html',import.meta.url),'utf8');
assert.doesNotMatch(html,/id="(?:local-import-start|local-file-fields|local-file|local-url)"/);
assert.match(html,/id="queue-saved-dialog"/);
assert(!existsSync(new URL('../web/local-import.js',import.meta.url)));
console.log('새 로컬 첨부 입력 제거 · 기존 VOD 선택 경로 유지 통과');
