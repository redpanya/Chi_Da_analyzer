// 무작위 값의 양 끝과 8개 구간이 모두 로컬 타일에 연결되는지 검사한다.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const web = path.resolve(__dirname, '../web');
const script = fs.readFileSync(path.join(web, 'pattern-background.js'), 'utf8');
const css = fs.readFileSync(path.join(web, 'pattern-background.css'), 'utf8');
for (const random of [0, ...Array.from({length: 8}, (_, i) => (i + .5) / 8), 1 - Number.EPSILON]) {
  const document = {documentElement: {dataset: {}}};
  const math = Object.create(Math);
  math.random = () => random;
  vm.runInNewContext(script, {document, Math: math});
  const index = document.documentElement.dataset.pattern;
  assert.equal(index, String(Math.floor(random * 8) + 1));
  assert.match(css, new RegExp(`data-pattern="${index}"`));
  const filename = `patterns/pattern-${index.padStart(2, '0')}.webp`;
  assert.ok(css.includes(filename));
  assert.ok(fs.statSync(path.join(web, filename)).size < 128 * 1024);
}
assert.match(css, /pointer-events:\s*none/);
assert.match(css, /@media print/);
assert.match(css, /forced-colors/);
console.log('통과: 8종 무작위 선택·로컬 자원·파일당 128 KiB 미만·클릭 통과·인쇄/고대비 제외');
