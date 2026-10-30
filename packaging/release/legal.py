"""고지·대응 소스를 수집하고 누락·해시 불일치 시 배포를 중단한다."""
import argparse
import hashlib
from http.client import IncompleteRead
from importlib.metadata import distributions
import json
from pathlib import Path, PureWindowsPath
import shutil
import socket
import ssl
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
import zipfile

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / "build/legal-sources"
TOKENS = ("license", "licence", "copying", "copyright", "notice", "authors")


def digest(file):
    with file.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def is_notice(name):
    # ThirdPartyNotices.txt, fastcluster-LICENSE.md도 놓치지 않는다.
    return any(token in name.lower() for token in TOKENS)


def checked_path(root, name):
    path = Path(name)
    if path.anchor or PureWindowsPath(name).anchor or ".." in path.parts or "\\" in name or ":" in name:
        raise ValueError("잘못된 고지·소스 경로: " + name)
    return root / path


def verify_materials(root=ROOT):
    manifest = json.loads((root / "licenses/manifest.json").read_text(encoding="utf-8"))
    for row in manifest["files"]:
        file = checked_path(root / "licenses", row["file"])
        if not file.is_file() or digest(file) != row["sha256"]:
            raise ValueError("고지 원문 누락 또는 해시 불일치: " + row["file"])
    required = {
        "onnxruntime/LICENSE", "onnxruntime/ThirdPartyNotices.txt",
        "models/CC-BY-4.0.txt", "models/Apache-2.0.txt",
        "fluidaudio/ThirdPartyLicenses/fastcluster-LICENSE.md",
        "fluidaudio/ThirdPartyLicenses/vbx-LICENSE.md",
    }
    if not required <= {row["file"] for row in manifest["files"]}:
        raise ValueError("필수 구성요소 고지가 없습니다")
    for name in ("LICENSE", "THIRD-PARTY-NOTICES.md", "docs/third-party-source-guide.md"):
        if not (root / name).is_file():
            raise ValueError("배포 이용 조건 문서가 없습니다: " + name)
    return manifest


def download(url, part, timeout=120):
    """임시 파일을 처음부터 받고 일시적인 통신 장애만 최대 3회 시도한다."""
    request = Request(url, headers={"User-Agent": "ChiDaanalyzer-source/1"})
    for attempt in range(3):
        try:
            with urlopen(request, timeout=timeout) as response, part.open("wb") as output:
                while block := response.read(1024 * 1024):
                    output.write(block)
            return
        except Exception as error:
            part.unlink(missing_ok=True)
            if isinstance(error, HTTPError):
                error.close()
            reason = error.reason if isinstance(error, URLError) else error
            retry = (error.code in (408, 425, 429, 500, 502, 503, 504)
                     if isinstance(error, HTTPError) else
                     isinstance(reason, (TimeoutError, ConnectionError, ssl.SSLEOFError, IncompleteRead))
                     or isinstance(reason, socket.gaierror) and reason.errno == socket.EAI_AGAIN)
            if not retry or attempt == 2:
                raise
            time.sleep(attempt + 1)


def fetch_sources(root=ROOT, cache=None):
    cache = cache or root / "build/legal-sources"
    cache.mkdir(parents=True, exist_ok=True)
    specs = json.loads((root / "packaging/release/legal_sources.json").read_text(encoding="utf-8"))
    for row in specs["sources"]:
        file = checked_path(cache, row["file"])
        file.parent.mkdir(parents=True, exist_ok=True)
        if not file.exists():
            part = file.with_name(file.name + ".part")
            try:
                download(row["url"], part)
                if digest(part) != row["sha256"]:
                    raise ValueError("대응 소스 체크섬 불일치: " + row["file"])
                part.replace(file)
            finally:
                part.unlink(missing_ok=True)
        if digest(file) != row["sha256"]:
            raise ValueError("대응 소스 체크섬 불일치: " + row["file"])
    return specs


def copy_static(folder, root=ROOT):
    verify_materials(root)
    folder.mkdir(parents=True, exist_ok=True)
    shutil.copytree(root / "licenses", folder / "licenses", dirs_exist_ok=True)
    # 자막 템플릿의 OFL 원문·출처는 앱 web 자산과 별도 고지 ZIP 모두에 보존한다.
    fonts = root / "web/fonts"
    if fonts.is_dir():
        for source in [*fonts.glob('*/OFL.txt'), fonts/'sources.json']:
            if source.is_file():
                dest=folder/'fonts'/source.relative_to(fonts);dest.parent.mkdir(parents=True,exist_ok=True)
                shutil.copy2(source,dest)
    for name in ("LICENSE", "THIRD-PARTY-NOTICES.md", "docs/third-party-source-guide.md"):
        dest = folder / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(root / name, dest)


