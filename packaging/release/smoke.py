"""실제 모델 없이 패키지·미디어·HTTP·종료 계약을 확인한다."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from urllib.request import build_opener, ProxyHandler, Request
import media_smoke
import report_smoke
import feature_smoke
import check_https

ROOT=Path(__file__).resolve().parents[2]


def main():
    if sys.platform=='darwin':
        package=next((ROOT/'dist/release').glob('*.app'))
        binary=package/'Contents/Resources/backend/archive-backend'
    else:binary=ROOT/'dist/release/ChiDaanalyzer/ChiDaanalyzer.exe'
    env=dict(os.environ)
    env.pop('PYTHONPATH',None);env.pop('PYTHONHOME',None)
    # CI의 UTF-8 강제 설정으로 일반 Windows 사용자의 문자셋 오류를 가리지 않는다.
    env['PYTHONUTF8']='0';env.pop('PYTHONIOENCODING',None)
    with tempfile.TemporaryDirectory(prefix='치 다 패키지 ') as temp:
        work=Path(temp)
        result=subprocess.run([str(binary),'--diagnose'],cwd=work,env=env,capture_output=True,timeout=90)
        if result.returncode:raise RuntimeError(result.stderr.decode('utf-8','replace'))
        report=json.loads(result.stdout)
        assert report['frozen'], '패키징된 실행기의 검사가 아닙니다'
        blocked=subprocess.run([str(binary),'--annotation-preview','--no-open'],
                               cwd=work,env=env,capture_output=True,timeout=30)
        assert blocked.returncode == 2 and '패키지에서는 주석 호환' in blocked.stderr.decode('utf-8','replace'), '배포본의 개발 주석 옵션 차단 실패'
        strict_csp="default-src 'self'; media-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'"
        if sys.platform == 'win32':
            assert report['compute']['visible'] and report['compute']['bundled']
            # GPU 없는 러너의 CPU 경로도 유지되어야 한다. GPU 실측으로 간주하지 않는다.
            native = binary.parent/'_internal/native'
            for engine, name in [('llama','llama-server'),('llama','llama-completion'),('whisper','whisper-cli')]:
                assert (native/(engine+'-vulkan')/(name+'.exe')).is_file()
        ffmpeg=report['tools']['ffmpeg']['path'];ffprobe=report['tools']['ffprobe']['path']
        report['https_range'] = check_https.check(ffmpeg, ffprobe, os.environ['GITHUB_REPOSITORY'], os.environ['GITHUB_SHA'])
        movie=work/'한글 영상.mp4'
        subprocess.run([ffmpeg,'-v','error','-f','lavfi','-i','color=c=black:s=320x180:r=25',
                        '-f','lavfi','-i','sine=frequency=440:sample_rate=16000','-t','1',
                        '-c:v','libx264','-pix_fmt','yuv420p','-c:a','aac',
                        '-metadata','title=한글 제목 日本語 🤩',str(movie)],check=True,timeout=30)
        probe=subprocess.check_output([ffprobe,'-v','error','-show_streams','-of','json',str(movie)])
        assert {s['codec_name'] for s in json.loads(probe)['streams']}=={'h264','aac'}
        subprocess.run([ffmpeg,'-v','error','-xerror','-i',str(movie),'-f','null','-'],check=True,timeout=30)
        fixture=media_smoke.prepare(work,movie,ffmpeg)
        recovery_fixture=media_smoke.prepare_recovery(work,movie,ffmpeg)
        ready=work/'ready.json';stop=work/'stop'
        with (work/'run.log').open('wb') as log:
            proc=subprocess.Popen([str(binary),'--no-open','--library',str(work/'보관함'),
                                   '--ready-file',str(ready),'--stop-file',str(stop)],cwd=work,env=env,stdout=log,stderr=log)
            try:
                for _ in range(600):
                    if ready.exists() or proc.poll() is not None:break
                    time.sleep(.1)
                if not ready.exists():raise RuntimeError((work/'run.log').read_text(encoding='utf-8',errors='replace'))
                url=json.loads(ready.read_text(encoding='utf-8'))['url']
                http=build_opener(ProxyHandler({}))
                for relative in ('','app.js','voice-model-help.js','voice-tool-status.js','voice-tabs.js',
                                 'compute.js','queue.js','queue-saved.js','reports.js',
                                 'context-background.js','context-inputs.js','context-fallback.js','timeline.js',
                                 'context-external.js','context-copy.js','vod-label.js'):
                    with http.open(url+relative,timeout=15) as response:
                        assert response.status==200
                        assert response.headers.get('Content-Security-Policy') == strict_csp
                for relative in ('video-split.html','video-split.js','video-split-audio.js','clip-studio.html',
                                 'clip-studio.js','studio-decorations.js','studio-fonts-ui.js',
                                 'studio-caption-design.js','studio-caption-templates.js','studio-image-editor.js'):
                    with http.open(url+relative, timeout=15) as response:
                        assert response.read() == (ROOT/'web'/relative).read_bytes(), relative
                for relative in ('pattern-background.js', 'pattern-background.css',
                                 *(f'patterns/pattern-{i:02}.webp' for i in range(1, 9))):
                    with http.open(url+relative, timeout=15) as response:
                        assert response.status == 200
                        assert response.read() == (ROOT/'web'/relative).read_bytes()
                with http.open(url+'api/config', timeout=30) as response:
                    assert response.headers.get('Content-Security-Policy') == strict_csp
                    config=json.load(response)
                assert config['annotation_preview'] is False
                report['web_security']={'csp':strict_csp,'annotation_preview':False,'preview_option_rejected':True}
                assert config['folders']['compute']['visible'] == (sys.platform == 'win32')
                if sys.platform == 'win32':
                    for mode in ('hybrid', 'cpu'):
                        request=Request(url+'api/compute', data=json.dumps({'mode':mode}).encode(),
                                        headers={'Content-Type':'application/json','Origin':url.rstrip('/').rsplit('/',1)[0]})
                        with http.open(request,timeout=30) as response: applied=json.load(response)
                        assert applied['compute']['mode']==mode
                report['media_pipeline']=media_smoke.check(http,url,fixture)
                report['import_recovery']=media_smoke.check_recovery(http,url,recovery_fixture)
                report['automation_reports']=report_smoke.check(http,url,fixture[0])
                report['editing_and_split']=feature_smoke.check(http,url,work,ffmpeg,ffprobe,fixture[0])
                stop.touch();assert proc.wait(timeout=20)==0;assert not ready.exists()
            finally:
                if proc.poll() is None:proc.kill();proc.wait(timeout=10)
        report['checks']=['포함 도구 실행','H.264/AAC 생성·읽기·디코딩','한글·공백 경로·다국어 제목',
                          '다운로드 후 검사 재개 (수신 대체)','패키지 원음 정보·추출 API','원본·채팅 보존',
                          '시작 시각 이동·기존 임시 재생본 복구','저장된 경계 응답의 채팅 보완',
                          '순차 작업 상태·VOD 번호 포함 리포트·구형 사본 보존·자동 전송 제거',
                          'HTTP 및 정적 모듈','배포 CSP 유지·개발 주석 옵션 차단','픽셀 배경 8종·CSS·JS 포함 및 원본 일치',
                          '무인코딩 전체/선택 오디오 분할·패킷 동일성','선택 AAC 미리듣기·원본 보존',
                          '동봉 한글 글꼴·PNG 자막 렌더링·PNG 클립 합성','정상 종료']
        (ROOT/'dist/smoke.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print('패키지 기본 실행 검사 통과 (모델 추론 제외)')


if __name__=='__main__':main()
