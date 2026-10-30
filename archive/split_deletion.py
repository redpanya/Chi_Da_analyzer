"""선택한 분할 작업의 소유 파일을 확인한 뒤 휴지통으로 이동한다."""
import hashlib
import json
from pathlib import Path
import re

from . import split_contract as contract
from .deletion import trash_path
from .storage import Conflict, read_json, save_json
from .file_metadata import owned_metadata


def _folder(path):
    path = Path(path)
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise Conflict('연결 경로가 있는 작업은 삭제할 수 없습니다. 실제 저장 위치를 확인하세요')
    return contract.local_path(str(path), directory=True)


def _inventory(folder, allowed, source, other_sources):
    folder = _folder(folder)
    protected = set()
    for item in (source, *other_sources):
        original = Path(item['path']).resolve()
        if original == folder or folder in original.parents:
            raise Conflict('이 폴더의 파일을 원본으로 사용하는 작업이 있습니다. 원본을 보존하기 위해 삭제를 중단합니다')
        protected.add((item['identity']['device'], item['identity']['inode']))
        if original.exists():
            info = original.stat(); protected.add((info.st_dev, info.st_ino))
    rows, size = [], 0
    for file in sorted(folder.rglob('*')):
        relative = file.relative_to(folder).as_posix()
        info = file.lstat()
        metadata = owned_metadata(file,folder,allowed)
        if file.is_symlink() or (relative not in allowed and not metadata) or not (file.is_file() or file.is_dir()):
            raise Conflict('작업 외 파일 또는 연결 파일이 있습니다. 별도로 옮긴 뒤 다시 삭제하세요: ' + file.name)
        if (info.st_dev, info.st_ino) in protected:
            raise Conflict('원본 영상과 연결된 파일이 있어 삭제를 중단했습니다')
        rows.append([relative, info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns])
        if file.is_file(): size += info.st_size
    info = folder.stat()
    return [str(folder), info.st_dev, info.st_ino, rows], size


def preview(file, other_sources=()):
    value = read_json(file)
    if value.get('id') != file.parent.name:
        raise Conflict('작업 기록의 식별 정보가 다릅니다')
    source = value['source']
    record_names = {'manifest.json', 'ffmpeg.log'}
    record_names.update(p.name for p in file.parent.glob('manifest.json.*.tmp'))
    records, size = _inventory(file.parent, record_names, source, other_sources)
    snapshots = [records, value]
    output_folder = value.get('folder')
    output_count = 0
    if output_folder and not value.get('deleted_output_folder'):
        try:
            folder = _folder(output_folder)
        except FileNotFoundError:
            raise Conflict('출력 폴더를 찾을 수 없습니다. 저장 디스크를 연결하고 폴더 위치를 확인하세요') from None
        if [folder.stat().st_dev, folder.stat().st_ino] != value['folder_identity']:
            raise Conflict('출력 폴더가 다른 폴더로 바뀌었습니다. 삭제하지 않았습니다')
        records_folder = file.parent.resolve()
        if folder == records_folder or folder in records_folder.parents or records_folder in folder.parents:
            raise Conflict('작업 기록과 출력 폴더가 겹쳐 삭제할 수 없습니다')
        names = set()
        for record in value['outputs'].values():
            target = contract.inside(folder, record['name'])
            names.add(target.name)
            if target.exists():
                if contract.identity(target) != record['identity']:
                    raise Conflict('분할 결과가 변경되었습니다. 변경한 파일을 따로 옮긴 뒤 다시 삭제하세요')
                output_count += 1
        # 강제 종료 때 남은 마지막 FFmpeg 임시 폴더만 기록된 명령으로 식별한다.
        command = value.get('command') or []
        if command:
            pattern = Path(command[-1])
            attempt = pattern.parent
            if pattern.name == 'part-%03d.mp4' and attempt.parent == folder and re.fullmatch(r'\.split-[\w-]+', attempt.name):
                names.add(attempt.name)
                names.update(f'{attempt.name}/{name}' for name in ('closed.csv', 'progress.txt'))
                names.update(f'{attempt.name}/part-{i:03d}.mp4' for i in range(len(value['plan']['parts'])))
        outputs, output_size = _inventory(folder, names, source, other_sources)
        snapshots.append(outputs); size += output_size
    token = hashlib.sha256(json.dumps(snapshots, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    return {'id': value['id'], 'name': source['name'], 'created_at': value['created_at'],
            'bytes': size, 'output_count': output_count, 'folder': output_folder,
            'record_folder': str(file.parent), 'token': token}


def delete(file, token, other_sources=()):
    checked = preview(file, other_sources)
    if not isinstance(token, str) or token != checked['token']:
        raise Conflict('확인한 작업의 파일이 바뀌었습니다. 삭제 창을 다시 열어 확인하세요')
    value = read_json(file)
    if value.get('folder') and not value.get('deleted_output_folder'):
        # 두 위치를 동시에 이동할 수 없으므로 출력 이동 성공을 기록한 뒤 기록 폴더를 지운다.
        trash_path(Path(value['folder']))
        value.update(deleted_output_folder=True, state='deleting', message='분할 파일 삭제 완료 · 작업 기록 삭제를 다시 시도하세요')
        save_json(file, value)
    # 첫 이동 이후 다른 파일이 추가되었으면 기록을 보존하고 재확인하게 한다.
    preview(file, other_sources)
    trash_path(file.parent)
    return {'id': value['id'], 'deleted': True}
