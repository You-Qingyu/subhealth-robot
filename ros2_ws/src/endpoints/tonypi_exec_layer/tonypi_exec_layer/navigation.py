"""基于 AprilTag 位姿的 TonyPi 离散动作状态机。"""

from dataclasses import dataclass
import random
import time
from typing import Callable

from .hardware import HeadScanSample, HeadScanStage, NavigationHardware, TurnDirection
from .motion import MotionExecutionError, MotionInterrupted
from .navigation_replay import NavigationReplay, ObservationAnnotation, ScanAnnotation
from .tag_pose import TagPose


TARGET_DISTANCE_M = 0.50
DISTANCE_TOLERANCE_M = 0.08
BEARING_TOLERANCE_DEG = 5.0
FACING_TOLERANCE_DEG = 15.0
APPROACH_HALF_ANGLE_DEG = 30.0
LATERAL_DIRECTION_EPSILON_DEG = 2.0
ARRIVAL_CONFIRMATIONS = 3
SEARCH_MAX_STEPS = 32
REAR_SCAN_STEPS = 16
DEFAULT_TASK_TIMEOUT_S = 120.0

TURN_LEFT_ACTION = 'turn_left_small_step'
TURN_RIGHT_ACTION = 'turn_right_small_step'
TERMINAL_TURN_LEFT_ACTION = 'turn_left_small_step_a'
TERMINAL_TURN_RIGHT_ACTION = 'turn_right_small_step_a'
LEFT_MOVE_ACTION = 'left_move'
RIGHT_MOVE_ACTION = 'right_move'
FORWARD_ACTION = 'go_forward_one_step'
BACKWARD_ACTION = 'back_one_step'
REQUIRED_ACTION_GROUPS = (
    TURN_LEFT_ACTION,
    TURN_RIGHT_ACTION,
    TERMINAL_TURN_LEFT_ACTION,
    TERMINAL_TURN_RIGHT_ACTION,
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


@dataclass
class _TargetProgress:
    """当前目标的搜索预算、扫描方向与连续到达计数。"""

    phase: str = 'OBSERVE_TARGET'
    scan_action: str | None = None
    body_action: str | None = None
    scan_steps: int = 0
    body_steps: int = 0
    arrived_frames: int = 0
    previous_action_frame: int | None = None

    def decide(self, pose: TagPose | None) -> NavigationDecision:
        if pose is not None:
            self.body_steps = 0
            self.body_action = None
        if pose is None and self.scan_steps == SEARCH_MAX_STEPS:
            decision = NavigationDecision('FAILED', None, 'target_not_found')
        elif pose is None and self.phase in ('BODY_SCAN', 'TURN_TOWARD_DETECTION'):
            if self.phase == 'BODY_SCAN' and self.body_steps == REAR_SCAN_STEPS:
                decision = NavigationDecision('REAR_HEAD_SCAN', None, 'rear_reached')
            else:
                action = self.body_action if self.phase == 'BODY_SCAN' else self.scan_action
                decision = NavigationDecision(self.phase, action, 'body_search')
        else:
            decision = decide(pose)
        self.arrived_frames = (
            self.arrived_frames + 1 if decision.phase == 'ARRIVAL_CONFIRM' else 0
        )
        return decision

    def finish_action(self, decision: NavigationDecision, frame_id: int) -> None:
        self.previous_action_frame = frame_id
        if decision.reason == 'body_search':
            self.scan_steps += 1
            if decision.phase == 'BODY_SCAN':
                self.body_steps += 1

    def finish_scan(self, direction: TurnDirection | None) -> None:
        if direction is not None:
            self.scan_action = (
                TURN_LEFT_ACTION if direction == TurnDirection.LEFT else TURN_RIGHT_ACTION
            )
            self.phase = 'TURN_TOWARD_DETECTION'
        else:
            self.phase = 'BODY_SCAN'
            if self.body_action is None:
                self.body_action = random.choice((TURN_LEFT_ACTION, TURN_RIGHT_ACTION))


def decide(pose: TagPose | None) -> NavigationDecision:
    """正前方观测分发可见目标；不可见交给云台搜索。"""
    if pose is None:
        return NavigationDecision('HEAD_SCAN', None, 'target_not_detected')
    if abs(pose.bearing_deg) > APPROACH_HALF_ANGLE_DEG:
        return NavigationDecision('ALIGN_VISIBLE_TARGET', _turn_toward_tag(pose), 'outside_approach_range')
    if pose.distance_m > TARGET_DISTANCE_M + DISTANCE_TOLERANCE_M:
        return NavigationDecision('APPROACH', FORWARD_ACTION, 'distance_too_far')
    return _terminal_decision(pose)


def _terminal_decision(pose: TagPose) -> NavigationDecision:
    if pose.distance_m < TARGET_DISTANCE_M - DISTANCE_TOLERANCE_M:
        return NavigationDecision('FINAL_ALIGN', BACKWARD_ACTION, 'distance_too_close')
    if abs(pose.bearing_deg) > BEARING_TOLERANCE_DEG:
        return NavigationDecision(
            'FINAL_ALIGN', _terminal_turn_toward_tag(pose), 'bearing_not_centered'
        )
    if pose.facing_error_deg <= FACING_TOLERANCE_DEG:
        return NavigationDecision('ARRIVAL_CONFIRM', None, 'within_arrival_tolerances')
    lateral_error = pose.normal_bearing_deg - pose.bearing_deg
    if abs(lateral_error) <= LATERAL_DIRECTION_EPSILON_DEG:
        return NavigationDecision('FINAL_ALIGN', None, 'lateral_direction_uncertain')
    action = LEFT_MOVE_ACTION if lateral_error > 0 else RIGHT_MOVE_ACTION
    return NavigationDecision('FINAL_ALIGN', action, 'facing_not_aligned')


def _turn_toward_tag(pose: TagPose) -> str:
    return TURN_LEFT_ACTION if pose.bearing_deg < 0 else TURN_RIGHT_ACTION


def _terminal_turn_toward_tag(pose: TagPose) -> str:
    return (
        TERMINAL_TURN_LEFT_ACTION
        if pose.bearing_deg < 0 else TERMINAL_TURN_RIGHT_ACTION
    )


class NavigationController:
    """逐帧分发正前方导航与有界目标搜索。"""

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
        progress = _TargetProgress()
        while True:
            failure = self._check_stop_conditions(deadline_unix_ms)
            if failure:
                if progress.previous_action_frame is not None:
                    self._replay.observation_failed(
                        progress.previous_action_frame, failure.error_code,
                    )
                return failure
            try:
                decision, frame_id = self._observe_and_record(
                    tag_id, target_index, progress,
                )
                result = self._advance_target(
                    tag_id, target_index, deadline_unix_ms,
                    progress, decision, frame_id,
                )
                if result is not None:
                    return result
            except MotionInterrupted as error:
                return NavigationResult(False, error.error_code, str(error))
            except MotionExecutionError as error:
                return NavigationResult(False, 'MOTION_FAILED', str(error))

    def _observe_and_record(
        self, tag_id: int, target_index: int, progress: _TargetProgress,
    ) -> tuple[NavigationDecision, int]:
        try:
            frame = self._hardware.observe_tags()
        except Exception as error:
            if progress.previous_action_frame is not None:
                self._replay.observation_failed(
                    progress.previous_action_frame,
                    getattr(error, 'error_code', type(error).__name__),
                )
            raise
        decision = progress.decide(frame.poses.get(tag_id))
        decision_at = time.monotonic()
        annotation = ObservationAnnotation(
            phase_before=progress.phase,
            phase_after=decision.phase,
            reason=decision.reason,
            action_group=decision.action_group,
            confirmations=progress.arrived_frames,
            previous_action_frame=progress.previous_action_frame,
            decision_at_monotonic=decision_at,
            scan_steps_completed=progress.scan_steps,
        )
        frame_id = self._replay.record(frame, tag_id, target_index, annotation)
        self._log_event({
            'event': 'decision',
            'frame_id': frame_id,
            'read_finished_at_monotonic': frame.read_finished_at_monotonic,
            'read_started_at_monotonic': frame.read_started_at_monotonic,
            'capture_sequence': frame.capture_sequence,
            'skipped_frames': frame.skipped_frames,
            'decision_at_monotonic': decision_at,
            'target_id': tag_id,
            'phase_before': progress.phase,
            'phase_after': decision.phase,
            'reason': decision.reason,
            'action_group': decision.action_group,
            'arrival_confirmations': progress.arrived_frames,
            'previous_action_frame': progress.previous_action_frame,
            'scan_steps_completed': progress.scan_steps,
            'pose': _pose_summary(frame.poses.get(tag_id)),
        })
        progress.previous_action_frame = None
        progress.phase = decision.phase
        return decision, frame_id

    def _advance_target(
        self, tag_id: int, target_index: int, deadline_unix_ms: int,
        progress: _TargetProgress, decision: NavigationDecision, frame_id: int,
    ) -> NavigationResult | None:
        if decision.phase == 'FAILED':
            failure = self._check_stop_conditions(deadline_unix_ms)
            return failure or NavigationResult(
                False, 'TARGET_NOT_FOUND',
                f'Tag {tag_id} not found after {progress.scan_steps} turns',
            )
        if decision.phase == 'ARRIVAL_CONFIRM':
            if progress.arrived_frames == ARRIVAL_CONFIRMATIONS:
                return NavigationResult(True, '', 'Target reached with stable observations')
            return None
        if decision.phase in ('HEAD_SCAN', 'REAR_HEAD_SCAN'):
            scan = self._hardware.scan_head(
                tag_id,
                lambda sample: self._record_head_sample(
                    sample, tag_id, target_index, decision.phase, progress.scan_steps,
                ),
            )
            if scan.direction is None and decision.phase == 'REAR_HEAD_SCAN':
                failure = self._check_stop_conditions(deadline_unix_ms)
                return failure or NavigationResult(
                    False, 'TARGET_NOT_FOUND', f'Tag {tag_id} not found behind robot',
                )
            progress.finish_scan(scan.direction)
            return None
        if decision.action_group is not None:
            self._run_step(frame_id, decision.action_group)
            progress.finish_action(decision, frame_id)
        return None

    def _record_head_sample(
        self, sample: HeadScanSample, tag_id: int, target_index: int,
        phase: str, scan_steps: int,
    ) -> None:
        detected = tag_id in sample.frame.poses
        reason = 'candidate' if detected else 'not_detected'
        sample_phase = (
            'VERIFY_HEAD_DETECTION' if sample.stage == HeadScanStage.CONFIRMATION else phase
        )
        frame_id = self._replay.record(
            sample.frame, tag_id, target_index,
            ObservationAnnotation(
                phase_before=phase,
                phase_after=sample_phase,
                reason=reason,
                action_group=None,
                confirmations=0,
                previous_action_frame=None,
                decision_at_monotonic=time.monotonic(),
                scan_steps_completed=scan_steps,
                scan=ScanAnnotation(
                    pulse=sample.pulse,
                    stage=sample.stage,
                    scan_direction=sample.scan_direction,
                    turn_direction=sample.turn_direction,
                ),
            ),
        )
        self._log_event({
            'event': 'head_scan', 'frame_id': frame_id, 'target_id': tag_id,
            'phase': sample_phase, 'head_pulse': sample.pulse,
            'stage': sample.stage.value, 'detected': detected,
            'head_scan_direction': sample.scan_direction.value,
            'head_turn_direction': (
                sample.turn_direction.value if sample.turn_direction is not None else None
            ),
            'read_finished_at_monotonic': sample.frame.read_finished_at_monotonic,
        })

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
