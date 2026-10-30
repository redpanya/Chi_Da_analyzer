import {timecode} from './player.js';
export function vodDuration(project){
  const range=project?.download_range;
  return project?.tasks?.video?.verification?.duration??(range?(range.end_ms-range.start_ms)/1000:project?.metadata?.duration);
}
export function vodLabel(project){
  const seconds=vodDuration(project);
  return (project?.metadata?.title||'제목 없음')+(Number.isFinite(seconds)&&seconds>=0?` (${timecode(seconds*1000)})`:' (길이 미확인)');
}
