export function speakerColor(id) {
  if (!id) return '#81968a';
  let value = 0;
  for (const char of id) value = (value * 31 + char.charCodeAt(0)) >>> 0;
  return `hsl(${value % 360} 48% 66%)`;
}

export function selectedRange(start, end, duration) {
  if (![start, end, duration].every(Number.isFinite) || start < 0 || end <= start || end > duration) {
    throw Error('선택 범위는 영상 안에서 시작 < 끝이어야 합니다.');
  }
  return {start_ms: Math.round(start), end_ms: Math.round(end)};
}

export function createTimeline({canvas, onSeek, onRange}) {
  let info = null, position = 0, range = null, down = null;
  function draw() {
    if (!info || !canvas.clientWidth) return;
    const width = canvas.clientWidth, scale = devicePixelRatio || 1, left = 86, area = width - left;
    canvas.width = width * scale; canvas.height = 192 * scale;
    const ctx = canvas.getContext('2d'); ctx.scale(scale, scale);
    ctx.fillStyle = '#FAFAFA'; ctx.fillRect(0, 0, width, 192);
    const x = ms => left + Math.max(0, Math.min(1, ms / info.duration_ms)) * area;
    const block = (start, end, y, h, color) => { ctx.fillStyle = color; ctx.fillRect(x(start), y, Math.max(1, x(end) - x(start)), h); };
    const stripe = (start, end, y, h) => {
      block(start, end, y, h, '#E5E2DE'); ctx.strokeStyle = '#99938D';
      ctx.save(); ctx.beginPath(); ctx.rect(x(start), y, Math.max(0, x(end) - x(start)), h); ctx.clip();
      for (let at = x(start) - h; at < x(end); at += 10) { ctx.beginPath(); ctx.moveTo(at, y + h); ctx.lineTo(at + h, y); ctx.stroke(); }
      ctx.restore();
    };
    for (const [label, y] of [['채팅 / 10초', 25], ['반응 후보', 87], ['발언·화자', 125], ['인식 실패', 165]]) {
      ctx.fillStyle = '#54504A'; ctx.font = '11px sans-serif'; ctx.fillText(label, 5, y);
      block(0, info.duration_ms, y + 7, 1, '#324238');
    }
    const max = Math.max(1, ...info.graph.map(r => r.messages || 0));
    if (!info.graph.length) stripe(0, info.duration_ms, 12, 42);
    for (const bin of info.graph) {
      const start = bin.start_ms + info.chat_offset_ms, end = bin.end_ms + info.chat_offset_ms;
      if (bin.coverage !== 'known' || info.boundary_unverified) stripe(start, end, 12, 42);
      if (bin.messages != null) { const h = bin.messages / max * 42; block(start, end, 54 - h, h, '#86c99d'); }
    }
    for (const row of info.reactions) block(row.start_ms, row.end_ms, 69, 18, '#daba7d');
    stripe(info.processed_ms, info.duration_ms, 105, 31);
    for (const row of info.tracks) {
      block(row.start_ms, row.end_ms, 105, 31, speakerColor(row.speaker));
      if (row.status === 'failed') block(row.start_ms, row.end_ms, 151, 18, '#f4a47d');
    }
    if (range) { block(range.start_ms, range.end_ms, 3, 182, '#B7481F18'); ctx.strokeStyle = '#B7481F'; ctx.strokeRect(x(range.start_ms), 3, x(range.end_ms) - x(range.start_ms), 182); }
    ctx.strokeStyle = '#18181B'; ctx.lineWidth = 2; ctx.beginPath(); ctx.moveTo(x(position), 0); ctx.lineTo(x(position), 192); ctx.stroke();
  }
  function at(event) {
    const bounds = canvas.getBoundingClientRect();
    return Math.round(Math.max(0, Math.min(1, (event.clientX - bounds.left - 86) / (bounds.width - 86))) * info.duration_ms);
  }
  canvas.onpointerdown = event => { if (info) { down = {ms: at(event), x: event.clientX}; canvas.setPointerCapture(event.pointerId); } };
  canvas.onpointerup = event => {
    if (!down || !info) return;
    const start = down; down = null;
    if (Math.abs(event.clientX - start.x) > 5) onRange(Math.min(start.ms, at(event)), Math.max(start.ms, at(event)));
    else onSeek(at(event));
  };
  canvas.onpointercancel = () => { down = null; };
  new ResizeObserver(draw).observe(canvas);
  return {set(value, ms, selection) { info = value; position = ms; range = selection; draw(); }};
}
