"""제작한 ZIP을 실제 앱 설치기로 설치한다. 모델·HF 인증·추론은 사용하지 않는다."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
from unittest.mock import patch
import wave

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from archive import runtime, speaker_tools as tools, speaker_tools_install as installer
from archive.storage import ProjectLock, read_json, save_json


def digest(file):
    with file.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def check(backend, output):
    platform = tools.platform_id()
    archive = output/f'chida-{backend}-{platform}.zip'
    asset = {'url': 'https://github.com/local-build-check', 'size': archive.stat().st_size,
             'sha256': digest(archive)}
    stop = threading.Event()
    with tempfile.TemporaryDirectory(prefix='화자 도구 설치 ') as temp:
        work = Path(temp)
        with patch.object(runtime, 'SUPPORT', work/'지원'), patch.object(runtime, 'MODEL_ROOT', work/'모델'):
            root = tools.home(backend)
            previous = root/'versions'/('1'*32)
            previous.mkdir(parents=True)
            old = previous/tools.entry_name(backend)
            old.write_bytes(b'previous-install-sentinel')
            save_json(previous/'tool.json', {'backend': backend, 'protocol': tools.PROTOCOL,
                      'platform': platform, 'entry': tools.entry_name(backend)})
            save_json(root/'active.json', {'version': previous.name})
            active_before = (root/'active.json').read_bytes()
            sentinels = [work/'모델/기존 모델.bin', work/'보관함/기존 결과.json']
            for file in sentinels:
                file.parent.mkdir(parents=True, exist_ok=True)
                file.write_bytes(b'preserve-existing-data')
            def update(**value):
                if value['message'] != '실행 도구 설치 완료 · 기존 모델·분석 결과 보존':
                    assert (root/'active.json').read_bytes() == active_before, '검사 전에 활성 버전이 바뀌었습니다'
            with patch.object(installer, 'release_asset', return_value=asset), \
                    patch.object(installer, 'open_url', side_effect=lambda _: archive.open('rb')), \
                    ProjectLock(work/'검사 작업') as lock:
                installer.install(backend, stop, lock, update)
                installed = tools.managed(backend)
                assert installed and installed.is_file() and installed.parent != previous
                assert old.read_bytes() == b'previous-install-sentinel'
                assert all(file.read_bytes() == b'preserve-existing-data' for file in sentinels)
                tools.check([str(installed), '--speaker-tool-check'], work/'restart.log', stop, lock, backend)
                active_after = (root/'active.json').read_bytes()
                with patch.object(installer, 'release_asset', return_value=asset | {'sha256': '0'*64}):
                    try:
                        installer.install(backend, stop, lock, lambda **_: None)
                    except ValueError as error:
                        assert 'SHA-256' in str(error)
                    else:
                        raise AssertionError('손상 파일의 설치가 허용됐습니다')
                assert (root/'active.json').read_bytes() == active_after
            assert not list(root.glob('.install-*'))
            # 8kHz 합성 WAV는 모델을 로드하기 전에 거부되어야 한다.
            # sherpa는 VAD 경로, pyannote는 diarize 경로의 실제 SoundFile 입력을 사용한다.
            audio = work/'잘못된 샘플레이트.wav'
            with wave.open(str(audio), 'wb') as wav:
                wav.setparams((1, 2, 8000, 8000, 'NONE', 'not compressed'))
                wav.writeframes(b'\0\0'*8000)
            request = work/'request.json'
            save_json(request, {'action': 'vad' if backend == 'sherpa' else 'diarize',
                      'audio': str(audio), 'cache': str(work/'없는 모델'), 'model': str(work/'없는 모델.onnx'),
                      'speakers': -1, 'output': str(work/'engine.json')})
            result = subprocess.run(tools.command(backend, request), capture_output=True, timeout=120)
            text = (result.stdout+result.stderr).decode('utf-8', 'replace')
            if backend == 'pyannote':
                text += json.dumps(read_json(work/'error.json'), ensure_ascii=False)
            assert result.returncode and '16kHz' in text, text[-3000:]
            assert not (work/'engine.json').exists()
            assert all(file.read_bytes() == b'preserve-existing-data' for file in sentinels)
    summary = {'backend': backend, 'platform': platform, 'archive_sha256': asset['sha256'],
               'real_zip_install': True, 'active_changes_after_check_only': True,
               'previous_install_and_model_and_result_preserved': True,
               'restart_protocol_check': True, 'bad_hash_preserves_active': True,
               'synthetic_audio_read_and_input_rejection': True,
               'model_inference': False, 'public_download': False}
    (output/f'{backend}-{platform}-install-smoke.json').write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('backend', choices=['sherpa', 'pyannote'])
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    check(args.backend, args.output.resolve())
