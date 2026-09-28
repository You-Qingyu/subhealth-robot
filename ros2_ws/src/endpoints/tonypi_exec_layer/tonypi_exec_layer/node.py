"""TonyPi AprilTag 闭环导航 ROS 2 action server。"""

import json
import os
import sys
import time
import threading

import rclpy
from rclpy.action import ActionServer, CancelResponse, GoalResponse
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from task_interfaces.action import ExecuteTask

from .camera import CameraObservationError, TagCamera
from .contract import InvalidPayload, UnsupportedPrimitive, parse_payload
from .head import HeadAligner
from .hardware import NavigationHardware
from .motion import FiniteMotionRunner
from .navigation import (
    DEFAULT_TASK_TIMEOUT_S,
    NavigationController,
    REQUIRED_ACTION_GROUPS,
)


class TonyPiExecLayerNode(Node):
    """提供 TonyPi AprilTag 闭环导航 action server。"""

    def __init__(self) -> None:
        super().__init__('tonypi_exec_layer')
        self.declare_parameter('action_name', '/tonypi/execute_task')
        self.declare_parameter('device_id', 'tonypi')
        self.declare_parameter('camera_device', '/dev/video0')
        self.declare_parameter('tag_family', '36h11')
        self.declare_parameter('camera_warmup_frames', 10)

        action_name = str(self.get_parameter('action_name').value)
        self._device_id = str(self.get_parameter('device_id').value)
        self._tonypi_root = os.environ.get('TONYPI_ROOT', '/home/pi/TonyPi')
        self._camera_device = str(self.get_parameter('camera_device').value)
        self._tag_family = str(self.get_parameter('tag_family').value)
        self._camera_warmup_frames = int(
            self.get_parameter('camera_warmup_frames').value
        )
        self._sdk = None
        self._head = None
        self._motion = None
        self._sdk_error = self._initialize_sdk()
        if not self._sdk_error:
            try:
                self._head = HeadAligner(self._sdk)
                self._motion = FiniteMotionRunner(
                    self._sdk,
                    os.path.join(self._tonypi_root, 'ActionGroups') + os.sep,
                )
            except Exception as error:  # noqa: BLE001 - 统一报告硬件初始化错误
                self._sdk_error = f'could not initialize TonyPi motion control: {error}'
        self._active_goal = False
        self._goal_state_lock = threading.Lock()
        self._action_server = ActionServer(
            self,
            ExecuteTask,
            action_name,
            execute_callback=self.execute_callback,
            goal_callback=self.goal_callback,
            cancel_callback=self.cancel_callback,
            callback_group=ReentrantCallbackGroup(),
        )
        if self._sdk_error:
            self.get_logger().error(self._sdk_error)
        else:
            self.get_logger().info(
                f'TonyPi SDK initialized; root={self._tonypi_root}'
            )

    def _initialize_sdk(self) -> str | None:
        sdk_path = os.path.join(self._tonypi_root, 'HiwonderSDK')
        if not os.path.isdir(sdk_path):
            return f'SDK root does not contain HiwonderSDK: {sdk_path}'
        sys.path.insert(0, sdk_path)
        try:
            import hiwonder.ActionGroupControl as action_group_control
        except Exception as error:  # noqa: BLE001 - 统一报告硬件初始化错误
            return f'could not initialize TonyPi SDK: {error}'
        self._sdk = action_group_control
        return None

    def goal_callback(self, goal_request: ExecuteTask.Goal) -> GoalResponse:
        """校验并接受最多一个正在执行的合法 goal。"""
        if not self._claim_goal_slot():
            return GoalResponse.REJECT
        try:
            self._validate_goal(goal_request)
        except (InvalidPayload, UnsupportedPrimitive, ValueError) as error:
            self._release_goal_slot()
            self.get_logger().warning(f'rejecting goal: {error}')
            return GoalResponse.REJECT
        return GoalResponse.ACCEPT

    def cancel_callback(self, _goal_handle) -> CancelResponse:
        """接受取消请求，由有限动作入口请求安全停止。"""
        return CancelResponse.ACCEPT

    def execute_callback(self, goal_handle) -> ExecuteTask.Result:
        """按目标顺序执行 AprilTag 闭环导航并发布终态结果。"""
        request = goal_handle.request
        try:
            if self._sdk_error:
                return self._abort_result(
                    goal_handle,
                    'SDK_INIT_FAILED',
                    self._sdk_error,
                )

            payload = parse_payload(request.primitive, request.payload_json)
            missing = self._missing_action_groups()
            if missing:
                message = f'missing action group files: {", ".join(missing)}'
                self.get_logger().error(message)
                return self._abort_result(
                    goal_handle,
                    'ACTION_GROUP_MISSING',
                    message,
                )

            deadline = self._effective_deadline(request.deadline_unix_ms)
            return self._execute_navigation(goal_handle, request, payload, deadline)
        except Exception as error:  # noqa: BLE001 - 统一转换为 endpoint 结果
            self.get_logger().exception(f'task execution failed: {error}')
            return self._abort_result(
                goal_handle,
                'ACTION_EXECUTION_FAILED',
                str(error),
            )
        finally:
            self._release_goal_slot()

    def _execute_navigation(
        self,
        goal_handle,
        request,
        payload: dict,
        deadline_unix_ms: int,
    ) -> ExecuteTask.Result:
        calibration_path = os.path.join(
            self._tonypi_root,
            'Functions/CameraCalibration/calibration_param.npz',
        )
        if not os.path.isfile(calibration_path):
            return self._abort_result(
                goal_handle,
                'CALIBRATION_MISSING',
                f'camera calibration file not found: {calibration_path}',
            )
        try:
            with TagCamera(
                self._camera_device,
                calibration_path,
                self._tag_family,
                self._camera_warmup_frames,
            ) as camera:
                controller = NavigationController(
                    hardware=NavigationHardware(
                        camera=camera,
                        head=self._head,
                        motion=self._motion,
                        allowed_actions=REQUIRED_ACTION_GROUPS,
                        is_cancel_requested=lambda: goal_handle.is_cancel_requested,
                        deadline_unix_ms=deadline_unix_ms,
                    ),
                    is_cancel_requested=lambda: goal_handle.is_cancel_requested,
                    publish_target_arrived=lambda tag_id, index, total: (
                        self._publish_target_arrived(
                            goal_handle,
                            tag_id,
                            index,
                            total,
                        )
                    ),
                    publish_step=lambda event: self._publish_navigation_step(
                        goal_handle, event
                    ),
                )
                navigation_result = controller.execute(
                    payload['target_tags'],
                    deadline_unix_ms,
                )
        except CameraObservationError as error:
            return self._abort_result(goal_handle, 'CAMERA_FAILED', str(error))
        except ValueError as error:
            return self._abort_result(goal_handle, 'CAMERA_CONFIG_FAILED', str(error))

        if not navigation_result.succeeded:
            return self._abort_result(
                goal_handle,
                navigation_result.error_code,
                navigation_result.message,
            )
        goal_handle.succeed()
        return self._result(goal_handle, 'succeeded', '', navigation_result.message)

    def _validate_goal(self, request: ExecuteTask.Goal) -> None:
        if not request.task_id:
            raise ValueError('task_id must not be empty')
        if request.device_id != self._device_id:
            raise ValueError(f'unsupported device_id: {request.device_id}')
        if request.deadline_unix_ms < 0:
            raise ValueError('deadline_unix_ms must not be negative')
        parse_payload(request.primitive, request.payload_json)

    def _claim_goal_slot(self) -> bool:
        with self._goal_state_lock:
            if self._active_goal:
                return False
            self._active_goal = True
            return True

    def _release_goal_slot(self) -> None:
        with self._goal_state_lock:
            self._active_goal = False

    def _missing_action_groups(self) -> list[str]:
        action_group_root = os.path.join(self._tonypi_root, 'ActionGroups')
        return [
            action_group
            for action_group in REQUIRED_ACTION_GROUPS
            if not os.path.isfile(
                os.path.join(action_group_root, f'{action_group}.d6a')
            )
        ]

    def _publish_target_arrived(
        self,
        goal_handle,
        tag_id: int,
        index: int,
        total: int,
    ) -> None:
        feedback = ExecuteTask.Feedback()
        feedback.task_id = goal_handle.request.task_id
        feedback.state = 'running'
        feedback.progress = (index + 1) / total
        feedback.phase = f'tag_{tag_id}'
        feedback.details_json = json.dumps(
            {
                'current_tag': tag_id,
                'target_index': index,
                'target_count': total,
                'stable_observations': 3,
            },
            separators=(',', ':'),
            sort_keys=True,
        )
        feedback.timestamp = self.get_clock().now().to_msg()
        goal_handle.publish_feedback(feedback)

    def _publish_navigation_step(self, goal_handle, event: dict) -> None:
        """将每步决策与前后位姿同时发送到日志和 action feedback。"""
        record = {'task_id': goal_handle.request.task_id, **event}
        details = json.dumps(
            record, ensure_ascii=False, separators=(',', ':'), sort_keys=True
        )
        self.get_logger().info(f'tonypi_navigation_step {details}')
        feedback = ExecuteTask.Feedback()
        feedback.task_id = goal_handle.request.task_id
        feedback.state = 'running'
        feedback.progress = event['target_index'] / event['target_count']
        feedback.phase = event['phase']
        feedback.details_json = details
        feedback.timestamp = self.get_clock().now().to_msg()
        goal_handle.publish_feedback(feedback)

    def _result(
        self, goal_handle, final_state: str, error_code: str, message: str
    ) -> ExecuteTask.Result:
        result = ExecuteTask.Result()
        result.task_id = goal_handle.request.task_id
        result.final_state = final_state
        result.error_code = error_code
        result.message = message
        result.finished_time = self.get_clock().now().to_msg()
        return result

    def _abort_result(
        self, goal_handle, error_code: str, message: str
    ) -> ExecuteTask.Result:
        goal_handle.abort()
        return self._result(goal_handle, 'failed', error_code, message)

    def _effective_deadline(self, deadline_unix_ms: int) -> int:
        if deadline_unix_ms:
            return deadline_unix_ms
        return time.time_ns() // 1_000_000 + int(DEFAULT_TASK_TIMEOUT_S * 1000)

    def destroy_node(self) -> None:
        """销毁 action server 和 ROS node，不追加复位动作。"""
        self._action_server.destroy()
        super().destroy_node()


def main(args=None) -> None:
    """初始化 ROS、运行 TonyPi endpoint，并在退出时释放 node。"""
    rclpy.init(args=args)
    node = TonyPiExecLayerNode()
    executor = MultiThreadedExecutor()
    executor.add_node(node)
    try:
        executor.spin()
    except KeyboardInterrupt:
        pass
    finally:
        executor.shutdown()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
