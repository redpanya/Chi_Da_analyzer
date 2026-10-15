"""추가 화자 엔진만 복사한다. 개발 소스·빌드 캐시·모델·HF 인증은 포함하지 않는다."""
import shutil


def install(resources, pyannote, fluid):
    required=(pyannote/'pyannote-worker', fluid)
    for file in required:
        if not file.is_file(): raise ValueError('화자 실행기가 없습니다: '+str(file))
    target=resources/'diarization'
    shutil.copytree(pyannote,target/'pyannote',symlinks=True)
    (target/'fluid').mkdir()
    shutil.copyfile(fluid,target/'fluid/archive-fluid-diarizer')
    shutil.copymode(fluid,target/'fluid/archive-fluid-diarizer')
