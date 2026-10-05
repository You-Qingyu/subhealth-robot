"""基于 AprilTag 位姿的 TonyPi 离散动作状态机。"""

from dataclasses import dataclass
import time
from typing import Callable

from .hardware import NavigationHardware
from .motion import MotionExecutionError, MotionInterrupted
from .navigation_replay import NavigationReplay
from .tag_pose import TagPose


TARGET_DISTANCE_M = 0.50
DISTANCE_TOLERANCE_M = 0.08
BEARING_TOLERANCE_DEG = 5.0
FACING_TOLERANCE_DEG = 15.0
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
    reason: str


@dataclass(frozen=True)
class NavigationResult:
    """一条目标路线的终态。"""

    succeeded: bool
    error_code: str
    message: str


def decide(pose: TagPose | None, phase: str) -> NavigationDecision:
    """仅根据当前正前方位姿与状态决定下一步。"""
    if pose is None:
        return NavigationDecision('search_align', None, 'target_not_detected')
    if abs(pose.bearing_deg) > SEARCH_HALF_ANGLE_DEG:
        return NavigationDecision('search_align', TURN_LEFT_ACTION, 'outside_search_range')
    if abs(pose.bearing_deg) > APPROACH_HALF_ANGLE_DEG:
        return NavigationDecision('search_align', _turn_toward_tag(pose), 'outside_approach_range')
    if phase == 'search_align':
        next_phase = (
            'approach' if pose.distance_m > TARGET_DISTANCE_M + DISTANCE_TOLERANCE_M
            else 'terminal_align'
        )
        return NavigationDecision(next_phase, None, 'target_acquired')
    if phase == 'approach':
        return _approach_decision(pose)
    return _terminal_decision(pose)


def _approach_decision(pose: TagPose) -> NavigationDecision:
    if pose.distance_m <= TARGET_DISTANCE_M + DISTANCE_TOLERANCE_M:
        return NavigationDecision('terminal_align', None, 'distance_in_terminal_range')
    return NavigationDecision('approach', FORWARD_ACTION, 'distance_too_far')


def _terminal_decision(pose: TagPose) -> NavigationDecision:
    if pose.distance_m > TARGET_DISTANCE_M + DISTANCE_TOLERANCE_M:
        return NavigationDecision('approach', None, 'distance_too_far')
    if pose.distance_m < TARGET_DISTANCE_M - DISTANCE_TOLERANCE_M:
        return NavigationDecision('terminal_align', BACKWARD_ACTION, 'distance_too_close')
    if abs(pose.bearing_deg) > BEARING_TOLERANCE_DEG:
        return NavigationDecision('terminal_align', _turn_toward_tag(pose), 'bearing_not_centered')
    if pose.facing_error_deg <= FACING_TOLERANCE_DEG:
        return NavigationDecision('arrived', None, 'within_arrival_tolerances')
    lateral_error = pose.normal_bearing_deg - pose.bearing_deg
    if abs(lateral_error) <= LATERAL_DIRECTION_EPSILON_DEG:
        return NavigationDecision('terminal_align', None, 'lateral_direction_uncertain')
    action = LEFT_MOVE_ACTION if lateral_error > 0 else RIGHT_MOVE_ACTION
    return NavigationDecision('terminal_align', action, 'facing_not_aligned')


def _turn_toward_tag(pose: TagPose) -> str:
    return TURN_LEFT_ACTION if pose.bearing_deg < 0 else TURN_RIGHT_ACTION


