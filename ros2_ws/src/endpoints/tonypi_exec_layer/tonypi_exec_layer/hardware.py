"""状态机使用的 TonyPi 硬件操作。"""

from dataclasses import dataclass
import time
from typing import Callable

from .camera import FrameObservation, TagCamera
from .head import (
    HEAD_HORIZONTAL_PULSE, HEAD_SCAN_MOVE_TIME_S, HEAD_SCAN_PULSES,
    HEAD_SETTLE_TIME_S, HeadAligner,
)
from .motion import FiniteMotionRunner, MotionInterrupted


@dataclass(frozen=True)
class HeadScanSample:
    frame: FrameObservation
    pulse: int
    stage: str


@dataclass(frozen=True)
class HeadScanResult:
    direction: str | None


class NavigationHardware:
    """将云台、相机和动作 SDK 收拢在状态机的硬件入口中。"""

    def __init__(
        self,
        camera: TagCamera,
        head: HeadAligner,
        motion: FiniteMotionRunner,
        allowed_actions: tuple[str, ...],
        is_cancel_requested: Callable[[], bool],
        deadline_unix_ms: int,
    ) -> None:
        self._camera = camera
        self._head = head
        self._motion = motion
        self._allowed_actions = allowed_actions
        self._is_cancel_requested = is_cancel_requested
        self._deadline_unix_ms = deadline_unix_ms

    def observe_tags(self) -> FrameObservation:
        """回正云台，读取当前新帧的所有 Tag。"""
        self._check_interruption()
        self._head.align()
        self._check_interruption()
        return self._camera.observe_tags(time.monotonic(), self._check_interruption)

    def execute_action(self, action_group: str) -> None:
        """在云台正前方执行一个经允许的有限动作组。"""
        if action_group not in self._allowed_actions:
            raise ValueError(f'未允许的动作组: {action_group}')
        self._check_interruption()
        self._head.align()
        self._check_interruption()
        self._motion.execute(
            action_group,
            self._is_cancel_requested,
            self._deadline_unix_ms,
        )
        self._check_interruption()

    def scan_head(
        self, tag_id: int, on_sample: Callable[[HeadScanSample], None],
    ) -> HeadScanResult:
        """机身静止扫描；运动帧只作为候选，停稳后的帧决定方向。"""
        direction = None
        self._check_interruption()
        self._head.align()
        try:
            for pulse in HEAD_SCAN_PULSES:
                self._check_interruption()
                self._head.turn_to(pulse)
                started_at = time.monotonic()
                while time.monotonic() - started_at < HEAD_SCAN_MOVE_TIME_S:
                    frame = self._camera.observe_tags(started_at, self._check_interruption)
                    on_sample(HeadScanSample(frame, pulse, 'moving'))
                    if tag_id in frame.poses:
                        break
                    self._check_interruption()
                self._wait(HEAD_SCAN_MOVE_TIME_S + HEAD_SETTLE_TIME_S - (time.monotonic() - started_at))
                if tag_id not in frame.poses:
                    continue
                confirmed = self._camera.observe_tags(time.monotonic(), self._check_interruption)
                on_sample(HeadScanSample(confirmed, pulse, 'confirmation'))
                pose = confirmed.poses.get(tag_id)
                if pose is not None:
                    if pulse == HEAD_HORIZONTAL_PULSE:
                        direction = 'left' if pose.bearing_deg < 0 else 'right'
                    else:
                        direction = 'right' if pulse < HEAD_HORIZONTAL_PULSE else 'left'
                    break
        finally:
            self._head.align()
        return HeadScanResult(direction)

    def _wait(self, seconds: float) -> None:
        until = time.monotonic() + max(0, seconds)
        while time.monotonic() < until:
            self._check_interruption()
            time.sleep(min(0.05, until - time.monotonic()))
        self._check_interruption()

    def _check_interruption(self) -> None:
        if self._is_cancel_requested():
            raise MotionInterrupted('CANCEL_REQUESTED')
        if time.time_ns() // 1_000_000 >= self._deadline_unix_ms:
            raise MotionInterrupted('DEADLINE_EXCEEDED')
