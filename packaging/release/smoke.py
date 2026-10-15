"""실제 모델 없이 패키지·미디어·HTTP·종료 계약을 확인한다."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from urllib.request import build_opener, ProxyHandler, Request

ROOT=Path(__file__).resolve().parents[2]


def main():
    if sys.platform=='darwin':
        package=next((ROOT/'dist/release').glob('*.app'))
        binary=package/'Contents/Resources/backend/archive-backend'
    else:binary=ROOT/'dist/release/Chi_Da_analyzer/Chi_Da_analyzer.exe'
    env=dict(os.environ)
    env.pop('PYTHONPATH',None);env.pop('PYTHONHOME',None)
    with tempfile.TemporaryDirectory(prefix='치 다 패키지 ') as temp:
        work=Path(temp)
        result=subprocess.run([str(binary),'--diagnose'],cwd=work,env=env,capture_output=True,timeout=90)
        if result.returncode:raise RuntimeError(result.stderr.decode('utf-8','replace'))
        report=json.loads(result.stdout)
        if sys.platform == 'win32':
            assert report['compute']['visible'] and report['compute']['bundled']
            # GPU 없는 러너의 CPU 경로도 유지되어야 한다. GPU 실측으로 간주하지 않는다.
            native = binary.parent/'_internal/native'
            for engine, name in [('llama','llama-server'),('llama','llama-completion'),('whisper','whisper-cli')]:
                assert (native/(engine+'-vulkan')/(name+'.exe')).is_file()
        ffmpeg=report['tools']['ffmpeg']['path'];ffprobe=report['tools']['ffprobe']['path']
        movie=work/'한글 영상.mp4'
        subprocess.run([ffmpeg,'-v','error','-f','lavfi','-i','color=c=black:s=320x180:r=25',
                        '-f','lavfi','-i','sine=frequency=440:sample_rate=16000','-t','1',
                        '-c:v','libx264','-pix_fmt','yuv420p','-c:a','aac',str(movie)],check=True,timeout=30)
        probe=subprocess.check_output([ffprobe,'-v','error','-show_streams','-of','json',str(movie)])
        assert {s['codec_name'] for s in json.loads(probe)['streams']}=={'h264','aac'}
        subprocess.run([ffmpeg,'-v','error','-xerror','-i',str(movie),'-f','null','-'],check=True,timeout=30)
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
                for relative in ('','app.js','voice-model-help.js','compute.js'):
                    with http.open(url+relative,timeout=15) as response:assert response.status==200
                with http.open(url+'api/config', timeout=30) as response: config=json.load(response)
                assert config['folders']['compute']['visible'] == (sys.platform == 'win32')
                if sys.platform == 'win32':
                    for mode in ('hybrid', 'cpu'):
                        request=Request(url+'api/compute', data=json.dumps({'mode':mode}).encode(),
                                        headers={'Content-Type':'application/json','Origin':url.rstrip('/').rsplit('/',1)[0]})
                        with http.open(request,timeout=30) as response: applied=json.load(response)
                        assert applied['compute']['mode']==mode
                stop.touch();assert proc.wait(timeout=20)==0;assert not ready.exists()
            finally:
                if proc.poll() is None:proc.kill();proc.wait(timeout=10)
        report['checks']=['포함 도구 실행','H.264/AAC 생성·읽기·디코딩','한글·공백 경로','HTTP 및 정적 모듈','정상 종료']
        (ROOT/'dist/smoke.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print('패키지 기본 실행 검사 통과 (모델 추론 제외)')


if __name__=='__main__':main()
