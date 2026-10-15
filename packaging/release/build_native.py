"""llama.cpp·whisper.cpp를 독립 정적 실행 파일로 빌드한다."""
import os
import argparse
from pathlib import Path
import shutil
import subprocess
import sys
from fetch_sources import ROOT, fetch


def run(args): subprocess.run([str(x) for x in args], check=True)


def build(vulkan=False):
    if vulkan and sys.platform != 'win32': raise ValueError('Vulkan 실행기는 Windows 빌드에서만 만듭니다')
    specs = fetch()
    for name, targets in [('llama', ['llama-server','llama-completion','llama-tokenize']), ('whisper',['whisper-cli'])]:
        source = next((ROOT/'build/native-src'/name).iterdir())
        output_name = name+'-vulkan' if vulkan else name
        if vulkan and name == 'llama': targets = ['llama-server','llama-completion']
        build = ROOT/'build/native-build'/output_name
        flags = ['-DCMAKE_BUILD_TYPE=Release','-DBUILD_SHARED_LIBS=OFF','-DGGML_NATIVE=OFF',
                 '-DGGML_OPENMP=OFF','-DGGML_BACKEND_DL=OFF','-DGGML_CCACHE=OFF']
        if sys.platform == 'darwin':
            flags += ['-DCMAKE_OSX_DEPLOYMENT_TARGET=14.0','-DCMAKE_OSX_ARCHITECTURES=arm64',
                      '-DGGML_METAL=ON','-DGGML_METAL_EMBED_LIBRARY=ON']
        else:
            flags += ['-A','x64','-DGGML_AVX=ON','-DGGML_AVX2=OFF','-DGGML_FMA=OFF','-DGGML_F16C=OFF',
                      '-DGGML_AVX512=OFF','-DGGML_CPU_ALL_VARIANTS=OFF', '-DCMAKE_MSVC_RUNTIME_LIBRARY=MultiThreaded']
            flags += ['-DGGML_VULKAN='+('ON' if vulkan else 'OFF')]
            if vulkan:
                if not os.environ.get('VULKAN_SDK'): raise ValueError('공식 Vulkan SDK를 먼저 준비하세요')
                flags += ['-DCMAKE_CXX_FLAGS=/FS']
        if name == 'llama':
            flags += ['-DLLAMA_BUILD_TESTS=OFF','-DLLAMA_BUILD_EXAMPLES=OFF','-DLLAMA_BUILD_APP=OFF',
                      '-DLLAMA_OPENSSL=OFF','-DLLAMA_BUILD_UI=OFF','-DLLAMA_USE_PREBUILT_UI=OFF']
        else: flags += ['-DWHISPER_BUILD_TESTS=OFF']
        run(['cmake','-S',source,'-B',build,*flags])
        run(['cmake','--build',build,'--config','Release','--parallel','3','--target',*targets])
        dest = ROOT/'build/native'/output_name
        dest.mkdir(parents=True,exist_ok=True)
        suffix = '.exe' if os.name == 'nt' else ''
        for target in targets:
            found = list((build/'bin').rglob(target+suffix))
            if len(found) != 1: raise ValueError(f'{target} 빌드 출력이 없습니다')
            shutil.copy2(found[0],dest/found[0].name)
        shutil.copy2(source/'LICENSE',dest/'LICENSE')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--vulkan', action='store_true')
    build(parser.parse_args().vulkan)
