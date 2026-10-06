"""状态机使用的两个 TonyPi 硬件操作。"""

import time
from typing import Callable

from .camera import FrameObservation, TagCamera
from .head import HeadAligner
from .motion import FiniteMotionRunner, MotionInterrupted


class NavigationHardware:
    """将云台、相机和动作 SDK 收拢在状态机的两个入口中。"""

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

    def _check_interruption(self) -> None:
        if self._is_cancel_requested():
            raise MotionInterrupted('CANCEL_REQUESTED')
        if time.time_ns() // 1_000_000 >= self._deadline_unix_ms:
            raise MotionInterrupted('DEADLINE_EXCEEDED')
