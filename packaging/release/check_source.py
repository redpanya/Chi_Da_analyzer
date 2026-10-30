"""OS별 셸과 무관하게 첫 검사 실패를 빌드 실패로 전달한다."""
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]


def main():
    modules = (
        'test_error_log', 'test_caption_isolation', 'test_portable', 'test_compute', 'test_media_probe', 'test_import_recovery', 'test_report_hardware',
        'test_automation_reports', 'test_server_assets', 'test_queue_registration',
        'test_context_background', 'test_voices', 'test_legal_packaging',
        'test_analysis_inputs', 'test_context_exchange', 'test_context_exchange_http',
        'test_context_exchange_zip', 'test_context_clips', 'test_context_comments',
    )
    env = os.environ | {'PYTHONPATH': os.pathsep.join((str(ROOT/'tests'), str(ROOT)))}
    subprocess.run([sys.executable, str(ROOT/'tests/run_isolated.py'), *modules, '-v'],
                   cwd=ROOT, env=env, check=True)
    for name in (
        'error_capture', 'frame_validation', 'studio_caption_validation', 'reports_ui', 'speech_readiness', 'speech_ui', 'timeline',
        'context_review_ui', 'voice_review', 'voices_ui', 'local_import_ui',
        'voice_tools_ui',
        'context_inputs', 'context_external', 'context_clips', 'context_tabs', 'context_copy', 'comment_playback', 'vod_label',
    ):
        subprocess.run(['node', str(ROOT/'tests'/f'test_{name}.mjs')],
                       cwd=ROOT, check=True)
    subprocess.run(['node', str(ROOT/'tests/test_pattern_background.cjs')],
                   cwd=ROOT, check=True)


if __name__ == '__main__':
    main()
