"""기본 CSP는 유지하고 소스 실행의 명시적 주석 미리보기만 허용한다."""
from . import runtime

STRICT_CSP = "default-src 'self'; media-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'"
PREVIEW_REJECTED = '패키지에서는 주석 호환 미리보기 옵션을 사용할 수 없습니다.'


def content_security_policy(annotation_preview=False):
    if annotation_preview and runtime.FROZEN:
        raise ValueError(PREVIEW_REJECTED)
    return STRICT_CSP + ("; style-src 'self' 'unsafe-inline'" if annotation_preview else '')
