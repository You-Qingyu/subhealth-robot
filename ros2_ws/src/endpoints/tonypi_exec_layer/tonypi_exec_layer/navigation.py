"""基于 AprilTag 位姿的 TonyPi 连续闭环导航。"""

from dataclasses import dataclass
import time
from typing import Callable

from .motion import ContinuousMotionRunner, MotionMonitorDecision
from .tag_pose import TagPose


TARGET_DISTANCE_M = 0.50
DISTANCE_TOLERANCE_M = 0.08
BEARING_TOLERANCE_DEG = 5.0
FACING_TOLERANCE_DEG = 10.0
LATERAL_DIRECTION_EPSILON_DEG = 2.0
ARRIVAL_CONFIRMATIONS = 3
NON_CONVERGENCE_CONFIRMATIONS = 3
MISSING_TAG_TIMEOUT_S = 1.0
DEFAULT_TASK_TIMEOUT_S = 120.0

TURN_LEFT_ACTION = 'turn_left_small_step'
TURN_RIGHT_ACTION = 'turn_right_small_step'
LEFT_MOVE_ACTION = 'left_move'
RIGHT_MOVE_ACTION = 'right_move'
FORWARD_ACTION = 'go_forward'
BACKWARD_ACTION = 'back'
REQUIRED_ACTION_GROUPS = (
    TURN_LEFT_ACTION,
    TURN_RIGHT_ACTION,
    LEFT_MOVE_ACTION,
    RIGHT_MOVE_ACTION,
    FORWARD_ACTION,
    BACKWARD_ACTION,
)


@dataclass(frozen=True)
class NavigationDecision:
    """单次新鲜位姿观测对应的下一步连续动作决定。"""

    phase: str
    action_group: str | None
    message: str


@dataclass(frozen=True)
class NavigationResult:
    """一条目标路线的终态。"""

    succeeded: bool
    error_code: str
    message: str


def decide(pose: TagPose) -> NavigationDecision:
    """将一个有效位姿转换为到达、失败或连续动作。"""
    if pose.facing_error_deg > FACING_TOLERANCE_DEG:
        return _lateral_alignment_decision(pose)
    if abs(pose.bearing_deg) > BEARING_TOLERANCE_DEG:
        return _turn_decision(pose)
    if pose.distance_m < TARGET_DISTANCE_M - DISTANCE_TOLERANCE_M:
        return NavigationDecision(
            phase='retreat',
            action_group=BACKWARD_ACTION,
            message='距离小于停止范围，连续后退并实时观测',
        )
    if pose.distance_m > TARGET_DISTANCE_M + DISTANCE_TOLERANCE_M:
        return NavigationDecision(
            phase='approach',
            action_group=FORWARD_ACTION,
            message='距离大于停止范围，连续前进并实时观测',
        )
    return NavigationDecision(
        phase='arrived',
        action_group=None,
        message='距离、水平方位和标签朝向均在停止范围内',
    )


def is_arrived(pose: TagPose) -> bool:
    """判断一次观测是否满足停止阈值。"""
    return decide(pose).phase == 'arrived'


