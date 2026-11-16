import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';

const source=readFileSync(new URL('../web/video-split-page.js',import.meta.url),'utf8').replace(/^import .*;\r?\n/gm,'').replace('export function','function');
function fixture(fetch,embedded=false){
 const input={value:'00:10:00'},video={paused:false};
 const root={hidden:true,childNodes:embedded?[input,video]:[],replaceChildren(...nodes){this.childNodes=nodes;},
  querySelector(selector){return selector==='#split-video'&&this.childNodes.includes(video)?video:null;}};
 let mounts=0,pauses=0,animations=0;
 const context=vm.createContext({fetch,DOMParser:class{parseFromString(){return {querySelector(selector){assert.equal(selector,'#video-split-page');return {querySelector:()=>video,childNodes:[input,video]};}};}},
  document:{createElement:tag=>({tag,setAttribute(){}})},enterView(){animations++;},
  createVideoSplit(){mounts++;return {pause(){pauses++;video.paused=true;}};}});
 vm.runInContext(source+'\nglobalThis.create=createVideoSplitPage;',context);
 return {root,input,video,view:context.create({root,workQueue:{}}),counts:()=>({mounts,pauses,animations})};
}
const ok=()=>Promise.resolve({ok:true,text:async()=>'<section id="video-split-page"></section>'});

test('첫 응답의 분할 화면을 즉시 연결하고 메뉴 왕복 시 입력과 DOM을 보존하며 재생을 중지한다',async()=>{
 let requests=0;const f=fixture(()=>{requests++;return ok();},true);
 const first=f.view.show(true);assert.equal(f.counts().mounts,1);await first;f.input.value='00:20:00';
 f.view.show(false);assert.equal(f.root.hidden,true);assert.equal(f.video.paused,true);
 await f.view.show(true);
 assert.equal(requests,0);assert.equal(f.counts().animations,0);assert.equal(f.root.childNodes[0],f.input);assert.equal(f.input.value,'00:20:00');
 assert.equal(f.root.hidden,false);assert.equal(f.counts().mounts,1);
 f.view.pause();assert.equal(f.counts().pauses,2);
});
test('옛 문서가 분할 화면을 복구하는 동안 메뉴가 바뀌어도 응답이 화면을 열거나 중복 애니메이션을 시작하지 않는다',async()=>{
 let resolve;const f=fixture(path=>{assert.equal(path,'./');return new Promise(done=>{resolve=done;});});
 const pending=f.view.show(true);assert.equal(f.view.show(true),pending);
 assert.equal(f.counts().animations,0);
 f.view.show(false);resolve(await ok());await pending;
 assert.equal(f.root.hidden,true);assert.equal(f.counts().animations,0);
 await f.view.show(true);assert.equal(f.root.hidden,false);assert.equal(f.counts().mounts,1);assert.equal(f.counts().animations,0);
});
test('로딩 오류 후 화면 안에서 재시도할 수 있다',async()=>{
 let requests=0;const f=fixture(()=>++requests===1?Promise.resolve({ok:false}):ok());
 await f.view.show(true);assert.equal(f.counts().mounts,0);
 const retry=f.root.childNodes[1];assert.equal(retry.textContent,'다시 불러오기');
 await retry.onclick();assert.equal(f.counts().mounts,1);assert.equal(requests,2);
});
test('기존 별도 페이지 주소는 검색 조건을 보존하고 공통 화면 주소로 연결한다',()=>{
 const oldPage=readFileSync(new URL('../web/video-split.html',import.meta.url),'utf8');
 const index=readFileSync(new URL('../web/index.html',import.meta.url),'utf8');
 assert.match(index,/id="video-split-page"[^>]* hidden>[\s\S]*id="split-source-form"[\s\S]*id="split-video"/);
 assert.equal(index.match(/id="split-video"/g).length,1);
 assert.doesNotMatch(oldPage,/id="split-video"/);
 assert.match(oldPage,/<script src="video-split-entry.js"><\/script>/);
 let target;const location={href:'http://127.0.0.1:1234/session/video-split.html?root=test#old-run',search:'?root=test',replace:value=>{target=value;}};
 vm.runInNewContext(readFileSync(new URL('../web/video-split-entry.js',import.meta.url),'utf8'),{URL,location});
 assert.equal(target,'http://127.0.0.1:1234/session/?root=test#split');
});
