"""OS별 셸과 무관하게 첫 검사 실패를 빌드 실패로 전달한다."""
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]


def main():
    modules = (
        'test_portable', 'test_compute', 'test_media_probe', 'test_import_recovery',
        'test_automation_reports', 'test_server_assets', 'test_queue_registration',
        'test_context_background', 'test_voices', 'test_legal_packaging',
    )
    env = os.environ | {'PYTHONPATH': os.pathsep.join((str(ROOT/'tests'), str(ROOT)))}
    subprocess.run([sys.executable, '-m', 'unittest', *modules, '-v'],
                   cwd=ROOT, env=env, check=True)
    for name in (
        'reports_ui', 'speech_readiness', 'speech_ui', 'timeline',
        'context_review_ui', 'voice_review', 'voices_ui', 'local_import_ui',
        'voice_tools_ui',
    ):
        subprocess.run(['node', str(ROOT/'tests'/f'test_{name}.mjs')],
                       cwd=ROOT, check=True)


if __name__ == '__main__':
    main()
