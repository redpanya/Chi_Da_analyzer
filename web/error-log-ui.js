const $=id=>document.getElementById(id);
const make=(tag,text='')=>{const e=document.createElement(tag);e.textContent=text;return e;};
export function createErrorLogUI({api,getProject}){
  let payload=null,serial=0,exportSerial=0,events=[],scope='';const chosen=new Set();
  const projectKey=()=>{const p=getProject();return p?.vod_id?JSON.stringify([p.root,p.vod_id,p.path]):'';};
  const filters=make('div');filters.className='error-log-filters';filters.innerHTML='<input id="error-filter-operation" type="search" placeholder="기능 검색" aria-label="오류 기능 필터"><select id="error-filter-period" aria-label="오류 기간"><option value="0">전체 기간</option><option value="1">최근 하루</option><option value="7">최근 7일</option><option value="30">최근 30일</option></select><button id="error-select-visible">표시 항목 선택</button><button id="error-select-clear">선택 해제</button><span id="error-select-count"></span>';
  $('error-log-rows').before(filters);
  function visible(){const op=$('error-filter-operation').value.trim().toLowerCase(),days=Number($('error-filter-period').value);return events.filter(r=>(!op||r.operation.toLowerCase().includes(op)||r.summary.toLowerCase().includes(op))&&(!days||Date.parse(r.last_at||r.at)>=Date.now()-days*86400000));}
  function selection(){
    $('error-select-count').textContent=chosen.size?`${chosen.size}건 선택 / 선택한 기록만 첨부`:`표시된 기록 ${visible().length}건을 첨부`;
    $('error-export-check').disabled=!visible().length;invalidate();
  }
  function renderRows(){
    const rows=visible().slice().reverse().map(r=>{const row=make('article');row.className='error-select-row';const label=make('label'),check=make('input');check.type='checkbox';check.checked=chosen.has(r.event_id);check.setAttribute('aria-label',r.summary+' 선택');check.onchange=()=>{check.checked?chosen.add(r.event_id):chosen.delete(r.event_id);selection();};label.append(check);
      const d=make('details'),title=make('summary',`${new Date(r.last_at||r.at).toLocaleString('ko-KR')} / ${r.summary} / ${r.count}회`);
      const meta=make('p',`${r.operation} / VOD ${r.vod_id}${r.code!==null?' / 종료 코드 '+r.code:''}`),message=make('pre',r.message||'상세 메시지 없음');message.className='error-log-message';d.append(title,meta,message);row.append(label,d);return row;});$('error-log-rows').replaceChildren(...rows);selection();
  }
  for(const id of ['error-filter-operation','error-filter-period'])$(id).addEventListener('input',()=>{chosen.clear();renderRows();});
  $('error-select-visible').onclick=()=>{visible().forEach(r=>chosen.add(r.event_id));renderRows();};$('error-select-clear').onclick=()=>{chosen.clear();renderRows();};
  function invalidate(){exportSerial++;payload=null;$('error-export-preview').value='';$('error-export-save').disabled=true;$('error-email').hidden=true;$('error-email-consent').checked=false;}
  function setProject(){
    const key=projectKey();if(key===scope)return;
    scope=key;serial++;events=[];chosen.clear();
    $('error-filter-operation').value='';$('error-filter-period').value='0';
    renderRows();$('error-log-state').textContent=key?'선택한 VOD의 오류 기록을 불러오세요.':'VOD를 선택하면 해당 오류 기록을 표시합니다.';
  }
  async function refresh(){
    setProject();events=[];chosen.clear();renderRows();
    const ticket=++serial,key=scope,vod=getProject()?.vod_id;
    const valid=()=>ticket===serial&&key===projectKey();
    try{
      const data=await api(key?'error-log-list':'error-log-config',{});if(!valid())return;
      $('error-log-enabled').checked=data.enabled;
      $('error-log-setting-state').textContent=data.enabled?'새 오류 기록 저장 중':'새 오류 기록 저장 안 함 / 기존 기록은 유지됩니다';
      events=key?data.events.filter(r=>String(r.vod_id)===String(vod)):[];
      $('error-log-state').textContent=(key?`VOD ${vod} 오류 기록 ${events.length}건`:'VOD를 선택하면 해당 오류 기록을 표시합니다.')+(data.warning?' / '+data.warning:'');
      renderRows();
    }catch(error){if(valid())$('error-log-state').textContent='오류 기록을 읽지 못했습니다 / '+error.message;}
  }
  $('error-log-apply').onclick=async()=>{
    $('error-log-apply').disabled=true;
    try{await api('error-log-settings',{enabled:$('error-log-enabled').checked});await refresh();}
    catch(e){$('error-log-setting-state').textContent='설정 저장 실패 / '+e.message;}
    finally{$('error-log-apply').disabled=false;}
  };
  $('error-log-refresh').onclick=refresh;
  $('error-export-check').onclick=async()=>{
    if(!scope||scope!==projectKey()||!visible().length)return;
    invalidate();const ticket=exportSerial,key=scope,ids=visible().filter(r=>!chosen.size||chosen.has(r.event_id)).map(r=>r.event_id);
    try{const value=await api('error-log-export',{ids});if(ticket!==exportSerial||key!==projectKey())return;payload=JSON.stringify(value,null,2);$('error-export-preview').value=payload;$('error-export-save').disabled=false;}
    catch(e){if(ticket===exportSerial&&key===projectKey())$('error-log-state').textContent='첨부용 JSON을 만들지 못했습니다 / '+e.message;}
  };
  $('error-export-save').onclick=()=>{
    if(!payload||scope!==projectKey())return;const url=URL.createObjectURL(new Blob([payload],{type:'application/json'}));
    const a=make('a');a.href=url;a.download='ChiDaanalyzer-errors-'+new Date().toISOString().slice(0,10)+'.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),30000);
  };
  $('error-email-consent').onchange=()=>{
    $('error-email').hidden=!payload||!$('error-email-consent').checked;
    $('error-email').href='mailto:redpanyaday@gmail.com?'+new URLSearchParams({subject:'치다 분석기 오류 제보',body:'확인한 오류 진단 JSON을 직접 첨부해 주세요.\n\n문제가 발생한 기능과 재현 방법:\n\n예상했던 동작:\n'}).toString().replaceAll('+','%20');
  };
  renderRows();
  return {refresh,setProject};
}
