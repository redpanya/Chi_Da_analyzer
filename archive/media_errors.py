"""공용 실행기의 오류를 도구·원인별로 안내한다. 원격 주소는 화면에 복사하지 않는다."""
from pathlib import Path


def failure_message(args, code, log):
    ffmpeg = Path(str(args[0])).stem.lower() == 'ffmpeg'
    label = '영상·오디오 처리 도구(FFmpeg)' if ffmpeg else '음성 처리 프로그램'
    reason = '처리 로그에서 자세한 오류를 확인하세요.'
    if ffmpeg:
        try:
            with log.open('rb') as stream:
                stream.seek(max(0, log.stat().st_size - 8192))
                tail = stream.read().decode('utf-8', errors='replace').lower()
        except OSError:
            tail = ''
        # Windows는 FFmpeg의 음수 오류 코드를 unsigned 32비트로 전달한다.
        signed = (int(code) + 2**31) % 2**32 - 2**31
        if signed == -1330794744 or 'protocol not found' in tail:
            reason = '필요한 입력 프로토콜을 지원하지 않습니다. HTTPS 지원이 포함된 최신 앱으로 업데이트하세요.'
        elif any(v in tail for v in ('certificate verify failed', 'certificate verification failed',
                                     'invalid certificate chain', 'sni or certificate check failed',
                                     'unable to negotiate tls/ssl session', 'creating security context failed',
                                     'ssl handshake failed', 'sec_e_untrusted_root', '0x80090325',
                                     '0x800b0109', '0x80090322', '0x800b010f', '0x800b0101')):
            reason = 'HTTPS 보안 연결·인증서 검증에 실패했습니다. PC 시각과 네트워크의 인증서 설정을 확인하세요.'
        elif 'mismatches allowed extensions' in tail:
            reason = '영상 조각의 확장자와 내부 형식이 맞지 않아 중단했습니다. 앱의 영상 형식 호환 여부를 확인하세요.'
        elif 'not in allowed_segment_extensions' in tail:
            reason = '허용하지 않는 영상 조각의 확장자가 감지돼 중단했습니다. 로그에서 입력 형식을 확인하세요.'
        elif 'no space left on device' in tail:
            reason = '저장 공간이 부족합니다. 공간을 확보한 뒤 다시 시도하세요.'
        elif any(v in tail for v in ('connection timed out', 'connection timeout', 'operation timed out')):
            reason = '영상 서버 응답 시간이 초과됐습니다. 연결 상태를 확인한 뒤 다시 시도하세요.'
    return f'{label} 실행이 종료됐습니다({code}). {reason} 로그: {log.resolve()}'
