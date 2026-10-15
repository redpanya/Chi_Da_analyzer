"""현재 분리 실행기 가상환경의 구성요소 출처와 라이선스를 수집한다."""
from importlib.metadata import distributions
from pathlib import Path
import argparse,json,shutil

p=argparse.ArgumentParser(description=__doc__);p.add_argument('worker',choices=['sam','roformer','pyannote']);args=p.parse_args()
root=Path(__file__).resolve().parent/'notices'/(args.worker+'-python');root.mkdir(exist_ok=True)
manifest=[]
for dist in distributions():
    name=dist.metadata['Name']
    for entry in dist.files or []:
        if entry.name.lower().startswith(('license','copying','notice')):
            source=Path(dist.locate_file(entry))
            if source.is_file():
                target=root/name/str(entry).replace('/','_');target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,target)
    manifest.append({'name':name,'version':dist.version,'license':dist.metadata.get('License-Expression') or dist.metadata.get('License'),'source':dist.metadata.get_all('Project-URL') or dist.metadata.get('Home-page')})
(root/'설치-목록.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
print(args.worker,len(manifest))