def collect(folder, *, python_runtime=True, root=ROOT):
    copy_static(folder, root)
    if not python_runtime:
        return
    rows = []
    for dist in distributions():
        name = dist.metadata.get("Name", "unknown")
        # 배포판 이름과 원본 파일 경로를 파일명으로 만들고 경로 탈출을 막는다.
        safe_name = "".join(c if c.isalnum() or c in "-_." else "_" for c in name)
        notices = []
        for entry in dist.files or []:
            if is_notice(entry.name):
                source = Path(dist.locate_file(entry))
                if source.is_file():
                    relative = "python/" + safe_name + "/" + str(entry).replace("/", "_").replace("\\", "_")
                    dest = folder / relative
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, dest)
                    notices.append(relative)
        rows.append({"name": name, "version": dist.version, "notices": notices,
                     "license": dist.metadata.get("License-Expression") or dist.metadata.get("License")})
    (folder / "python-packages.json").write_text(
        json.dumps({"scope": "빌드 환경 목록; 실제 동봉 목록과 다름", "packages": rows},
                   ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    # 실행 시 쓰는 Python 버전의 원문을 받는다. 태그를 고정하며 코드로 실행하지 않는다.
    version = ".".join(map(str, sys.version_info[:3]))
    runtime = folder / "python-runtime"
    runtime.mkdir(exist_ok=True)
    url = f"https://raw.githubusercontent.com/python/cpython/v{version}/LICENSE"
    part = runtime / "LICENSE.part"
    try:
        download(url, part, timeout=60)
        data = part.read_bytes()
        if b"PYTHON SOFTWARE FOUNDATION LICENSE VERSION 2" not in data:
            raise ValueError("Python 런타임 고지 응답을 확인할 수 없습니다")
        part.replace(runtime / "LICENSE")
    finally:
        part.unlink(missing_ok=True)
    (runtime / "source.json").write_text(json.dumps(
        {"version": version, "url": url, "sha256": hashlib.sha256(data).hexdigest()},
        ensure_ascii=False, indent=2), encoding="utf-8")


def check_folder(folder, root=ROOT):
    expected = verify_materials(root)
    for row in expected["files"]:
        file = checked_path(folder / "licenses", row["file"])
        if not file.is_file() or digest(file) != row["sha256"]:
            raise ValueError("패키지 고지 누락 또는 변경: " + row["file"])
    for name in ("LICENSE", "THIRD-PARTY-NOTICES.md", "docs/third-party-source-guide.md"):
        if digest(folder / name) != digest(root / name):
            raise ValueError("패키지 이용 조건 불일치: " + name)


def zip_files(target, files, *, compression=zipfile.ZIP_DEFLATED):
    target.parent.mkdir(parents=True, exist_ok=True)
    part = target.with_name(target.name + ".part")
    try:
        with zipfile.ZipFile(part, "w", compression=compression) as archive:
            for file, name in sorted(files, key=lambda x: x[1]):
                # OS별 소스 ZIP을 동일한 내용·해시로 재현한다.
                info = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
                info.create_system = 3
                info.compress_type = compression
                info.external_attr = 0o100644 << 16
                archive.writestr(info, file.read_bytes())
        part.replace(target)
    finally:
        part.unlink(missing_ok=True)


def source_archive(target, root=ROOT):
    verify_materials(root)
    specs = fetch_sources(root)
    cache = root / "build/legal-sources"
    files = [(cache / row["file"], "sources/" + row["file"]) for row in specs["sources"]]
    for folder in (root / "licenses", root / "packaging/release/legal-recipes"):
        files += [(p, p.relative_to(root).as_posix()) for p in folder.rglob("*") if p.is_file()]
    for name in ("LICENSE", "THIRD-PARTY-NOTICES.md", "docs/third-party-source-guide.md",
                 "packaging/release/legal.py", "packaging/release/legal_sources.json"):
        files.append((root / name, name))
    # 소스는 이미 압축되어 있다. 재압축하지 않아 OS별 zlib 버전 차이도 배제한다.
    zip_files(target, files, compression=zipfile.ZIP_STORED)


def notice_archive(folder, target):
    check_folder(folder)
    zip_files(target, [(p, p.relative_to(folder).as_posix())
                       for p in folder.rglob("*") if p.is_file()])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("sources", "check", "notices", "source-archive"))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.action == "sources":
        fetch_sources()
    elif args.action == "check":
        verify_materials()
    elif args.action == "notices":
        if not args.output:
            parser.error("--output이 필요합니다")
        collect(args.output)
        check_folder(args.output)
    elif args.action == "source-archive":
        source_archive(args.output or ROOT / "dist/artifacts/legal-corresponding-sources.zip")
