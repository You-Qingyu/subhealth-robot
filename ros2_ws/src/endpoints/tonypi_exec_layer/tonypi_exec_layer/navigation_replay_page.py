"""生成可直接用 file:// 打开的逐帧回放页。"""

import json
from pathlib import Path


def frame_summary(record: dict) -> dict:
    """将浏览时需要的字段保存在页面内；完整记录仍在同名 JSON 中。"""
    fields = (
        'target_id', 'target_index', 'phase_before', 'phase_after', 'reason',
        'action_group', 'arrival_confirmations', 'scan_steps_completed',
        'head_pulse', 'head_stage', 'head_scan_direction', 'head_turn_direction',
        'capture_sequence', 'skipped_frames', 'read_finished_at_monotonic',
        'decision_at_monotonic', 'action_elapsed_ms', 'action_error',
        'next_observation_error', 'action_effect',
    )
    pose = record['target_pose']
    pose_fields = (
        'distance_m', 'bearing_deg', 'facing_error_deg', 'normal_bearing_deg',
        'reprojection_error_px', 'image_margin_px',
    )
    return {
        **{field: record.get(field) for field in fields},
        'detected_tag_ids': list(record['poses']),
        'target_pose': {field: pose[field] for field in pose_fields} if pose else None,
    }


def write_index(directory: Path, summaries: list[dict]) -> None:
    """原子更新单文件回放页；不要求浏览器从 file:// 发起 fetch。"""
    data = json.dumps(summaries, ensure_ascii=True).replace('<', '\\u003c')
    html = _PAGE.replace('FRAME_SUMMARIES', data)
    path = directory / 'index.html'
    temporary = path.with_suffix('.html.tmp')
    temporary.write_text(html, encoding='utf-8')
    temporary.replace(path)


_PAGE = """<!doctype html>
<html lang="zh"><meta charset="utf-8"><title>TonyPi 逐帧回放</title>
<style>
body{background:#202124;color:#eee;font:16px sans-serif;margin:0}
h1{text-align:center}
.controls{text-align:center}
button{padding:8px;margin:8px}
a{color:#8ab4f8}
.replay{display:grid;grid-template-columns:minmax(0,1fr) minmax(360px,520px);gap:16px;align-items:start;padding:0 16px}
img{display:block;max-width:100%;height:auto;margin:auto}
pre{background:#2b2c30;border-radius:4px;margin:0;max-height:80vh;overflow:auto;padding:16px;text-align:left;white-space:pre-wrap;word-break:break-word}
@media(max-width:900px){.replay{grid-template-columns:1fr}pre{max-height:none}}
</style>
<h1>TonyPi 逐帧回放</h1>
<div class="controls">
  <button onclick="show(index-1)">上一帧</button><span id="counter"></span>
  <button onclick="show(index+1)">下一帧</button>
  <button onclick="toggle()" id="play">播放</button>
  <a id="data" target="_blank">查看同名 JSON</a>
</div>
<div class="replay">
  <img id="frame" alt="当前观测帧">
  <pre id="details">读取页面内的帧摘要中……</pre>
</div>
<script>
const summaries = FRAME_SUMMARIES;
const total = summaries.length;
let index = 1, timer = null;
function format(value) { return value === null || value === undefined ? '—' : String(value); }
function render(summary) {
  const pose = summary.target_pose;
  const effect = summary.action_effect;
  const rows = [
    ['目标 Tag', summary.target_id], ['目标序号', summary.target_index],
    ['检出的 Tag', summary.detected_tag_ids.join(', ') || '无'],
    ['阶段', `${summary.phase_before} → ${summary.phase_after}`],
    ['决策原因', summary.reason], ['动作组', summary.action_group],
    ['到达连续帧', summary.arrival_confirmations],
    ['不可见转体次数', summary.scan_steps_completed],
    ['云台 PWM', summary.head_pulse], ['扫描帧阶段', summary.head_stage],
    ['云台扫描方向', summary.head_scan_direction],
    ['确认的机身转向', summary.head_turn_direction],
    ['目标距离 (m)', pose?.distance_m], ['目标偏角 (°)', pose?.bearing_deg],
    ['目标正对误差 (°)', pose?.facing_error_deg],
    ['法线水平角 (°)', pose?.normal_bearing_deg],
    ['重投影误差 (px)', pose?.reprojection_error_px],
    ['图像边距 (px)', pose?.image_margin_px],
    ['采集帧序号', summary.capture_sequence], ['跳过的帧数', summary.skipped_frames],
    ['主机读帧时间', summary.read_finished_at_monotonic],
    ['决策时间', summary.decision_at_monotonic],
    ['动作耗时 (ms)', summary.action_elapsed_ms],
    ['动作错误', summary.action_error],
    ['下一次观测错误', summary.next_observation_error],
    ['下次观测帧', effect?.next_observation_frame_id],
    ['动作后距离变化 (m)', effect?.distance_delta_m],
    ['动作后偏角变化 (°)', effect?.bearing_delta_deg],
  ];
  return rows.map(([label, value]) => `${label}：${format(value)}`).join('\\n');
}
function show(number) {
  index = Math.max(1, Math.min(total, number));
  const stem = String(index).padStart(6, '0');
  document.getElementById('frame').src = stem + '.png';
  document.getElementById('data').href = stem + '.json';
  document.getElementById('counter').textContent = `${index} / ${total}`;
  document.getElementById('details').textContent = render(summaries[index-1]);
}
function toggle() {
  if (timer) { clearInterval(timer); timer = null; }
  else timer = setInterval(() => show(index === total ? 1 : index + 1), 900);
  document.getElementById('play').textContent = timer ? '暂停' : '播放';
}
document.onkeydown = e => {
  if (e.key === 'ArrowLeft') show(index-1);
  if (e.key === 'ArrowRight') show(index+1);
};
show(1);
</script></html>
"""
