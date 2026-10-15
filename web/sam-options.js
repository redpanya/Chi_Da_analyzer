// 두 분리 화면에서 같은 서버 설정과 안내를 사용한다.
export function createSamOptions(select, hint, note) {
  let profiles = [], wanted = 'standard';
  const describe = () => {
    hint.textContent = profiles.find(p => p.id === select.value)?.description || '분리 설정을 확인하는 중입니다.';
  };
  select.onchange = () => { wanted = select.value; describe(); };
  return {
    get value() { return select.value || wanted; },
    reset(value = 'standard') { wanted = value; select.value = value; describe(); },
    load(sam) {
      profiles = sam.profiles || [];
      select.replaceChildren(...profiles.map(p => {
        const option = document.createElement('option'); option.value = p.id; option.textContent = p.label; return option;
      }));
      select.value = profiles.some(p => p.id === wanted) ? wanted : 'standard';
      note.textContent = sam.speed_note || '';
      describe();
    },
  };
}
