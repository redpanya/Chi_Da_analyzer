'use strict';
const { app, BrowserWindow, Menu, dialog, ipcMain, session, shell } = require('electron');
const fs = require('node:fs');
const fsp = fs.promises;
const os = require('node:os');
const path = require('node:path');
const { spawn } = require('node:child_process');
const { randomBytes } = require('node:crypto');
const { setTimeout: delay } = require('node:timers/promises');
const { readyAddress, trustedPage, handoff, inside } = require('./policy.cjs');
const { createUpdater, confirmStartup } = require('./updates.cjs');

const win32 = process.platform === 'win32';
const project = path.resolve(__dirname, '..');
const updateSmoke = process.env.CHIDA_DESKTOP_UPDATE_SMOKE === '1' && /^[\da-f]{8}(?:-[\da-f]{4}){3}-[\da-f]{12}$/.test(process.env.CHIDA_UPDATE_ATTEMPT || '');
const smoke = updateSmoke || process.argv.includes('--desktop-smoke');
const control = randomBytes(32).toString('hex');
let smokeDir, win, child, exited, temp, base, updates;
let closing = false, checkingClose = false, exitCode = 0, quitting;
app.setName('치(지직) 다(시보기) 분석기');
if (smoke) {
  smokeDir = process.env.CHIDA_DESKTOP_SMOKE_DIR;
  if (!smokeDir || !path.isAbsolute(smokeDir) || !fs.lstatSync(smokeDir).isDirectory() || fs.readdirSync(smokeDir).length) {
    throw Error('검증 전용 빈 폴더의 절대 경로를 지정하세요.');
  }
  smokeDir = fs.realpathSync(smokeDir);
}
const support = win32 ? path.join(process.env.LOCALAPPDATA || app.getPath('appData'), 'ChiDaAnalyzer') :
  path.join(app.getPath('appData'), '치지직 보관함');
const profile = path.join(smokeDir || support, 'desktop-profile');
fs.mkdirSync(profile, {recursive:true});
app.setPath('userData', profile);
app.setPath('sessionData', profile);
if (win32) app.setAppUserModelId('redpanya.ChiDaAnalyzer');

