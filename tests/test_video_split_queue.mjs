import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import test from 'node:test';

const source=fs.readFileSync(new URL('../web/video-split.js',import.meta.url),'utf8');
const refreshSource=source.slice(source.indexOf('async function refresh(){'),source.indexOf('// 같은 탭에서 이동'));

function setup(initial={}){
  const listeners={},nodes={'split-error':{hidden:false}},calls=[],restored=[];
  const state={requesting:false,refreshing:false,job:null,queuedTask:null,sourceId:null,...initial};
  const context=vm.createContext({...state,document:{addEventListener:(name,fn)=>listeners[name]=fn},
    $:id=>nodes[id],controls(){},error:e=>calls.push(['error',e]),
    active:()=>false,stateView(){},planView(){},edits:{accept(){}},
    async api(action,data){calls.push([action,data]);return {id:data.id,state:'planning'};},
    restoreCurrent:value=>restored.push(value),
  });
  vm.runInContext(refreshSource,context);
  return {context,calls,restored,nodes,change:item=>listeners['work-queue-change']({detail:item})};
}

test('대기열 실행이 현재 요청 종료 전에 도착해도 다음 갱신에서 현재 작업을 연다',async()=>{
  const view=setup({requesting:true,sourceId:'source',queuedTask:{id:'queue',state:'queued'}});
  view.change({id:'queue',action:'split-plan',state:'running',run:'run'});
  assert.equal(view.restored.length,0);
  view.context.requesting=false;
  await view.context.refresh();
  assert.equal(view.restored[0].id,'run');
  assert.equal(view.context.queuedTask,null);
  assert.equal(view.nodes['split-error'].hidden,true);
});

test('새 화면에서도 현재 대기 중인 분할 작업을 찾되 완료된 과거 작업은 불러오지 않는다',async()=>{
  const view=setup();
  view.change({id:'old',action:'split-plan',state:'complete',run:'old-run'});
  assert.equal(view.context.queuedTask,null);
  view.change({id:'queue',action:'split-plan',state:'queued'});
  view.change({id:'queue',action:'split-plan',state:'complete',run:'run'});
  await new Promise(setImmediate);
  assert.equal(view.restored[0].id,'run');
});

test('선택한 다른 파일은 관계없는 대기열 작업으로 교체하지 않는다',()=>{
  const view=setup({sourceId:'other-source'});
  view.change({id:'other',action:'split-start',state:'running',run:'other-run'});
  view.change({id:'vod',action:'speech-start',state:'running'});
  assert.equal(view.context.queuedTask,null);
  assert.equal(view.restored.length,0);
});

test('current 응답이 먼저 복원된 뒤에도 같은 파일의 저장 대기를 연결한다',async()=>{
  const view=setup({sourceId:'source',job:{id:'run',state:'ready'}});
  view.change({id:'queue',action:'split-start',source_id:'source',state:'queued'});
  assert.equal(view.context.queuedTask.id,'queue');
  view.change({id:'queue',action:'split-start',source_id:'source',state:'running',run:'run'});
  await new Promise(setImmediate);
  assert.equal(view.restored[0].id,'run');
});

test('실행 전에 취소되거나 실패한 대기 작업은 입력 잠금을 해제한다',async()=>{
  for(const state of ['cancelled','error']){
    const view=setup({queuedTask:{id:'queue',state:'queued'}});
    view.change({id:'queue',action:'split-plan',state,message:'작업을 시작하지 못했습니다'});
    await view.context.refresh();
    assert.equal(view.context.queuedTask,null);
    assert.equal(view.calls[0][0],'error');
  }
});
