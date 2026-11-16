'use strict';
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const os = require('node:os');
const path = require('node:path');
const {createHash,generateKeyPairSync,sign} = require('node:crypto');
const {createUpdater,compareVersions,verifyManifest} = require('../desktop/updates.cjs');

const {privateKey,publicKey} = generateKeyPairSync('ed25519');
const sample=Buffer.from('검증용 디스크 이미지');
const version='1.10.0', name='ChiDaanalyzer-1.10.0-macOS-arm64.dmg';
const hash=createHash('sha256').update(sample).digest('hex');
const asset={platform:'darwin',arch:'arm64',name,size:sample.length,sha256:hash};
const release={tag_name:'v'+version,draft:false,prerelease:false,assets:[{name,size:sample.length,state:'uploaded'}]};
const manifest=Buffer.from(JSON.stringify({schema:1,app:'ChiDaanalyzer',version,assets:[asset]}));
const signature=sign(null,manifest,privateKey).toString('base64');

async function scenario(t,replace={}) {
  const root=await fs.realpath(await fs.mkdtemp(path.join(os.tmpdir(),'chida-update-check-')));
  t.after(()=>fs.rm(root,{recursive:true,force:true}));
  const key=path.join(root,'key.pem');
  await fs.writeFile(key,publicKey.export({type:'spki',format:'pem'}));
  let opened;
  const replies=new Map([['latest',JSON.stringify(release)],['update-manifest.json',manifest],['update-manifest.sig',signature],[name,sample]]);
  const updater=createUpdater({app:{getVersion:()=>'1.2.0',getPath:()=>root},platform:'darwin',arch:'arm64',
    publicKeyFile:key,dialog:{showOpenDialog:async()=>({canceled:false,filePaths:[root]})},
    getWindow:()=>({}),shell:{showItemInFolder:f=>{opened=f;}},
    fetchImpl:async(url,opts)=>{
      const filename=path.basename(url.pathname);
      const intercept=replace[filename];
      if(intercept) return intercept(url,opts);
      assert.ok(replies.has(filename));
      return new Response(replies.get(filename));
    }});
  return {updater,root,opened:()=>opened};
}

test('정식 버전 비교와 서명 파일의 플랫폼 및 자산 검증',()=>{
  assert.ok(compareVersions('1.10.0','1.2.9')>0);
  assert.equal(compareVersions('1.2.0','1.2.0'),0);
  assert.throws(()=>compareVersions('1.2.1-dev','1.2.0'));
  assert.deepEqual(verifyManifest(manifest,signature,publicKey,release,'darwin','arm64'),asset);
  assert.throws(()=>verifyManifest(manifest,signature,publicKey,release,'win32','x64'));
  assert.throws(()=>verifyManifest(manifest,signature,publicKey,{...release,prerelease:true},'darwin','arm64'));
  assert.throws(()=>verifyManifest(Buffer.concat([manifest,Buffer.from(' ')]),signature,publicKey,release,'darwin','arm64'));
});

test('DMG 수신 및 Finder 열기에서 기존 같은 이름 파일을 보존한다',async t=>{
  const {updater,root,opened}=await scenario(t);
  await fs.writeFile(path.join(root,name),'기존 파일');
  assert.equal((await updater.check()).phase,'available');
  const changes=[];
  updater.onState(s=>changes.push(s.phase));
  const saved=await updater.download();
  assert.equal(saved.phase,'downloaded');
  assert.equal(saved.received,saved.size);
  assert.notEqual(saved.fileName,name);
  assert.deepEqual(await fs.readFile(path.join(root,saved.fileName)),sample);
  assert.equal(await fs.readFile(path.join(root,name),'utf8'),'기존 파일');
  assert.ok(changes.includes('downloading'));
  updater.reveal();
  assert.equal(opened(),path.join(root,saved.fileName));
  assert.equal((await updater.apply()).phase,'downloaded');
});

test('수신 중 변경, 크기 초과, 외부 리다이렉트는 결과 파일을 만들지 않는다',async t=>{
  const invalid=[new Response(Buffer.alloc(sample.length)),new Response(Buffer.alloc(sample.length+1)),
    new Response(null,{status:302,headers:{location:'https://example.org/file'}})];
  for(const response of invalid) {
    const {updater,root}=await scenario(t,{[name]:()=>response});
    assert.equal((await updater.check()).phase,'available');
    assert.equal((await updater.download()).phase,'error');
    assert.deepEqual(await fs.readdir(root),['key.pem']);
  }
});

test('기존 정식 버전에는 업데이트가 표시되지 않는다',async t=>{
  const {updater}=await scenario(t,{latest:()=>new Response(JSON.stringify({...release,tag_name:'v1.1.0'}))});
  assert.equal((await updater.check()).phase,'current');
  assert.equal((await updater.download()).phase,'current');
});

test('사용자가 수신을 취소하면 임시 파일만 지워지고 다시 받을 수 있다',async t=>{
  let requestStarted;
  const entered=new Promise(resolve=>{requestStarted=resolve;});
  const {updater,root}=await scenario(t,{[name]:(_url,{signal})=>{
    requestStarted();
    return new Promise((_resolve,reject)=>signal.addEventListener('abort',()=>reject(signal.reason),{once:true}));
  }});
  await updater.check();
  const pending=updater.download();
  await entered;updater.cancel();
  assert.equal((await pending).phase,'available');
  assert.deepEqual(await fs.readdir(root),['key.pem']);
});