class NavigationController:
    """编排云台置位、连续动作、实时观测和稳定到达确认。"""

    def __init__(
        self,
        camera,
        head,
        motion: ContinuousMotionRunner,
        is_cancel_requested: Callable[[], bool],
        publish_target_arrived: Callable[[int, int, int], None],
    ) -> None:
        self._camera = camera
        self._head = head
        self._motion = motion
        self._is_cancel_requested = is_cancel_requested
        self._publish_target_arrived = publish_target_arrived

    def execute(
        self,
        target_tags: list[int],
        deadline_unix_ms: int,
    ) -> NavigationResult:
        """按顺序闭环到达所有目标 Tag。"""
        for index, tag_id in enumerate(target_tags):
            result = self._navigate_to_tag(
                tag_id,
                index,
                len(target_tags),
                deadline_unix_ms,
            )
            if not result.succeeded:
                return result
        return NavigationResult(True, '', 'Task completed')

    def _navigate_to_tag(
        self,
        tag_id: int,
        index: int,
        total: int,
        deadline_unix_ms: int,
    ) -> NavigationResult:
        has_moved = False
        while True:
            failure = self._check_stop_conditions(deadline_unix_ms)
            if failure:
                return failure
            self._head.align()
            failure = self._check_stop_conditions(deadline_unix_ms)
            if failure:
                return failure
            pose = self._observe_tag(tag_id, has_moved, deadline_unix_ms)
            if isinstance(pose, NavigationResult):
                return pose
            decision = decide(pose)
            if decision.phase == 'fail':
                failure = self._confirm_non_convergence(
                    tag_id,
                    pose,
                    decision.message,
                    deadline_unix_ms,
                )
                if failure is not None:
                    return failure
                continue
            if decision.phase == 'arrived':
                confirmation = self._confirm_arrival(
                    tag_id,
                    pose,
                    deadline_unix_ms,
                )
                if confirmation is not None:
                    if not confirmation.succeeded:
                        return confirmation
                    self._publish_target_arrived(tag_id, index, total)
                    return confirmation
                continue

            segment_result = self._run_motion_segment(
                tag_id,
                decision,
                deadline_unix_ms,
            )
            if segment_result is not None:
                if not segment_result.succeeded:
                    return segment_result
                self._publish_target_arrived(tag_id, index, total)
                return segment_result
            has_moved = True

    def _run_motion_segment(
        self,
        tag_id: int,
        decision: NavigationDecision,
        deadline_unix_ms: int,
    ) -> NavigationResult | None:
        """持续执行当前动作，直到视觉要求停止或重新规划。"""
        monitor = _ContinuousObservationMonitor(
            camera=self._camera,
            tag_id=tag_id,
            action_group=decision.action_group,
            is_cancel_requested=self._is_cancel_requested,
            deadline_unix_ms=deadline_unix_ms,
        )
        try:
            stop_decision = self._motion.run_until(
                decision.action_group,
                monitor,
            )
        except Exception as error:  # noqa: BLE001 - 转换为导航终态
            return NavigationResult(False, 'MOTION_FAILED', str(error))
        if stop_decision.reason == 'arrived':
            return NavigationResult(True, '', 'Target reached with stable observations')
        if stop_decision.reason == 'failure':
            return NavigationResult(
                False,
                stop_decision.error_code,
                stop_decision.message,
            )
        if stop_decision.reason == 'lost':
            pose = self._observe_tag(tag_id, True, deadline_unix_ms)
            if isinstance(pose, NavigationResult):
                return pose
        return None

    def _confirm_arrival(
        self,
        tag_id: int,
        first_pose: TagPose,
        deadline_unix_ms: int,
    ) -> NavigationResult | None:
        """要求连续三帧满足停止条件；不满足时交回主循环。"""
        poses = [first_pose]
        while len(poses) < ARRIVAL_CONFIRMATIONS:
            failure = self._check_stop_conditions(deadline_unix_ms)
            if failure:
                return failure
            pose = self._observe_tag(tag_id, True, deadline_unix_ms)
            if isinstance(pose, NavigationResult):
                return pose
            if not is_arrived(pose):
                return None
            poses.append(pose)
        return NavigationResult(True, '', 'Target reached with stable observations')

    def _confirm_non_convergence(
        self,
        tag_id: int,
        first_pose: TagPose,
        message: str,
        deadline_unix_ms: int,
    ) -> NavigationResult | None:
        """只在连续三帧没有可用侧移方向时报告不可收敛。"""
        poses = [first_pose]
        while len(poses) < NON_CONVERGENCE_CONFIRMATIONS:
            failure = self._check_stop_conditions(deadline_unix_ms)
            if failure:
                return failure
            pose = self._observe_tag(tag_id, True, deadline_unix_ms)
            if isinstance(pose, NavigationResult):
                return pose
            if decide(pose).phase != 'fail':
                return None
            poses.append(pose)
        return NavigationResult(False, 'NON_CONVERGENT_POSE', message)

    def _observe_tag(
        self,
        tag_id: int,
        has_moved: bool,
        deadline_unix_ms: int,
    ) -> TagPose | NavigationResult:
        """读取目标；移动后短暂丢失时等待，初始丢失则直接失败。"""
        pose = self._camera.observe(tag_id)
        if pose is not None:
            return pose
        if not has_moved:
            return NavigationResult(False, 'TAG_NOT_VISIBLE', '目标 Tag 不在初始画面中')
        retry_until = time.monotonic() + MISSING_TAG_TIMEOUT_S
        while time.monotonic() < retry_until:
            failure = self._check_stop_conditions(deadline_unix_ms)
            if failure:
                return failure
            time.sleep(0.05)
            pose = self._camera.observe(tag_id)
            if pose is not None:
                return pose
        return NavigationResult(False, 'TAG_LOST', '目标 Tag 在移动后 1 秒内未重新出现')

    def _check_stop_conditions(self, deadline_unix_ms: int) -> NavigationResult | None:
        if self._is_cancel_requested():
            return NavigationResult(False, 'CANCEL_REQUESTED', 'Cancellation observed')
        if _deadline_expired(deadline_unix_ms):
            return NavigationResult(False, 'DEADLINE_EXCEEDED', 'Task deadline elapsed')
        return None


