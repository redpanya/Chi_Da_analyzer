"""원격 구간 수신과 정확한 파일 생성을 분리한다."""
from hashlib import sha256
import json
import math
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from urllib.parse import urlsplit
from yt_dlp import YoutubeDL
from yt_dlp.networking import Request
from yt_dlp.networking.exceptions import HTTPError
from .source import ydl_options, check_cancel, fragment_concurrency
from . import clip_render, http_download, range_mp4, range_hls, range_parts
from .storage import Conflict
from .video import browser_streams
from .vod_extractor import extract_vod

BLOCK = 4 * 1024**2
REMOTE = ['-protocol_whitelist','https,http,tcp,tls,crypto,data','-tls_verify','1','-rw_timeout','20000000']


def mp4_jobs(ydl, url, headers, start, end, count, stop):
    def request(a,b,etag=None):
        h = headers | {'Range':f'bytes={a}-{b-1}'}
        if etag:
            h['If-Range'] = etag
        return ydl.urlopen(Request(url,headers=h))
    try:
        with request(0,1) as resp:
            total = http_download._range(resp,0,0)
            etag = resp.headers.get('ETag')
            if not range_parts.strong_tag(etag):
                etag = None
            if len(resp.read(2)) != 1:
                raise http_download.RangeUnsupported('부분 요청 응답의 길이가 다릅니다')
    except HTTPError as error:
        status = error.status
        error.close()
        if status in (400,405,416,501):
            raise http_download.RangeUnsupported('서버가 부분 요청을 지원하지 않습니다') from None
        raise ValueError(f'MP4 인덱스 요청 오류 (HTTP {status})') from None
    def read(a,b):
        check_cancel(stop)
        with request(a,b,etag) as resp:
            http_download._range(resp,a,b-1,total)
            if etag and resp.headers.get('ETag') != etag:
                raise Conflict('구간 준비 중 원격 영상이 달라졌습니다')
            block = resp.read(b-a+1)
            if len(block) != b-a:
                raise ValueError('MP4 인덱스 응답이 잘렸습니다')
            return block
    prefix,spans = range_mp4.plan(read,total,start,end)
    size = sum(b-a for a,b in spans)
    step = min(BLOCK,max(65536, math.ceil(size/count)))
    jobs = []
    for a,b in spans:
        for first in range(a,b,step):
            jobs.append((url,first,min(first+step,b),f'{len(jobs):08}.bin'))
    return jobs,prefix,total,etag


def boundary_packet(file, at, info):
    video = next(s for s in info['streams'] if s['codec_type']=='video')
    origin = float(info['format'].get('start_time',0))
    if abs(float(video.get('start_time',0))-origin) > .001:
        return None
    desired = at+origin
    result = subprocess.run(['ffprobe','-v','error','-protocol_whitelist','file','-select_streams','v:0',
        '-read_intervals',f'{desired}%+#1','-show_packets','-show_entries','packet=pts_time,dts_time,flags',
        '-of','json',str(file)],capture_output=True,timeout=30)
    if result.returncode:
        return None
    rows = json.loads(result.stdout).get('packets',[])
    if rows and 'K' in rows[0].get('flags','') and abs(float(rows[0].get('pts_time','inf'))-desired) < .00001:
        return rows[0]
    return None


def exact_tracks(file, duration, source_info):
    info = clip_render.probe(file)
    streams = [s for s in info['streams'] if s['codec_type'] in ('audio','video')]
    if (not browser_streams(info) or len(streams) !=
            sum(s['codec_type'] in ('audio','video') for s in source_info['streams'])):
        return set()
    return {s['codec_type'] for s in streams if abs(float(s.get('start_time','inf'))) < .001
            and abs(float(s.get('duration',0))-duration) < .001}


def make_video(file, start, duration, target, stop, lock, update, remote=False, reason=''):
    source = REMOTE if remote else ['-protocol_whitelist','file']
    def progress(phase, message, low, high):
        begin = time.monotonic()
        def report(**v):
            fraction = v.get('progress',0)
            update(progress=low+fraction*(high-low),phase=phase,message=message,
                   processing_rate=round(duration*fraction/max(.001,time.monotonic()-begin),2))
        update(progress=low,phase=phase,message=message)
        return report
    low = 0 if remote else .72
    args = source+['-threads','2','-ss',str(start),'-i',str(file),'-t',str(duration),'-map','0:v:0','-map','0:a:0?']
    copied = audio_encoded = False
    if not remote:
        info = clip_render.probe(file)
        if browser_streams(info) and boundary_packet(file,start,info):
            try:
                copy = args+['-c:v','copy']
                end = start+duration
                if end < float(info['format']['duration'])-.001:
                    packet = boundary_packet(file,end,info)
                    if packet and 'dts_time' in packet:
                        # 다음 키프레임의 디코딩 순서에서 잘라 B프레임 참조 묶음을 유지한다.
                        cutoff = float(packet['dts_time']) - float(info['format'].get('start_time',0)) - start
                        copy += ['-bsf:v',f"noise=drop='gte(dts*tb,{cutoff-.000001})'"]
                required = {s['codec_type'] for s in info['streams'] if s['codec_type'] in ('video','audio')}
                for codec in ('copy','aac'):
                    clip_render.command(copy+['-c:a',codec,'-movflags','+faststart',str(target)],target.parent,
                        target.stem+'-'+codec,stop,lock,progress('process','원본 영상 복사' if codec=='copy' else '영상 복사 및 음성 경계 정리',low,.84),duration)
                    tracks = exact_tracks(target,duration,info)
                    if tracks == required:
                        proof = clip_render.verify(target,duration,stop,lock,progress('verify','복사한 구간 검사',.85,1))
                        copied, audio_encoded = True, codec=='aac'
                        break
                    if 'video' not in tracks:
                        break
            except ValueError:
                check_cancel(stop)
    if not copied:
        clip_render.command(args+['-c:v','libx264','-threads:v','2','-preset','veryfast','-crf','20',
                        '-pix_fmt','yuv420p','-c:a','aac','-movflags','+faststart',str(target)],
                        target.parent,target.stem,stop,lock,progress('process',('단일 원격 처리 / '+reason) if remote else '요청 시각에 맞춰 구간 처리',low,.85),duration)
        proof = clip_render.verify(target,duration,stop,lock,progress('verify','지정 구간 전체 검사',.85,1))
    return proof | {'video_stream_copy':copied, 'stream_copy':copied and not audio_encoded}


