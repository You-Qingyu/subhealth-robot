"""按有限动作记录导航观测、决策和完成结果。"""

from dataclasses import dataclass
import time
from typing import Callable

from .tag_pose import TagPose


@dataclass
class PendingStep:
    """一次已决定动作的起始位姿与计时。"""

    number: int
    phase: str
    action_group: str
    before: dict | None
    before_captured_at: float
    started_at: float
    action_elapsed_ms: int | None = None


class NavigationTrace:
    """每个目标的动作链；记录接口不会读取相机或调用动作 SDK。"""

    def __init__(
        self,
        tag_id: int,
        target_index: int,
        target_count: int,
        publish: Callable[[dict], None],
    ) -> None:
        self._tag_id = tag_id
        self._index = target_index
        self._total = target_count
        self._publish = publish
        self._step_number = 0

    def started(
        self,
        phase: str,
        action_group: str,
        pose: TagPose | None,
        captured_at: float,
    ) -> PendingStep:
        self._step_number += 1
        step = PendingStep(
            number=self._step_number,
            phase=phase,
            action_group=action_group,
            before=_pose_snapshot(pose),
            before_captured_at=captured_at,
            started_at=time.monotonic(),
        )
        self._emit(step, 'started')
        return step

    def motion_finished(self, step: PendingStep) -> None:
        step.action_elapsed_ms = _elapsed_ms(step.started_at)

    def observed(
        self,
        step: PendingStep,
        pose: TagPose | None,
        captured_at: float,
    ) -> None:
        self._emit(
            step,
            'observed',
            after=_pose_snapshot(pose),
            after_captured_at=captured_at,
        )

    def stopped(self, step: PendingStep, error_code: str) -> None:
        self._emit(step, 'stopped', error_code=error_code)

    def phase_changed(self, phase: str, pose: TagPose | None) -> None:
        self._publish({
            'event': 'phase_changed',
            'phase': phase,
            'tag_id': self._tag_id,
            'target_index': self._index,
            'target_count': self._total,
            'step': self._step_number,
            'observation': _pose_snapshot(pose),
        })

    def _emit(
        self,
        step: PendingStep,
        event: str,
        after: dict | None = None,
        after_captured_at: float | None = None,
        error_code: str | None = None,
    ) -> None:
        self._publish({
            'event': event,
            'tag_id': self._tag_id,
            'target_index': self._index,
            'target_count': self._total,
            'step': step.number,
            'phase': step.phase,
            'action_group': step.action_group,
            'before': step.before,
            'after': after,
            'before_captured_at_monotonic': step.before_captured_at,
            'after_captured_at_monotonic': after_captured_at,
            'action_elapsed_ms': step.action_elapsed_ms,
            'total_elapsed_ms': _elapsed_ms(step.started_at),
            'error_code': error_code,
        })


def _elapsed_ms(started_at: float) -> int:
    return round((time.monotonic() - started_at) * 1000)


def _pose_snapshot(pose: TagPose | None) -> dict | None:
    if pose is None:
        return None
    return {
        'distance_m': pose.distance_m,
        'forward_m': pose.forward_m,
        'lateral_m': pose.lateral_m,
        'vertical_m': pose.vertical_m,
        'bearing_deg': pose.bearing_deg,
        'normal_bearing_deg': pose.normal_bearing_deg,
        'facing_error_deg': pose.facing_error_deg,
        'image_margin_px': pose.image_margin_px,
        'reprojection_error_px': pose.reprojection_error_px,
    }
