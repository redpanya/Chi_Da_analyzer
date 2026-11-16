import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
import {collectRanges,totalLength} from '../web/clip-studio-model.js';
import {studioSteps,studioReturnLinks} from '../web/studio-workspace.js';
import {sourcePage} from '../web/studio-source-pages.js';

const source=readFileSync(new URL('../web/clip-studio.js',import.meta.url),'utf8').replace(/^import .*;$/gm,'');
const html=readFileSync(new URL('../web/clip-studio.html',import.meta.url),'utf8');
const tick=()=>new Promise(done=>setImmediate(done));

function enter(mixStep,withRoot=true){
  class Element {
    dataset={};classList={add(){}};value='';children=[];selectedOptions=[{textContent:'원본'}];style={};
    pause(){} setAttribute(){} addEventListener(){}
    replaceChildren(...children){this.children=children;}
    append(...children){this.children.push(...children);}
  }
  const ids=new Map();
  const element=id=>{
    if(!ids.has(id)){
      const node=new Element();node.textContent=html.match(new RegExp('id="'+id+'"[^>]*>([^<]*)'))?.[1]||'';ids.set(id,node);
    }
    return ids.get(id);
  };
  const body=new Element(),location=new URL('http://localhost/'+(mixStep?'mix':'clip')+'-studio.html?vod_id=1'+(withRoot?'&root=test':'')+(mixStep?'&step='+mixStep:''));
  const pending={},requests=[],defaultScene='첫 번째 분석 후보';
  pending.promise=new Promise((resolve,reject)=>Object.assign(pending,{resolve,reject}));
  async function fetch(url){
    requests.push(url);
    let data;
    switch(url){
      case 'api/config':data={root:'test'};break;
      case 'api/state':data={vod_id:'1',root:'test',metadata:{duration:15,title:'방송'},context:{runs:[{id:'run'}]}};break;
      case 'api/context-result':data={complete:true,items:[{title:defaultScene,start_ms:5000,end_ms:8000}]};break;
      case 'api/studio-info':data=await pending.promise;break;
      default:throw Error('예상하지 않은 요청 '+url);
    }
    return {ok:true,json:async()=>data};
  }
  const context=vm.createContext({URL,URLSearchParams,location,fetch,studioSteps,studioReturnLinks,sourcePage,collectRanges,totalLength,
    document:{body,getElementById:element,querySelector:()=>new Element(),querySelectorAll:()=>[],createElement:()=>new Element()},
    window:{addEventListener(){}},sessionStorage:{setItem(){}},Option:class{},ResizeObserver:class{observe(){}},
    timecode:String,commentTimeText:String,bindClipOrder(){},setStudioMenuLinks(){},createEditUndo:()=>({}),
    createStudioInspector:()=>({setTab(){}}),createStudioWorkspace:()=>({setStep:step=>{body.dataset.studioStep=step;}}),
    createWorkQueue:()=>({accept:data=>data}),createMixStudio:()=>({key:'선택',read:()=>pending.promise}),
    createStudioTools:({restore})=>({init(project,data){if(data.draft)restore(data.draft.request.clips);},
      activeChanged(){},beforeSelect(){return true;},profileChecked(){return false;},selectionChanged(){}})
  });
  const initialized=vm.runInContext(source+'\ninitialized;',context);
  return {body,element,pending,initialized,requests,defaultScene};
}

test('저장한 초안이 도착하기 전에는 다른 분석 후보나 빈 담은 목록을 표시하지 않는다',async()=>{
  const saved={id:'저장 구간',title:'실제 첫 구간',start_ms:9000,end_ms:11000};
  for(const [draft,title,count] of [
    [{request:{clips:[saved]}},saved.title,1],[{request:{clips:[]}},'문맥을 선택해 주세요',0],[null,'첫 번째 분석 후보',1]
  ]){
    const app=enter();await tick();
    assert.deepEqual([...app.requests].sort(),['api/context-result','api/state','api/studio-info']);
    assert.match(app.element('active-title').textContent,/불러오는 중/);
    assert.equal(app.element('assembly-count').textContent,'');
    app.pending.resolve({draft});await app.initialized;
    assert.equal(app.element('active-title').textContent,title);
    assert.equal(app.element('assembly-count').textContent,count);
  }
});

test('이전 주소와 초안 읽기 실패에서는 기본 보관함과 분석 구간을 사용할 수 있다',async()=>{
  const app=enter(null,false);await tick();
  assert.ok(app.requests.includes('api/config'));
  app.pending.reject(Error('초안 조회 실패'));await app.initialized;
  assert.equal(app.element('active-title').textContent,app.defaultScene);
  assert.equal(app.element('studio-notice').textContent,'초안 조회 실패');
  assert.equal(app.element('media-empty').hidden,false);
});

test('믹스 자료 응답 전부터 주소가 가리키는 단계를 표시하고 잘못된 단계는 구간으로 연다',async()=>{
  for(const step of [...studioSteps,'잘못된단계']){
    const app=enter(step);
    assert.equal(app.body.dataset.studioStep,studioSteps.includes(step)?step:'range');
    app.pending.reject(Error('믹스 읽기 실패'));await app.initialized;
    assert.equal(app.element('studio-notice').textContent,'믹스 읽기 실패');
  }
});
