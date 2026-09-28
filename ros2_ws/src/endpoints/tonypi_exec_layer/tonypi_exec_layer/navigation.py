"""基于 AprilTag 位姿的 TonyPi 单目标闭环导航。"""

from dataclasses import dataclass
import time
from typing import Callable

from .tag_pose import TagPose


TARGET_DISTANCE_M = 0.50
DISTANCE_TOLERANCE_M = 0.08
BEARING_TOLERANCE_DEG = 5.0
FACING_TOLERANCE_DEG = 10.0
ARRIVAL_CONFIRMATIONS = 3
NON_CONVERGENCE_CONFIRMATIONS = 3
MISSING_TAG_TIMEOUT_S = 1.0
DEFAULT_TASK_TIMEOUT_S = 120.0

TURN_LEFT_ACTION = 'turn_left_small_step'
TURN_RIGHT_ACTION = 'turn_right_small_step'
FORWARD_ACTION = 'go_forward_one_small_step'
BACKWARD_ACTION = 'back_one_step'
REQUIRED_ACTION_GROUPS = (
    TURN_LEFT_ACTION,
    TURN_RIGHT_ACTION,
    FORWARD_ACTION,
    BACKWARD_ACTION,
)


@dataclass(frozen=True)
class NavigationDecision:
    """单次新鲜位姿观测对应的下一步决定。"""

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
    """将一个有效位姿转换为到达、失败或单个有限动作。"""
    if _needs_unresolvable_facing(pose):
        return NavigationDecision(
            phase='fail',
            action_group=None,
            message=(
                '标签相对朝向误差超过 10°，但水平方位已对齐；'
                '当前版本不支持侧向调整'
            ),
        )
    if abs(pose.bearing_deg) > BEARING_TOLERANCE_DEG:
        return _turn_decision(pose)
    if pose.distance_m < TARGET_DISTANCE_M - DISTANCE_TOLERANCE_M:
        return NavigationDecision(
            phase='retreat',
            action_group=BACKWARD_ACTION,
            message='距离小于停止范围，执行一次后退小步',
        )
    if pose.distance_m > TARGET_DISTANCE_M + DISTANCE_TOLERANCE_M:
        return NavigationDecision(
            phase='approach',
            action_group=FORWARD_ACTION,
            message='距离大于停止范围，执行一次前进小步',
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
    """编排置位、观测、单步动作和连续到达确认。"""

    def __init__(
        self,
        camera,
        head,
        run_action: Callable[[str], None],
        is_cancel_requested: Callable[[], bool],
        publish_target_arrived: Callable[[int, int, int], None],
    ) -> None:
        self._camera = camera
        self._head = head
        self._run_action = run_action
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
                    tag_id, pose, deadline_unix_ms
                )
                if confirmation is not None:
                    if not confirmation.succeeded:
                        return confirmation
                    self._publish_target_arrived(tag_id, index, total)
                    return confirmation
                continue

            action_result, moved = self._execute_next_action(
                tag_id, deadline_unix_ms
            )
            if not action_result.succeeded:
                return action_result
            has_moved = has_moved or moved

    def _execute_next_action(
        self,
        tag_id: int,
        deadline_unix_ms: int,
    ) -> tuple[NavigationResult, bool]:
        """动作前重新置位和观测，避免使用云台变化前的旧位姿。"""
        failure = self._check_stop_conditions(deadline_unix_ms)
        if failure:
            return failure, False
        self._head.align()
        failure = self._check_stop_conditions(deadline_unix_ms)
        if failure:
            return failure, False
        pose = self._observe_tag(tag_id, True, deadline_unix_ms)
        if isinstance(pose, NavigationResult):
            return pose, False
        decision = decide(pose)
        if decision.phase == 'fail':
            failure = self._confirm_non_convergence(
                tag_id,
                pose,
                decision.message,
                deadline_unix_ms,
            )
            if failure is not None:
                return failure, False
            return NavigationResult(True, '', '重新观测后无需执行当前动作'), False
        if decision.phase == 'arrived':
            return NavigationResult(True, '', 'Target already reached'), False
        failure = self._check_stop_conditions(deadline_unix_ms)
        if failure:
            return failure, False
        self._run_action(decision.action_group)
        return NavigationResult(True, '', decision.message), True

    def _confirm_non_convergence(
        self,
        tag_id: int,
        first_pose: TagPose,
        message: str,
        deadline_unix_ms: int,
    ) -> NavigationResult | None:
        """过滤动作后短暂抖动，只在连续三帧确认后报告不可收敛。"""
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


def _turn_decision(pose: TagPose) -> NavigationDecision:
    if pose.bearing_deg < 0:
        return NavigationDecision(
            phase='align',
            action_group=TURN_LEFT_ACTION,
            message='目标在相机左侧，执行一次左转小步',
        )
    return NavigationDecision(
        phase='align',
        action_group=TURN_RIGHT_ACTION,
        message='目标在相机右侧，执行一次右转小步',
    )


def _needs_unresolvable_facing(pose: TagPose) -> bool:
    return (
        abs(pose.bearing_deg) <= BEARING_TOLERANCE_DEG
        and pose.facing_error_deg > FACING_TOLERANCE_DEG
    )


def _deadline_expired(deadline_unix_ms: int) -> bool:
    return time.time_ns() // 1_000_000 >= deadline_unix_ms
