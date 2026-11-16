"""완결된 HLS 재생 목록에서 구간에 걸치는 조각과 초기화 데이터만 선택한다."""
from decimal import Decimal, InvalidOperation
from urllib.parse import urljoin, urlsplit
from yt_dlp.utils import parse_m3u8_attributes
from .http_download import RangeUnsupported


def plan(text, url, start_ms, end_ms):
    if not text.lstrip().startswith('#EXTM3U') or '#EXT-X-ENDLIST' not in text.splitlines():
        raise RangeUnsupported('완결된 HLS 미디어 재생 목록이 아닙니다')
    items = []
    at = Decimal(0)
    duration = byte_range = init = previous = origin = None
    local = ['#EXTM3U', '#EXT-X-VERSION:7', '#EXT-X-PLAYLIST-TYPE:VOD']
    def resource(uri, spec):
        resolved = urljoin(url, uri)
        if urlsplit(resolved).scheme != 'https':
            raise ValueError('HTTPS 영상 조각만 받을 수 있습니다')
        if spec is None:
            return resolved, None, None
        length, sep, offset = spec.partition('@')
        if not sep and (not previous or previous[0] != resolved or previous[2] is None):
            raise RangeUnsupported('HLS 조각의 시작 위치를 확인할 수 없습니다')
        first = int(offset) if sep else previous[2]
        if first < 0 or int(length) <= 0:
            raise RangeUnsupported('HLS 조각 범위가 올바르지 않습니다')
        return resolved, first, first+int(length)
    for line in map(str.strip, text.splitlines()):
        if line.startswith(('#EXT-X-DISCONTINUITY', '#EXT-X-GAP', '#EXT-X-STREAM-INF')):
            raise RangeUnsupported('연속 타임라인이 아닌 HLS입니다')
        if line.startswith('#EXT-X-KEY:') and parse_m3u8_attributes(line.partition(':')[2]).get('METHOD') != 'NONE':
            raise RangeUnsupported('별도 키가 필요한 HLS입니다')
        if line.startswith('#EXT-X-TARGETDURATION:'):
            local.append('#EXT-X-TARGETDURATION:'+str(int(line.partition(':')[2])))
        elif line.startswith('#EXT-X-MAP:'):
            attrs = parse_m3u8_attributes(line.partition(':')[2])
            if init is not None or items:
                raise RangeUnsupported('초기화 구간이 변경되는 HLS입니다')
            init = resource(attrs['URI'], attrs.get('BYTERANGE'))
        elif line.startswith('#EXTINF:'):
            try:
                duration = Decimal(line[8:].split(',')[0])
            except InvalidOperation:
                raise RangeUnsupported('HLS 조각 길이를 확인할 수 없습니다') from None
            if not duration.is_finite() or duration <= 0:
                raise RangeUnsupported('HLS 조각 길이가 올바르지 않습니다')
        elif line.startswith('#EXT-X-BYTERANGE:'):
            byte_range = line.partition(':')[2]
        elif line and not line.startswith('#'):
            if duration is None:
                raise RangeUnsupported('HLS 조각 길이가 없습니다')
            previous = resource(line, byte_range)
            after = at + duration*1000
            if at < end_ms and after > start_ms:
                if origin is None:
                    origin = at
                    if init:
                        items.append(init)
                        local.append('#EXT-X-MAP:URI="00000000.mp4"')
                local.extend([f'#EXTINF:{duration},', f'{len(items):08}.m4s' if init else f'{len(items):08}.ts'])
                items.append(previous)
            at, duration, byte_range = after, None, None
    if origin is None or end_ms > at+1:
        raise ValueError('요청 구간이 HLS 미디어 범위를 벗어납니다')
    local.append('#EXT-X-ENDLIST')
    return items, '\n'.join(local)+'\n', float((start_ms-origin)/1000)
