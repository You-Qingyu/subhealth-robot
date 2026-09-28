"""TonyPi 官方动作组的连续执行控制。"""

from dataclasses import dataclass
import threading
import time
from typing import Callable


MOTION_OBSERVATION_INTERVAL_S = 0.08
MOTION_STOP_TIMEOUT_S = 5.0


@dataclass(frozen=True)
class MotionMonitorDecision:
    """视觉监控对当前连续动作段的控制决定。"""

    stop: bool
    reason: str
    error_code: str = ''
    message: str = ''


class MotionExecutionError(RuntimeError):
    """官方动作组线程无法按预期启动或停止时抛出。"""


class ContinuousMotionRunner:
    """把 SDK 的无限动作组循环隐藏在可停止的单次动作段接口后。"""

    def __init__(self, action_group_control, action_group_root: str) -> None:
        if not hasattr(action_group_control, 'runActionGroup'):
            raise ValueError('TonyPi SDK 缺少 runActionGroup')
        if not hasattr(action_group_control, 'stopActionGroup'):
            raise ValueError('TonyPi SDK 缺少 stopActionGroup')
        self._sdk = action_group_control
        self._action_group_root = action_group_root

    def run_until(
        self,
        action_group: str,
        monitor: Callable[[], MotionMonitorDecision],
    ) -> MotionMonitorDecision:
        """持续运行一个动作组，直到视觉监控要求停止。"""
        thread_error: list[BaseException] = []
        worker = threading.Thread(
            target=self._run_action_group,
            args=(action_group, thread_error),
            name=f'tonypi-motion-{action_group}',
            daemon=True,
        )
        worker.start()
        try:
            return self._monitor_until_stop(worker, monitor, thread_error)
        except BaseException:
            self._stop_worker(worker)
            raise

    def _monitor_until_stop(
        self,
        worker: threading.Thread,
        monitor: Callable[[], MotionMonitorDecision],
        thread_error: list[BaseException],
    ) -> MotionMonitorDecision:
        while worker.is_alive():
            decision = monitor()
            if decision.stop:
                self._stop_worker(worker)
                return decision
            time.sleep(MOTION_OBSERVATION_INTERVAL_S)
        self._raise_worker_exit(thread_error)
        raise MotionExecutionError('动作组线程在收到停止决定前退出')

    def _run_action_group(
        self,
        action_group: str,
        thread_error: list[BaseException],
    ) -> None:
        try:
            self._sdk.runActionGroup(
                action_group,
                times=0,
                path=self._action_group_root,
            )
        except BaseException as error:  # noqa: BLE001 - 将线程异常交回导航线程
            thread_error.append(error)

    def _stop_worker(self, worker: threading.Thread) -> None:
        if not worker.is_alive():
            return
        self._sdk.stopActionGroup()
        worker.join(MOTION_STOP_TIMEOUT_S)
        if worker.is_alive():
            raise MotionExecutionError('动作组线程未能在 5 秒内停止')

    @staticmethod
    def _raise_worker_exit(thread_error: list[BaseException]) -> None:
        if thread_error:
            raise MotionExecutionError(f'动作组线程异常: {thread_error[0]}') from thread_error[0]
