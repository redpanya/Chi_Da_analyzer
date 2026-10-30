"""이메일 첨부용 리포트 형식. 원문·자유 로그는 포함하지 않는다."""
import json
import math
import re

POLICY = '2026-10-18.2'
MAX_BYTES = 131072
STAGES = {'download', 'audio', 'transcribe', 'diarize', 'reactions', 'summary', 'model'}
STATES = {'running', 'complete', 'partial', 'error', 'paused', 'reused', 'skipped'}
COUNTS = {'video_seconds', 'transcript_segments', 'transcript_characters', 'transcript_processed_seconds',
          'chat_messages', 'chat_characters', 'summary_input_speech_characters', 'summary_input_chat_characters',
          'generated_tokens', 'prompt_tokens', 'prompt_ms', 'generation_ms', 'fresh_attempts', 'checkpoint_reuses',
          'model_load_seconds', 'tokenizer_seconds', 'requests_without_response_metrics'}
ERRORS = {'none', 'task_failed', 'interrupted', 'needs_review', 'prerequisite_missing', 'disk_unavailable', 'result_unreadable'}


def validate(value):
    if not isinstance(value, dict) or set(value) != {'schema', 'policy', 'report_id', 'vod_id', 'app_version', 'hardware', 'options', 'stages', 'counts'}:
        raise ValueError('제출 리포트 필드가 올바르지 않습니다')
    if value['schema'] != 2 or value['policy'] != POLICY or not re.fullmatch(r'[a-f0-9]{32}', str(value['report_id'])):
        raise ValueError('리포트 버전 또는 번호를 확인하세요')
    if not isinstance(value['vod_id'], str) or not re.fullmatch(r'[1-9][0-9]{0,17}', value['vod_id']):
        raise ValueError('리포트의 VOD 번호를 확인하세요')
    if not re.fullmatch(r'\d+\.\d+\.\d+', str(value['app_version'])):
        raise ValueError('앱 버전을 확인하세요')
    hardware = value['hardware']
    text_fields = {'os', 'os_version', 'architecture', 'cpu', 'gpu'}
    number_fields = {'cores', 'threads', 'ram_bytes'}
    if not isinstance(hardware, dict) or set(hardware) != text_fields | number_fields:
        raise ValueError('장치 정보 필드를 확인하세요')
    for key in text_fields:
        item = hardware[key]
        if item is not None and (not isinstance(item, str) or len(item) > 240 or any(ord(c) < 32 for c in item)):
            raise ValueError('장치 정보 형식을 확인하세요')
    for key in number_fields:
        number(hardware[key])
    options = value['options']
    allowed = {'language': {'ko', 'en', 'ja', 'auto'}, 'vad': {'standard', 'sensitive', 'off'},
               'speaker_backend': {'none', 'sherpa', 'pyannote', 'fluid'}, 'compute_requested': {'cpu', 'hybrid', 'platform_default'},
               'compute_actual': {'unknown', 'cpu', 'vulkan', 'metal'}, 'summary_model': {'gemma-4-E4B-it-Q4_K_M', 'unknown'}, 'speech_model': {'large-v3-turbo-q5_0'}}
    if not isinstance(options, dict) or set(options)-{'summary_mode'} != set(allowed) | {'thinking', 'hint_characters'}:
        raise ValueError('설정 정보 필드를 확인하세요')
    if options.get('summary_mode','detail') not in ('detail','timestamps','clips'):
        raise ValueError('문맥 모드를 확인하세요')
    for key, choices in allowed.items():
        if not isinstance(options[key], str) or options[key] not in choices:
            raise ValueError('설정 값이 올바르지 않습니다')
    if type(options['thinking']) is not bool:
        raise ValueError('사고 설정을 확인하세요')
    number(options['hint_characters'])
    if not isinstance(value['stages'], list) or len(value['stages']) > 300:
        raise ValueError('단계 기록 수를 확인하세요')
    for stage in value['stages']:
        if not isinstance(stage, dict) or set(stage)-{'summary_mode'} != {'stage', 'state', 'seconds', 'error_code'}:
            raise ValueError('단계 정보 필드를 확인하세요')
        if 'summary_mode' in stage and (stage['stage']!='summary' or stage['summary_mode'] not in ('detail','timestamps','clips')):
            raise ValueError('단계의 문맥 모드를 확인하세요')
        if stage['stage'] not in STAGES or stage['state'] not in STATES or stage['error_code'] not in ERRORS:
            raise ValueError('단계 상태를 확인하세요')
        number(stage['seconds'])
    if not isinstance(value['counts'], dict) or set(value['counts']) - COUNTS:
        raise ValueError('처리량 필드를 확인하세요')
    for item in value['counts'].values():
        number(item)
    if len(encode(value)) > MAX_BYTES:
        raise ValueError('리포트 크기 제한을 초과했습니다')
    return value


def number(value):
    if value is not None and (type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 10**16):
        raise ValueError('리포트 수치를 확인하세요')


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')