class _ContinuousObservationMonitor:
    """把实时位姿帧转换为连续动作线程的停止决定。"""

    def __init__(
        self,
        camera,
        tag_id: int,
        action_group: str | None,
        is_cancel_requested: Callable[[], bool],
        deadline_unix_ms: int,
    ) -> None:
        self._camera = camera
        self._tag_id = tag_id
        self._action_group = action_group
        self._is_cancel_requested = is_cancel_requested
        self._deadline_unix_ms = deadline_unix_ms
        self._arrived_frames = 0

    def __call__(self) -> MotionMonitorDecision:
        if self._is_cancel_requested():
            return MotionMonitorDecision(True, 'failure', 'CANCEL_REQUESTED', 'Cancellation observed')
        if _deadline_expired(self._deadline_unix_ms):
            return MotionMonitorDecision(True, 'failure', 'DEADLINE_EXCEEDED', 'Task deadline elapsed')
        pose = self._camera.observe(self._tag_id)
        if pose is None:
            return MotionMonitorDecision(True, 'lost')
        decision = decide(pose)
        if decision.phase == 'arrived':
            self._arrived_frames += 1
            if self._arrived_frames >= ARRIVAL_CONFIRMATIONS:
                return MotionMonitorDecision(True, 'arrived')
            return MotionMonitorDecision(False, 'continue')
        self._arrived_frames = 0
        if decision.phase == 'fail':
            return MotionMonitorDecision(True, 'replan')
        if decision.action_group != self._action_group:
            return MotionMonitorDecision(True, 'replan')
        return MotionMonitorDecision(False, 'continue')


def _lateral_alignment_decision(pose: TagPose) -> NavigationDecision:
    lateral_error = pose.normal_bearing_deg - pose.bearing_deg
    if abs(lateral_error) <= LATERAL_DIRECTION_EPSILON_DEG:
        return NavigationDecision(
            phase='fail',
            action_group=None,
            message=(
                '标签朝向误差超过 10°，但有符号横向误差不足以选择侧移方向；'
                '当前姿态无法通过侧移收敛'
            ),
        )
    if lateral_error > 0:
        return NavigationDecision(
            phase='lateral_align',
            action_group=LEFT_MOVE_ACTION,
            message='标签法线方向需要向左侧移，连续观测中',
        )
    return NavigationDecision(
        phase='lateral_align',
        action_group=RIGHT_MOVE_ACTION,
        message='标签法线方向需要向右侧移，连续观测中',
    )


def _turn_decision(pose: TagPose) -> NavigationDecision:
    if pose.bearing_deg < 0:
        return NavigationDecision(
            phase='turn',
            action_group=TURN_LEFT_ACTION,
            message='标签中心在相机左侧，连续左转并实时观测',
        )
    return NavigationDecision(
        phase='turn',
        action_group=TURN_RIGHT_ACTION,
        message='标签中心在相机右侧，连续右转并实时观测',
    )


def _deadline_expired(deadline_unix_ms: int) -> bool:
    return time.time_ns() // 1_000_000 >= deadline_unix_ms
