"""OS별로 빌드한 FFmpeg를 써서 최근 추가 기능을 검사한다."""
import os
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]


def main():
    for row in json.loads((ROOT/'web/fonts/sources.json').read_text(encoding='utf-8')):
        file = ROOT/'web/fonts'/row['file']
        assert hashlib.sha256(file.read_bytes()).hexdigest() == row['sha256'], '동봉 글꼴·OFL 원문 변경: '+row['file']
    env = os.environ | {'PYTHONPATH': os.pathsep.join((str(ROOT/'tests'), str(ROOT))),
                        'PATH': str(ROOT/'build/native/ffmpeg')+os.pathsep+os.environ.get('PATH', '')}
    # Windows CreateProcess는 전달한 env의 PATH로 실행 파일을 찾지 않는다.
    ffmpeg = ROOT/'build/native/ffmpeg'/('ffmpeg.exe' if os.name == 'nt' else 'ffmpeg')
    decoders = subprocess.check_output([str(ffmpeg), '-hide_banner', '-decoders'], env=env, text=True)
    assert any(' png ' in line for line in decoders.splitlines()), '배포 FFmpeg에 자막·이미지용 PNG 디코더가 없습니다'
    subprocess.run([sys.executable, str(ROOT/'packaging/release/check_media_colors.py')], cwd=ROOT, env=env, check=True)
    modules = (
        'test_annotation_preview', 'test_automation_selection', 'test_automation_summary',
        'test_download_scope', 'test_context_guidance', 'test_context_clip_chat',
        'test_context_exchange_prompt', 'test_context_result_deletion', 'test_speaker_tools',
        'test_polish', 'test_studio_jobs', 'test_clip_render', 'test_studio_decorations',
        'test_caption_fonts', 'test_font_families', 'test_caption_rendering',
        'test_caption_design', 'test_caption_templates',
        'test_video_split', 'test_video_split_server', 'test_split_deletion', 'test_split_audio_cache', 'test_media_https', 'test_media_errors',
    )
    subprocess.run([sys.executable, str(ROOT/'tests/run_isolated.py'), *modules, '-v'], cwd=ROOT, env=env, check=True)
    for name in ('queue_options', 'workspace_ui', 'context_guidance', 'context_external_prompt', 'context_clip_evidence',
                 'mini_player', 'polish', 'video_split', 'clip_studio',
                 'studio_fonts', 'studio_caption_size', 'studio_caption_design',
                 'studio_caption_validation', 'studio_image_geometry', 'studio_image_panel'):
        subprocess.run(['node', str(ROOT/'tests'/f'test_{name}.mjs')], cwd=ROOT, check=True)


if __name__ == '__main__':
    main()
