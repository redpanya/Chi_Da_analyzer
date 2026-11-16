"""배포 이미지 안의 앱 경로와 Apple Silicon 로컬 서명을 확인한다."""
import subprocess


def verify_bundle(app):
    for file in (app, *app.rglob('*')):
        if not file.name.isascii() or (file.is_symlink() and not str(file.readlink()).isascii()):
            raise ValueError(f'번들 경로의 파일 이름을 확인하세요: {file.name}')
    subprocess.run(['codesign', '--verify', '--deep', '--strict', str(app)], check=True, timeout=90)
