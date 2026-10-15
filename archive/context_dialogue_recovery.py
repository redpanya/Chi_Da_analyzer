"""오류 재검토는 이전 결과를 보존한 새 실행에서 최초 영향 지점부터 재개한다."""
import shutil
import uuid
from .context_job import local
from .storage import read_json, save_json, stamp


def restore(job, saved):
    folder=local(job.path,f"runs/{saved['id']}")
    retry=folder/'retry-from.json'
    if not retry.exists():return saved
    if any(p.is_symlink() for p in folder.rglob('*')):raise ValueError('연결 파일이 있는 문맥 결과는 자동 복구 복사할 수 없습니다')
    previous=saved['id'];id=uuid.uuid4().hex;target=local(job.path,f'runs/{id}')
    shutil.copytree(folder,target)
    save_json(target/'dialogue-state.json',read_json(retry))
    (target/'retry-from.json').unlink()
    saved=saved|{'id':id,'recovered_from':previous,'created_at':stamp(),'complete':False}
    save_json(target/'result.json',saved)
    job.update(run=id,full_run=id,runs=job.value['runs']+[{'id':id,'scope':'full','label':'전체 영상 · 대사 중심 복구','title':stamp()}])
    return saved
