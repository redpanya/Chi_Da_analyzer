"""고정 ggml 로더와 플러그인을 앱 안에 묶고 외부 Homebrew 경로를 제거한다."""
import hashlib
import shutil
import subprocess
import tarfile
import tempfile
from pathlib import Path

SOURCE_SHA='3db46896650440531f03fd5b6f29b4dbf4f5b0a4157e6f4be4786a12d8545971'

def run(*args):subprocess.run([str(x) for x in args],check=True)

def dependencies(file):
    return [line.strip().split(' (')[0] for line in subprocess.check_output(['otool','-L',str(file)],text=True).splitlines()[1:]]

def install(internal,archive):
    if hashlib.sha256(archive.read_bytes()).hexdigest()!=SOURCE_SHA:
        raise ValueError('ggml 0.26.0 공식 소스 압축 파일의 SHA-256이 다릅니다')
    plugins=Path('/opt/homebrew/opt/ggml/libexec')
    if not plugins.resolve().is_relative_to('/opt/homebrew/Cellar/ggml/0.26.0'):
        raise ValueError('ggml 플러그인도 고정 버전 0.26.0이어야 합니다')
    with tempfile.TemporaryDirectory(prefix='archive-ggml-') as tmp:
        folder=Path(tmp)
        with tarfile.open(archive) as source:source.extractall(folder,filter='data')
        build=folder/'build'
        # 기본 백엔드 탐색을 실행 파일 폴더로 돌린다. GGML_BACKEND_PATH는 대체 경로가 아니다.
        run('cmake','-S',folder/'ggml-0.26.0','-B',build,'-DCMAKE_BUILD_TYPE=Release',
            '-DGGML_BACKEND_DL=ON','-DGGML_BACKEND_DIR=','-DGGML_CPU=OFF','-DGGML_METAL=OFF',
            '-DGGML_BLAS=OFF','-DGGML_OPENMP=OFF','-DGGML_CCACHE=OFF','-DGGML_BUILD_TESTS=OFF','-DGGML_BUILD_EXAMPLES=OFF')
        run('cmake','--build',build,'--target','ggml','-j','6')
        loader=internal/'libggml.0.dylib'
        shutil.copyfile(build/'src/libggml.0.26.0.dylib',loader)
    run('install_name_tool','-id','@rpath/libggml.0.dylib',loader)
    for dep in dependencies(loader):
        if Path(dep).name.startswith('libggml-base.'):
            run('install_name_tool','-change',dep,'@loader_path/libggml-base.0.dylib',loader)
    run('codesign','--force','--sign','-',loader)
    files=sorted(plugins.glob('*.so'))
    if not files:raise ValueError('앱에 포함할 ggml CPU/Metal 플러그인이 없습니다')
    for source in files:
        dest=internal/'bin'/source.name;shutil.copyfile(source,dest)
        for dep in dependencies(dest):
            if Path(dep).name.startswith('libggml-base.'):
                run('install_name_tool','-change',dep,'@loader_path/../libggml-base.0.dylib',dest)
            elif dep.endswith('/libomp.dylib'):
                run('install_name_tool','-change',dep,'@loader_path/../whisper-libs/libomp.dylib',dest)
            elif dep.startswith('/opt/homebrew/'):
                raise ValueError('외부 라이브러리 의존성이 남았습니다: '+dep)
        run('codesign','--force','--sign','-',dest)
