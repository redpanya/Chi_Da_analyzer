import {vodLabel} from './vod-label.js';
import {createSavedPicker,savedDescription} from './queue-saved.js';
const states={queued:'대기',running:'진행 중',paused:'일시정지',complete:'완료',partial:'일부 완료',error:'확인 필요',reused:'기존 자료 사용',skipped:'생략'};
const stages={download:'영상·전체 채팅',audio:'원음 추출',transcribe:'음성 전사',diarize:'화자 구분',reactions:'채팅 반응 분석',summary:'AI 문맥 요약'};
const languages={ko:'한국어',auto:'자동 감지',ja:'일본어',en:'영어'},vads={standard:'표준',sensitive:'민감',off:'끄기'},backends={sherpa:'sherpa-onnx',pyannote:'pyannote · Community-1',fluid:'FluidAudio · Community-1'};
const editable=item=>item.state==='queued'&&!item.report&&!item.stage&&!Object.keys(item.stages||{}).length;
export function createQueue({api,getRoot,onOpen,onChanged,onLock}){
 const $=id=>document.getElementById(id);let busy=false,polling=false,last='',root=getRoot(),data=null,importBusy=false;const selected=new Set();
 const node=(tag,text='')=>{const n=document.createElement(tag);n.textContent=text;return n;};
 const picker=createSavedPicker({api,getRoot,getSelected:()=>[...$('queue-inputs').children].flatMap(row=>row.project?[row.project.vod_id]:[]),onSelect:selectSaved});
 function controls(){
   const active=!!data?.active,locked=busy||importBusy;
   $('queue-add').disabled=locked;$('queue-more').disabled=locked;$('queue-saved').disabled=locked;
   $('queue-start').disabled=locked||active||!data?.items.some(i=>['queued','paused','running'].includes(i.state));
   $('queue-pause').disabled=busy||!data?.owned;
   $('queue-apply').disabled=locked||active||!selected.size;
   for(const control of $('queue-inputs').querySelectorAll('input,button,textarea'))control.disabled=locked;
   onLock?.(locked||active);
 }
 function numbered(){[...$('queue-inputs').children].forEach((r,i)=>r.querySelector('.queue-number').textContent=String(i+1));}
 function row(project){
   const wrap=node('div');wrap.className='input-row queue-url';wrap.project=project||null;
   const number=node('span');number.className='queue-number';wrap.append(number);
   if(project){const content=node('div');content.className='queue-saved-entry';content.append(node('strong',vodLabel(project)),node('small',savedDescription(project)));wrap.append(content);}
   else{const input=node('input');input.type='url';input.placeholder='https://chzzk.naver.com/video/… 또는 naver.me';input.setAttribute('aria-label','등록할 VOD 주소');wrap.append(input);}
   for(const [label,name,fn] of [
     ['↑','등록 순서 앞으로',()=>{if(wrap.previousElementSibling)wrap.parentElement.insertBefore(wrap,wrap.previousElementSibling);}],
     ['↓','등록 순서 뒤로',()=>{if(wrap.nextElementSibling)wrap.parentElement.insertBefore(wrap.nextElementSibling,wrap);}],
     ['−','이 등록 자료 삭제',()=>{wrap.remove();if(!$('queue-inputs').children.length)row();}]
   ]){const button=node('button',label);button.type='button';button.className='secondary';button.setAttribute('aria-label',name);button.onclick=()=>{fn();numbered();};wrap.append(button);}
   const background=node('textarea');background.className='queue-background';background.rows=1;background.maxLength=500;background.placeholder='이 VOD의 방송 배경 (선택 · 비우면 저장된 설명 사용)';background.setAttribute('aria-label','이 VOD의 방송 배경 설명');wrap.append(background);
   $('queue-inputs').append(wrap);numbered();controls();return wrap;
 }
 function selectSaved(project){
   if(busy||importBusy)return;
   if([...$('queue-inputs').children].some(row=>row.project?.vod_id===project.vod_id)){$('queue-notice').textContent='이미 등록할 자료에 선택한 VOD입니다';return;}
   const rows=[...$('queue-inputs').children];if(rows.length===1&&!rows[0].project&&!rows[0].querySelector('input').value.trim())rows[0].remove();
   row(project);$('queue-notice').textContent='저장한 VOD를 선택했습니다. 설정을 확인하고 목록에 등록하세요';
 }
 function settings(){return {mode:$('queue-mode').value,height:Number($('queue-height').value),language:$('queue-language').value,asr_options:{vad:$('queue-vad').value,prompt:$('queue-prompt').value},speakers_enabled:$('queue-voices').checked,backend:$('queue-backend').value,thinking:$('queue-thinking').checked,allow_partial_chat:$('queue-partial-chat').checked,continue_voice_error:$('queue-continue-voice').checked};}
 function mode(){$('queue-analysis-options').hidden=$('queue-mode').value!=='analysis';$('queue-backend').disabled=!$('queue-voices').checked;}
 async function action(fn){
   if(busy||importBusy)return;busy=true;controls();$('queue-notice').textContent='처리 중…';
   try{$('queue-notice').textContent=await fn()||'';}catch(error){$('queue-notice').textContent=error.message;}
   finally{busy=false;controls();await refresh();}
 }
 function render(value){
   data=value;
   for(const id of selected)if(!data.items.some(i=>i.id===id&&editable(i)))selected.delete(id);
   const running=data.items.findIndex(i=>i.state==='running');
   $('queue-status').textContent=`전체 ${data.items.length}개${running>=0?` · ${running+1}번째 처리 중`:''} · ${data.message||'등록 후 순차 작업을 시작하세요'}`;
   $('queue-list').replaceChildren();
   for(const [i,item] of data.items.entries()){
     const article=node('article');const title=node('strong',`${i+1}. ${item.title} · VOD ${item.vod}`);
     if(editable(item)){const label=node('label');label.className='inline-check';const check=node('input');check.type='checkbox';check.checked=selected.has(item.id);check.disabled=busy||data.active;check.setAttribute('aria-label',`${item.title} 대기 설정 선택`);check.onchange=()=>{if(check.checked)selected.add(item.id);else selected.delete(item.id);controls();};label.append(check,title);article.append(label);}else article.append(title);
     const opts=item.options;const status=node('p',`${states[item.state]||item.state}${item.stage?' · '+stages[item.stage]:''} · ${opts.mode==='analysis'?'AI 요약까지':'다운로드만'} · 저장·이어받기 화질 ${item.quality||'기존 등록 화질'} (등록 시 확정)`);status.className=item.state==='error'?'queue-error':'hint';
     article.append(status);
     if(opts.mode==='analysis')article.append(node('p',`전사 ${languages[opts.language]||opts.language} · 발화 검출 ${vads[opts.asr_options?.vad||'standard']||'표준'}${opts.asr_options?.prompt?' · 용어 힌트: '+opts.asr_options.prompt:''} · 화자 ${opts.speakers_enabled?backends[opts.backend]:'생략'} · 사고 ${opts.thinking?'켜기':'끄기'} · 검증 필요 채팅 ${opts.allow_partial_chat?'사용':'보류'} · 화자 오류 ${opts.continue_voice_error?'계속':'중단'}`));
     if(opts.background)article.append(node('p','방송 배경: '+opts.background));
     if(item.state==='queued')article.append(node('p',`예상: ${item.preview||'완료 자료를 확인하고 필요한 단계부터 처리'}`));
     const steps=node('p',Object.entries(item.stages||{}).map(([key,val])=>`${stages[key]}: ${states[val]||val}`).join(' → '));steps.className='hint';
     const buttons=node('div');buttons.className='play-actions';const open=node('button','VOD 열기');open.onclick=()=>onOpen(data.root,item.vod);buttons.append(open);
     if(item.state!=='running'){
       const remove=node('button','목록에서 제거');remove.className='subtle';remove.onclick=()=>action(async()=>{await api('queue-remove',{root:getRoot(),id:item.id});return '목록 항목만 제거했습니다. VOD 파일과 리포트는 유지됩니다';});buttons.append(remove);
       if(['error','partial','paused'].includes(item.state)){const retry=node('button','기존 설정으로 다시 대기');retry.className='secondary';retry.onclick=()=>action(()=>api('queue-retry',{root:getRoot(),id:item.id}).then(()=>''));buttons.append(retry);}
     }
     article.append(node('p',item.message||''),steps,buttons);$('queue-list').append(article);
   }
   controls();
 }
 function rootChanged(){
   if(root===getRoot())return;root=getRoot();last='';data=null;selected.clear();picker.close();
   for(const row of [...$('queue-inputs').children])if(row.project)row.remove();
   if(!$('queue-inputs').children.length)row();numbered();$('queue-list').replaceChildren();$('queue-status').textContent='현재 보관함의 목록을 확인합니다';$('queue-notice').textContent='';controls();
 }
 async function refresh(){
   rootChanged();if(polling||!getRoot())return;polling=true;const requested=getRoot();
   try{const value=await api('queue-status',{root:requested});if(requested!==getRoot())return;const signature=JSON.stringify(value);if(last!==signature){last=signature;render(value);onChanged?.();}else controls();}
   catch(error){if(requested===getRoot())$('queue-notice').textContent=error.message;}finally{polling=false;}
 }
 $('queue-more').onclick=()=>row();$('queue-saved').onclick=()=>picker.open();$('queue-mode').onchange=mode;$('queue-voices').onchange=mode;
 $('queue-add').onclick=()=>action(async()=>{
   const rows=[...$('queue-inputs').children].filter(r=>r.project||r.querySelector('input')?.value.trim());
   if(!rows.length)throw Error('VOD 주소를 입력하거나 저장한 VOD를 선택하세요');
   const requested=getRoot(),options=settings(),errors=[];let added=0;
   for(const row of rows){
     try{
       const description=row.querySelector('.queue-background').value.trim();
       const perVod=description?{...options,background:description}:options;
       if(row.project){const result=await api('queue-add-saved',{root:requested,vod_ids:[row.project.vod_id],options:perVod});if(result.errors.length)throw Error(result.errors[0].message);}
       else await api('queue-add',{root:requested,url:row.querySelector('input').value.trim(),options:perVod});
       row.remove();added++;
     }catch(error){errors.push(`${row.project?'VOD '+row.project.vod_id:row.querySelector('input').value}: ${error.message}`);}
   }
   if(!$('queue-inputs').children.length)row();numbered();
   return `${added}개 등록 완료${errors.length?' · 실패한 자료는 남겨두었습니다.\n'+errors.join('\n'):'. 순차 작업 시작을 누르면 진행합니다'}`;
 });
 $('queue-apply').onclick=()=>action(async()=>{await api('queue-settings',{root:getRoot(),ids:[...selected],options:settings()});selected.clear();last='';return '선택한 미실행 대기 항목에 설정을 적용했습니다';});
 $('queue-start').onclick=()=>action(()=>api('queue-start',{root:getRoot()}).then(()=>''));$('queue-pause').onclick=()=>action(()=>api('queue-pause',{root:getRoot()}).then(()=>''));
 row();mode();return {refresh,rootChanged,selectSaved,setImportBusy(value){importBusy=value;controls();}};
}
