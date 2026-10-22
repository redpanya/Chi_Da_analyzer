import assert from 'node:assert/strict';
import {vodLabel} from '../web/vod-label.js';
const project={metadata:{title:'제목 <원문>',duration:49939},tasks:{video:{}}};
assert.equal(vodLabel(project),'제목 <원문> (13:52:19)');
assert.equal(vodLabel({...project,tasks:{video:{verification:{duration:72000}}}}),'제목 <원문> (20:00:00)');
assert.equal(vodLabel({metadata:{title:'무음',duration:0}}),'무음 (00:00:00)');
assert.equal(vodLabel({metadata:{title:'미확인'}}),'미확인 (길이 미확인)');
assert.equal(vodLabel({metadata:{duration:NaN}}),'제목 없음 (길이 미확인)');
console.log('VOD 전체 길이: 13시간·20시간·0초·미확인 표시 통과');
