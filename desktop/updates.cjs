'use strict';

const fs = require('node:fs/promises');
const {constants} = require('node:fs');
const {pipeline} = require('node:stream/promises');
const path = require('node:path');
const {createHash, randomUUID, verify} = require('node:crypto');
const {spawn} = require('node:child_process');
const {EventEmitter} = require('node:events');

const repository = 'redpanya/Chi_Da_analyzer';
const latest = 'https://api.github.com/repos/' + repository + '/releases/latest';
const releaseHosts = new Set(['api.github.com', 'github.com', 'release-assets.githubusercontent.com',
  'objects.githubusercontent.com', 'github-releases.githubusercontent.com']);
const versionPattern = /^(0|[1-9]\d{0,5})\.(0|[1-9]\d{0,5})\.(0|[1-9]\d{0,5})$/;
const limit = 8 * 1024 ** 3;

function versionParts(value) {
  if (typeof value !== 'string' || !versionPattern.test(value)) throw Error('정식 버전 번호를 확인할 수 없습니다.');
  return value.split('.').map(Number);
}
function compareVersions(left, right) {
  const a = versionParts(left), b = versionParts(right);
  return a[0] - b[0] || a[1] - b[1] || a[2] - b[2];
}
function assetName(version, platform) {
  return 'ChiDaanalyzer-' + version + (platform === 'darwin' ? '-macOS-arm64.dmg' : '-Windows-x64.zip');
}
function verifyManifest(bytes, signatureText, publicKey, release, platform, arch) {
  const encoded = signatureText.trim();
  if (!/^[A-Za-z0-9+/]{86}==$/.test(encoded) || !verify(null, bytes, publicKey, Buffer.from(encoded,'base64')))
    throw Error('업데이트 발행자 서명을 확인하지 못했습니다.');
  const doc = JSON.parse(bytes.toString('utf8'));
  versionParts(doc.version);
  if (doc.schema !== 1 || doc.app !== 'ChiDaanalyzer' || release.tag_name !== 'v' + doc.version ||
      release.draft !== false || release.prerelease !== false || !Array.isArray(doc.assets))
    throw Error('호환되는 정식 업데이트 목록을 확인할 수 없습니다.');
  const candidates = doc.assets.filter(item => item && item.platform === platform && item.arch === arch);
  const asset = candidates[0];
  if (candidates.length !== 1 || asset.name !== assetName(doc.version, platform) ||
      !Number.isSafeInteger(asset.size) || asset.size <= 0 || asset.size > limit ||
      !/^[a-f0-9]{64}$/.test(asset.sha256))
    throw Error('이 운영체제와 CPU에 맞는 업데이트 파일이 없습니다.');
  const published = release.assets.filter(item => item.name === asset.name && item.state === 'uploaded');
  if (published.length !== 1 || published[0].size !== asset.size ||
      (published[0].digest && published[0].digest !== 'sha256:' + asset.sha256))
    throw Error('게시된 파일과 서명된 배포 정보가 일치하지 않습니다.');
  return asset;
}

async function request(url, signal, fetchImpl) {
  for (let hops = 0; hops < 6; hops++) {
    const target = new URL(url);
    if (target.protocol !== 'https:' || !releaseHosts.has(target.hostname) || target.port ||
        target.username || target.password) throw Error('공식 배포 주소를 확인하지 못했습니다.');
    const response = await fetchImpl(target, {redirect:'manual',signal,
      headers:{'User-Agent':'ChiDaanalyzer-desktop','Accept-Encoding':'identity'}});
    if ([301,302,303,307,308].includes(response.status)) {
      await response.body?.cancel();
      const next = response.headers.get('location');
      if (!next) throw Error('배포 파일의 이동 주소가 없습니다.');
      url = new URL(next, target).href;
      continue;
    }
    if (!response.ok || !response.body) {
      await response.body?.cancel();
      throw Error('GitHub 배포 파일을 받을 수 없습니다 (' + response.status + ').');
    }
    return response;
  }
  throw Error('배포 주소가 너무 많이 변경됐습니다.');
}

