"""基于 AprilTag 位姿的 TonyPi 离散动作状态机。"""

from dataclasses import dataclass
import time
from typing import Callable

from .hardware import NavigationHardware
from .motion import MotionExecutionError, MotionInterrupted
from .tag_pose import TagPose


TARGET_DISTANCE_M = 0.50
DISTANCE_TOLERANCE_M = 0.08
BEARING_TOLERANCE_DEG = 5.0
FACING_TOLERANCE_DEG = 10.0
SEARCH_HALF_ANGLE_DEG = 45.0
APPROACH_HALF_ANGLE_DEG = 30.0
LATERAL_DIRECTION_EPSILON_DEG = 2.0
ARRIVAL_CONFIRMATIONS = 3
DEFAULT_TASK_TIMEOUT_S = 120.0

TURN_LEFT_ACTION = 'turn_left_small_step'
TURN_RIGHT_ACTION = 'turn_right_small_step'
LEFT_MOVE_ACTION = 'left_move'
RIGHT_MOVE_ACTION = 'right_move'
FORWARD_ACTION = 'go_forward_one_step'
BACKWARD_ACTION = 'back_one_step'
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
    """当前帧确定的状态与至多一个有限动作。"""

    phase: str
    action_group: str | None


@dataclass(frozen=True)
class NavigationResult:
    """一条目标路线的终态。"""

    succeeded: bool
    error_code: str
    message: str


def decide(pose: TagPose | None, phase: str) -> NavigationDecision:
    """仅根据当前正前方位姿与状态决定下一步。"""
    if pose is None:
        return NavigationDecision('search_align', TURN_LEFT_ACTION)
    if abs(pose.bearing_deg) > SEARCH_HALF_ANGLE_DEG:
        return NavigationDecision('search_align', TURN_LEFT_ACTION)
    if abs(pose.bearing_deg) > APPROACH_HALF_ANGLE_DEG:
        return NavigationDecision('search_align', _turn_toward_tag(pose))
    if phase == 'search_align':
        next_phase = (
            'approach' if pose.distance_m > TARGET_DISTANCE_M + DISTANCE_TOLERANCE_M
            else 'terminal_align'
        )
        return NavigationDecision(next_phase, None)
    if phase == 'approach':
        return _approach_decision(pose)
    return _terminal_decision(pose)


def _approach_decision(pose: TagPose) -> NavigationDecision:
    if pose.distance_m <= TARGET_DISTANCE_M + DISTANCE_TOLERANCE_M:
        return NavigationDecision('terminal_align', None)
    return NavigationDecision('approach', FORWARD_ACTION)


def _terminal_decision(pose: TagPose) -> NavigationDecision:
    if pose.distance_m > TARGET_DISTANCE_M + DISTANCE_TOLERANCE_M:
        return NavigationDecision('approach', None)
    if pose.distance_m < TARGET_DISTANCE_M - DISTANCE_TOLERANCE_M:
        return NavigationDecision('terminal_align', BACKWARD_ACTION)
    if abs(pose.bearing_deg) > BEARING_TOLERANCE_DEG:
        return NavigationDecision('terminal_align', _turn_toward_tag(pose))
    if pose.facing_error_deg <= FACING_TOLERANCE_DEG:
        return NavigationDecision('arrived', None)
    lateral_error = pose.normal_bearing_deg - pose.bearing_deg
    if abs(lateral_error) <= LATERAL_DIRECTION_EPSILON_DEG:
        return NavigationDecision('terminal_align', None)
    action = LEFT_MOVE_ACTION if lateral_error > 0 else RIGHT_MOVE_ACTION
    return NavigationDecision('terminal_align', action)


def _turn_toward_tag(pose: TagPose) -> str:
    return TURN_LEFT_ACTION if pose.bearing_deg < 0 else TURN_RIGHT_ACTION


class NavigationController:
    """只通过两个硬件入口逐帧推进目标状态。"""

    def __init__(
        self,
        hardware: NavigationHardware,
        is_cancel_requested: Callable[[], bool],
        publish_target_arrived: Callable[[int, int, int], None],
    ) -> None:
        self._hardware = hardware
        self._is_cancel_requested = is_cancel_requested
        self._publish_target_arrived = publish_target_arrived

    def execute(
        self,
        target_tags: list[int],
        deadline_unix_ms: int,
    ) -> NavigationResult:
        """依次到达目标，整条路线共用 deadline。"""
        for index, tag_id in enumerate(target_tags):
            result = self._navigate_to_tag(tag_id, deadline_unix_ms)
            if not result.succeeded:
                return result
            self._publish_target_arrived(tag_id, index, len(target_tags))
        return NavigationResult(True, '', 'Task completed')

    def _navigate_to_tag(
        self,
        tag_id: int,
        deadline_unix_ms: int,
    ) -> NavigationResult:
        phase = 'search_align'
        arrived_frames = 0
        while True:
            failure = self._check_stop_conditions(deadline_unix_ms)
            if failure:
                return failure
            try:
                frame = self._hardware.observe_tags()
                decision = decide(frame.poses.get(tag_id), phase)
                if decision.phase == 'arrived':
                    arrived_frames += 1
                    if arrived_frames == ARRIVAL_CONFIRMATIONS:
                        return NavigationResult(
                            True, '', 'Target reached with stable observations'
                        )
                    continue
                arrived_frames = 0
                phase = decision.phase
                if decision.action_group is not None:
                    self._hardware.execute_action(decision.action_group)
            except MotionInterrupted as error:
                return NavigationResult(False, error.error_code, str(error))
            except MotionExecutionError as error:
                return NavigationResult(False, 'MOTION_FAILED', str(error))

    def _check_stop_conditions(self, deadline_unix_ms: int) -> NavigationResult | None:
        if self._is_cancel_requested():
            return NavigationResult(False, 'CANCEL_REQUESTED', 'Cancellation observed')
        if time.time_ns() // 1_000_000 >= deadline_unix_ms:
            return NavigationResult(False, 'DEADLINE_EXCEEDED', 'Task deadline elapsed')
        return None