def receive(vod, start_ms, end_ms, target, stop, lock, update, *, height=480, format_id=None, concurrent_fragments=1):
    check_cancel(stop)
    count = fragment_concurrency(concurrent_fragments)
    start,duration = start_ms/1000,(end_ms-start_ms)/1000
    if target.exists() or target.is_symlink():
        raise Conflict('이미 존재하는 구간 출력 파일을 덮어쓸 수 없습니다')
    selector = format_id or f'best[height<={height}][vcodec!=none][acodec!=none]/best[height<={height}]'
    with YoutubeDL(ydl_options() | {'format':selector}) as ydl:
        info = extract_vod(ydl,vod)
        url = info.get('url')
        if not isinstance(url,str) or urlsplit(url).scheme != 'https':
            raise ValueError('구간 다운로드 가능한 HTTPS 영상 주소가 없습니다')
        headers = {k:v for k,v in (info.get('http_headers') or {}).items() if k.lower() not in ('range','if-range','accept-encoding')}
        headers['Accept-Encoding'] = 'identity'
        protocol = info.get('protocol')
        total = etag = None
        prefix = playlist = None
        try:
            if protocol == 'https':
                jobs,prefix,total,etag = mp4_jobs(ydl,url,headers,start,end_ms/1000,count,stop)
            elif protocol == 'm3u8_native':
                with ydl.urlopen(Request(url,headers=headers)) as resp:
                    raw = resp.read(8*1024**2+1)
                    if len(raw)>8*1024**2:
                        raise http_download.RangeUnsupported('HLS 재생 목록 크기 제한을 초과했습니다')
                    media,playlist,start = range_hls.plan(raw.decode('utf-8-sig'),resp.url,start_ms,end_ms)
                names = [s.split('"')[1] if s.startswith('#EXT-X-MAP:') else s for s in playlist.splitlines()
                         if s.startswith('#EXT-X-MAP:') or not s.startswith('#')]
                jobs = [(*item,name) for item,name in zip(media,names,strict=True)]
            else:
                raise http_download.RangeUnsupported('이 형식은 단일 원격 탐색을 사용합니다')
        except http_download.RangeUnsupported as error:
            update(progress=0,phase='process',message=f'{error}. 단일 원격 탐색으로 처리합니다')
            return make_video(url,start_ms/1000,duration,target,stop,lock,update,remote=True,reason=str(error))
        # 강한 원격 식별자가 없는 경우 다른 실행의 자료를 혼합하지 않는다.
        identity = (vod,info.get('format_id'),start_ms,end_ms,total,etag,BLOCK,
                    [(a,b,n) for _,a,b,n in jobs])
        if playlist:
            identity += (playlist, [(urlsplit(u).netloc,urlsplit(u).path) for u,*_ in jobs])
        reusable = bool(etag or playlist)
        if reusable:
            key = sha256(json.dumps(identity).encode()).hexdigest()
            folder = target.parent/('range-cache-'+key)
            marker = folder/'transfer.id'
            if folder.exists() or folder.is_symlink():
                if folder.is_symlink() or marker.is_symlink() or not marker.is_file() or marker.read_text('ascii') != key:
                    raise Conflict('기존 폴더를 이 구간의 수신 캐시로 확인할 수 없습니다')
            else:
                folder.mkdir()
                marker.write_text(key,encoding='ascii')
        else:
            folder = Path(tempfile.mkdtemp(prefix='range-session-',dir=target.parent))
        success = False
        try:
            range_parts.receive(ydl,headers,jobs,folder,count,stop,update,total=total,etag=etag,validate_parts=bool(playlist))
            check_cancel(stop)
            with tempfile.TemporaryDirectory(prefix='range-build-',dir=folder) as tmp:
                if prefix is not None:
                    update(progress=.72,phase='assemble',message='받은 조각을 MP4로 정리하고 있습니다')
                    src = Path(tmp)/'input.mp4'
                    with src.open('xb') as dest:
                        dest.write(prefix)
                        for *_,name in jobs:
                            with (folder/name).open('rb') as part:
                                while buf := part.read(1024**2):
                                    check_cancel(stop)
                                    dest.write(buf)
                else:
                    src = folder/'input.m3u8'
                    if src.is_symlink():
                        raise Conflict('연결된 재생 목록은 사용할 수 없습니다')
                    src.write_text(playlist,encoding='ascii')
                proof = make_video(src,start,duration,target,stop,lock,update)
            success = True
            return proof
        finally:
            if success or not reusable:
                shutil.rmtree(folder)
