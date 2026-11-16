'use strict';
const fs = require('node:fs');
const path = require('node:path');
const {createHash, createPublicKey, createPrivateKey, sign, verify} = require('node:crypto');
const project = require('../../desktop/package.json');

async function main() {
  const [dir, flag, keyPath] = process.argv.slice(2);
  if (!dir || flag !== '--key' || !keyPath) throw Error('사용법: node sign_update.cjs 배포폴더 --key 개인키파일');
  const key = createPrivateKey(fs.readFileSync(keyPath));
  const trusted = createPublicKey(fs.readFileSync(path.join(__dirname, '../../desktop/release-public.pem')));
  if (key.asymmetricKeyType !== 'ed25519' || !createPublicKey(key).equals(trusted))
    throw Error('앱에 등록한 배포 공개키와 일치하지 않습니다.');
  const assets = [];
  for (const [platform, arch, suffix] of [['darwin','arm64','macOS-arm64.dmg'], ['win32','x64','Windows-x64.zip']]) {
    const name = 'ChiDaanalyzer-' + project.version + '-' + suffix;
    const file = path.join(dir, name);
    const hash = createHash('sha256');
    let size = 0;
    for await (const bytes of fs.createReadStream(file)) {
      hash.update(bytes);
      size += bytes.length;
    }
    if (!size) throw Error('배포 파일이 비어 있습니다.');
    assets.push({platform, arch, name, size, sha256:hash.digest('hex')});
  }
  const manifest = Buffer.from(JSON.stringify({schema:1, app:'ChiDaanalyzer', version:project.version, assets}, null, 2) + '\n');
  const signature = sign(null, manifest, key);
  if (!verify(null, manifest, trusted, signature)) throw Error('생성된 서명을 검증하지 못했습니다.');
  fs.writeFileSync(path.join(dir, 'update-manifest.json'), manifest);
  fs.writeFileSync(path.join(dir, 'update-manifest.sig'), signature.toString('base64') + '\n');
}
main().catch(err => { console.error(err.message); process.exitCode = 1; });