async function startBackend() {
  temp = await fsp.mkdtemp(path.join(os.tmpdir(), 'chida-desktop-'));
  const ready = path.join(temp, 'ready.json');
  const args = ['--no-open', '--ready-file', ready, '--stop-file', path.join(temp, 'stop'), '--parent-pid', String(process.pid)];
  const env = {...process.env};
  env.CHIDA_DESKTOP_CONTROL = control;
  delete env.PYTHONHOME;
  delete env.PYTHONPATH;
  if (smoke) {
    Object.assign(env, {HOME:smokeDir, LOCALAPPDATA:smokeDir, USERPROFILE:smokeDir});
    args.push('--library', path.join(smokeDir, 'library'));
  }
  const backend = path.join(process.resourcesPath, 'backend', 'archive-backend' + (win32 ? '.exe' : ''));
  const devPython = path.join(project, '.venv', win32 ? 'Scripts/python.exe' : 'bin/python');
  if (!app.isPackaged) args.unshift(path.join(project, 'app.py'));
  child = spawn(app.isPackaged ? backend : (fs.existsSync(devPython) ? devPython : (win32 ? 'python' : 'python3')), args,
    {env, cwd:app.isPackaged ? path.dirname(backend) : project, stdio:'ignore', windowsHide:true});
  let ended = false;
  exited = new Promise(resolve => {
    const end = () => { ended = true; resolve(); };
    child.once('error', end); child.once('exit', end);
  });
  const endTime = Date.now() + 60000;
  while (Date.now() < endTime && !ended && !closing) {
    try { base = readyAddress(JSON.parse(await fsp.readFile(ready, 'utf8')), child.pid); return; }
    catch (e) { if (e.code !== 'ENOENT') throw e; }
    await delay(80);
  }
  throw Error(ended ? 'Python 처리기가 시작되지 않았습니다. 배포 폴더의 처리 도구를 확인하세요.' : 'Python 처리기의 응답을 기다리는 시간이 초과되었습니다.');
}
async function activity() {
  const response = await fetch(new URL('api/desktop-activity', base), {signal:AbortSignal.timeout(5000),redirect:'error'});
  if (!response.ok) throw Error('작업 상태를 확인하지 못했습니다.');
  const data = await response.json();
  if (typeof data.busy !== 'boolean' || ![data.library,data.models].every(v => typeof v === 'string' && path.isAbsolute(v))) {
    throw Error('처리기가 올바른 작업 상태를 반환하지 않았습니다.');
  }
  return data;
}
async function verifySettings(wc) {
  // 실제 화면과 같은 버튼을 눌러 확인한다. 업데이트 조회, 파일 열기 및 전송은 실행하지 않는다.
  return wc.executeJavaScript(`(async () => {
    const find = id => document.getElementById(id);
    const until = async getter => {
      const end = Date.now() + 12000;
      while (Date.now() < end) {
        const value = getter();
        if (value) return value;
        await new Promise(resolve => setTimeout(resolve, 100));
      }
      throw Error('설정 화면 준비 시간 초과');
    };
    const lens = await until(() => document.querySelector('.brand-mark .brand-start-fill'));
    const greenLens = getComputedStyle(lens).fill === 'rgb(0, 255, 163)';
    (await until(() => document.querySelector('.step-primary #step9'))).click();
    (await until(() => document.querySelector('.task-rail button[title="앱 업데이트"]'))).click();
    await until(() => find('desktop-update-version').textContent.includes('현재 버전'));
    const visible = id => !!find(id)?.getClientRects().length;
    return {greenLens,settings:visible('desktop-update'),notices:visible('desktop-licenses'),
      independent:visible('app-info') && find('app-info').innerText.includes('네이버 및 치지직과 제휴 관계가 없습니다'),
      updateGuide:find('desktop-update-guide').textContent,versionLabel:find('desktop-update-version').textContent,
      checkButton:visible('desktop-update-check')};
  })()`);
}
async function prepareToQuit() {
  if (closing) throw Error('실행기를 종료하는 중입니다.');
  const data = await activity();
  if (data.busy) throw Error('진행 중이거나 대기 중인 작업이 있습니다. 작업이 끝난 뒤 업데이트하세요.');
  try {
    await guard('freeze');
    const current = await activity();
    const install = await fsp.realpath(path.dirname(process.execPath));
    if (win32) {
      for (const file of [current.library, current.models, profile]) {
        const resolved = await fsp.realpath(file).catch(error => { if (error.code === 'ENOENT') return file; throw error; });
        if (inside(install, resolved)) throw Error('프로그램 폴더 안에 보관함, 모델 또는 사용자 설정이 있습니다. 자료를 프로그램 폴더 밖으로 옮긴 뒤 업데이트하세요.');
      }
    }
  } catch (e) {
    await guard('thaw').catch(()=>{});
    throw e;
  }
}
async function guard(action) {
  const response = await fetch(new URL('api/desktop-'+action, base), {method:'POST',
    headers:{'X-Chida-Control':control},signal:AbortSignal.timeout(5000),redirect:'error'});
  if (!response.ok) throw Error('처리 중인 작업이 있습니다. 작업 완료 후 다시 시도하세요.');
}
function stopAndQuit() {
  if (quitting) return quitting;
  closing = true;
  quitting = (async () => {
    try {
      updates?.dispose();
      if (child && exited) {
        await fsp.writeFile(path.join(temp, 'stop'), '');
        await exited; // 저장과 외부 도구 정리가 끝날 때까지 강제 종료하지 않는다.
      }
      if (temp) await fsp.rm(temp, {recursive:true,force:true});
    } catch {
      exitCode = 1;
    } finally {
      app.exit(exitCode);
    }
  })();
  return quitting;
}
function quitForUpdate() {
  // 적용은 편집 초안이 없는 기본 창의 설정에서만 요청할 수 있다.
  closing = true;
  win?.hide();
  void stopAndQuit();
}
function foreground() {
  if (win && !win.isDestroyed()) { if (win.isMinimized()) win.restore(); win.show(); win.focus(); }
}
async function interceptClose(event) {
  if (closing || !base) return;
  event.preventDefault();
  if (checkingClose) return;
  checkingClose = true;
  try {
    let busy = true;
    try { busy = (await activity()).busy; } catch {}
    if (busy) {
      const {response} = await dialog.showMessageBox(win, {
        type:'question', message:'작업을 정리하고 종료할까요?', detail:'실행 중인 작업이나 상태를 확인하지 못한 작업이 있을 수 있습니다. 완료한 자료는 보존됩니다.',
        buttons:['계속 실행', '작업 정리 후 종료'], defaultId:0, cancelId:0
      });
      if (response !== 1) return;
    }
    closing = true;
    win.close();
  } finally { checkingClose = false; }
}
async function start() {
  await startBackend();
  if (closing) return;
  Menu.setApplicationMenu(win32 ? null : Menu.buildFromTemplate([{role:'appMenu'}, {role:'editMenu'}, {role:'windowMenu'}]));
  win = new BrowserWindow({width:1280,height:840,minWidth:660,minHeight:480,show:false,backgroundColor:'#0e0f10',
    webPreferences:{preload:path.join(__dirname,'preload.cjs'),contextIsolation:true,sandbox:true,nodeIntegration:false,
      webviewTag:false,webSecurity:true,devTools:!app.isPackaged}});
  const wc = win.webContents;
  const permitted = (wcArg, permission, origin) => wcArg === wc &&
    permission === 'clipboard-sanitized-write' && (origin === base.origin || origin === base.origin + '/') && trustedPage(base,wc.getURL());
  session.defaultSession.setPermissionCheckHandler(permitted);
  session.defaultSession.setPermissionRequestHandler((contents,permission,reply) => reply(permitted(contents,permission,base.origin)));
  const openLink = url => {
    if (!trustedPage(base, wc.getURL())) return;
    const kind = handoff(base, url);
    if (kind === 'download') wc.downloadURL(url);
    if (kind === 'external') void shell.openExternal(url).catch(() => {});
  };
  wc.setWindowOpenHandler(({url}) => {
    openLink(url);
    return {action:'deny'};
  });
  wc.on('will-redirect',event => { if (!trustedPage(base,event.url)) event.preventDefault(); });
  wc.on('will-frame-navigate',(event) => {
    if (!event.isMainFrame || !trustedPage(base,event.url)) {
      event.preventDefault();
      if (event.isMainFrame) openLink(event.url);
    }
  });
  wc.on('will-attach-webview', e => e.preventDefault());
  wc.on('will-prevent-unload', e => {
    const choice = dialog.showMessageBoxSync(win, {type:'question',message:'저장하지 않은 변경 사항이 있습니다.',
      buttons:['계속 편집', '변경 사항 버리기'],defaultId:0,cancelId:0});
    if (choice === 1) e.preventDefault(); else closing = false;
  });
  win.on('close', interceptClose);
  win.on('closed', () => { win = null; void stopAndQuit(); });
  updates = createUpdater({app,dialog,shell,getWindow:() => win,prepareToQuit,quitForUpdate,resumeAfterFailedUpdate:()=>guard('thaw')});
  const actions = {state:()=>updates.status(),check:()=>updates.check(),download:()=>updates.download(),cancel:()=>updates.cancel(),
    apply:()=>updates.apply(),reveal:()=>updates.reveal(),notices:async()=>{
      const err = await shell.openPath(app.isPackaged ? path.join(process.resourcesPath,'THIRD-PARTY-NOTICES') : path.join(project,'THIRD-PARTY-NOTICES.md'));
      if (err) throw Error('라이선스 고지를 열지 못했습니다.');
    }};
  for (const [name,fn] of Object.entries(actions)) {
    ipcMain.handle('chida:'+name, async (e,...args) => {
      if (args.length || closing || e.sender !== wc || !e.senderFrame || e.senderFrame !== wc.mainFrame || !trustedPage(base,e.senderFrame.url)) {
        throw Error('앱 화면에서만 사용할 수 있습니다.');
      }
      if (name !== 'state' && (new URL(e.senderFrame.url).pathname !== base.pathname ||
          !await wc.executeJavaScript("Boolean(document.getElementById('desktop-update')?.getClientRects().length)"))) {
        throw Error('앱 설정 화면에서 실행하세요.');
      }
      return fn();
    });
  }
  exited.then(() => {
    if (closing) return;
    exitCode = 1;
    if (!smoke) dialog.showErrorBox('처리기 종료', 'Python 처리기가 예기치 않게 종료되었습니다. 앱을 다시 열어 주세요.');
    void stopAndQuit();
  });
  await win.loadURL(base.href);
  if (!trustedPage(base,wc.getURL())) throw Error('시작 화면을 열지 못했습니다.');
  const ready = await wc.executeJavaScript("Promise.resolve(window.chidaDesktop.state()).then(s => ({version:s.currentVersion,phase:s.phase,ui:!!document.getElementById('library-cards'),sandbox:typeof window.require==='undefined'}))");
  if (!ready.ui || !ready.sandbox || ready.version !== app.getVersion()) throw Error('첫 화면 또는 설정 연결을 확인하지 못했습니다.');
  if (smoke) {
    const data = await activity();
    if (!inside(smokeDir,data.library) || !inside(smokeDir,data.models) || data.busy) throw Error('격리 보관함을 확인하지 못했습니다.');
    const view = await verifySettings(wc);
    if (!view.greenLens || !view.settings || !view.notices || !view.independent || !view.checkButton ||
        !view.versionLabel.includes(ready.version) || !view.updateGuide.includes(win32 ? '교체 후 재실행' : 'DMG')) {
      throw Error('첫 화면 표시 또는 앱 설정의 업데이트 안내를 확인하지 못했습니다.');
    }
    await fsp.writeFile(path.join(smokeDir,'smoke.json'),JSON.stringify({...ready,...view,pid:process.pid,platform:process.platform,arch:process.arch,
      electron:process.versions.electron,pythonReady:true,isolated:true},null,2),{flag:'wx'});
    if (updateSmoke) await confirmStartup(app);
    await stopAndQuit();
  } else {
    await confirmStartup(app);
    win.show();
  }
}
if (app.requestSingleInstanceLock()) {
  app.on('second-instance',foreground);
  app.on('activate',foreground);
  app.on('before-quit',e => {
    if (quitting) return;
    e.preventDefault();
    if (win && !win.isDestroyed()) win.close(); else void stopAndQuit();
  });
  app.on('window-all-closed',() => { void stopAndQuit(); });
  app.whenReady().then(start).catch(async e => {
    if (closing) return;
    exitCode = 1;
    if (smoke) await fsp.writeFile(path.join(smokeDir, 'failure.txt'), String(e.message), {flag:'wx'}).catch(()=>{});
    else dialog.showErrorBox('앱 실행 오류', e.message);
    await stopAndQuit();
  });
} else app.quit();
