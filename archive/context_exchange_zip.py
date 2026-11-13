"""자료 ZIP 생성과 제한된 결과 ZIP 읽기. 압축 내용은 디스크에 풀지 않는다."""
import base64
import binascii
import io
import json
import re
import stat
import zipfile
import zlib
from . import context_exchange as exchange, context_exchange_data as data
from .storage import read_json

MAX_BYTES=data.MAX_RESULT_BYTES
MAX_MEMBERS=6000


def work_order(saved):
    if saved.get('work_order'):return saved['work_order']
    chunks=saved.get('chunks',[])
    names='\n'.join(f'{c["id"]}: 자료/chida-{saved["id"][:8]}-{c["id"]}.json → chida-result-{saved["id"][:8]}-{c["id"]}.json' for c in chunks)
    label={'detail':'상세 문맥 정리','timestamps':'타임스탬프','clips':'클립 후보 찾기'}[saved['mode']]
    return f'''치다분석기 외부 AI 작업서
내보내기 ID: {saved.get('id','자료 생성 시 확정')}
{f'총 {len(chunks)}묶음' if chunks else '자료 생성 시 전체 파일 목록 확정'} · {label}

ZIP을 읽지 못하는 서비스에는 압축을 푼 후 이 작업서와 자료 JSON을 직접 첨부하세요. 이 요청은 서비스의 입력 한도나 자동 연속 작업을 보장하지 않습니다.

분석 및 결과 규칙
{saved.get('request_prompt') or exchange.prompt(saved['mode'],saved.get('custom_request',''),chat_discovery=bool(saved.get('clip_chat_revision')))}
파일별 작업 목록
{names or '자료 생성 후 여기에 모든 입력 JSON과 결과 JSON의 파일명이 번호순으로 들어갑니다. 첨부된 전체 목록을 처리하세요.'}
'''


def pack(path,id):
    target=exchange.folder(path,id);saved=read_json(target/'manifest.json');source=read_json(target/'source.json')
    return pack_snapshot(saved,source)


