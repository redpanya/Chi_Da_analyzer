export function queuePreflight({api,getRoot,onStart}){
 const dialog=document.createElement('dialog');dialog.className='queue-preflight';dialog.setAttribute('aria-labelledby','preflight-title');
 dialog.innerHTML='<h2 id="preflight-title">시작 전 확인</h2><p>선택한 단계의 준비 상태입니다. 완료 자료는 실행기가 확인한 뒤 재사용합니다.</p><div id="preflight-checks"></div><details><summary>실행할 VOD</summary><div id="preflight-items"></div></details><p id="preflight-note" role="status"></p><div class="play-actions"><button id="preflight-close">돌아가기</button><button id="preflight-start" class="primary">이 설정으로 시작</button></div>';
 document.body.append(dialog);const find=id=>dialog.querySelector('#'+id);let requested='';
 find('preflight-close').onclick=()=>dialog.close();
 find('preflight-start').onclick=()=>{if(requested!==getRoot()){find('preflight-note').textContent='보관함이 변경됐습니다. 다시 확인하세요.';return;}dialog.close();onStart();};
 return async()=>{requested=getRoot();find('preflight-checks').replaceChildren();find('preflight-items').replaceChildren();find('preflight-start').disabled=true;find('preflight-note').textContent='준비 상태 확인 중…';dialog.showModal();
  try{const value=await api('queue-preflight',{root:requested});if(requested!==getRoot()||!dialog.open)return;
   for(const check of value.checks){const p=document.createElement('p');p.textContent=`${check.ready?'✓':'확인 필요'} ${check.label} · ${check.detail}`;p.className=check.ready?'hint':'notice-warning';find('preflight-checks').append(p);}
   for(const item of value.items){const p=document.createElement('p');p.textContent=`${item.title} · ${item.preview}`;find('preflight-items').append(p);}
   find('preflight-note').textContent=value.checks.some(c=>!c.ready)?'준비가 필요한 단계가 있습니다. 완료 자료로 재사용 가능한 단계는 진행하고, 준비되지 않은 작업은 실행기에서 안전하게 중단·안내합니다.':'준비 상태를 확인했습니다. 인증·쓰기 권한·자료 일치 여부는 각 단계에서 다시 검사합니다.';
   find('preflight-start').disabled=!value.items.length;
  }catch(e){find('preflight-note').textContent=e.message;}
 };
}
