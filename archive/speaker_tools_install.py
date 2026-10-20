"""고정 공식 릴리스의 실행 도구만 검증 후 설치한다. 실패한 설치는 활성화하지 않는다."""
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import tempfile
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, HTTPRedirectHandler, build_opener
import uuid
import zipfile

from . import speaker_tools as tools
from .source import check_cancel
from .storage import ProjectLock, read_json, save_json

MAX_DOWNLOAD = 4 * 1024**3
MAX_EXPANDED = 12 * 1024**3
HOSTS = {'api.github.com', 'github.com', 'release-assets.githubusercontent.com', 'objects.githubusercontent.com'}


def allowed(url):
    parsed = urlsplit(url)
    if parsed.scheme != 'https' or parsed.hostname not in HOSTS or parsed.username or parsed.password or parsed.port or parsed.fragment:
        raise ValueError('실행 도구의 배포 주소를 확인할 수 없습니다')
    return url


class Redirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return super().redirect_request(req, fp, code, msg, headers, allowed(newurl))


def open_url(url):
    try:
        return build_opener(Redirects()).open(Request(allowed(url), headers={'User-Agent':'ChiDaAnalyzer-speaker-tools'}), timeout=20)
    except HTTPError: raise
    except (URLError, TimeoutError):
        raise ValueError('실행 도구 배포 서버에 연결하지 못했습니다. 인터넷 연결을 확인하고 다시 설치하세요') from None


def release_asset(backend, stop):
    check_cancel(stop)
    name = f'chida-{backend}-{tools.platform_id()}.zip'
    try:
        with open_url(f'https://api.github.com/repos/{tools.REPOSITORY}/releases/tags/{tools.RELEASE}') as response:
            raw = response.read(2 * 1024**2 + 1)
        if len(raw) > 2 * 1024**2: raise ValueError('실행 도구 배포 정보 크기가 예상과 다릅니다')
        release = json.loads(raw)
    except HTTPError as error:
        if error.code == 404: raise ValueError('실행 도구 설치 파일이 아직 공개 배포되지 않았습니다. 관리자에게 실행 도구 배포를 요청하세요') from None
        if error.code in (403, 429): raise ValueError('실행 도구 배포 서버의 요청 제한입니다. 잠시 후 다시 설치하세요') from None
        raise
    check_cancel(stop)
    if release.get('draft') or release.get('tag_name') != tools.RELEASE: raise ValueError('공개 실행 도구 릴리스를 확인하지 못했습니다')
    matches = [v for v in release.get('assets', []) if v.get('name') == name and v.get('state') == 'uploaded']
    if len(matches) != 1: raise ValueError('현재 운영체제용 실행 도구가 아직 배포되지 않았습니다')
    asset = matches[0]
    digest = asset.get('digest') or ''
    expected = f'https://github.com/{tools.REPOSITORY}/releases/download/{tools.RELEASE}/{name}'
    if (asset.get('browser_download_url') != expected or not re.fullmatch(r'sha256:[0-9a-f]{64}', digest)
            or type(asset.get('size')) is not int or not 0 < asset['size'] <= MAX_DOWNLOAD):
        raise ValueError('실행 도구의 크기·SHA-256 배포 정보를 확인하지 못했습니다')
    return {'url': expected, 'size': asset['size'], 'sha256': digest[7:]}


def download(asset, target, stop, update):
    digest = hashlib.sha256(); size = 0
    with open_url(asset['url']) as response, target.open('xb') as output:
        while block := response.read(1024 * 1024):
            check_cancel(stop)
            size += len(block)
            if size > asset['size']: raise ValueError('실행 도구 다운로드 크기가 예상과 다릅니다')
            digest.update(block); output.write(block)
            update(message='실행 도구 다운로드 중', progress={'bytes':size, 'total_bytes':asset['size']})
    check_cancel(stop)
    if size != asset['size'] or digest.hexdigest() != asset['sha256']:
        raise ValueError('실행 도구 다운로드 SHA-256 검사가 실패했습니다. 기존 설치는 유지됩니다')


