import assert from 'node:assert/strict';
import {voiceModelHelp} from '../web/voice-model-help.js';
import {getHelpContent} from '../web/help-content.js';

const ready={ready:true,engine:true,supported:true};
for(const backend of ['sherpa','pyannote','fluid']) {
  const guide=voiceModelHelp(backend,ready);
  assert.match(guide.status,/바로 사용 가능/);
  assert.equal(guide.links.length,0);
  for(const model of [{...ready,engine:false},{...ready,supported:false}]) {
    assert.doesNotMatch(voiceModelHelp(backend,model).status,/바로 사용 가능/);
  }
}
const first=voiceModelHelp('pyannote',{...ready,ready:false});
assert.match(first.status,/최초 다운로드 시 HF 로그인/);
assert.ok(first.paragraphs.some(p=>p.includes('사이트 로그인만으로')));
assert.ok(first.paragraphs.some(p=>p.includes('hf auth login')));
assert.equal(first.links.length,2);
assert.ok(first.links.every(link=>new URL(link.url).hostname==='huggingface.co'));
assert.equal(voiceModelHelp('fluid',{...ready,ready:false}).links.length,0);
// 모델 준비 직후 같은 도움말을 다시 열면 최초 인증 안내를 반복하지 않는다.
let data={ready:'false',engine:'true',supported:'true'};
const read=(id,kind)=>kind==='dataset'?data:kind==='value'?'pyannote':'pyannote.audio + Community-1';
assert.equal(getHelpContent('voice-model',read).links.length,2);
data={...data,ready:'true'};
const prepared=getHelpContent('voice-model',read);
assert.equal(prepared.links.length,0);
assert.match(prepared.current,/바로 사용 가능/);
assert.equal(getHelpContent('speech-model',read).title,'전사 모델·언어');
console.log('화자 모델 도움말: 최초 준비·완료·실행 도구 없음·미지원·현재 상태 연결 통과');
