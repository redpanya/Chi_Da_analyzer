const search = document.querySelector('#manual-search');
const entries = [...document.querySelectorAll('.entry')];
const chapters = [...document.querySelectorAll('.chapter')];
const clear = document.querySelector('#clear-search');
const expand = document.querySelector('#expand-all');
const status = document.querySelector('#search-status');
const normalize = value => value.normalize('NFKC').toLocaleLowerCase().replace(/\s+/g, ' ').trim();
const searchable = new Map(entries.map(entry => [entry, normalize(entry.dataset.search)]));
let beforeSearch = null;

function refreshExpand() {
  const visible = entries.filter(entry => !entry.hidden);
  const allOpen = visible.length > 0 && visible.every(entry => entry.open);
  expand.textContent = allOpen ? '모두 접기' : '모두 펼치기';
  expand.setAttribute('aria-expanded', String(allOpen));
  expand.disabled = !visible.length;
}

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
  chapters.forEach(chapter => { chapter.hidden = ![...chapter.querySelectorAll('.entry')].some(entry => !entry.hidden); });
  clear.hidden = !words.length;
  document.querySelector('#contents').hidden = Boolean(words.length);
  document.querySelector('#empty-state').hidden = count !== 0;
  status.textContent = words.length ? `검색 결과 ${count}개` : `${chapters.length}개 주제, ${entries.length}개 안내`;
  if (!words.length) beforeSearch = null;
  refreshExpand();
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

const themeButton = document.querySelector('#theme-toggle');
const savedTheme = localStorage.getItem('manual-theme');
if (savedTheme === 'light' || savedTheme === 'dark') document.documentElement.dataset.theme = savedTheme;
function updateThemeButton() {
  const light = document.documentElement.dataset.theme === 'light';
  themeButton.setAttribute('aria-label', light ? '어두운 화면으로 전환' : '밝은 화면으로 전환');
  themeButton.textContent = light ? '어두운 화면' : '밝은 화면';
}
themeButton.addEventListener('click', () => {
  const next = document.documentElement.dataset.theme === 'light' ? 'dark' : 'light';
  document.documentElement.dataset.theme = next;
  localStorage.setItem('manual-theme', next);
  updateThemeButton();
});
updateThemeButton();

const dialog = document.querySelector('#image-dialog');
const enlarged = document.querySelector('#enlarged-shot');
document.querySelectorAll('.shot-button').forEach(button => button.addEventListener('click', () => {
  enlarged.src = button.dataset.source;
  enlarged.alt = button.dataset.caption;
  document.querySelector('#image-caption').textContent = button.dataset.caption;
  dialog.showModal();
}));
document.querySelector('#close-image').addEventListener('click', () => dialog.close());
dialog.addEventListener('click', event => { if (event.target === dialog) dialog.close(); });
dialog.addEventListener('close', () => { enlarged.removeAttribute('src'); });
refreshExpand();

function openLinkedGuide() {
  const target = document.getElementById(location.hash.slice(1));
  const entry = target?.closest('details.entry');
  if (entry) {
    if (search.value) resetSearch();
    entry.open = true;
    entry.scrollIntoView();
  }
}
window.addEventListener('hashchange', openLinkedGuide);
openLinkedGuide();
