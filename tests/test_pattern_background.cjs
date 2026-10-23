// 무작위 값의 양 끝과 8개 구간이 모두 로컬 타일에 연결되는지 검사한다.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const web = path.resolve(__dirname, '../web');
const script = fs.readFileSync(path.join(web, 'pattern-background.js'), 'utf8');
const css = fs.readFileSync(path.join(web, 'pattern-background.css'), 'utf8');
const size = Number(css.match(/--pattern-size:\s*(\d+)px/)[1]);
const gap = Number(css.match(/--pattern-gap:\s*(\d+)px/)[1]);
assert.equal(size, 256, '소품 표시 크기는 기존 512px의 50%');
assert.ok(gap >= 64 && gap <= 96, '소품 축소와 별도로 반복 사이에 여백을 둔다');
for (const random of [0, ...Array.from({length: 8}, (_, i) => (i + .5) / 8), 1 - Number.EPSILON]) {
  const layers = [], listeners = {};
  const element = () => ({
    clientWidth: 1280, clientHeight: 720, childElementCount: 0, attributes: {}, updates: 0,
    setAttribute(name, value) { this.attributes[name] = value; },
    replaceChildren(...children) { this.childElementCount = children.length; this.updates++; },
  });
  const document = {documentElement: {dataset: {}}, createElement: element,
    body: {prepend(layer) { layers.push(layer); }}};
  const math = Object.create(Math);
  math.random = () => random;
  vm.runInNewContext(script, {document, Math: math,
    getComputedStyle: () => ({getPropertyValue: name => name === '--pattern-size' ? size : gap}),
    window: {addEventListener(name, callback) { listeners[name] = callback; }},
  });
  const index = document.documentElement.dataset.pattern;
  assert.equal(index, String(Math.floor(random * 8) + 1));
  assert.match(css, new RegExp(`data-pattern="${index}"`));
  const filename = `patterns/pattern-${index.padStart(2, '0')}.webp`;
  assert.ok(css.includes(filename));
  assert.ok(fs.statSync(path.join(web, filename)).size < 128 * 1024);
  assert.equal(layers.length, 1);
  const layer = layers[0];
  assert.equal(layer.attributes['aria-hidden'], 'true');
  const initialUpdates = layer.updates;
  listeners.resize();
  assert.equal(layer.updates, initialUpdates, '크기 변화가 없으면 DOM을 다시 만들지 않는다');
  for (const [width, height] of [[180, 400], [980, 720], [1920, 1080], [3840, 2160]]) {
    layer.clientWidth = width; layer.clientHeight = height;
    listeners.resize();
    const columns = Math.max(1, Math.floor((width + gap) / (size + gap)));
    const rows = Math.max(1, Math.ceil((height - gap / 2) / (size + gap)));
    assert.ok(layer.childElementCount >= columns * rows, '창이 커져도 장식 칸이 부족하지 않는다');
    assert.equal(document.documentElement.dataset.pattern, index, '창 크기 변경 때 종류를 바꾸지 않는다');
  }
}
assert.match(css, /pointer-events:\s*none/);
assert.match(css, /@media print/);
assert.match(css, /forced-colors/);
console.log('통과: 8종 선택·50% 크기·독립 간격·창 크기 대응·접근성·128 KiB 미만');
