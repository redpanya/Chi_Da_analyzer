import assert from 'node:assert/strict';
import {voiceToolStatus} from '../web/voice-tool-status.js';

const missing={id:'pyannote',engine:false,ready:true,supported:true,tool:{source:'missing',install_path:'/모델/speaker-tools'}};
let view=voiceToolStatus(missing);
assert.match(view.status,/첫 사용 시 자동 설치/);assert.match(view.install,/다운로드/);
assert.equal(view.canInstall,true);assert.equal(view.canCheck,false);
view=voiceToolStatus({...missing,engine:true,tool:{managed:true}});
assert.equal(view.canCheck,true);assert.match(view.install,/다시 설치/);
assert.equal(view.hint,''); // 별도의 앱 지원 폴더를 표시하지 않는다.
view=voiceToolStatus({...missing,supported:false});assert.equal(view.canInstall,false);assert.match(view.status,/미지원/);
view=voiceToolStatus(missing,{backend:'pyannote',action:'install-engine',state:'running',message:'다운로드 중'});
assert.match(view.install,/설치 중/);assert.equal(view.status,'다운로드 중');
view=voiceToolStatus(missing,{backend:'sherpa',action:'install-engine',state:'running'});
assert.match(view.status,/첫 사용 시 자동 설치/);
console.log('실행 도구 UI: 미설치·별도 설치·포함 도구·미지원·진행 상태 구분 통과');
