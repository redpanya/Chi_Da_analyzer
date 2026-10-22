import {timecode} from './player.js';
export function vodLabel(project){
  const seconds=project?.tasks?.video?.verification?.duration??project?.metadata?.duration;
  return (project?.metadata?.title||'제목 없음')+(Number.isFinite(seconds)&&seconds>=0?` (${timecode(seconds*1000)})`:' (길이 미확인)');
}
