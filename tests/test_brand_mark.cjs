const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const web = path.resolve(__dirname, '../web');
const code = fs.readFileSync(path.join(web, 'pattern-background.js'), 'utf8');
function boot({random = .025, storage = new Map(), href = 'http://127.0.0.1:1234/run/', blocked = false} = {}) {
  const logos = [], events = {}, pending = [];
  const node = tag => ({tag, attributes: {}, children: [],
    setAttribute(key, value) {this.attributes[key] = value;},
    append(...children) {this.children.push(...children);},
    replaceChildren(...children) {this.children = children;},
  });
  const document = {
    querySelectorAll: () => [24, 34].map(size => ({
      getAttribute: () => String(size), replaceWith(logo) {logos.push(logo);},
    })),
    querySelector: () => null,
    createElementNS(namespace, tag) {assert.equal(namespace, 'http://www.w3.org/2000/svg'); return node(tag);},
    addEventListener(type, handler) {events[type] = handler;},
  };
  let calls = 0;
  const math = Object.create(Math);
  math.random = () => {calls++; return random;};
  const sessionStorage = {
    getItem(key) {if (blocked) throw Error('저장소 제한'); return storage.get(key) ?? null;},
    setItem(key, value) {if (blocked) throw Error('저장소 제한'); storage.set(key, value);},
  };
  vm.runInNewContext(code, {document, Math: math, URL, location: {href}, sessionStorage,
    queueMicrotask: callback => pending.push(callback)});
  return {logos, events, storage, calls: () => calls, art: () => logos[0].children[4].children[0],
    flush: () => {while (pending.length) pending.shift()();},
    click({trusted = true, disabled = false, active = false, menu = true} = {}) {
      events.click({isTrusted: trusted, target: {closest: () => menu ? {
        tagName: 'BUTTON', matches: selector => selector.includes(':disabled') ? disabled : active,
      } : null}});
    }};
}
const identity = app => JSON.stringify(app.art());
const choices = new Set();
for (let index = 0; index < 20; index++) {
  const app = boot({random: (index + .5) / 20});
  assert.equal(app.calls(), 0, '처음에는 무작위 선택 없이 녹색 돋보기');
  assert.equal(app.art().tag, 'circle');
  assert.deepEqual(app.art().attributes, {class: 'brand-start-fill', cx: '17', cy: '17', r: '11.1'});
  const frames = app.logos.map(logo => JSON.stringify(logo.children.slice(0, 3)));
  for (const options of [{trusted: false}, {disabled: true}, {active: true}, {menu: false}]) app.click(options);
  assert.equal(app.calls(), 0, '자동 복원, 사용 불가, 현재 메뉴, 일반 클릭은 무시');
  app.click();
  assert.equal(app.calls(), 1, '사용자 메뉴 클릭마다 한 번 교체');
  for (const [number, logo] of app.logos.entries()) {
    assert.equal(logo.attributes.width, String([24, 34][number]));
    assert.equal(logo.attributes['aria-hidden'], 'true');
    assert.equal(JSON.stringify(logo.children.slice(0, 3)), frames[number], '돋보기 외곽 유지');
    assert.equal(logo.children[3].children[0].tag, 'clipPath', '렌즈 안에서만 소품 노출');
    const art = logo.children[4].children[0], image = art.children[0];
    assert.equal(art.attributes.overflow, 'hidden');
    const [x, y, width, height] = art.attributes.viewBox.split(' ').map(Number);
    assert.ok(x >= 0 && y >= 0 && x + width <= 512 && y + height <= 512);
    assert.ok(width < 512 && height < 512, '전체 패턴 대신 개별 소품');
    assert.ok(Math.abs(Number(art.attributes.width) / Number(art.attributes.height) - width / height) < 1e-10,
      '비율을 유지해 인접 소품 노출 방지');
    assert.ok(Math.abs(Math.max(Number(art.attributes.width), Number(art.attributes.height)) - 24) < 1e-10,
      '소품 긴 변은 17에서 24로 확대');
    assert.equal(image.tag, 'image');
    assert.ok(fs.existsSync(path.join(web, image.attributes.href)));
    choices.add(image.attributes.href + ':' + art.attributes.viewBox);
  }
  assert.equal(JSON.stringify(app.logos[0].children[4].children[0]), JSON.stringify(app.logos[1].children[4].children[0]),
    '같은 문서 로고는 같은 소품');
  const first = identity(app);
  app.click();
  assert.notEqual(identity(app), first, '직전 소품의 연속 선택 방지');
}
assert.equal(choices.size, 20, '개별 소품 20종 모두 선택 가능');
const original = boot(); original.click();
for (const suffix of ['#library', 'clip-studio.html?vod_id=1', 'video-split.html']) {
  const next = boot({storage: original.storage, href: 'http://127.0.0.1:1234/run/' + suffix});
  assert.equal(identity(next), identity(original), '새로고침과 같은 실행의 문서 이동에서 소품 유지');
  assert.equal(next.calls(), 0, '문서 로드에서 추가 교체 없음');
}
assert.equal(boot({storage: original.storage, href: 'http://127.0.0.1:1234/new-run/'}).art().attributes.class,
  'brand-start-fill', '새 실행 주소는 녹색 돋보기로 시작');
for (const saved of ['-1', '20', 'NaN', '', 'bad']) {
  assert.equal(boot({storage: new Map([['chida-brand:/run/', saved]])}).art().attributes.class, 'brand-start-fill');
}
const restricted = boot({blocked: true}); restricted.click();
assert.equal(restricted.art().attributes.class, 'brand-motif', '저장소 제한에도 메뉴와 로고 동작');
const keyboard = boot();
let selected = {};
const list = {querySelector: () => selected}, tab = {closest: () => list};
const arrow = {isTrusted: true, key: 'ArrowRight', target: {closest: () => tab}};
keyboard.events.keydown(arrow); keyboard.flush();
assert.equal(keyboard.calls(), 0, '선택 탭이 바뀌지 않으면 소품 유지');
keyboard.events.keydown(arrow); selected = {}; keyboard.flush();
assert.equal(keyboard.calls(), 1, '방향키로 실제 선택 탭을 옮기면 한 번 교체');
const design = fs.readFileSync(path.join(web, 'design-system.js'), 'utf8');
assert.equal(design.split("import './pattern-background.js'").length - 1, 1);
for (const page of ['index.html', 'clip-studio.html']) {
  const html = fs.readFileSync(path.join(web, page), 'utf8');
  assert.ok(html.includes('src="design-system.js"'));
  assert.ok(!html.includes('src="pattern-background.js"'), '중복 초기화 방지');
  assert.ok(html.includes('href="icons/chida-16.png"'), '파비콘 보존');
}
const css = fs.readFileSync(path.join(web, 'design-system.css'), 'utf8');
assert.match(css, /\.brand-mark \.brand-lens \{fill:var\(--ds-input\);stroke:var\(--ds-accent\)/);
assert.match(css, /\.brand-mark \.brand-tile \{fill:var\(--ds-surface\)/);
assert.match(css, /\.brand-mark \.brand-start-fill \{fill:#00ffa3;/);
console.log('첫 녹색 돋보기, 메뉴별 교체, 소품 확대, 직전 중복 방지, 문서 이동, 저장소 예외와 테마 검사 통과');