async function readBytes(url, max, signal, fetchImpl) {
  const response = await request(url, signal, fetchImpl);
  const chunks = [];
  let length = 0;
  for await (const chunk of response.body) {
    length += chunk.length;
    if (length > max) throw Error('업데이트 정보 크기가 허용 범위를 넘습니다.');
    chunks.push(chunk);
  }
  return Buffer.concat(chunks,length);
}

async function saveVerified(response, part, asset, signal, progress) {
  let size = 0;
  const hash = createHash('sha256');
  const file = await fs.open(part,'wx',0o600);
  try {
    await pipeline(response.body, async function* (source) {
      for await (const chunk of source) {
        size += chunk.length;
        if (size > asset.size) throw Error('다운로드가 게시된 크기를 넘었습니다.');
        hash.update(chunk);
        progress(size);
        yield chunk;
      }
    }, file.createWriteStream(), {signal});
  } finally { await file.close(); }
  if (size !== asset.size || hash.digest('hex') !== asset.sha256)
    throw Error('파일 크기 또는 SHA-256이 일치하지 않습니다. 다시 다운로드하세요.');
}

async function publishDownload(part, folder, name) {
  const {name:stem,ext} = path.parse(name);
  for (let n = 0; n < 1000; n++) {
    const file = path.join(folder, n ? stem + ' (' + n + ')' + ext : name);
    try {
      try { await fs.link(part,file); }
      catch (err) {
        if (!['EPERM','EOPNOTSUPP','ENOTSUP','ENOSYS','EXDEV'].includes(err.code)) throw err;
        await fs.copyFile(part,file,constants.COPYFILE_EXCL);
      }
      return file;
    } catch (err) { if (err.code !== 'EEXIST') throw err; }
  }
  throw Error('같은 이름의 파일이 많습니다. 다른 폴더를 선택하세요.');
}

function contained(parent, child) {
  const rel = path.relative(parent,child);
  return !rel || (!path.isAbsolute(rel) && rel !== '..' && !rel.startsWith('..' + path.sep));
}

function runHelper(exe, args) {
  return new Promise((resolve,reject) => {
    const child = spawn(exe,args,{cwd:path.dirname(exe),windowsHide:true,stdio:'ignore'});
    child.once('error',reject);
    child.once('exit',code => code === 0 ? resolve() : reject(Error('Windows 업데이트 준비에 실패했습니다.')));
  });
}

