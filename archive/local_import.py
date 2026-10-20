"""브라우저 첨부를 조각별 검증하며 보관함에 복사한다. 외부 파일 경로를 받지 않는다."""
import hashlib
import math
import os
from pathlib import Path
import shutil
import threading
import uuid

from . import video, chat, task_timing
from .source import check_cancel, Cancelled, safe_error
from .storage import read_json, save_json, Conflict

CHUNK = 4 * 1024**2

def options(value):
    if not isinstance(value,dict) or set(value)!={'name','size','start_vod_ms','confirmed'}:
        raise ValueError('첨부 파일과 영상 시간 연결을 확인하세요')
    if not isinstance(value['name'],str) or not 1<=len(value['name'])<=255 or Path(value['name']).suffix.lower() not in ('.mp4','.mov','.mkv'):
        raise ValueError('MP4·MOV·MKV 비디오 파일을 선택하세요')
    if type(value['size']) is not int or not 0<value['size']<=2*1024**4:
        raise ValueError('파일 크기를 확인하세요 (최대 2TB)')
    if type(value['start_vod_ms']) is not int or not 0<=value['start_vod_ms']<=7*86400000 or value['confirmed'] is not True:
        raise ValueError('같은 VOD의 연속 영상인지, 시작 시각이 맞는지 확인하세요')
    return dict(value)

