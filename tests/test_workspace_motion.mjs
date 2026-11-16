import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import test from 'node:test';

const source = fs.readFileSync(new URL('../web/workspace-motion.js', import.meta.url), 'utf8');

function setup({ reduce = false, supportsPreference = true } = {}) {
  const listeners = new Map();
  const media = {
    matches: reduce,
    addEventListener(type, listener) {
      if (!listeners.has(type)) listeners.set(type, new Set());
      listeners.get(type).add(listener);
    },
    change(value) {
      this.matches = value;
      for (const listener of listeners.get('change') || []) listener({ matches: value });
    },
  };
  const context = vm.createContext({URL,...(supportsPreference ? { matchMedia: () => media } : {})});
  vm.runInContext(source.replace(/^export /gm, '') + '\nglobalThis.motionAPI = { animateUI, cancelMotion, enterView, bindDocumentMotion };', context);
  return { ...context.motionAPI, media, listeners };
}

function element() {
  return {
    animations: [],
    animate(frames, options) {
      const animation = {
        frames, options, cancelled: false, cancelCount: 0, finishCount: 0,
        cancel() { this.cancelled = true; this.cancelCount += 1; },
        finish() { this.finishCount += 1; this.onfinish?.(); },
        // 이미 브라우저 이벤트 큐에 들어간 finish가 취소 이후 도착하는 상황도 재현한다.
        lateFinish() { this.onfinish?.(); },
      };
      this.animations.push(animation);
      return animation;
    },
  };
}

function documentFixture({native=true,studio=false,reduce=false}={}){
 const motion=setup({reduce}),events={},windowEvents={},classes=new Set(),main=element(),grid=element();
 const root={documentElement:{classList:classes},body:{classList:{contains:name=>studio&&name==='studio-workspace'}},
  querySelector:selector=>({'main':main,'.studio-grid':grid})[selector],addEventListener:(name,fn)=>events[name]=fn};
 const win={location:{href:'http://localhost:8000/session/video-split.html#work'},addEventListener:(name,fn)=>windowEvents[name]=fn};
 if(native)win.CSSViewTransitionRule=class {};
 motion.bindDocumentMotion(root,win);return {root,win,events,windowEvents,classes,main,grid};
}

test('문서 탐색은 브라우저가 처리하고 편집 준비나 뒤로 가기 시 화면을 다시 숨기지 않는다',()=>{
 const f=documentFixture();
 for(const page of ['./#library','mix-studio.html?mix=test','clip-studio.html?vod_id=1']){
  const link={href:new URL(page,f.win.location.href).href,hasAttribute:()=>false};
  f.events.click({button:0,target:{closest:()=>link},preventDefault(){assert.fail('문서 탐색을 가로챘습니다');}});
 }
 assert.deepEqual(Object.keys(f.events),['click']);
 assert.equal(f.windowEvents.pageswap,undefined);
 assert.equal(f.classes.has('document-motion-fallback'),false);
 assert.equal(documentFixture({native:false}).classes.has('document-motion-fallback'),true);
});

test('편집기 왕복에서는 도착한 화면만 투명도 변화 없이 움직인다',()=>{
 const transition={viewTransition:{}};
 for(const studio of [false,true]){
  const view=documentFixture({studio}),panel=studio?view.grid:view.main;
  view.windowEvents.pagereveal({viewTransition:null});
  assert.equal(panel.animations.length,0);
  view.windowEvents.pagereveal(transition);
  assert.equal((studio?view.main:view.grid).animations.length,0);
  const [arrival]=panel.animations;
  assert.deepEqual(Array.from(arrival.frames,frame=>frame.translate),['0 4px','0 0']);
  assert.ok(arrival.frames.every(frame=>!('opacity' in frame)));
  const reduced=documentFixture({studio,reduce:true});
  reduced.windowEvents.pagereveal(transition);
  assert.equal((studio?reduced.grid:reduced.main).animations.length,0);
 }
});

test('현재 문서 메뉴만 새로고침을 막고 실제 이동과 수정키 동작은 보존한다',()=>{
 const f=documentFixture();
 const click=(url,extra={},attrs={})=>{
  let prevented=false;const link={href:new URL(url,'http://localhost:8000/session/').href,target:attrs.target||'',hasAttribute:()=>!!attrs.download};
  f.events.click({button:0,target:{closest:()=>link},preventDefault(){prevented=true;},...extra});return prevented;
 };
 assert.equal(click('video-split.html'),true);
 assert.equal(click('video-split.html#work'),true);
 for(const url of ['video-split.html#other','video-split.html?new=1','clip-studio.html','./#library','https://example.com/session/video-split.html'])assert.equal(click(url),false);
 for(const extra of [{defaultPrevented:true},{button:1},{metaKey:true},{ctrlKey:true},{shiftKey:true},{altKey:true}])assert.equal(click('video-split.html',extra),false);
 assert.equal(click('video-split.html',{}, {target:'_blank'}),false);
 assert.equal(click('video-split.html',{}, {download:true}),false);
});

