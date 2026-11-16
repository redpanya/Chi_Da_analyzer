import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
import {collectRanges,totalLength} from '../web/clip-studio-model.js';
import {studioSteps,studioReturnLinks} from '../web/studio-workspace.js';
import {sourcePage} from '../web/studio-source-pages.js';

const source=readFileSync(new URL('../web/clip-studio.js',import.meta.url),'utf8').replace(/^import .*;$/gm,'');
const mixSource=readFileSync(new URL('../web/mix-studio.js',import.meta.url),'utf8').replace(/^import .*;$/gm,'').replace(/^export /gm,'');
const html=readFileSync(new URL('../web/clip-studio.html',import.meta.url),'utf8');
const tick=()=>new Promise(done=>setImmediate(done));

function enter(mixStep,withRoot=true,mixItems=null,explicitKey=null){
  class Element {
    dataset={};classList=new Set();value='';children=[];selectedOptions=[{textContent:'원본'}];style={};
    pause(){} setAttribute(){} removeAttribute(){} hasAttribute(){return false;} addEventListener(){}
    querySelector(selector){return selector==='a'?this.children.find(child=>child.tag==='a'):new Element();}
    closest(){return this;} get nextElementSibling(){return this;}
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
  const body=new Element(),location=new URL('http://localhost/'+(mixStep?'mix':'clip')+'-studio.html');
  if(!mixStep)location.searchParams.set('vod_id','1');
  if(withRoot)location.searchParams.set('root','test');
  if(mixStep)location.searchParams.set('step',mixStep);
  if(explicitKey)location.searchParams.set('mix',explicitKey);
  const pending={},requests=[],defaultScene='첫 번째 분석 후보',editorRequests=[];
  pending.promise=new Promise((resolve,reject)=>Object.assign(pending,{resolve,reject}));
  async function fetch(url,options){
    requests.push(url);
    let data;
    switch(url){
      case 'api/config':data={root:'test'};break;
      case 'api/state':data={vod_id:'1',root:'test',metadata:{duration:15,title:'방송'},context:{runs:[{id:'run'}]}};break;
      case 'api/context-result':data={complete:true,items:[{title:defaultScene,start_ms:5000,end_ms:8000}]};break;
      case 'api/studio-info':data=await pending.promise;break;
      case 'api/mix-info':
        assert.equal(JSON.parse(options.body).library_root,'test');
        data=mixItems?{items:mixItems}:await pending.promise;
        break;
      case 'api/mix-editor':{
        const {library_root,key}=JSON.parse(options.body);
        assert.equal(library_root,'test');editorRequests.push(key);
        const item=mixItems.find(row=>row.key===key);
        const clip={...item,id:key,start_ms:1000,end_ms:3000};
        data={items:mixItems,editor_page:'mix-studio.html',project:{root:'test',vod_id:'1',input:{start_vod_ms:0},duration_ms:8000,metadata:{title:'방송'}},
          original:clip,draft:{request:{clips:[clip]}}};break;
      }
      default:throw Error('예상하지 않은 요청 '+url);
    }
    return {ok:true,json:async()=>data};
  }
  const context=vm.createContext({URL,URLSearchParams,location,fetch,studioSteps,studioReturnLinks,sourcePage,collectRanges,totalLength,
    document:{body,getElementById:element,querySelector:()=>new Element(),querySelectorAll:()=>[],addEventListener(){},createElement:tag=>Object.assign(new Element(),{tag})},
    window:{addEventListener(){}},history:{replaceState(state,title,url){location.href=url;}},sessionStorage:{setItem(){}},Option:class{},ResizeObserver:class{observe(){}},
    timecode:String,commentTimeText:String,bindClipOrder(){},setStudioMenuLinks(){},createEditUndo:()=>({clear(){}}),
    createStudioInspector:()=>({setTab(){}}),createStudioWorkspace:()=>({setStep:step=>{body.dataset.studioStep=step;}}),
    createWorkQueue:()=>({accept:data=>data}),
    createStudioTools:({restore,mix})=>{
      mix?.bind({}, {checked:()=>false});
      return {init(project,data){if(data.draft)restore(data.draft.request.clips);},preparePresets(){},
        activeChanged(){},beforeSelect(){return true;},profileChecked(){return false;},selectionChanged(){}};
    }
  });
  context.createMixStudio=vm.runInContext('(()=>{'+mixSource+';return createMixStudio;})()',context);
  const initialized=vm.runInContext(source+'\ninitialized;',context);
  return {body,element,pending,initialized,requests,defaultScene,editorRequests,location};
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

test('믹스 메뉴는 첫 편집 가능 구간을 열고 구간 링크는 지정한 구간을 연다',async()=>{
  const items=[{key:'missing',title:'원본 없음',problem:'영상을 찾을 수 없습니다.'},
    {key:'first',title:'첫 장면'},{key:'next',title:'다음 장면'}];
  for(const [key,selected] of [[null,items[1]],['next',items[2]]]){
    const app=enter('range',!!key,items,key);
    await app.initialized;
    assert.deepEqual(app.editorRequests,[selected.key]);
    assert.equal(app.requests.includes('api/mix-info'),!key);
    assert.equal(app.element('active-title').textContent,selected.title);
    assert.equal(app.element('mix-assembly').children.length,3);
    assert.equal(app.body.classList.has('mix-unavailable'),false);
    assert.equal(app.location.searchParams.get('mix'),selected.key);
    assert.equal(app.location.searchParams.get('root'),'test');
  }
});

test('빈 믹스와 모든 원본이 누락된 믹스는 원본 편집 요청 없이 안내를 표시한다',async()=>{
  const notices=[];
  for(const items of [[],[{key:'gone',title:'원본 없음',problem:'영상을 찾을 수 없습니다.'}]]){
    const app=enter('range',true,items);await app.initialized;
    assert.deepEqual(app.requests,['api/mix-info']);
    assert.ok(app.body.classList.has('mix-unavailable'));
    const back=new URL(app.element('studio-return').href,app.location);
    assert.equal(back.searchParams.get('library_root'),'test');
    assert.equal(back.hash,'#mix');
    assert.equal(app.element('mix-order-play').disabled,true);
    const notice=app.element('mix-order-notice').textContent;
    assert.ok(notice);notices.push(notice);
  }
  assert.notEqual(notices[0],notices[1]);
});
