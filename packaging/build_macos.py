"""ARM64 macOS 로컬 검증 앱을 새 출력 폴더에 조립한다. 사용자 보관함은 건드리지 않는다."""
import argparse,json,plistlib,shutil,subprocess,sys
from pathlib import Path

ROOT=Path(__file__).resolve().parent.parent

def run(*args):subprocess.run([str(a) for a in args],check=True)

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--backend',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--ggml-source-archive',type=Path,required=True)
 p.add_argument('--pyannote-backend',type=Path,required=True);p.add_argument('--fluid-binary',type=Path,required=True);a=p.parse_args()
 for folder,name in ((a.backend,'archive-backend'),(a.pyannote_backend,'pyannote-worker')):
  if not (folder/name).is_file():raise SystemExit('필수 실행기가 없습니다: '+str(folder/name))
 if not a.fluid_binary.is_file():raise SystemExit('FluidAudio 실행기가 없습니다')
 output=a.output.resolve();output.mkdir(parents=True,exist_ok=True)
 app=output/'ChiDaanalyzer.app'
 if app.exists():raise SystemExit('출력 앱이 이미 있습니다. 새 출력 폴더를 사용하세요')
 contents=app/'Contents';resources=contents/'Resources';(contents/'MacOS').mkdir(parents=True);resources.mkdir()
 shutil.copytree(a.backend,resources/'backend',symlinks=True)
 from diarization_bundle import install as install_diarization
 install_diarization(resources,a.pyannote_backend,a.fluid_binary)
 # Torch의 libomp와 현재 ggml의 libomp는 ABI가 달라 전사 프로세스용 복사본을 격리한다.
 internal=resources/'backend/_internal'
 run('xcrun','swiftc','-O','-target','arm64-apple-macos27.0',ROOT/'packaging/Trash.swift','-o',internal/'bin/vod-trash')
 run('codesign','--force','--sign','-',internal/'bin/vod-trash')
 ggml=internal/'libggml-base.0.dylib'
 original=Path('/opt/homebrew/opt/ggml/lib/libggml-base.0.dylib')
 dependencies=lambda f:[line.strip().split(' (')[0] for line in subprocess.check_output(['otool','-L',str(f)],text=True).splitlines()[1:]]
 omp=next(Path(p) for p in dependencies(original) if p.endswith('/libomp.dylib'))
 separate=internal/'whisper-libs';separate.mkdir();shutil.copyfile(omp,separate/'libomp.dylib')
 run('install_name_tool','-id','@rpath/libomp.dylib',separate/'libomp.dylib')
 for old in dependencies(ggml):
  if old.endswith('/libomp.dylib'):run('install_name_tool','-change',old,'@loader_path/whisper-libs/libomp.dylib',ggml)
 for file in (ggml,separate/'libomp.dylib'):run('codesign','--force','--sign','-',file)
 from ggml_bundle import install
 install(internal,a.ggml_source_archive)
 run('codesign','--force','--sign','-',internal/'Python.framework')
 run('xcrun','swiftc','-O','-target','arm64-apple-macos27.0',ROOT/'packaging/Launcher.swift','-o',contents/'MacOS/ArchiveLauncher')
 with (contents/'Info.plist').open('wb') as f:plistlib.dump({'CFBundleIdentifier':'local.chzzk.archive','CFBundleName':'ChiDaanalyzer','CFBundleDisplayName':'ChiDaanalyzer','CFBundleExecutable':'ArchiveLauncher','CFBundlePackageType':'APPL','CFBundleVersion':'25','CFBundleShortVersionString':'0.17.0','LSMinimumSystemVersion':'27.0','NSHighResolutionCapable':True,'NSHumanReadableCopyright':'로컬 검증 버전 · 구성요소 라이선스는 Resources/NOTICES 참조'},f)
 notice=resources/'NOTICES';notice.mkdir();shutil.copyfile(ROOT/'README.md',notice/'README.ko.md')
 shutil.copytree(ROOT/'packaging/notices',notice/'third-party',dirs_exist_ok=True)
 # 로컬 검증용 임시 서명. Developer ID 서명·공증을 대신하지 않는다.
 run('codesign','--force','--deep','--sign','-',app)
 from release.macos_package_check import verify_bundle
 verify_bundle(app)
 print(app)

if __name__=='__main__':main()
