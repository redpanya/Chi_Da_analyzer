// 소품 단위 크롭·축소와 창 크기별 반복을 브라우저 의존성 없이 확인한다.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const web = path.resolve(__dirname, '../web');
const script = fs.readFileSync(path.join(web, 'pattern-background.js'), 'utf8');
const css = fs.readFileSync(path.join(web, 'pattern-background.css'), 'utf8');
const pitch = Number(css.match(/--pattern-pitch:\s*(\d+)px/)[1]);
assert.equal(pitch, 156);
for (const random of [0, ...Array.from({length: 8}, (_, i) => (i + .5) / 8), 1 - Number.EPSILON]) {
  const layers = [], listeners = {};
  const element = () => ({
    clientWidth: 1280, clientHeight: 720, children: [], attributes: {}, updates: 0,
    style: {setProperty(name, value) { this[name] = value; }},
    setAttribute(name, value) { this.attributes[name] = value; },
    append(child) { this.children.push(child); },
    replaceChildren(...children) { this.children = children; this.updates++; },
  });
  const document = {documentElement: {dataset: {}}, createElement: element,
    body: {prepend(layer) { layers.push(layer); }}};
  const math = Object.create(Math);
  math.random = () => random;
  vm.runInNewContext(script, {document, Math: math,
    getComputedStyle: () => ({getPropertyValue: () => pitch}),
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
  assert.equal(layer.style['--pattern-sheet-size'], '256px', '원본 512px 대비 정확히 50%');
  const unique = new Set();
  for (const cell of layer.children) {
    assert.equal(cell.children.length, 1, '칸 하나에는 시트가 아닌 소품 하나만 표시');
    const sprite = cell.children[0];
    const width = parseFloat(sprite.style.width), height = parseFloat(sprite.style.height);
    const [x, y] = sprite.style.backgroundPosition.split(' ').map(value => -parseFloat(value));
    assert.ok(width > 0 && height > 0 && width <= 100 && height <= 100, '소품 크기는 최대 100px');
    assert.ok(x >= 0 && y >= 0 && x + width <= 256 && y + height <= 256, '원본 시트 내부만 표시');
    assert.ok(pitch - width >= 56 && pitch - height >= 56, '개별 소품 사이 최소 여백');
    unique.add([x, y, width, height].join(','));
  }
  assert.equal(unique.size, [2, 5, 2, 3, 2, 2, 2, 2][Number(index) - 1], '선택 폴더의 모든 소품 종류 사용');
  const initialUpdates = layer.updates;
  listeners.resize();
  assert.equal(layer.updates, initialUpdates, '칸 수가 같으면 DOM을 다시 만들지 않는다');
  for (const [width, height] of [[100, 400], [980, 720], [1920, 1080], [3840, 2160]]) {
    layer.clientWidth = width; layer.clientHeight = height;
    listeners.resize();
    assert.equal(layer.children.length, Math.max(1, Math.floor(width / pitch)) * Math.ceil(height / pitch));
    assert.equal(document.documentElement.dataset.pattern, index, '창 크기를 바꿔도 테마 유지');
  }
}
assert.match(css, /pointer-events:\s*none/);
assert.match(css, /@media print/);
assert.match(css, /forced-colors/);
console.log('통과: 8종·20개 소품 독립 표시·50% 축소·156px 반복·창 크기 대응·접근성');
