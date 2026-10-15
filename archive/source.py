"""공개 치지직 주소와 응답을 확인하고 재생 비밀값은 메모리에만 둔다."""

import json
import re
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen, HTTPRedirectHandler, build_opener

from yt_dlp import YoutubeDL
from .storage import vod_id


class Cancelled(Exception):
    pass


def check_cancel(event):
    if event.is_set():
        raise Cancelled('중단 요청을 반영했습니다')


def safe_error(error):
    if isinstance(error, HTTPError):
        if error.code in (401, 403):
            return '공개 접근 권한을 확인할 수 없습니다. 로그인 필요·접근 제한 여부를 확인하세요'
        return f'서버 응답 오류({error.code}). 주소와 제공 상태를 확인하고 재시도하세요'
    if isinstance(error, PermissionError):
        return '폴더 쓰기 권한이 없습니다. 권한이나 저장 위치를 확인하세요'
    if isinstance(error, OSError) and error.errno == 28:
        return '저장 공간이 부족합니다. 원본을 유지한 채 공간을 확보하고 이어받으세요'
    return re.sub(r'https?://\S+', '[주소 생략]', str(error))[:700]


def request_json(url, stop=None):
    stop = stop or threading.Event()
    request = Request(url, headers={'User-Agent': 'Mozilla/5.0', 'Referer': 'https://chzzk.naver.com/'})
    for attempt in range(3):
        check_cancel(stop)
        try:
            with urlopen(request, timeout=20) as response:
                value = json.load(response)
            check_cancel(stop)
            return value
        except HTTPError as error:
            if error.code not in (429, 500, 502, 503, 504) or attempt == 2:
                raise
        except (URLError, TimeoutError):
            if attempt == 2:
                raise
        if stop.wait(2 ** (attempt + 1)):
            raise Cancelled()


def resolve_url(value):
    value = value.strip()
    parsed = urlsplit(value)
    if parsed.scheme != 'https' or parsed.username or parsed.password or parsed.port:
        raise ValueError('https://chzzk.naver.com/video/번호 또는 https://naver.me/공유주소를 입력하세요')
    if parsed.hostname == 'naver.me' and re.fullmatch(r'/[A-Za-z0-9]+', parsed.path):
        class Redirects(HTTPRedirectHandler):
            def redirect_request(self, req, fp, code, msg, headers, newurl):
                target = urlsplit(newurl)
                if target.scheme != 'https' or target.hostname not in ('naver.me', 'chzzk.naver.com') or target.username or target.port:
                    raise ValueError('치지직 영상으로 연결되는 공개 공유주소만 사용할 수 있습니다')
                return super().redirect_request(req, fp, code, msg, headers, newurl)
        with build_opener(Redirects()).open(Request(value, headers={'User-Agent': 'Mozilla/5.0'}), timeout=20) as response:
            parsed = urlsplit(response.url)
    match = re.fullmatch(r'/video/([1-9][0-9]{0,17})/?', parsed.path)
    if parsed.hostname != 'chzzk.naver.com' or not match:
        raise ValueError('치지직 VOD 주소가 아닙니다. /video/번호 주소를 확인하세요')
    return vod_id(match[1])


class Logger:
    def debug(self, *_):
        pass

    def warning(self, *_):
        pass

    def error(self, *_):
        pass


def ydl_options():
    return {'quiet': True, 'logger': Logger(), 'noplaylist': True, 'socket_timeout': 20,
            'retries': 3, 'fragment_retries': 3, 'skip_unavailable_fragments': False,
            'continuedl': True, 'overwrites': False, 'fixup': 'never',
            'concurrent_fragment_downloads': 1}


def metadata(vod, stop=None):
    payload = request_json(f'https://api.chzzk.naver.com/service/v3/videos/{vod_id(vod)}', stop)
    content = payload.get('content') if isinstance(payload, dict) else None
    if not isinstance(payload, dict) or payload.get('code') != 200 or not isinstance(content, dict) or str(content.get('videoNo')) != vod:
        raise ValueError('영상 정보를 확인할 수 없습니다. 삭제·접근 제한 여부를 확인하세요')
    return {'id': vod, 'url': f'https://chzzk.naver.com/video/{vod}',
            'title': content.get('videoTitle') or f'VOD {vod}',
            'channel': (content.get('channel') or {}).get('channelName') or '',
            'duration': content.get('duration'), 'chat_enabled': content.get('videoChatEnabled'),
            'video_type': content.get('videoType'), 'vod_status': content.get('vodStatus')}


def inspect(value):
    vod = resolve_url(value)
    meta = metadata(vod)
    with YoutubeDL(ydl_options()) as downloader:
        info = downloader.extract_info(meta['url'], download=False)
    formats = []
    for item in info.get('formats', []):
        if item.get('ext') != 'mp4' or item.get('protocol') not in ('m3u8_native', 'https') or item.get('has_drm'):
            continue
        if item.get('vcodec') in (None, 'none') or item.get('acodec') == 'none':
            continue
        estimate = item.get('filesize') or item.get('filesize_approx')
        if not estimate and item.get('tbr') and meta.get('duration'):
            estimate = int(item['tbr'] * 1000 / 8 * meta['duration'])
        formats.append({'id': item['format_id'], 'height': item.get('height'),
                        'fps': item.get('fps'), 'protocol': item['protocol'],
                        'estimated_bytes': estimate,
                        'label': f"{item.get('height') or '?'}p · {item.get('fps') or '?'}fps"})
    if not formats:
        raise ValueError('현재 지원하는 공개 MP4 화질이 없습니다')
    meta['formats'] = sorted(formats, key=lambda f: (f['height'] or 0, f['fps'] or 0), reverse=True)
    return meta
