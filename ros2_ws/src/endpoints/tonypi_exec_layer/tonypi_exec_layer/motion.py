"""TonyPi 官方 SDK 的单次有限动作组执行。"""

import threading
import time
from typing import Callable


MOTION_POLL_INTERVAL_S = 0.05
MOTION_STOP_TIMEOUT_S = 5.0
MOTION_SETTLE_TIME_S = 0.5


class MotionExecutionError(RuntimeError):
    """动作无法可靠完成或停止。"""


class MotionInterrupted(MotionExecutionError):
    """动作期间收到取消或超过整条路线的 deadline。"""

    def __init__(self, error_code: str) -> None:
        self.error_code = error_code
        super().__init__(error_code)


class FiniteMotionRunner:
    """保证一次只执行一个 ``times=1`` 动作且停止后才允许下一动作。"""

    def __init__(self, action_group_control, action_group_root: str) -> None:
        if not hasattr(action_group_control, 'runActionGroup'):
            raise ValueError('TonyPi SDK 缺少 runActionGroup')
        if not hasattr(action_group_control, 'stopActionGroup'):
            raise ValueError('TonyPi SDK 缺少 stopActionGroup')
        self._sdk = action_group_control
        self._root = action_group_root
        self._lock = threading.Lock()
        self._blocked = False

    def execute(
        self,
        action_group: str,
        is_cancel_requested: Callable[[], bool],
        deadline_unix_ms: int,
    ) -> None:
        """阻塞直到有限动作结束；取消或超时则请求 SDK 在安全边界停止。"""
        if not self._lock.acquire(blocking=False):
            raise MotionExecutionError('已有动作组正在执行')
        try:
            if self._blocked:
                raise MotionExecutionError('上一个动作组尚未确认停止')
            self._execute_locked(action_group, is_cancel_requested, deadline_unix_ms)
        finally:
            self._lock.release()

    def _execute_locked(
        self,
        action_group: str,
        is_cancel_requested: Callable[[], bool],
        deadline_unix_ms: int,
    ) -> None:
        errors: list[BaseException] = []
        worker = threading.Thread(
            target=self._run_action,
            args=(action_group, errors),
            name=f'tonypi-motion-{action_group}',
            daemon=True,
        )
        worker.start()
        while worker.is_alive():
            reason = _interruption(is_cancel_requested, deadline_unix_ms)
            if reason:
                self._stop_worker(worker)
                raise MotionInterrupted(reason)
            worker.join(MOTION_POLL_INTERVAL_S)
        if errors:
            raise MotionExecutionError(f'动作组线程异常: {errors[0]}') from errors[0]
        time.sleep(MOTION_SETTLE_TIME_S)

    def _run_action(self, action_group: str, errors: list[BaseException]) -> None:
        try:
            self._sdk.runActionGroup(action_group, times=1, path=self._root)
        except BaseException as error:  # noqa: BLE001 - 将线程异常交回主线程
            errors.append(error)

    def _stop_worker(self, worker: threading.Thread) -> None:
        try:
            if worker.is_alive():
                self._sdk.stopActionGroup()
        except Exception as error:
            self._blocked = True
            worker.join(MOTION_STOP_TIMEOUT_S)
            raise MotionExecutionError(f'无法请求动作组停止: {error}') from error
        worker.join(MOTION_STOP_TIMEOUT_S)
        if worker.is_alive():
            self._blocked = True
            raise MotionExecutionError('动作组未能在 5 秒内停止；禁止后续动作')
        # SDK 的 stop 标志是全局变量：恰好在自然结束时设置会污染下一次动作。
        self._sdk.stop_action_group = False


def _interruption(
    is_cancel_requested: Callable[[], bool],
    deadline_unix_ms: int,
) -> str | None:
    if is_cancel_requested():
        return 'CANCEL_REQUESTED'
    if time.time_ns() // 1_000_000 >= deadline_unix_ms:
        return 'DEADLINE_EXCEEDED'
    return None
