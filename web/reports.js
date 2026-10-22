const stages={download:'영상·채팅 다운로드/검증',audio:'원음 추출',transcribe:'음성 전사',diarize:'화자 구분',reactions:'채팅 반응 분석',summary:'AI 문맥 요약',model:'모델 준비'};
const states={running:'진행 중',complete:'완료',partial:'일부 완료',error:'실패',paused:'중단',reused:'기존 결과 사용',skipped:'생략'};
const names={video_seconds:'영상 길이(초)',transcript_segments:'전사 발언 수',transcript_characters:'전사 문자 수',transcript_processed_seconds:'전사 완료 범위(초)',chat_messages:'채팅 수',chat_characters:'채팅 문자 수',summary_input_speech_characters:'요약 입력 후보 전사 문자 수',summary_input_chat_characters:'요약 입력 후보 채팅 문자 수',generated_tokens:'요약 생성 토큰(누적)',prompt_tokens:'요약 입력 평가 토큰(누적)',prompt_ms:'입력 평가 시간(ms)',generation_ms:'생성 시간(ms)',fresh_attempts:'모델 요청 수(재시도 포함)',checkpoint_reuses:'요약 체크포인트 재사용 수',model_load_seconds:'요약 모델 로딩(초)',tokenizer_seconds:'토큰 계산(초)',requests_without_response_metrics:'응답 계측이 없는 요청 수'};
const hardwareText=h=>`${h.os??'미확인'} ${h.os_version??''} · ${h.architecture??'미확인'}\nCPU: ${h.cpu||'미확인'} · ${h.cores??'?'}코어 / ${h.threads??'?'}스레드\nGPU: ${h.gpu||'미확인'}\nRAM: ${h.ram_bytes? (h.ram_bytes/1024**3).toFixed(1)+' GiB':'미확인'}`;

export function createReports({api,getProject}){
 const $=id=>document.getElementById(id);
 let selected=null,preview=null,revision=0;
 const node=(tag,text)=>{const n=document.createElement(tag);n.textContent=text;return n;};
 function reset(){revision++;preview=null;$('report-save').disabled=true;$('report-payload').value='';}
 function parameters(){const p=getProject();if(!p)throw Error('저장한 VOD를 먼저 선택하세요');return {root:p.root,vod_id:p.vod_id};}
 async function read(){
  reset();const generation=revision,id=$('report-select').value;
  selected=null;$('report-data').hidden=true;
  if(!id)return;
  const data=await api('report-read',{...parameters(),report_id:id});
  if(generation!==revision)return;
  selected=id;$('report-data').hidden=false;
  $('report-vod').textContent=`VOD ${data.payload.vod_id} · 이 실행에 기록된 PC 사양`;
  $('report-run-hardware').textContent=hardwareText(data.payload.hardware);
  $('report-stages').replaceChildren();
  for(const stage of data.payload.stages){
   const tr=document.createElement('tr');
   for(const text of [stage.summary_mode==='timestamps'?'빠른 타임스탬프':stages[stage.stage],states[stage.state],stage.seconds==null?'미계측':stage.seconds.toLocaleString()+'초',stage.error_code==='none'?'—':stage.error_code])tr.append(node('td',text));
   $('report-stages').append(tr);
  }
  $('report-counts').replaceChildren();
  for(const [key,value] of Object.entries(data.payload.counts))$('report-counts').append(node('p',`${names[key]||key}: ${value==null?'미계측':value.toLocaleString()}`));
  $('report-log').textContent=data.events.map(e=>`${e.at} · ${stages[e.stage]} · ${states[e.state]||e.state}${e.message?' · '+e.message:''}`).concat(data.details.map(e=>`${stages[e.stage]} · ${e.message}`)).join('\n');
  $('report-notice').textContent=data.warning||'';
 }
 async function refresh(){
  reset();const generation=revision;
  try{
   const config=await api('report-config',{});
   if(generation!==revision)return;
   $('report-hardware').textContent=hardwareText(config.hardware);
   if(!getProject()){$('report-select').replaceChildren();$('report-data').hidden=true;$('report-notice').textContent='저장한 VOD를 선택하면 새로 기록한 리포트를 볼 수 있습니다.';return;}
   const rows=await api('reports',parameters());
   if(generation!==revision)return;
   $('report-select').replaceChildren();
   for(const item of rows){const option=node('option',`${new Date(item.created_at).toLocaleString()} · ${item.id.slice(0,8)}`);option.value=item.id;$('report-select').append(option);}
   if(rows.some(i=>i.id===selected))$('report-select').value=selected;
   await read();
   if(!rows.length)$('report-notice').textContent='아직 리포트가 없습니다. 이번 버전에서 새로 실행한 작업부터 기록합니다.';
  }catch(e){$('report-notice').textContent=e.message;}
 }
 $('report-refresh').onclick=refresh;
 $('report-select').onchange=()=>read().catch(e=>$('report-notice').textContent=e.message);
 $('report-preview').onclick=async()=>{
  reset();const generation=revision;
  try{
   if(!selected)throw Error('실행 기록을 먼저 선택하세요');
   const result=await api('report-preview',{...parameters(),report_id:selected});
   if(generation!==revision)return;
   preview=result.payload;$('report-payload').value=JSON.stringify(preview,null,2);$('report-save').disabled=false;
   $('report-notice').textContent='VOD 번호를 포함한 이메일 첨부용 사본입니다. 내용을 확인하고 JSON을 저장하세요. 앱에서 자동 전송하지 않습니다.';
  }catch(e){if(generation===revision)$('report-notice').textContent=e.message;}
 };
 $('report-save').onclick=()=>{
  if(!preview){$('report-notice').textContent='이메일 첨부용 JSON 미리보기를 먼저 눌러주세요';return;}
  const blob=new Blob([JSON.stringify(preview,null,2)],{type:'application/json'}),url=URL.createObjectURL(blob),a=document.createElement('a');
  a.href=url;a.download=`chida-report-vod-${preview.vod_id}-${preview.report_id}.json`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
  $('report-notice').textContent='JSON 파일 다운로드를 요청했습니다. 저장된 파일을 메일에 직접 첨부하세요. 아직 이메일로 전송되지 않았습니다.';
 };
 return {refresh,clear(){reset();selected=null;$('report-data').hidden=true;}};
}