function createUpdater({app, dialog, shell, getWindow, prepareToQuit, quitForUpdate, resumeAfterFailedUpdate,
    platform=process.platform, arch=process.arch, fetchImpl=globalThis.fetch, publicKeyFile=path.join(__dirname,'release-public.pem')}) {
  const currentVersion = app.getVersion(), events = new EventEmitter();
  const updateRoot = path.join(app.getPath('userData'),'updates');
  let state = {phase:'idle',currentVersion,platform,version:'',received:0,size:0,message:'',fileName:'',checkedAt:''};
  let selected=null, downloaded='', operation=null, closed=false;
  function snapshot() {return {...state};}
  function set(values) {state = {...state,...values}; events.emit('state',snapshot()); return snapshot();}
  const errorText = err => String(err?.message || err).slice(0,450);
  if (platform === 'win32') {
    // 이전 기동 확인 후 남은 보조 실행 파일만 다음 실행에서 정리한다.
    void fs.readFile(path.join(updateRoot,'last-result.json'),'utf8').then(async text=>{
      const last = JSON.parse(text);
      if (state.phase === 'idle' && !closed) set({message:String(last.message || '').slice(0,450)});
      const folder = last.folder, target = await fs.realpath(path.dirname(app.getPath('exe')));
      if (typeof folder !== 'string' || !path.isAbsolute(folder) ||
          !/^\.chida-update-[a-zA-Z0-9]{6}$/.test(path.basename(folder))) return;
      if ((await fs.lstat(folder)).isSymbolicLink() ||
          path.relative(path.join(path.dirname(target),path.basename(folder)),await fs.realpath(folder))) return;
      const plan = JSON.parse(await fs.readFile(path.join(folder,'plan.json'),'utf8'));
      const step = JSON.parse(await fs.readFile(path.join(folder,'step.json'),'utf8'));
      if (step.phase !== 'complete' || plan.token !== last.token || path.relative(await fs.realpath(plan.target),target)) return;
      const names = await fs.readdir(folder);
      if (names.some(n=>!['plan.json','step.json','chida-update.exe'].includes(n))) return;
      for (const name of ['chida-update.exe','step.json','plan.json']) await fs.unlink(path.join(folder,name));
      await fs.rmdir(folder);
      await fs.unlink(path.join(updateRoot,'last-result.json'));
    }).catch(()=>{});
  }
  async function check() {
    if (operation || closed) return snapshot();
    operation = new AbortController();
    const signal = AbortSignal.any([operation.signal,AbortSignal.timeout(30000)]);
    set({phase:'checking',checkedAt:new Date().toISOString(),message:'',received:0,size:0,fileName:'',version:''});
    selected = null; downloaded = '';
    try {
      if (!((platform === 'darwin' && arch === 'arm64') || (platform === 'win32' && arch === 'x64')))
        throw Error('이 운영체제와 CPU의 공식 배포 파일이 없습니다.');
      const release = JSON.parse((await readBytes(latest,2*1024*1024,signal,fetchImpl)).toString('utf8'));
      if (release.draft !== false || release.prerelease !== false || !/^v/.test(release.tag_name))
        throw Error('공개 정식 릴리스를 확인하지 못했습니다.');
      const version = release.tag_name.slice(1);
      if (compareVersions(version,currentVersion) <= 0) return set({phase:'current',message:'사용 가능한 새 버전이 없습니다.'});
      const base = 'https://github.com/' + repository + '/releases/download/v' + version + '/';
      const [bytes,sig,key] = await Promise.all([
        readBytes(base+'update-manifest.json',256*1024,signal,fetchImpl),
        readBytes(base+'update-manifest.sig',256,signal,fetchImpl),fs.readFile(publicKeyFile)
      ]);
      const asset = verifyManifest(bytes,sig.toString('ascii'),key,release,platform,arch);
      selected = {...asset,url:base+asset.name};
      return set({phase:'available',version,size:asset.size,fileName:asset.name,message:'새 버전을 다운로드할 수 있습니다.'});
    } catch (err) {return set({phase:'error',message:errorText(err)});}
    finally { operation?.abort(); operation=null; }
  }

  async function download() {
    if (!selected || operation || closed || !['available','error'].includes(state.phase)) return snapshot();
    const ctrl = new AbortController();
    operation = ctrl;
    let part;
    try {
      let folder = path.join(updateRoot,'downloads');
      if (platform === 'darwin') {
        const choice = await dialog.showOpenDialog(getWindow(),{title:'DMG를 저장할 폴더 선택',properties:['openDirectory','createDirectory']});
        if (choice.canceled || !choice.filePaths[0] || ctrl.signal.aborted) return snapshot();
        folder = await fs.realpath(choice.filePaths[0]);
        if (folder.split(path.sep).some(p=>p.toLowerCase().endsWith('.app')))
          throw Error('앱 내부가 아닌 저장 폴더를 선택하세요.');
      } else {await fs.mkdir(folder,{recursive:true});}
      set({phase:'downloading',received:0,message:'업데이트를 다운로드하고 있습니다.'});
      part = path.join(folder,'.chida-' + randomUUID() + '.part');
      const response = await request(selected.url,ctrl.signal,fetchImpl);
      let last = 0;
      await saveVerified(response,part,selected,ctrl.signal,n=>{
        if (Date.now()-last >= 180 || n === selected.size) {last=Date.now();set({received:n});}
      });
      ctrl.signal.throwIfAborted();
      downloaded = await publishDownload(part,folder,selected.name);
      return set({phase:platform==='darwin'?'downloaded':'ready',fileName:path.basename(downloaded),
        message:platform==='darwin'?'DMG를 저장했습니다. 앱을 종료하고 Finder에서 DMG를 열어 앱을 교체하세요.':'파일 검증이 끝났습니다. 재실행하여 업데이트할 수 있습니다.'});
    } catch(err) {
      return set({phase:ctrl.signal.aborted?'available':'error',received:0,message:ctrl.signal.aborted?'다운로드를 취소했습니다.':errorText(err)});
    } finally {
      if (part) await fs.rm(part,{force:true}).catch(()=>{});
      operation=null;
    }
  }

  async function apply() {
    if (platform !== 'win32' || state.phase !== 'ready' || !downloaded || operation || closed) return snapshot();
    operation = new AbortController();
    let work, launched=false, preparedToQuit=false;
    try {
      const target = await fs.realpath(path.dirname(app.getPath('exe')));
      if (!app.isPackaged || path.basename(target) === '' || contained(target,await fs.realpath(updateRoot)))
        throw Error('전용 포터블 앱 폴더에서만 적용할 수 있습니다.');
      const token = randomUUID();
      work = await fs.mkdtemp(path.join(path.dirname(target),'.chida-update-'));
      const helper = path.join(work,'chida-update.exe'), config=path.join(work,'plan.json');
      await fs.copyFile(path.join(process.resourcesPath,'chida-update.exe'),helper,constants.COPYFILE_EXCL);
      await fs.writeFile(config,JSON.stringify({app:'ChiDaanalyzer',target,archive:downloaded,version:state.version,
        previousVersion:currentVersion,sha256:selected.sha256,size:selected.size,pid:process.pid,token,updateRoot}),{flag:'wx',mode:0o600});
      set({phase:'applying',message:'프로그램 폴더와 새 버전을 검사하고 있습니다.'});
      try {await runHelper(helper,['prepare',config]);}
      catch(err) {
        const result = await fs.readFile(path.join(work,'error.txt'),'utf8').catch(()=>'');
        throw Error(result || err.message);
      }
      await prepareToQuit();
      preparedToQuit=true;
      const child = spawn(helper,['replace',config],{cwd:work,detached:true,windowsHide:true,stdio:'ignore'});
      await new Promise((resolve,reject)=>{child.once('error',reject);child.once('spawn',resolve);});
      launched=true;child.unref();
      await quitForUpdate();
      return snapshot();
    } catch(err) {
      if (launched) await fs.writeFile(path.join(work,'cancel'),'1',{flag:'wx'}).catch(()=>{});
      if (preparedToQuit && resumeAfterFailedUpdate) {
        try {await resumeAfterFailedUpdate();}
        catch(resumeError) {return set({phase:'ready',message:errorText(err) + ' / ' + errorText(resumeError)});}
      }
      return set({phase:'ready',message:errorText(err)});
    }
    finally {
      if (work && !launched) await fs.rm(work,{recursive:true,force:true}).catch(()=>{});
      operation=null;
    }
  }

  return {state:snapshot,status:snapshot,check,download,apply,
    cancel(){if(state.phase==='downloading')operation?.abort();return snapshot();},
    reveal(){if(state.phase==='downloaded' && downloaded)shell.showItemInFolder(downloaded);return snapshot();},
    onState(fn){events.on('state',fn);return ()=>events.off('state',fn);},
    dispose(){closed=true;operation?.abort();events.removeAllListeners();}
  };
}

async function confirmStartup(app) {
  const token = process.env.CHIDA_UPDATE_ATTEMPT;
  if (!token || !/^[\da-f]{8}(?:-[\da-f]{4}){3}-[\da-f]{12}$/.test(token) || process.env.CHIDA_UPDATE_VERSION !== app.getVersion()) return;
  const file = path.join(app.getPath('userData'),'updates',token+'.ready');
  await fs.mkdir(path.dirname(file),{recursive:true});
  await fs.writeFile(file,app.getVersion(),{flag:'wx',mode:0o600});
  delete process.env.CHIDA_UPDATE_ATTEMPT;
  delete process.env.CHIDA_UPDATE_VERSION;
}

module.exports={createUpdater,confirmStartup,verifyManifest,compareVersions};