class NavigationController:
    """只通过两个硬件入口逐帧推进目标状态。"""

    def __init__(
        self,
        hardware: NavigationHardware,
        is_cancel_requested: Callable[[], bool],
        publish_target_arrived: Callable[[int, int, int], None],
        replay: NavigationReplay,
        log_event: Callable[[dict], None],
    ) -> None:
        self._hardware = hardware
        self._is_cancel_requested = is_cancel_requested
        self._publish_target_arrived = publish_target_arrived
        self._replay = replay
        self._log_event = log_event

    def execute(
        self,
        target_tags: list[int],
        deadline_unix_ms: int,
    ) -> NavigationResult:
        """依次到达目标，整条路线共用 deadline。"""
        for index, tag_id in enumerate(target_tags):
            result = self._navigate_to_tag(tag_id, index, deadline_unix_ms)
            if not result.succeeded:
                return result
            self._publish_target_arrived(tag_id, index, len(target_tags))
        return NavigationResult(True, '', 'Task completed')

    def _navigate_to_tag(
        self,
        tag_id: int,
        target_index: int,
        deadline_unix_ms: int,
    ) -> NavigationResult:
        phase = 'search_align'
        arrived_frames = 0
        previous_action_frame: int | None = None
        while True:
            failure = self._check_stop_conditions(deadline_unix_ms)
            if failure:
                if previous_action_frame is not None:
                    self._replay.observation_failed(previous_action_frame, failure.error_code)
                return failure
            try:
                try:
                    frame = self._hardware.observe_tags()
                except Exception as error:
                    if previous_action_frame is not None:
                        self._replay.observation_failed(
                            previous_action_frame,
                            getattr(error, 'error_code', type(error).__name__),
                        )
                    raise
                decision = decide(frame.poses.get(tag_id), phase)
                decision_at = time.monotonic()
                if decision.phase == 'arrived':
                    arrived_frames += 1
                else:
                    arrived_frames = 0
                frame_id = self._replay.record(
                    frame, tag_id, target_index, phase, decision.phase,
                    decision.reason, decision.action_group, arrived_frames,
                    previous_action_frame,
                    decision_at,
                )
                self._log_event({
                    'event': 'decision',
                    'frame_id': frame_id,
                    'captured_at_monotonic': frame.captured_at_monotonic,
                    'decision_at_monotonic': decision_at,
                    'target_id': tag_id,
                    'phase_before': phase,
                    'phase_after': decision.phase,
                    'reason': decision.reason,
                    'action_group': decision.action_group,
                    'arrival_confirmations': arrived_frames,
                    'previous_action_frame': previous_action_frame,
                    'pose': _pose_summary(frame.poses.get(tag_id)),
                })
                previous_action_frame = None
                phase = decision.phase
                if decision.phase == 'arrived':
                    if arrived_frames == ARRIVAL_CONFIRMATIONS:
                        return NavigationResult(
                            True, '', 'Target reached with stable observations'
                        )
                    continue
                if decision.action_group is not None:
                    self._run_step(frame_id, decision.action_group)
                    previous_action_frame = frame_id
            except MotionInterrupted as error:
                return NavigationResult(False, error.error_code, str(error))
            except MotionExecutionError as error:
                return NavigationResult(False, 'MOTION_FAILED', str(error))

    def _run_step(self, frame_id: int, action_group: str) -> None:
        started_at = time.monotonic()
        self._replay.action_started(frame_id, started_at)
        self._log_event({
            'event': 'action_started',
            'frame_id': frame_id,
            'action_group': action_group,
            'started_at_monotonic': started_at,
        })
        try:
            self._hardware.execute_action(action_group)
        except Exception as error:
            finished_at = time.monotonic()
            self._replay.action_finished(
                frame_id,
                round((finished_at - started_at) * 1000),
                getattr(error, 'error_code', type(error).__name__),
                finished_at,
            )
            self._log_action_finished(
                frame_id, action_group, started_at, finished_at,
                getattr(error, 'error_code', type(error).__name__),
            )
            raise
        finished_at = time.monotonic()
        self._replay.action_finished(
            frame_id,
            round((finished_at - started_at) * 1000),
            finished_at_monotonic=finished_at,
        )
        self._log_action_finished(
            frame_id, action_group, started_at, finished_at, None,
        )

    def _log_action_finished(
        self,
        frame_id: int,
        action_group: str,
        started_at: float,
        finished_at: float,
        error: str | None,
    ) -> None:
        self._log_event({
            'event': 'action_finished',
            'frame_id': frame_id,
            'action_group': action_group,
            'started_at_monotonic': started_at,
            'finished_at_monotonic': finished_at,
            'elapsed_ms': round((finished_at - started_at) * 1000),
            'error': error,
        })

    def _check_stop_conditions(self, deadline_unix_ms: int) -> NavigationResult | None:
        if self._is_cancel_requested():
            return NavigationResult(False, 'CANCEL_REQUESTED', 'Cancellation observed')
        if time.time_ns() // 1_000_000 >= deadline_unix_ms:
            return NavigationResult(False, 'DEADLINE_EXCEEDED', 'Task deadline elapsed')
        return None


def _pose_summary(pose: TagPose | None) -> dict | None:
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
        'reprojection_error_px': pose.reprojection_error_px,
        'image_margin_px': pose.image_margin_px,
    }