class Upload:
    def __init__(self,project):
        self.project=project;self.path=project.path;self.stop=threading.Event();self.closed=False;self.thread=None
        self.id=uuid.uuid4().hex
        self.folder=self.path/'media';self.folder.mkdir(exist_ok=True)
        if any(p.is_symlink() for p in self.folder.iterdir()): raise ValueError('미디어 연결 파일은 지원하지 않습니다')
        self.part=self.folder/'import.part';self.record=self.folder/'import.json'
        self.input=project.data['input'];self.sha=[]
        if self.record.exists():
            old=read_json(self.record)
            if old['input']!=self.input:raise Conflict('다른 파일의 가져오기가 있습니다. 같은 파일을 선택하거나 다른 보관함을 사용하세요')
            self.sha=old['chunks']
        # 확정 이름으로 이동한 직후 종료된 경우도 같은 첨부 해시로 다시 검증한다.
        original=self.folder/('imported'+Path(self.input['name']).suffix.lower())
        if not self.part.exists() and self.sha and original.is_file():
            if original.stat().st_size != self.input['size']: raise ValueError('확정 복사본 크기가 맞지 않습니다')
            self.part=original
        if self.part.exists():
            if self.part.stat().st_size < self.bytes: raise ValueError('임시 파일이 완료 기록보다 짧습니다. 다른 보관함에서 새로 가져오세요')
            if self.part != original:
                with self.part.open('r+b') as f:f.truncate(min(len(self.sha)*CHUNK,self.input['size']))
        elif self.sha:raise ValueError('가져오기 임시 파일이 없어 이어갈 수 없습니다')
        self.checked=0
        self.project.update('video',state='running',message='첨부 파일을 이 Mac의 보관함에 복사합니다',timing=task_timing.start(project.data['tasks']['video'],resume=True),progress={'bytes':self.bytes,'total_bytes':self.input['size']})

    @property
    def bytes(self):return min(len(self.sha)*CHUNK,self.input['size'])

    def status(self):return {'upload':self.id,'chunk_size':CHUNK,'chunks':len(self.sha),'bytes':self.bytes,'total_bytes':self.input['size']}

    def chunk(self,index,sha,body=None):
        check_cancel(self.stop)
        if self.thread or self.closed:raise Conflict('현재 파일을 받을 수 없습니다')
        if type(index) is not int or index!=self.checked or index>len(self.sha):raise ValueError('파일 조각 순서가 맞지 않습니다. 같은 파일을 다시 선택하세요')
        if not isinstance(sha,str) or len(sha)!=64:raise ValueError('파일 조각 해시가 없습니다')
        if index<len(self.sha):
            if sha!=self.sha[index]:raise ValueError('다른 파일입니다. 이전 파일과 조각 해시가 다릅니다')
        else:
            size=min(CHUNK,self.input['size']-self.bytes)
            if size<=0 or not body or len(body)!=size or hashlib.sha256(body).hexdigest()!=sha:raise ValueError('전송한 파일 조각의 크기 또는 해시가 맞지 않습니다')
            if shutil.disk_usage(self.path).free<size+128*1024**2:raise OSError('보관함 저장 공간이 부족합니다')
            with self.part.open('ab') as f:f.write(body);f.flush();os.fsync(f.fileno())
            self.sha.append(sha);save_json(self.record,{'input':self.input,'chunks':self.sha})
        self.checked+=1
        self.project.update('video',progress={'bytes':self.bytes,'total_bytes':self.input['size']},message='첨부 파일 복사·기존 조각 확인 중')
        return self.status()

    def finish(self):
        if self.bytes!=self.input['size'] or self.checked!=len(self.sha):raise ValueError('전체 파일 조각을 확인하지 못했습니다')
        if self.thread:raise Conflict('영상 검사 중입니다')
        self.thread=threading.Thread(target=self.verify,daemon=True);self.thread.start()

    def verify(self):
        phase='video'
        try:
            self.project.update('video',state='verifying',message='복사본 무결성·영상 전체 디코딩 검사 중')
            digest=hashlib.sha256()
            with self.part.open('rb') as f:
                for sha in self.sha:
                    check_cancel(self.stop);block=f.read(CHUNK)
                    if hashlib.sha256(block).hexdigest()!=sha:raise ValueError('보관함 복사본 검사에 실패했습니다')
                    digest.update(block)
                if f.read(1):raise ValueError('복사본 뒤에 알 수 없는 데이터가 있습니다')
            detail=video.probe(self.part);duration=float(detail['format']['duration'])
            if not math.isfinite(duration) or duration>7*86400:raise ValueError('지원 영상 길이를 벗어났습니다')
            video.run_media(['ffmpeg','-nostdin','-v','error','-xerror','-i',str(self.part),'-map','0:v:0','-map','0:a?','-f','null','-'],self.project,self.stop,'import-decode.log')
            original=self.folder/('imported'+Path(self.input['name']).suffix.lower())
            # 원본 확정은 모든 검사 성공 후에만 한다. 실패·중단은 .part에서 재개한다.
            playback=original
            if not video.reusable_mp4(original,detail):
                if shutil.disk_usage(self.path).free<self.input['size']*2+256*1024**2:raise OSError('재생용 MP4를 만들 저장 공간이 부족합니다')
                self.project.update('video',state='exporting',message='원본을 유지하고 호환 재생용 MP4 생성 중')
                pending=self.folder/'import-playback.part.mp4'
                video.run_media(['ffmpeg','-nostdin','-v','error','-y','-i',str(self.part),'-map','0:v:0','-map','0:a?','-c:v','libx264','-preset','veryfast','-crf','18','-pix_fmt','yuv420p','-c:a','aac','-movflags','+faststart',str(pending)],self.project,self.stop,'import-playback.log')
                check=video.probe(pending)
                video.validate_playback(self.project,self.part,detail,pending,check,False,self.stop)
                duration=float(check['format']['duration'])
                video.run_media(['ffmpeg','-nostdin','-v','error','-xerror','-i',str(pending),'-f','null','-'],self.project,self.stop,'import-playback-check.log')
                playback=self.folder/'import-playback.mp4';pending.replace(playback)
            check_cancel(self.stop)
            if self.part != original:
                if original.exists():raise Conflict('기존 원본 복사본이 있어 덮어쓰지 않습니다')
                self.part.replace(original)
            self.project.update('video',state='complete',message='내 비디오 복사·검사 완료 · 첨부 원본은 그대로입니다',
                verification={'duration':duration,'sha256':digest.hexdigest(),'source':'local',
                              'files':{'original':video.media_timeline.identity(original),'playback':video.media_timeline.identity(playback)}},
                assets={'original':str(original.relative_to(self.path)),'playback':str(playback.relative_to(self.path))})
            phase='chat'
            if self.project.snapshot()['tasks']['chat']['state'] not in ('complete','empty','unavailable'):
                self.project.update('chat',state='running',message='전체 채팅 수집 중',timing=task_timing.start(self.project.snapshot()['tasks']['chat'],resume=True))
                chat.collect(self.project,self.stop)
        except Exception as error:
            paused=isinstance(error,Cancelled) or self.stop.is_set()
            try:self.project.update(phase,state='paused' if paused else 'error',message=('중단했습니다. 같은 파일을 다시 첨부해 이어받으세요' if phase=='video' else '채팅 수집을 중단했습니다. 채팅 이어받기를 누르세요') if paused else safe_error(error))
            except OSError:pass
        finally:self.project.lock.close();self.closed=True

    def cancel(self):
        self.stop.set()
        if not self.thread:
            try:self.project.update('video',state='paused',message='같은 파일을 다시 첨부해 이어받으세요')
            finally:self.project.lock.close();self.closed=True
