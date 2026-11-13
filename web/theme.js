/* 최초 페인트 전에 실행합니다. 이 환경값은 영상/편집 결과와 독립입니다. */
(function () {
  'use strict';
  if (window.ChidaTheme) return;
  const KEY = 'chida:theme';
  const COOKIE = 'chida_theme_preference';
  const valid = value => ['system', 'light', 'dark'].includes(value);
  const media = window.matchMedia ? window.matchMedia('(prefers-color-scheme: dark)') : null;
  const connections = new WeakMap();
  let preference = 'dark';
  let theme = '';
  let memoryOnly = false;
  let ignoreCookie = false;
  function read() {
    // loopback 쿠키는 무작위 서버 포트가 달라져도 테마 값만 기억합니다.
    try {
      const value = document.cookie.split(';').map(item => item.trim()).find(item => item.startsWith(COOKIE + '='))?.slice(COOKIE.length + 1);
      if (!ignoreCookie && valid(value)) return value;
    } catch (_) { /* 저장 차단 시 현재 창의 선택 유지 */ }
    try {
      const value = window.localStorage.getItem(KEY);
      if (valid(value)) return value;
    } catch (_) { /* 저장 차단 시 기본 다크 사용 */ }
    return null;
  }
  function apply() {
    const next = preference === 'system' ? (media?.matches ? 'dark' : 'light') : preference;
    const changed = theme !== next || document.documentElement.dataset.themePreference !== preference;
    theme = next;
    const root = document.documentElement;
    root.dataset.theme = theme;
    root.dataset.themePreference = preference;
    root.classList.toggle('wa-dark', theme === 'dark');
    root.classList.toggle('wa-light', theme === 'light');
    if (changed) document.dispatchEvent(new CustomEvent('chida-themechange', { detail: { preference, theme } }));
  }
  function setPreference(value) {
    if (!valid(value)) return false;
    preference = value;
    memoryOnly = true;
    try {
      document.cookie = COOKIE + '=' + value + '; Max-Age=31536000; Path=/; SameSite=Strict';
      memoryOnly = !document.cookie.split(';').some(item => item.trim() === COOKIE + '=' + value);
      ignoreCookie = memoryOnly;
    } catch (_) { ignoreCookie = true; /* 쿠키가 막혀도 localStorage 또는 현재 창에서 동작 */ }
    try { window.localStorage.setItem(KEY, value); memoryOnly = false; } catch (_) { /* 현재 창 유지 */ }
    apply();
    return true;
  }
  function synchronize() {
    if (memoryOnly) return;
    const value = read();
    if (value && value !== preference) { preference = value; apply(); }
  }
  function connect(select) {
    if (!select || connections.has(select)) return connections.get(select) || (() => {});
    select.value = preference;
    const change = () => { setPreference(select.value); select.value = preference; };
    const update = () => { select.value = preference; };
    select.addEventListener('change', change);
    document.addEventListener('chida-themechange', update);
    const disconnect = () => {
      select.removeEventListener('change', change);
      document.removeEventListener('chida-themechange', update);
      connections.delete(select);
    };
    connections.set(select, disconnect);
    return disconnect;
  }
  window.ChidaTheme = Object.freeze({ getPreference: () => preference, setPreference, resolved: () => theme, connect });
  preference = read() || 'dark';
  apply();
  if (media?.addEventListener) media.addEventListener('change', () => { if (preference === 'system') apply(); });
  else if (media?.addListener) media.addListener(() => { if (preference === 'system') apply(); });
  window.addEventListener('storage', event => {
    if (event.key !== KEY || !valid(event.newValue)) return;
    preference = event.newValue; apply();
  });
  window.addEventListener('focus', synchronize);
  document.addEventListener('visibilitychange', () => { if (!document.hidden) synchronize(); });
})();
