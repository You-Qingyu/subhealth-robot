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
            'captured_at_monotonic': frame.captured_at_monotonic,
            'poses': {str(key): asdict(value) for key, value in frame.poses.items()},
            'target_pose': asdict(pose) if pose else None,
            'phase_before': phase_before,
            'phase_after': phase_after,
            'reason': reason,
            'action_group': action_group,
            'arrival_confirmations': confirmations,
            'previous_action_frame': previous_action_frame,
            'action_elapsed_ms': None,
            'action_error': None,
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
        return number

    def action_finished(
        self, frame_id: int, elapsed_ms: int, error: str | None = None
    ) -> None:
        path = self.directory / f'{frame_id:06d}.json'
        record = json.loads(path.read_text(encoding='utf-8'))
        record['action_elapsed_ms'] = elapsed_ms
        record['action_error'] = error
        self._write_record(frame_id, record)

    def observation_failed(self, frame_id: int, error_code: str) -> None:
        path = self.directory / f'{frame_id:06d}.json'
        record = json.loads(path.read_text(encoding='utf-8'))
        record['next_observation_error'] = error_code
        self._write_record(frame_id, record)

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
<style>body{background:#202124;color:#eee;font:16px sans-serif;text-align:center}
img{max-width:95vw;max-height:80vh}a{color:#8ab4f8}button{padding:8px;margin:8px}</style>
<h1>TonyPi 逐帧回放</h1>
<button onclick="show(index-1)">上一帧</button><span id="counter"></span>
<button onclick="show(index+1)">下一帧</button>
<button onclick="toggle()" id="play">播放</button>
<a id="data" target="_blank">查看同名 JSON</a><br>
<img id="frame" alt="当前决策帧">
<script>
const total = FRAME_COUNT;
let index = 1, timer = null;
function show(number) {
  index = Math.max(1, Math.min(total, number));
  const stem = String(index).padStart(6, '0');
  document.getElementById('frame').src = stem + '.png';
  document.getElementById('data').href = stem + '.json';
  document.getElementById('counter').textContent = `${index} / ${total}`;
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
    canvas = np.full((height, width + 440, 3), 32, dtype=np.uint8)
    canvas[:, :width] = image
    pose = frame.poses.get(record['target_id'])
    lines = [
        f"frame {record['frame_id']}  target {record['target_id']}",
        f"phase: {record['phase_before']} -> {record['phase_after']}",
        f"reason: {record['reason']}",
        f"action: {record['action_group'] or 'none'}",
        f"previous action frame: {record['previous_action_frame']}",
        f"arrival confirmations: {record['arrival_confirmations']}",
    ]
    if pose is None:
        lines.append('TARGET NOT DETECTED')
    else:
        lines += [
            f'distance_m: {pose.distance_m:.3f}',
            f'forward_m: {pose.forward_m:.3f}',
            f'lateral_m: {pose.lateral_m:.3f}',
            f'vertical_m: {pose.vertical_m:.3f}',
            f'bearing_deg: {pose.bearing_deg:.2f}',
            f'normal_bearing_deg: {pose.normal_bearing_deg:.2f}',
            f'facing_error_deg: {pose.facing_error_deg:.2f}',
            f'image_margin_px: {pose.image_margin_px:.2f}',
            f'reprojection_error_px: {pose.reprojection_error_px:.2f}',
        ]
    for index, line in enumerate(lines):
        cv2.putText(
            canvas, line, (width + 12, 28 + index * 29),
            cv2.FONT_HERSHEY_SIMPLEX, 0.48, (240, 240, 240), 1, cv2.LINE_AA,
        )
    return canvas
