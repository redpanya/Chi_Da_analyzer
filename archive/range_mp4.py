"""MP4 표본 인덱스로 요청 구간의 압축 데이터를 찾고 로컬 청크 위치를 갱신한다."""
from array import array
from bisect import bisect_right
from heapq import merge
from itertools import chain
import struct
import sys

from .http_download import RangeUnsupported

LIMIT = 128 * 1024**2


def boxes(data, start, end):
    while start < end:
        size, kind = struct.unpack_from('>I4s', data, start)
        head = 8
        if size == 1:
            size, = struct.unpack_from('>Q', data, start + 8)
            head = 16
        if not size:
            size = end - start
        if size < head or start + size > end:
            raise RangeUnsupported('MP4 상자 길이를 확인할 수 없습니다')
        yield kind, (start + head, start + size)
        start += size


def number(data, pos):
    return struct.unpack_from('>I', data, pos)[0]


def table(data, box, width):
    start, end = box
    count = number(data, start + 4)
    if start + 8 + count * width * 4 != end:
        raise RangeUnsupported('MP4 표본 테이블의 길이가 다릅니다')
    return struct.iter_unpack('>' + 'I' * width, memoryview(data)[start + 8:end])


def track_window(data, track, movie_scale, start, end):
    contents = dict(boxes(data, *track))
    media = dict(boxes(data, *contents[b'mdia']))
    handler = media[b'hdlr'][0]
    if data[handler+8:handler+12] not in (b'vide', b'soun'):
        raise RangeUnsupported('추가 트랙이 있는 MP4입니다')
    mdhd = media[b'mdhd'][0]
    scale = number(data, mdhd + (20 if data[mdhd] else 12))
    shift = 0
    if b'edts' in contents:
        edit, last = dict(boxes(data, *contents[b'edts']))[b'elst']
        fmt = '>Qqi' if data[edit] else '>Iii'
        entries = list(struct.iter_unpack(fmt, memoryview(data)[edit+8:last]))
        lead = 0
        if len(entries) == 2 and entries[0][1] == -1:
            lead = entries.pop(0)[0] / movie_scale
        if len(entries) != 1 or entries[0][1] < 0 or entries[0][2] != 65536:
            raise RangeUnsupported('복합 편집 목록이 있는 MP4입니다')
        shift = entries[0][1] - lead * scale
    stbl = dict(boxes(data, *dict(boxes(data, *media[b'minf']))[b'stbl']))
    # 표시 시각과 디코딩 시각 차이만큼 경계를 넓혀 참조 프레임도 가져온다.
    skew = 0
    if b'ctts' in stbl:
        signed = data[stbl[b'ctts'][0]] == 1
        for _, value in table(data, stbl[b'ctts'], 2):
            skew = max(skew, abs(value - 2**32 if signed and value >= 2**31 else value))
    ticks = samples = 0
    first = last = None
    for count, delta in table(data, stbl[b'stts'], 2):
        limit = ticks + count * delta
        for is_first, at in ((True, start*scale+shift-skew), (False, end*scale+shift+skew)):
            if at < limit:
                index = samples + max(0, int((at-ticks)//delta))
                if is_first and first is None:
                    first = index
                if not is_first and last is None:
                    last = index
        ticks = limit
        samples += count
    first = min(samples-1, first if first is not None else samples-1)
    last = min(samples-1, (last if last is not None else samples-1) + 1)
    if b'stss' in stbl:
        keys = array('I', (i-1 for i, in table(data, stbl[b'stss'], 1)))
        if not keys:
            raise RangeUnsupported('MP4 키프레임 인덱스가 비어 있습니다')
        first = keys[max(0, bisect_right(keys, first)-1)]
    else:
        first = max(0, first-1)
    wide = b'co64' in stbl
    pos, tail = stbl[b'co64' if wide else b'stco']
    offsets = array('Q' if wide else 'I')
    offsets.frombytes(data[pos+8:tail])
    if sys.byteorder == 'little':
        offsets.byteswap()
    if len(offsets) != number(data, pos+4):
        raise RangeUnsupported('MP4 파일 위치 개수가 다릅니다')
    runs = list(table(data, stbl[b'stsc'], 3))
    if not runs or runs[0][0] != 1:
        raise RangeUnsupported('MP4의 첫 청크를 찾을 수 없습니다')
    low = high = None
    sample = 0
    for idx, (chunk, per, _) in enumerate(runs):
        next_chunk = runs[idx+1][0] if idx+1 < len(runs) else len(offsets)+1
        if not per or not chunk < next_chunk <= len(offsets)+1:
            raise RangeUnsupported('MP4 청크 구성이 올바르지 않습니다')
        after = sample + (next_chunk-chunk)*per
        if sample <= first < after:
            low = chunk-1 + (first-sample)//per
        if sample <= last < after:
            high = chunk-1 + (last-sample)//per
        sample = after
    if low is None or high is None or sample != samples:
        raise RangeUnsupported('MP4 요청 범위의 표본을 찾을 수 없습니다')
    return offsets, low, high, pos+8


def plan(read, total, start, end):
    at = 0
    ftyp = moov = None
    mdat = None
    seen = 0
    while at < total:
        seen += 1
        if seen > 256 or total-at < 8:
            raise RangeUnsupported('MP4 최상위 인덱스를 확인할 수 없습니다')
        header = read(at, min(total, at+16))
        size, kind = struct.unpack_from('>I4s', header)
        head = 8
        if size == 1:
            if len(header) < 16:
                raise RangeUnsupported('MP4의 확장 상자 길이가 잘렸습니다')
            size, = struct.unpack_from('>Q', header, 8)
            head = 16
        size = size or total-at
        if size < head or at+size > total:
            raise RangeUnsupported('MP4 인덱스를 확인할 수 없습니다')
        if kind in (b'ftyp', b'moov'):
            if size > LIMIT:
                raise RangeUnsupported('MP4 인덱스 크기 제한을 초과했습니다')
            block = read(at, at+size)
            if kind == b'ftyp':
                ftyp = block
            else:
                moov = bytearray(block)
                moov_head = head
        if kind == b'mdat':
            if mdat:
                raise RangeUnsupported('분할 컨테이너 MP4입니다')
            mdat = (at+head, at+size)
        if kind == b'moof':
            raise RangeUnsupported('분할 컨테이너 MP4입니다')
        at += size
    if not (ftyp and moov and mdat):
        raise RangeUnsupported('MP4 구간 인덱스가 없습니다')
    try:
        entries = list(boxes(moov, moov_head, len(moov)))
        mvhd = dict(entries)[b'mvhd'][0]
        scale = number(moov, mvhd+(20 if moov[mvhd] else 12))
        tracks = [track_window(moov, box, scale, start, end) for kind, box in entries if kind == b'trak']
    except (struct.error, KeyError, ZeroDivisionError, IndexError, OverflowError) as error:
        raise RangeUnsupported('지원하지 않는 MP4 표본 인덱스입니다') from error
    # 원본의 시간 테이블을 유지한다. 수신한 청크만 작은 로컬 mdat에 배치한다.
    # 선택 밖의 청크는 EOF를 가리키므로 존재하지 않는 데이터를 디코딩할 수 없다.
    def ordered(offsets, low, high):
        for i, offset in enumerate(offsets):
            yield offset, i == 0 or low <= i <= high

    streams = [ordered(offsets,low,high) for offsets,low,high,_ in tracks]
    spans = []
    previous = None
    take = False
    for offset, selected in chain(merge(*streams), [(mdat[1], False)]):
        if offset < mdat[0] or offset > mdat[1] or previous is not None and offset <= previous:
            raise RangeUnsupported('MP4 청크 위치가 올바르지 않습니다')
        if take:
            if spans and previous-spans[-1][1] <= 65536:
                spans[-1] = (spans[-1][0],offset)
            else:
                spans.append((previous,offset))
        previous, take = offset,selected
    if not spans:
        raise RangeUnsupported('MP4 구간 데이터가 없습니다')
    base = len(ftyp)+len(moov)+16
    origins = []
    for a,b in spans:
        origins.append(base-a)
        base += b-a
    starts = [a for a,_ in spans]
    for offsets, low, high, pos in tracks:
        if offsets.itemsize == 4 and base >= 2**32:
            raise RangeUnsupported('MP4의 32비트 청크 위치를 초과했습니다')
        for i, old in enumerate(offsets):
            j = bisect_right(starts, old)-1
            offsets[i] = old + origins[j] if j >= 0 and old < spans[j][1] else base
        if sys.byteorder == 'little':
            offsets.byteswap()
        moov[pos:pos+len(offsets)*offsets.itemsize] = offsets.tobytes()
    return ftyp + moov + struct.pack('>I4sQ', 1, b'mdat', base-len(ftyp)-len(moov)), spans
