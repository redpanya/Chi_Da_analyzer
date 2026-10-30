"""공개 원격 영상의 지정 구간을 정확한 길이로 받는 공용 경로."""
from urllib.parse import urlsplit
from yt_dlp import YoutubeDL
from .source import ydl_options, check_cancel
from . import clip_render


def receive(vod, start_ms, end_ms, target, stop, lock, update, *, height=480, format_id=None):
    check_cancel(stop)
    selector = format_id or f'best[height<={height}][vcodec!=none][acodec!=none]/best[height<={height}]'
    with YoutubeDL(ydl_options() | {'format':selector}) as ydl:
        info = ydl.extract_info(f'https://chzzk.naver.com/video/{vod}', download=False)
    check_cancel(stop)
    url = info.get('url')
    if not isinstance(url, str) or urlsplit(url).scheme != 'https':
        raise ValueError('구간 다운로드 가능한 HTTPS 영상 주소가 없습니다')
    duration = (end_ms-start_ms)/1000
    clip_render.command(['-protocol_whitelist','https,http,tcp,tls,crypto,data','-tls_verify','1','-rw_timeout','20000000',
        '-ss',str(start_ms/1000),'-i',url,'-t',str(duration),'-map','0:v:0','-map','0:a:0?',
        '-c:v','libx264','-preset','veryfast','-crf','20','-pix_fmt','yuv420p','-c:a','aac','-movflags','+faststart',str(target)],
        target.parent, target.stem, stop, lock, lambda **v:update(**(v | {'progress':v.get('progress',0)*.85})), duration)
    return clip_render.verify(target, duration, stop, lock,
                              lambda **v:update(**(v | {'progress':.85+v.get('progress',0)*.15})))
