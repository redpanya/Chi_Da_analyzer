"""Windows 배포 ZIP으로 포터블 교체 및 새 앱 시작 실패 후 복원을 확인한다."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'desktop'))
import replace_windows as updater

PREVIOUS = '0.0.1'
PROBE = '''
using System;
using System.Diagnostics;
using System.IO;
using System.Threading;

class Previous {
    static int Main(string[] args) {
        string dir = Environment.GetEnvironmentVariable("CHIDA_PREVIOUS_PROBE");
        if (args.Length == 1 && args[0] == "--running") {
            File.WriteAllText(Path.Combine(dir, "running"), "ready");
            for (int i = 0; i < 3000; i++) {
                if (File.Exists(Path.Combine(dir, "quit"))) return 0;
                Thread.Sleep(200);
            }
            return 1;
        }
        var self = Process.GetCurrentProcess();
        File.WriteAllLines(Path.Combine(dir, "restored"), new string[] {self.MainModule.FileName, self.Id.ToString()});
        return 0;
    }
}
'''


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8'))


def digest(path):
    with path.open('rb') as reader:
        return hashlib.file_digest(reader, 'sha256').hexdigest()


def await_file(path, seconds=20):
    deadline = time.monotonic() + seconds
    while not path.is_file():
        if time.monotonic() >= deadline:
            raise TimeoutError(f'기록 대기 시간 초과: {path.name}')
        time.sleep(.1)


def compile_previous(root):
    source = root / 'Previous.cs'
    source.write_text(PROBE, encoding='utf-8')
    output = root / 'previous.exe'
    subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command',
                    'Add-Type -Path $env:CHIDA_PROBE_SOURCE -OutputAssembly $env:CHIDA_PROBE_EXE '
                    '-OutputType WindowsApplication -ErrorAction Stop'],
                   env=os.environ | {'CHIDA_PROBE_SOURCE': str(source), 'CHIDA_PROBE_EXE': str(output)},
                   check=True, timeout=90)
    return output


def run_helper(binary, phase, config, env, *, expect_success):
    result = subprocess.run([binary, phase, config], env=env, timeout=300)
    if (result.returncode == 0) != expect_success:
        log = config.parent / 'error.txt'
        raise RuntimeError(f'{phase}: 종료 코드 {result.returncode}. ' +
                           (log.read_text(encoding='utf-8') if log.exists() else '오류 기록 없음'))


def scenario(base, archive, checksum, version, previous, *, fail):
    target = base / updater.APP
    work = base / ('.chida-update-' + uuid.uuid4().hex[:6])
    profile = base / 'run'
    for folder in (target, work, profile):
        folder.mkdir(parents=True)
    receipt = profile / 'desktop-profile' / 'updates'
    # 실패 예는 앱 초기화 전에 종료하므로 복원 도구가 남길 기록 경로를 준비한다.
    if fail:
        receipt.mkdir(parents=True)
    marker = base / '보관한 결과.txt'
    marker.write_text('교체 전에 저장한 자료', encoding='utf-8')
    shutil.copy2(previous, target / updater.IMAGE)
    updater.save_json(target / updater.INVENTORY, {'app': updater.APP, 'version': PREVIOUS, 'files': [updater.IMAGE]})

    helper = work / 'chida-update.exe'
    with zipfile.ZipFile(archive) as packed:
        with packed.open(updater.APP + '/resources/chida-update.exe') as src, helper.open('xb') as dst:
            shutil.copyfileobj(src, dst)

    env = os.environ | {'CHIDA_PREVIOUS_PROBE': str(base), 'CHIDA_DESKTOP_UPDATE_SMOKE': '1',
                        'CHIDA_DESKTOP_SMOKE_DIR': str(profile)}
    for variable, name in [('APPDATA', 'roaming'), ('LOCALAPPDATA', 'local'), ('USERPROFILE', 'user'),
                           ('TEMP', 'temp'), ('TMP', 'temp')]:
        directory = base / name
        directory.mkdir(exist_ok=True)
        env[variable] = str(directory)
    token = str(uuid.uuid4())
    config = work / 'plan.json'
    with subprocess.Popen([target / updater.IMAGE, '--running'], env=env) as old:
        try:
            await_file(base / 'running')
            updater.save_json(config, {'app': updater.APP, 'target': str(target), 'archive': str(archive),
                                     'version': version, 'previousVersion': PREVIOUS, 'sha256': checksum,
                                     'size': archive.stat().st_size, 'pid': old.pid, 'token': token,
                                     'updateRoot': str(receipt)})
            run_helper(helper, 'prepare', config, env, expect_success=True)
            assert read_json(work / 'step.json')['phase'] == 'prepared'
            assert old.poll() is None and digest(target / updater.IMAGE) == digest(previous)
        finally:
            (base / 'quit').touch()
        assert old.wait(timeout=15) == 0

    if fail:
        # ZIP 자체는 그대로 두고 임시 준비본에서만 Electron의 시작 실패를 유도한다.
        (work / 'new/resources/app/main.cjs').write_text("require('electron').app.exit(43);\n", encoding='utf-8')
    run_helper(helper, 'replace', config, env, expect_success=not fail)
    assert marker.read_text(encoding='utf-8') == '교체 전에 저장한 자료'
    assert read_json(receipt / 'last-result.json')['token'] == token
    phase = read_json(work / 'step.json')['phase']
    if fail:
        assert phase == 'restored' and (work / 'failed').is_dir()
        assert not (work / 'previous').exists()
        assert not (receipt / (token + '.ready')).exists()
        await_file(base / 'restored')
        process_path, pid = (base / 'restored').read_text(encoding='utf-8-sig').splitlines()
        assert Path(process_path).samefile(target / updater.IMAGE)
        updater.wait_for_parent(int(pid))
        assert digest(target / updater.IMAGE) == digest(previous)
        return {'복원': True, '이전 실행 파일 재시작': True, '기존 자료 보존': True}

    assert phase == 'complete' and not (work / 'previous').exists()
    assert not (receipt / (token + '.ready')).exists()
    await_file(profile / 'smoke.json')
    report = read_json(profile / 'smoke.json')
    assert report['version'] == version and report['platform'] == 'win32' and report['arch'] == 'x64'
    assert all(report[key] is True for key in ('pythonReady', 'ui', 'sandbox', 'isolated'))
    updater.wait_for_parent(report['pid'])
    updater.inspect_install(target, version)
    return {'교체': True, 'Electron': report['electron'], 'Python 기동': True, '기존 자료 보존': True}


def main():
    if sys.platform != 'win32':
        raise SystemExit('이 검사는 Windows x64 빌드에서 실행합니다.')
    version = read_json(ROOT / 'desktop/package.json')['version']
    archive = ROOT / 'dist/artifacts' / f'{updater.APP}-{version}-Windows-x64.zip'
    checksum = digest(archive)
    build = ROOT / 'build'
    build.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='upd-', dir=build) as temp:
        root = Path(temp)
        previous = compile_previous(root)
        result = {'버전': version, '배포 ZIP SHA-256': checksum}
        for label, fail in [('정상 교체', False), ('시작 실패 복원', True)]:
            with tempfile.TemporaryDirectory(prefix='case-', dir=root) as location:
                result[label] = scenario(Path(location), archive, checksum, version, previous, fail=fail)
        if digest(archive) != checksum:
            raise RuntimeError('검사 중 배포 ZIP이 변경됐습니다.')
    report = build / 'windows-update-smoke.json'
    report.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
