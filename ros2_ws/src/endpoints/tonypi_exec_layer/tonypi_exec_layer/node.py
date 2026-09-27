"""TonyPi 动作组 ROS 2 action server。"""

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

from .contract import InvalidPayload, UnsupportedPrimitive, UnsupportedTag, parse_payload
from .execution import execution_steps


class TonyPiExecLayerNode(Node):
    """提供第一版 TonyPi ROS 2 执行 contract 的 action server。"""

    def __init__(self) -> None:
        super().__init__('tonypi_exec_layer')
        self.declare_parameter('action_name', '/tonypi/execute_task')
        self.declare_parameter('device_id', 'tonypi')

        action_name = str(self.get_parameter('action_name').value)
        self._device_id = str(self.get_parameter('device_id').value)
        self._tonypi_root = os.environ.get('TONYPI_ROOT', '/home/pi/TonyPi')
        self._sdk = None
        self._sdk_error = self._initialize_sdk()
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
        return ''

    def goal_callback(self, goal_request: ExecuteTask.Goal) -> GoalResponse:
        """校验并接受最多一个正在执行的合法 goal。"""
        if not self._claim_goal_slot():
            return GoalResponse.REJECT
        try:
            self._validate_goal(goal_request)
        except (InvalidPayload, UnsupportedPrimitive, UnsupportedTag, ValueError) as error:
            self._release_goal_slot()
            self.get_logger().warning(f'rejecting goal: {error}')
            return GoalResponse.REJECT
        return GoalResponse.ACCEPT

    def cancel_callback(self, _goal_handle) -> CancelResponse:
        """接受取消请求，但由执行回调在当前动作完成后处理。"""
        return CancelResponse.ACCEPT

    def execute_callback(self, goal_handle) -> ExecuteTask.Result:
        """按目标顺序执行动作组并发布反馈和终态结果。"""
        request = goal_handle.request
        try:
            if self._sdk_error:
                return self._abort_result(
                    goal_handle,
                    'SDK_INIT_FAILED',
                    self._sdk_error,
                )

            steps = self._prepare_steps(request)
            missing = self._missing_action_groups(steps)
            if missing:
                message = f'missing action group files: {", ".join(missing)}'
                self.get_logger().error(message)
                return self._abort_result(
                    goal_handle,
                    'ACTION_GROUP_MISSING',
                    message,
                )

            return self._execute_steps(goal_handle, request, steps)
        except Exception as error:  # noqa: BLE001 - 统一转换为 endpoint 结果
            self.get_logger().exception(f'task execution failed: {error}')
            return self._abort_result(
                goal_handle,
                'ACTION_EXECUTION_FAILED',
                str(error),
            )
        finally:
            self._release_goal_slot()

    def _prepare_steps(self, request):
        payload = parse_payload(request.primitive, request.payload_json)
        return execution_steps(payload['target_tags'])

    def _execute_steps(self, goal_handle, request, steps) -> ExecuteTask.Result:
        executed_action_groups = []
        for step in steps:
            if self._deadline_expired(request.deadline_unix_ms):
                return self._abort_result(
                    goal_handle,
                    'DEADLINE_EXCEEDED',
                    'Task deadline elapsed before the next action',
                )
            if goal_handle.is_cancel_requested:
                return self._abort_result(
                    goal_handle,
                    'CANCEL_REQUESTED',
                    'Cancellation observed before the next action',
                )

            self._run_action_group(step.action_group, request.task_id)
            executed_action_groups.append(step.action_group)
            self._publish_feedback(goal_handle, step, executed_action_groups)
            self.get_logger().info(
                f'task_id={request.task_id} tag_id={step.tag_id} '
                f'action_group={step.action_group} '
                f'executed_action_groups={executed_action_groups}'
            )

        if goal_handle.is_cancel_requested:
            return self._abort_result(
                goal_handle,
                'CANCEL_REQUESTED',
                'Cancellation observed after the current action',
            )
        goal_handle.succeed()
        return self._result(goal_handle, 'succeeded', '', 'Task completed')

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

    def _missing_action_groups(self, steps) -> list[str]:
        action_group_root = os.path.join(self._tonypi_root, 'ActionGroups')
        return [
            step.action_group
            for step in steps
            if not os.path.isfile(
                os.path.join(action_group_root, f'{step.action_group}.d6a')
            )
        ]

    def _run_action_group(self, action_group: str, task_id: str) -> None:
        self.get_logger().info(
            f'task_id={task_id} starting action_group={action_group}'
        )
        self._sdk.runActionGroup(
            action_group,
            path=os.path.join(self._tonypi_root, 'ActionGroups') + os.sep,
        )

    def _publish_feedback(self, goal_handle, step, executed_action_groups) -> None:
        feedback = ExecuteTask.Feedback()
        feedback.task_id = goal_handle.request.task_id
        feedback.state = 'running'
        feedback.progress = step.progress
        feedback.phase = f'tag_{step.tag_id}'
        feedback.details_json = json.dumps(
            {
                'current_tag': step.tag_id,
                'next_tag': step.next_tag,
                'action_group': step.action_group,
                'executed_action_groups': executed_action_groups,
            },
            separators=(',', ':'),
            sort_keys=True,
        )
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

    def _deadline_expired(self, deadline_unix_ms: int) -> bool:
        if deadline_unix_ms == 0:
            return False
        return time.time_ns() // 1_000_000 >= deadline_unix_ms

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
