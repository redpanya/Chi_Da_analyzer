import {createCoachmark} from './coachmark.js';
import {guides,names,registration} from './tutorial-guides.js';

const pages=['library','register','prepare','analysis','voiceReview','explore','analysis','report','external','settings','jobs','split','mix'];
const prepareTasks={'download-settings':'download','audio-settings':'audio','speech-settings':'speech','voice-settings':'voices','context-settings':'context','clip-settings':'context'};
const $=id=>document.getElementById(id);
const find=step=>step&&(!step.when||step.when())&&[...document.querySelectorAll(step.selector)].find(el=>el.getClientRects().length&&!el.closest('[hidden],[inert]'));

export function createTutorial({api,openFolders,go,report,showClipStep}){
  let prefs=null,screen='',active='',stage='address',index=0,entry=0,displayed=null,first=false;
  let suspended=false,folderError='',hasLibrary=false,pending=Promise.resolve();
  let navigatingClip=false;
  const mark=createCoachmark({next:()=>advance(1),back:()=>advance(-1),library:()=>{first=false;go(0);},skip,disable:()=>setting('disable'),refresh:()=>draw()});
  const request=data=>api('tutorial',data);
  function message(text){if($('tutorial-notice'))$('tutorial-notice').textContent=text;report?.(text);}
  function save(data){
    const result=pending.then(()=>request(data));
    pending=result.then(apply,error=>message('튜토리얼 설정을 저장하지 못했습니다. '+error.message));
    return result;
  }
  function apply(value){
    prefs=value;
    if($('tutorial-enabled'))$('tutorial-enabled').checked=value.enabled;
  }
  function close(){active='';suspended=false;displayed=null;mark.hide();}
  function skip(){
    first=false;
    const el=displayed?.el;
    close();
    if(!el?.isConnected)return;
    const controls='button,a,input,select,textarea';
    (el.matches(controls)?el:el.querySelector(controls))?.focus({preventScroll:true});
  }
  function steps(){return active==='register'?registration[stage]:guides[active];}
  function draw(direction=1){
    if(!active||suspended)return;
    const list=steps();
    while(active!=='clip'&&index>=0&&index<list.length&&!find(list[index]))index+=direction;
    if(index<0||index>=list.length){close();return;}
    const step=list[index],el=find(step);
    const modal=document.querySelector('dialog:modal');
    if(!el||(modal&&!modal.contains(el))){mark.hide();displayed=null;return;}
    const shortcut=active==='welcome'&&index===0&&hasLibrary;
    const blocked=active==='welcome'&&((index===0&&!$('root').value)||(index===1&&!$('model-root').value)||(folderError!==''&&folderError===el.id));
    if(displayed?.el===el&&displayed.step===step&&displayed.blocked===blocked&&displayed.shortcut===shortcut)return;
    displayed={el,step,blocked,shortcut};
    const clip=active==='clip',later=clip?index<list.length-1:list.slice(index+1).some(find);
    const group=clip?`${names.clip}  ${index+1}/${list.length}  ${$('tab-'+step.tab).lastElementChild.textContent}`:names[active];
    mark.show(el,step,group,{first:clip?index===0:!list.slice(0,index).some(find),waiting:step.wait,blocked,shortcut,label:step.label||(later?'다음':'안내 마치기')});
  }
  function moveTo(next,direction=1){
    if(active==='clip'&&guides.clip[next]){
      navigatingClip=true;
      try{if(!showClipStep(guides.clip[next]))return;}
      finally{navigatingClip=false;}
    }
    index=next;draw(direction);
  }
  function advance(direction){
    if(active==='welcome'&&direction>0&&index===guides.welcome.length-1){
      close();go(1);return;
    }
    if(active==='register'&&stage==='started'&&direction>0){close();go(10);return;}
    moveTo(index+direction,direction);
  }
  function phase(value){
    if(stage===value)return;
    stage=value;
    if(active==='register'){index=0;displayed=null;draw();}
  }
  async function visit(key,force=false){
    const ticket=++entry;close();
    if(!key||!prefs)return;
    const available=key==='register'?registration[stage]:guides[key];
    if(!available?.some(find))return;
    const status=prefs.guides[key];
    if(!force&&status!=='replay'&&(!prefs.enabled||status==='seen'))return;
    // 첫 사용 안내를 다시 본 경우 등록 단계도 이어서 보여준다.
    if(force&&status!=='replay'&&(status==='seen'||!prefs.enabled))await save({action:'replay',guide:key});
    const result=await save({action:'visit',guide:key});
    if(ticket!==entry||!result.show)return;
    active=key;moveTo(0);
  }
  function startVisit(key,force=false){visit(key,force).catch(()=>{});}
  function view(key){
    if(!prefs||screen===key)return;
    const continueFirst=first&&screen==='settings'&&key==='register';
    first=false;screen=key;
    startVisit(key,continueFirst);
  }
  function workspace({page,use,task,registration:part,settingsTab}){
    const key=prepareTasks[task]||(use?'work':pages[page]);
    if(key==='register'){
      const phaseName=task==='queue-options'?'options':part===2?'confirm':'address';
      if(screen!==key||!['queued','preflight','started'].includes(stage)||part!==2||task)phase(phaseName);
    }
    if(active==='welcome'&&page===9&&settingsTab!==0){close();first=false;}
    view(key);
  }
  async function welcome(){
    screen='settings';first=true;openFolders();await visit('welcome');
  }
  async function setting(action,key){
    ++entry;close();first=false;
    try{
      await save({action,guide:key});
      if(action==='disable'||action==='enable')return;
      if(key==='welcome'){await welcome();return;}
      if(key===screen){await visit(key);return;}
      if(['library','register','jobs','split','settings'].includes(key)){go(pages.indexOf(key));return;}
      if(key==='mix'){location.assign($('open-mix').href);return;}
      $('tutorial-notice').textContent=names[key]+' 화면에 들어가면 안내를 다시 보여드립니다.';
    }catch{if(prefs&&$('tutorial-enabled'))$('tutorial-enabled').checked=prefs.enabled;}
  }
  function bindSettings(){
    if(!$('tutorial-choice'))return;
    for(const [key,label] of Object.entries(names))$('tutorial-choice').add(new Option(label,key));
    $('tutorial-replay').onclick=()=>setting('replay',$('tutorial-choice').value);
    $('tutorial-enabled').onchange=e=>setting(e.target.checked?'enable':'disable');
  }
  // 기존 화면의 선택, 뒤로 가기, 모달 닫기도 같은 안내 상태에 반영한다.
  document.addEventListener('change',()=>{if(active)draw();});
  if(showClipStep)document.addEventListener('studio-inspector-change',({detail})=>{
    if(active!=='clip'||navigatingClip)return;
    if(document.querySelector('.inspector').hidden){close();return;}
    const matches=step=>step.tab===detail.tab&&step.panel===detail.panel;
    if(!matches(guides.clip[index])){
      const next=guides.clip.findIndex(matches);
      if(next>=0)index=next;
    }
    draw();
  });
  document.addEventListener('toggle',event=>{
    if(event.target.tagName!=='DIALOG')return;
    if(active==='register'&&event.target.classList.contains('queue-preflight')){
      if(event.target.open)phase('preflight');
      else if(stage==='preflight')phase('queued');
    }
    if(active)draw();
  },true);
  window.addEventListener('pagehide',()=>{++entry;close();});
  window.addEventListener('pageshow',event=>{
    if(event.persisted)request({}).then(value=>{apply(value);startVisit(screen);}).catch(()=>{});
  });
  return {
    async init(value,initial,plain){
      bindSettings();apply(value);
      if(plain){await welcome().catch(()=>{});return;}
      screen='';if(typeof initial==='string')view(initial);else workspace(initial);
    },
    workspace,
    catalog(value){hasLibrary=!!value.projects.length;if(active==='welcome')draw();},
    queueEvent(kind){
      if(active!=='register')return;
      phase(kind);
    },
    picking(id,busy,failed=false){
      if(active!=='welcome')return;
      suspended=busy;
      if(busy){displayed=null;mark.hide();}
      else{folderError=failed?id:'';draw();}
    }
  };
}
