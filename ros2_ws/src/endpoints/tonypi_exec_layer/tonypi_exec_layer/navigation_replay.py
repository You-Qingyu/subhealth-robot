"""将导航实际使用的每一帧保存为图片和同名机器可读记录。"""

from dataclasses import asdict, dataclass
import json
from pathlib import Path
import uuid

import cv2
import numpy as np

from .camera import FrameObservation
from .hardware import HeadScanStage, TurnDirection
from .navigation_replay_page import frame_summary, write_index


@dataclass(frozen=True)
class ScanAnnotation:
    pulse: int
    stage: HeadScanStage
    scan_direction: TurnDirection
    turn_direction: TurnDirection | None


@dataclass(frozen=True)
class ObservationAnnotation:
    phase_before: str
    phase_after: str
    reason: str
    action_group: str | None
    confirmations: int
    previous_action_frame: int | None
    decision_at_monotonic: float
    scan_steps_completed: int
    scan: ScanAnnotation | None = None


class NavigationReplay:
    """一个任务的逐帧回放；不读取相机，也不执行动作。"""

    def __init__(self, root: Path, task_id: str) -> None:
        self.directory = root / uuid.uuid4().hex
        self.directory.mkdir(parents=True)
        (self.directory / 'raw').mkdir()
        self._task_id = task_id
        self._number = 0
        self._summaries: list[dict] = []

    def record(
        self,
        frame: FrameObservation,
        tag_id: int,
        target_index: int,
        annotation: ObservationAnnotation,
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
            'decision_at_monotonic': annotation.decision_at_monotonic,
            'poses': {str(key): asdict(value) for key, value in frame.poses.items()},
            'target_pose': asdict(pose) if pose else None,
            'phase_before': annotation.phase_before,
            'phase_after': annotation.phase_after,
            'reason': annotation.reason,
            'action_group': annotation.action_group,
            'arrival_confirmations': annotation.confirmations,
            'previous_action_frame': annotation.previous_action_frame,
            'scan_steps_completed': annotation.scan_steps_completed,
            'head_pulse': annotation.scan.pulse if annotation.scan else None,
            'head_stage': annotation.scan.stage.value if annotation.scan else None,
            'head_scan_direction': (
                annotation.scan.scan_direction.value if annotation.scan else None
            ),
            'head_turn_direction': (
                annotation.scan.turn_direction.value
                if annotation.scan and annotation.scan.turn_direction is not None else None
            ),
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
        if annotation.previous_action_frame is not None:
            self._record_action_effect(annotation.previous_action_frame, number, frame)
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
        summary = frame_summary(record)
        if frame_id == len(self._summaries) + 1:
            self._summaries.append(summary)
        else:
            self._summaries[frame_id - 1] = summary
        write_index(self.directory, self._summaries)


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
