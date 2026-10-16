const search = document.querySelector('#manual-search');
const entries = [...document.querySelectorAll('.entry')];
const chapters = [...document.querySelectorAll('.chapter')];
const clear = document.querySelector('#clear-search');
const expand = document.querySelector('#expand-all');
const status = document.querySelector('#search-status');
const normalize = value => value.normalize('NFKC').toLocaleLowerCase().replace(/\s+/g, ' ').trim();
const searchable = new Map(entries.map(entry => [entry, normalize(entry.dataset.search)]));
let beforeSearch = null;

function filter() {
  const words = normalize(search.value).split(' ').filter(Boolean);
  if (words.length && !beforeSearch) beforeSearch = new Map(entries.map(entry => [entry, entry.open]));
  let count = 0;
  for (const entry of entries) {
    const found = words.every(word => searchable.get(entry).includes(word));
    entry.hidden = !found;
    if (words.length) entry.open = found;
    else if (beforeSearch) entry.open = beforeSearch.get(entry);
    if (found) count++;
  }
  for (const chapter of chapters) chapter.hidden = ![...chapter.querySelectorAll('.entry')].some(entry => !entry.hidden);
  document.body.classList.toggle('searching', !!words.length);
  clear.hidden = !words.length;
  document.querySelector('#empty-state').hidden = count !== 0;
  status.textContent = words.length ? `검색 결과 ${count}개 · 설명서 안에서 찾았어요` : '9개 주제 · 102개 안내 · 설명 바로 아래 화면 참고';
  if (!words.length) beforeSearch = null;
  refreshExpand();
}

function refreshExpand() {
  const visible = entries.filter(entry => !entry.hidden);
  const allOpen = visible.length > 0 && visible.every(entry => entry.open);
  expand.textContent = allOpen ? '모두 접기' : '모두 펼치기';
  expand.setAttribute('aria-expanded', String(allOpen));
  expand.disabled = !visible.length;
}

function resetSearch() { search.value = ''; filter(); }
search.addEventListener('input', filter);
clear.addEventListener('click', () => { resetSearch(); search.focus(); });
document.querySelector('#empty-clear').addEventListener('click', () => { resetSearch(); search.focus(); });
expand.addEventListener('click', () => {
  const next = expand.getAttribute('aria-expanded') !== 'true';
  entries.filter(entry => !entry.hidden).forEach(entry => { entry.open = next; });
  refreshExpand();
});
entries.forEach(entry => entry.addEventListener('toggle', refreshExpand));
document.querySelectorAll('a[href^="#"]').forEach(link => link.addEventListener('click', () => {
  if (search.value) resetSearch();
}));

const dialog = document.querySelector('#image-dialog');
const enlarged = document.querySelector('#enlarged-shot');
document.querySelectorAll('.image-button').forEach(button => button.addEventListener('click', () => {
  const copy = button.querySelector('.shot-viewport').cloneNode(true);
  copy.querySelector('img').loading = 'eager';
  // 확대 화면의 SVG ID가 본문과 충돌하지 않게 한다.
  copy.querySelectorAll('[id]').forEach(element => { element.id += '-modal'; });
  copy.querySelectorAll('[marker-end]').forEach(element => {
    element.setAttribute('marker-end', element.getAttribute('marker-end').replace(')', '-modal)'));
  });
  enlarged.replaceChildren(copy);
  document.querySelector('#original-shot').href = button.dataset.source;
  document.querySelector('#image-caption').textContent = button.dataset.caption;
  dialog.showModal();
}));
document.querySelector('#close-image').addEventListener('click', () => dialog.close());
dialog.addEventListener('click', event => { if (event.target === dialog) dialog.close(); });
dialog.addEventListener('close', () => enlarged.replaceChildren());
refreshExpand();

// 인쇄 후에는 이용자가 펼쳐 둔 안내와 검색 범위를 되돌린다.
let beforePrint;
window.addEventListener('beforeprint', () => {
  beforePrint = entries.map(entry => ({ open: entry.open, hidden: entry.hidden }));
  entries.forEach(entry => { entry.open = true; entry.hidden = false; });
  chapters.forEach(chapter => { chapter.hidden = false; });
});
window.addEventListener('afterprint', () => {
  if (!beforePrint) return;
  entries.forEach((entry, i) => Object.assign(entry, beforePrint[i]));
  chapters.forEach(chapter => { chapter.hidden = ![...chapter.querySelectorAll('.entry')].some(entry => !entry.hidden); });
  beforePrint = null;
  refreshExpand();
});