def pack_snapshot(saved,source,selected=None):
    id=saved['id'];buffer=io.BytesIO();order=work_order(saved)
    names=None if selected is None else set(selected)
    with zipfile.ZipFile(buffer,'w',compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('작업서.txt',order.encode('utf-8'))
        if names is not None:
            ordered=[c['id'] for c in saved['chunks'] if c['id'] in names]
            request=f'''치다분석기 외부 AI 보완 요청 — 이 파일을 먼저 읽으세요.
내보내기 ID: {id}
보완 대상: {', '.join(ordered)} ({len(ordered)}묶음)

이번 요청의 처리 범위는 위 보완 대상과 이 ZIP의 자료 JSON뿐입니다.
작업서.txt는 최초 요청을 보존한 원문이며 전체 목록이 들어 있습니다. 작업서의 "전체 파일"은 이번 보완에서는 이 ZIP에 들어 있는 대상 전체로 한정합니다. 이전에 정상 처리한 다른 묶음을 다시 만들지 마세요.
분석 기준·추가 요청·방송 상황·결과 형식은 원래 작업서를 그대로 따르세요. export_id·chunk_id·mode·coverage·발언 ID를 변경하지 마세요.
각 입력 JSON의 previous_reference·following_reference는 앞뒤 문맥 참고용입니다. 참고 자료 자체를 추가 결과로 만들지 마세요.
대상 파일을 번호순으로 모두 처리하고 chida-result-{id[:8]}-묶음ID.json으로 하나씩 저장하세요. 모든 대상이 완료되면 결과 JSON만 ZIP으로 제공하세요.
일부만 완료했으면 완료·미완료 번호를 알려주세요. 실제 파일 생성이 불가능하면 그 한계를 알리세요. 원본 전체 작업이 완료되었다고 표현하지 마세요.
'''
            archive.writestr('먼저읽기-보완요청.txt',request.encode('utf-8'))
        for c,content in exchange.documents(saved,source):
            if names is None or c['id'] in names:
                archive.writestr(f'자료/chida-{id[:8]}-{c["id"]}.json',json.dumps(content,ensure_ascii=False,indent=2).encode('utf-8'))
    suffix='자료' if names is None else '보완자료'
    result={'name':f'chida-{id[:8]}-{suffix}.zip','base64':base64.b64encode(buffer.getvalue()).decode('ascii'),'work_order':order}
    if names is not None:result['chunks']=ordered
    return result


def repair(path,vod,id):
    saved,source=exchange.load_active(path,vod,id)
    missing=[c['id'] for c in saved['chunks'] if c['id'] not in saved['replies']]
    if not missing:raise ValueError('미수신 묶음이 없습니다. 정상 결과는 다시 요청하지 않습니다')
    return pack_snapshot(saved,source,missing)


def unpack(encoded):
    if not isinstance(encoded,str) or len(encoded)>4*((MAX_BYTES+2)//3):raise ValueError('결과 ZIP은 10MiB 이내로 선택하세요')
    try:content=base64.b64decode(encoded,validate=True)
    except (ValueError,binascii.Error):raise ValueError('ZIP 파일 데이터를 읽지 못했습니다') from None
    if len(content)>MAX_BYTES:raise ValueError('결과 ZIP은 10MiB 이내로 선택하세요')
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            members=archive.infolist()
            if len(members)>MAX_MEMBERS:raise ValueError('ZIP 내부 항목이 너무 많습니다')
            if sum(m.file_size for m in members)>MAX_BYTES:raise ValueError('ZIP 압축을 푼 전체 크기는 10MiB 이내여야 합니다')
            files=[];seen=set()
            for member in members:
                # Windows의 ZipInfo는 역슬래시를 정규화하므로 원래 이름을 먼저 검사한다.
                name=member.orig_filename;parts=name.rstrip('/').split('/')
                if not name or '\\' in name or '\x00' in member.orig_filename or any(p in ('','..','.') for p in parts) or re.match(r'^[A-Za-z]:',name):
                    raise ValueError('ZIP 내부 경로가 올바르지 않습니다')
                if name.casefold() in seen:raise ValueError('ZIP 내부에 같은 이름의 파일이 중복되어 있습니다')
                seen.add(name.casefold())
                kind=stat.S_IFMT(member.external_attr>>16)
                if kind not in (0,stat.S_IFREG,stat.S_IFDIR):raise ValueError('ZIP의 링크·특수 파일은 허용하지 않습니다')
                if member.flag_bits&1:raise ValueError('암호화한 ZIP은 사용할 수 없습니다')
                if member.compress_type not in (zipfile.ZIP_STORED,zipfile.ZIP_DEFLATED):raise ValueError('일반 ZIP 압축 방식으로 다시 저장하세요')
                if member.is_dir() or parts[0]=='__MACOSX' or parts[-1]=='.DS_Store' or parts[-1].startswith('._'):continue
                if not name.lower().endswith('.json'):raise ValueError('결과 JSON 파일만 ZIP에 넣으세요. 입력 자료·작업서는 제외하세요')
                with archive.open(member) as stream:raw=stream.read(MAX_BYTES+1)
                if len(raw)!=member.file_size or len(raw)>MAX_BYTES:raise ValueError('ZIP 내부 파일 크기가 올바르지 않습니다')
                try:files.append((name,raw.decode('utf-8-sig'),None))
                except UnicodeDecodeError:files.append((name,None,'UTF-8 JSON으로 저장하세요'))
            if not files:raise ValueError('ZIP에 결과 JSON 파일이 없습니다')
            return files
    except (zipfile.BadZipFile,NotImplementedError,RuntimeError,EOFError,OverflowError,zlib.error):
        raise ValueError('손상되었거나 지원하지 않는 ZIP입니다. 결과 JSON들을 다시 압축하세요') from None