def extract(archive, folder, stop):
    with zipfile.ZipFile(archive) as source:
        infos = source.infolist()
        size = sum(v.file_size for v in infos)
        if len(infos) > 100000 or size > MAX_EXPANDED: raise ValueError('실행 도구 압축 해제 크기가 제한을 넘습니다')
        if shutil.disk_usage(folder).free < size + 256 * 1024**2: raise OSError(28, '실행 도구 설치 공간 부족')
        seen = set()
        for info in infos:
            check_cancel(stop)
            path = PurePosixPath(info.filename)
            mode = info.external_attr >> 16
            # Windows 드라이브/ADS·대소문자 충돌과 macOS/Unix 연결 파일을 함께 거부한다.
            if (not path.parts or path.is_absolute() or any(p in ('.','..') or ':' in p or p.endswith((' ','.')) or
                    re.fullmatch(r'(CON|PRN|AUX|NUL|COM[0-9]|LPT[0-9])(?:\..*)?',p,re.I) for p in path.parts)
                    or '\\' in info.filename or '\x00' in info.filename or
                    stat.S_IFMT(mode) not in (0, stat.S_IFREG, stat.S_IFDIR)):
                raise ValueError('실행 도구 압축 파일의 경로 또는 연결 파일이 안전하지 않습니다')
            key = str(path).casefold()
            if key in seen: raise ValueError('실행 도구 압축 파일의 경로가 중복됩니다')
            seen.add(key)
            target = folder.joinpath(*path.parts)
            if info.is_dir(): target.mkdir(parents=True, exist_ok=True); continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with source.open(info) as data, target.open('xb') as output:
                while block := data.read(1024 * 1024):
                    check_cancel(stop); output.write(block)
            target.chmod(0o755 if mode & 0o111 else 0o644)


def install(backend, stop, lock, update):
    if not tools.supported(backend): raise ValueError('이 장치에서는 선택 실행 도구를 지원하지 않습니다')
    root = tools.home(backend)
    for path in [root, *root.parents]:
        if path.is_symlink(): raise ValueError('실행 도구 설치 경로의 연결 폴더는 사용할 수 없습니다')
    with ProjectLock(root):
        if (root/'versions').is_symlink() or (root/'active.json').is_symlink():
            raise ValueError('실행 도구 설치 경로의 연결 파일은 사용할 수 없습니다')
        update(message='선택 실행 도구의 배포 정보를 확인합니다', progress={})
        asset = release_asset(backend, stop)
        if shutil.disk_usage(root).free < asset['size'] + 256 * 1024**2: raise OSError(28, '실행 도구 다운로드 공간 부족')
        with tempfile.TemporaryDirectory(prefix='.install-', dir=root) as temp:
            stage = Path(temp); archive = stage/'download.zip'; package = stage/'package'; package.mkdir()
            download(asset, archive, stop, update)
            update(message='실행 도구 압축 해제·호환성 검사 중', progress={})
            extract(archive, package, stop)
            manifest = read_json(package/'tool.json')
            if (manifest.get('backend'), manifest.get('protocol'), manifest.get('platform'), manifest.get('entry')) != (
                    backend, tools.PROTOCOL, tools.platform_id(), tools.entry_name(backend)):
                raise ValueError('실행 도구가 현재 앱·운영체제와 호환되지 않습니다')
            file = package/tools.entry_name(backend)
            if not file.is_file(): raise ValueError('실행 도구 파일이 없습니다')
            tools.check([str(file), '--speaker-tool-check'], root/'last-install.log', stop, lock, backend)
            check_cancel(stop)
            version = uuid.uuid4().hex
            versions = root/'versions'; versions.mkdir(exist_ok=True)
            final = versions/version
            package.replace(final)
            try:
                check_cancel(stop)
                save_json(root/'active.json', {'version':version, 'sha256':asset['sha256'], 'release':tools.RELEASE})
            except BaseException:
                shutil.rmtree(final)
                raise
        update(message='실행 도구 설치 완료 · 기존 모델·분석 결과 보존', progress={})
