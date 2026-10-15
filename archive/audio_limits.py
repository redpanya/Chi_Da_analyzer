"""전체 음성 작업 상한과 WAV 컨테이너 선택. 실행기에서도 외부 의존성 없이 사용한다."""
MAX_MS = 20 * 3600 * 1000
RIFF_BYTES = 2**32 - 4096


def duration(ms):
    if type(ms) is not int or not 0 < ms <= MAX_MS:
        raise ValueError('전체 음성 처리는 최대 20시간까지 지원합니다')
    return ms


def wav_format(frames, rate, channels, sample_bytes=4):
    if frames < 0 or frames > MAX_MS * rate // 1000:
        raise ValueError('전체 음성 처리는 최대 20시간까지 지원합니다')
    return 'RF64' if frames * channels * sample_bytes > RIFF_BYTES else 'WAV'


def remaining_space(folder, duration_ms, bytes_per_ms, margin):
    # 중단 전 조각을 이미 저장했으면 남은 예상분만 요구한다. 임시 파일은 빼지 않는다.
    saved=sum(p.stat().st_size for p in folder.iterdir() if p.is_file() and not p.is_symlink()
              and (p.suffix=='.npz' or p.name in ('source44.wav','source48.wav')))
    return max(0,duration_ms*bytes_per_ms-saved)+margin
