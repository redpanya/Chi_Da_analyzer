"""한 번의 스트림 순회로 전체를 나눈다. 완료 파일은 덮어쓰지 않는다."""
import csv
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
from . import processes, split_contract as contract, split_media as media
from .source import check_cancel
from .split_storage import check_volume
from . import split_audio


def render(work):
    value = work.value
    source, plan = value['source'], value['plan']
    src = contract.unchanged(source)
    folder = contract.local_path(value['folder'], directory=True)
    if (folder.stat().st_dev, folder.stat().st_ino) != tuple(value['folder_identity']):
        raise ValueError('출력 폴더가 변경됐습니다. 기존 결과를 확인하세요')
    for entry in value['outputs'].values():
        if contract.identity(contract.inside(folder, entry['name'])) != entry['identity']:
            raise ValueError('완료 파일이 변경됐습니다. 새 작업으로 시작하세요')
    work.update(output_filesystem=check_volume(folder, source['identity']['bytes']))
    # 재개는 처음부터 동일한 패킷 배치를 재현하고 완료 조각만 버린다. 시크 시 오디오 중복을 피한다.
    needed = int(source['identity']['bytes']*1.05) + 256*1024**2
    if shutil.disk_usage(folder).free < needed:
        raise ValueError(f'추가 공간 약 {needed/1024**3:.1f}GiB가 필요합니다. 저장 공간을 확보하세요')
    attempt = Path(tempfile.mkdtemp(prefix='.split-', dir=folder))
    listing, progress, log = attempt/'closed.csv', attempt/'progress.txt', work.file.parent/'ffmpeg.log'
    video_start = float(next(s for s in source['streams'] if s['codec_type'] == 'video').get('start_time', 0)) - source['origin']
    args = ['ffmpeg', '-hide_banner', '-v', 'warning', '-nostdin', '-n', '-copyts', '-start_at_zero',
            *media.input_args(src), *split_audio.mapping(source, value.get('audio_selection')),
            '-map_metadata', '0', '-map_chapters', '-1',
            '-c', 'copy', '-avoid_negative_ts', 'disabled', '-f', 'segment',
            # segment muxer의 분할 시각은 기준 영상의 첫 PTS부터 센다. 오디오 선행분을 보존한다.
            '-reference_stream', 'v:0', '-segment_times', ','.join(f'{c["actual"]-video_start:.6f}' for c in plan['cuts']),
            # PTS가 영상 시간 단위로 반올림돼 경계보다 수십 μs 앞서는 경우 같은 키프레임을 유지한다.
            '-segment_time_delta', str(.5/source['fps']),
            '-reset_timestamps', '1', '-break_non_keyframes', '0', '-segment_format', 'mp4',
            '-segment_format_options', 'avoid_negative_ts=disabled', '-segment_list_type', 'csv',
            '-segment_list', str(listing), '-progress', str(progress), str(attempt/'part-%03d.mp4')]
    processed = set()
    work.update(message='재인코딩 없이 선택한 트랙 분할 저장 중', command=args, progress=0)

    def accept_closed():
        if not listing.exists():
            return
        rows = list(csv.reader(listing.read_text(encoding='utf-8').splitlines()))
        for index, row in enumerate(rows):
            if index in processed or len(row) != 3:
                continue
            if index >= len(plan['parts']) or row[0] != f'part-{index:03d}.mp4':
                raise ValueError('분할 도구의 출력 목록이 계획과 다릅니다')
            part = plan['parts'][index]
            if abs(float(row[1])-part['start']) > .05:
                raise ValueError('실제 분할 경계가 변경되었습니다. 출력 내용을 확인하세요')
            file = contract.inside(attempt, row[0])
            check_cancel(work.stop)
            if str(index) not in work.value['outputs']:
                work.update(message=f'{index+1}/{len(plan["parts"])} 파일 마무리·경계 검사 중')
                checked = media.verify(file, source, part, work.stop, value.get('audio_selection'))
                target = contract.inside(folder, part['name'])
                # 링크 생성은 이미 존재하는 경로를 원자적으로 덮어쓰지 않는다. 같은 볼륨 안에서만 수행한다.
                try:
                    os.link(file, target)
                except OSError:
                    # exFAT에는 하드링크가 없다. 독점 생성 후 복사하며 실패한 본 작업 파일만 제거한다.
                    if target.exists():
                        raise ValueError('동일 이름의 출력이 있습니다. 기존 파일은 덮어쓰지 않습니다') from None
                    created = False
                    try:
                        with target.open('xb') as dest, file.open('rb') as inp:
                            created = True
                            while block := inp.read(4*1024**2):
                                check_cancel(work.stop)
                                dest.write(block)
                            dest.flush(); os.fsync(dest.fileno())
                    except BaseException:
                        if created:
                            target.unlink(missing_ok=True)
                        raise
                record = part | checked | {'identity': contract.identity(target)}
                work.update(outputs=work.value['outputs'] | {str(index): record})
            file.unlink()
            processed.add(index)

    child = None
    try:
        with log.open('ab') as err:
            child = processes.popen(args, lock_fd=work.lock.fd, stdout=subprocess.DEVNULL, stderr=err)
            while child.poll() is None:
                check_cancel(work.stop)
                accept_closed()
                if progress.exists():
                    values = dict(line.split('=', 1) for line in progress.read_text(errors='replace').splitlines() if '=' in line)
                    at = max(0, int(values.get('out_time_us', '0'))/1000000)
                    work.update(progress=min(.99, at/source['duration']), message='재인코딩 없이 분할 저장 중', processed_seconds=at)
                if shutil.disk_usage(folder).free < 64*1024**2:
                    raise ValueError('저장 공간이 부족합니다. 완료 파일은 보존했습니다')
                time.sleep(.1)
            check_cancel(work.stop)
            if child.returncode:
                raise ValueError('분할 도구가 종료됐습니다. 디스크 연결·공간·파일 상태를 확인하세요. ' + log.read_text(errors='replace')[-1200:])
            accept_closed()
        contract.unchanged(source)
        if len(work.value['outputs']) != len(plan['parts']):
            raise ValueError('일부 파일이 완성되지 않았습니다. 완료 파일은 보존했습니다')
    finally:
        if child and child.poll() is None:
            processes.stop(child)
        # 직접 생성한 이번 임시 폴더만 정리한다. 완성 출력과 다른 시도의 파일에는 손대지 않는다.
        if attempt.exists() and not attempt.is_symlink():
            shutil.rmtree(attempt)