test('같은 요소의 새 모션은 이전 모션을 취소하고 늦은 완료를 무시한다', () => {
  const motion = setup(), node = element(), completed = [];
  const first = motion.animateUI(node, [{ opacity: 0 }, { opacity: 1 }], {}, () => completed.push('old'));
  const second = motion.animateUI(node, [{ opacity: 1 }, { opacity: 0 }], {}, () => completed.push('new'));
  assert.equal(first.cancelCount, 1);
  first.lateFinish();
  assert.deepEqual(completed, []);
  second.finish();
  assert.deepEqual(completed, ['new']);
  assert.equal(second.cancelled, false);
});

test('직접 취소와 중복 취소 뒤에는 완료 콜백을 실행하지 않는다', () => {
  const motion = setup(), node = element(); let count = 0;
  const animation = motion.animateUI(node, [], {}, () => count++);
  motion.cancelMotion(node); motion.cancelMotion(node);
  animation.lateFinish();
  assert.equal(animation.cancelCount, 1);
  assert.equal(count, 0);
});

test('중복 finish 이벤트가 와도 완료 콜백은 한 번만 실행한다', () => {
  const motion = setup(), node = element(); let count = 0;
  const animation = motion.animateUI(node, [], {}, () => count++);
  animation.finish(); animation.lateFinish(); motion.cancelMotion(node);
  assert.equal(count, 1);
  assert.equal(animation.cancelCount, 0);
});

test('서로 다른 요소의 애니메이션은 독립적으로 취소된다', () => {
  const motion = setup(), a = element(), b = element(), completed = [];
  const first = motion.animateUI(a, [], {}, () => completed.push('a'));
  const second = motion.animateUI(b, [], {}, () => completed.push('b'));
  motion.cancelMotion(a); first.lateFinish(); second.finish();
  assert.deepEqual(completed, ['b']);
  assert.equal(second.cancelCount, 0);
});

test('동작 줄이기를 켜고 실행하면 프레임 생성 없이 즉시 완료한다', () => {
  const motion = setup({ reduce: true }), node = element(); let count = 0;
  const result = motion.animateUI(node, [], {}, () => count++);
  assert.equal(result, undefined);
  assert.equal(node.animations.length, 0);
  assert.equal(count, 1);
});

test('실행 도중 동작 줄이기를 켜면 활성 모션만 끝내고 중복 변경을 무시한다', () => {
  const motion = setup(), a = element(), b = element(), completed = [];
  const abandoned = motion.animateUI(a, [], {}, () => completed.push('abandoned'));
  const first = motion.animateUI(a, [], {}, () => completed.push('a'));
  const second = motion.animateUI(b, [], {}, () => completed.push('b'));
  motion.media.change(false);
  assert.equal(first.finishCount, 0);
  motion.media.change(true); motion.media.change(true);
  assert.deepEqual(completed, ['a', 'b']);
  assert.equal(abandoned.finishCount, 0);
  assert.equal(first.finishCount, 1);
  assert.equal(second.finishCount, 1);
  assert.equal(motion.listeners.get('change').size, 1);
  abandoned.lateFinish(); first.lateFinish(); second.lateFinish();
  assert.deepEqual(completed, ['a', 'b']);
});

test('애니메이션 API가 없는 요소는 즉시 완료하고 미디어 쿼리 미지원도 허용한다', () => {
  const motion = setup({ supportsPreference: false }); let count = 0;
  motion.animateUI({}, [], {}, () => count++);
  motion.animateUI(null, [], {}, () => count++);
  assert.equal(count, 1);
  const node = element(), animation = motion.animateUI(node, [], {}, () => count++);
  animation.finish();
  assert.equal(count, 2);
});

test('옵션 재정의와 화면 이동 방향은 공통 감속 곡선을 유지한다', () => {
  const motion = setup(), node = element();
  const custom = motion.animateUI(node, [], { duration: 180 });
  assert.equal(custom.options.duration, 180);
  assert.equal(custom.options.easing, 'cubic-bezier(.2,.8,.2,1)');
  const forward = motion.enterView(node, 1);
  assert.equal(forward.frames[0].transform, 'translateX(12px)');
  assert.equal(forward.options.duration, 260);
  const backward = motion.enterView(node, -1);
  assert.equal(backward.frames[0].transform, 'translateX(-12px)');
  const page = motion.enterView(node, 0);
  assert.equal(page.frames[0].transform, 'translateY(8px)');
  assert.equal(page.frames.at(-1).transform, 'translate(0)');
});

