"""将导航实际使用的每一帧保存为图片和同名机器可读记录。"""

from dataclasses import asdict
import json
from pathlib import Path
import uuid

import cv2
import numpy as np

from .camera import FrameObservation


class NavigationReplay:
    """一个任务的逐帧回放；不读取相机，也不执行动作。"""

    def __init__(self, root: Path, task_id: str) -> None:
        self.directory = root / uuid.uuid4().hex
        self.directory.mkdir(parents=True)
        (self.directory / 'raw').mkdir()
        self._task_id = task_id
        self._number = 0

    def record(
        self,
        frame: FrameObservation,
        tag_id: int,
        target_index: int,
        phase_before: str,
        phase_after: str,
        reason: str,
        action_group: str | None,
        confirmations: int,
        previous_action_frame: int | None,
        decision_at_monotonic: float,
    ) -> int:
        self._number += 1
        number = self._number
        stem = f'{number:06d}'
        pose = frame.poses.get(tag_id)
        record = {
            'task_id': self._task_id,
            'frame_id': number,
            'target_id': tag_id,
            'target_index': target_index,
            'read_finished_at_monotonic': frame.read_finished_at_monotonic,
            'read_started_at_monotonic': frame.read_started_at_monotonic,
            'capture_sequence': frame.capture_sequence,
            'skipped_frames': frame.skipped_frames,
            'decision_at_monotonic': decision_at_monotonic,
            'poses': {str(key): asdict(value) for key, value in frame.poses.items()},
            'target_pose': asdict(pose) if pose else None,
            'phase_before': phase_before,
            'phase_after': phase_after,
            'reason': reason,
            'action_group': action_group,
            'arrival_confirmations': confirmations,
            'previous_action_frame': previous_action_frame,
            'action_started_at_monotonic': None,
            'action_finished_at_monotonic': None,
            'action_elapsed_ms': None,
            'action_error': None,
            'action_effect': None,
            'next_observation_error': None,
            'raw_image': f'raw/{stem}.png',
        }
        if not cv2.imwrite(str(self.directory / 'raw' / f'{stem}.png'), frame.image):
            raise OSError(f'无法保存原始观测帧: {stem}')
        annotated = _annotate(frame, record)
        if not cv2.imwrite(str(self.directory / f'{stem}.png'), annotated):
            raise OSError(f'无法保存标注观测帧: {stem}')
        self._write_record(number, record)
        self._write_index()
        if previous_action_frame is not None:
            self._record_action_effect(previous_action_frame, number, frame)
        return number

    def action_started(self, frame_id: int, started_at_monotonic: float) -> None:
        path = self.directory / f'{frame_id:06d}.json'
        record = json.loads(path.read_text(encoding='utf-8'))
        record['action_started_at_monotonic'] = started_at_monotonic
        self._write_record(frame_id, record)

    def action_finished(
        self,
        frame_id: int,
        elapsed_ms: int,
        error: str | None = None,
        finished_at_monotonic: float | None = None,
    ) -> None:
        path = self.directory / f'{frame_id:06d}.json'
        record = json.loads(path.read_text(encoding='utf-8'))
        record['action_elapsed_ms'] = elapsed_ms
        record['action_error'] = error
        record['action_finished_at_monotonic'] = finished_at_monotonic
        self._write_record(frame_id, record)

    def observation_failed(self, frame_id: int, error_code: str) -> None:
        path = self.directory / f'{frame_id:06d}.json'
        record = json.loads(path.read_text(encoding='utf-8'))
        record['next_observation_error'] = error_code
        self._write_record(frame_id, record)

    def _record_action_effect(
        self,
        action_frame_id: int,
        observation_frame_id: int,
        frame: FrameObservation,
    ) -> None:
        path = self.directory / f'{action_frame_id:06d}.json'
        record = json.loads(path.read_text(encoding='utf-8'))
        before = record['target_pose']
        after_pose = frame.poses.get(record['target_id'])
        after = asdict(after_pose) if after_pose else None
        finished_at = record['action_finished_at_monotonic']
        observation_at = frame.read_finished_at_monotonic
        record['action_effect'] = {
            'next_observation_frame_id': observation_frame_id,
            'next_observation_at_monotonic': observation_at,
            'next_observation_delay_ms': (
                round((observation_at - finished_at) * 1000)
                if finished_at is not None else None
            ),
            'target_detected': after is not None,
            'distance_delta_m': _delta(before, after, 'distance_m'),
            'bearing_delta_deg': _delta(before, after, 'bearing_deg'),
            'normal_bearing_delta_deg': _delta(
                before, after, 'normal_bearing_deg'
            ),
            'facing_error_delta_deg': _delta(
                before, after, 'facing_error_deg'
            ),
            'image_margin_delta_px': _delta(
                before, after, 'image_margin_px'
            ),
        }
        self._write_record(action_frame_id, record)

    def _write_record(self, frame_id: int, record: dict) -> None:
        path = self.directory / f'{frame_id:06d}.json'
        temporary = path.with_suffix('.json.tmp')
        temporary.write_text(
            json.dumps(record, ensure_ascii=False, indent=2) + '\n', encoding='utf-8'
        )
        temporary.replace(path)

    def _write_index(self) -> None:
        page = """<!doctype html>
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
  <img id="frame" alt="当前决策帧">
  <pre id="details">读取帧记录中……</pre>
</div>
<script>
const total = FRAME_COUNT;
let index = 1, timer = null, requestNumber = 0;
async function show(number) {
  index = Math.max(1, Math.min(total, number));
  const stem = String(index).padStart(6, '0');
  const currentRequest = ++requestNumber;
  document.getElementById('frame').src = stem + '.png';
  document.getElementById('data').href = stem + '.json';
  document.getElementById('counter').textContent = `${index} / ${total}`;
  const details = document.getElementById('details');
  details.textContent = '读取帧记录中……';
  try {
    const response = await fetch(stem + '.json', {cache: 'no-store'});
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const record = await response.json();
    if (currentRequest === requestNumber) {
      details.textContent = JSON.stringify(record, null, 2);
    }
  } catch (error) {
    if (currentRequest === requestNumber) {
      details.textContent = `无法读取 ${stem}.json：${error}`;
    }
  }
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
        (self.directory / 'index.html').write_text(
            page.replace('FRAME_COUNT', str(self._number)), encoding='utf-8'
        )


def _annotate(frame: FrameObservation, record: dict) -> np.ndarray:
    image = frame.image.copy()
    for tag_id, pose in frame.poses.items():
        corners = np.rint(pose.image_corners_px).astype(np.int32)
        color = (0, 220, 0) if tag_id == record['target_id'] else (0, 180, 255)
        cv2.polylines(image, [corners], True, color, 2)
        cv2.putText(
            image, f'ID {tag_id} {pose.distance_m:.2f}m {pose.bearing_deg:.1f}deg',
            (int(corners[0][0]), max(20, int(corners[0][1]) - 5)),
            cv2.FONT_HERSHEY_SIMPLEX, 0.48, color, 2,
        )
    height, width = image.shape[:2]
    cv2.drawMarker(image, (width // 2, height // 2), (255, 255, 0))
    return image


def _delta(before: dict | None, after: dict | None, field: str) -> float | None:
    if before is None or after is None:
        return None
    return after[field] - before[field]
