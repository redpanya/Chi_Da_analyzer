const $=id=>document.getElementById(id);
const make=(tag,text='')=>{const e=document.createElement(tag);e.textContent=text;return e;};
export function createErrorLogUI({api}){
  let payload=null,serial=0;
  function invalidate(){payload=null;$('error-export-preview').value='';$('error-export-save').disabled=true;$('error-email').hidden=true;$('error-email-consent').checked=false;}
  async function refresh(){
    const ticket=++serial;invalidate();
    try{
      const data=await api('error-log-list',{});if(ticket!==serial)return;
      $('error-log-enabled').checked=data.enabled;
      $('error-log-setting-state').textContent=data.enabled?'새 오류 기록 저장 중':'새 오류 기록 저장 안 함 · 기존 기록은 유지됩니다';
      $('error-log-state').textContent=`최근 ${data.events.length}건 · 최대 ${data.limit}건 / 약 4MB · 같은 오류는 반복 횟수로 표시`+(data.warning?' · '+data.warning:'');
      const rows=data.events.slice().reverse().map(r=>{
        const d=make('details'),title=make('summary',`${new Date(r.last_at||r.at).toLocaleString('ko-KR')} · ${r.summary} · ${r.count}회`);
        const meta=make('p',`${r.operation}${r.vod_id?' · VOD '+r.vod_id:''}${r.code!==null?' · 종료 코드 '+r.code:''}`);
        const message=make('pre',r.message||'상세 메시지 없음');message.className='error-log-message';
        d.append(title,meta,message);return d;
      });
      $('error-log-rows').replaceChildren(...rows);
    }catch(error){if(ticket===serial)$('error-log-state').textContent='오류 기록을 읽지 못했습니다 · '+error.message;}
  }
  $('error-log-apply').onclick=async()=>{
    $('error-log-apply').disabled=true;
    try{await api('error-log-settings',{enabled:$('error-log-enabled').checked});await refresh();}
    catch(e){$('error-log-setting-state').textContent='설정 저장 실패 · '+e.message;}
    finally{$('error-log-apply').disabled=false;}
  };
  $('error-log-refresh').onclick=refresh;
  $('error-export-check').onclick=async()=>{
    const ticket=++serial;invalidate();
    try{const value=await api('error-log-export',{});if(ticket!==serial)return;payload=JSON.stringify(value,null,2);$('error-export-preview').value=payload;$('error-export-save').disabled=false;}
    catch(e){if(ticket===serial)$('error-log-state').textContent='첨부용 JSON을 만들지 못했습니다 · '+e.message;}
  };
  $('error-export-save').onclick=()=>{
    if(!payload)return;const url=URL.createObjectURL(new Blob([payload],{type:'application/json'}));
    const a=make('a');a.href=url;a.download='ChiDaanalyzer-errors-'+new Date().toISOString().slice(0,10)+'.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),30000);
  };
  $('error-email-consent').onchange=()=>{
    $('error-email').hidden=!payload||!$('error-email-consent').checked;
    $('error-email').href='mailto:redpanyaday@gmail.com?'+new URLSearchParams({subject:'치다 분석기 오류 제보',body:'확인한 오류 진단 JSON을 직접 첨부해 주세요.\n\n문제가 발생한 기능과 재현 방법:\n\n예상했던 동작:\n'}).toString().replaceAll('+','%20');
  };
  return {refresh};
}
