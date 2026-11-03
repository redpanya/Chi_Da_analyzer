"""분할용 로컬 컨테이너 계약. 확장자에 맞는 역다중화기를 명시한다."""
from pathlib import Path

VIDEO_FORMATS = {
    '.mp4': ('mov', 'mp4'), '.m4v': ('mov', 'mp4'), '.mov': ('mov', 'mov'),
    '.mkv': ('matroska', 'matroska'), '.webm': ('matroska', 'webm'),
}
VIDEO_CODECS = {'h264', 'hevc', 'vp8', 'vp9', 'mpeg4', 'mjpeg', 'prores'}
# 번들에 AV1 소프트웨어 디코더가 없어 시작·끝 재생 검사를 보장하지 못하는 형식은 제외한다.
AUDIO_CODECS = {'aac', 'mp3', 'ac3', 'eac3', 'alac', 'flac', 'opus', 'vorbis',
                'pcm_s16le', 'pcm_s24le', 'pcm_s32le', 'pcm_f32le', 'pcm_f64le',
                'pcm_s16be', 'pcm_s24be', 'pcm_s32be'}
# 미리듣기도 재인코딩하지 않는다. 브라우저가 읽을 수 있는 별도 컨테이너에 복사한다.
AUDIO_PREVIEWS = {'aac': '.m4a', 'alac': '.m4a', 'mp3': '.mp3',
                  'flac': '.flac', 'opus': '.ogg', 'vorbis': '.ogg',
                  'pcm_s16le': '.wav', 'pcm_s24le': '.wav', 'pcm_s32le': '.wav',
                  'pcm_f32le': '.wav', 'pcm_f64le': '.wav'}


def output(source):
    suffix = Path(source['path']).suffix.lower()
    if suffix not in VIDEO_FORMATS:
        raise ValueError('MP4·M4V·MOV·MKV·WebM 파일을 선택하세요')
    return suffix, VIDEO_FORMATS[suffix][1]


def input_args(path):
    suffix = Path(path).suffix.lower()
    demuxer = VIDEO_FORMATS.get(suffix, (None,))[0]
    if demuxer is None:
        demuxer = {'.m4a': 'mov', '.mp3': 'mp3', '.flac': 'flac', '.ogg': 'ogg', '.wav': 'wav'}.get(suffix)
    if demuxer is None:
        raise ValueError('지원하지 않는 파일 형식입니다')
    args = ['-protocol_whitelist', 'file']
    # 파일로 위장한 재생목록·네트워크 입력과 MOV 외부 파일 참조를 허용하지 않는다.
    if demuxer == 'mov':
        args += ['-enable_drefs', '0', '-use_absolute_path', '0']
    return [*args, '-f', demuxer, '-i', str(path)]


def preview_note(source):
    video = next(s for s in source['streams'] if s['codec_type'] == 'video')
    return (f'{Path(source["path"]).suffix[1:].upper()} · {video["codec_name"].upper()} · '
            '미리보기 지원은 브라우저에 따라 다릅니다. 재생되지 않아도 시각 입력으로 분할할 수 있습니다.')
