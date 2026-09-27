"""ROS 2 action server for deterministic task execution."""

import json
import time

import rclpy
from rclpy.action import ActionServer, GoalResponse
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from task_interfaces.action import ExecuteTask

from .contract import (
    InvalidPayload,
    parse_payload,
    UnsupportedPrimitive,
)
from .execution import (
    execution_steps,
    validate_step_delay,
)


class MockExecLayerNode(Node):
    """Serve predictable execution results for integration testing."""

    def __init__(self) -> None:
        super().__init__('mock_exec_layer')
        self.declare_parameter('action_name', '/mock_exec/execute_task')
        self.declare_parameter('device_id', 'mock_exec')
        self.declare_parameter('step_delay_s', 1.0)

        action_name = self.get_parameter('action_name').value
        self._device_id = str(self.get_parameter('device_id').value)
        self._step_delay_s = validate_step_delay(
            float(self.get_parameter('step_delay_s').value)
        )
        self._action_server = ActionServer(
            self,
            ExecuteTask,
            action_name,
            execute_callback=self.execute_callback,
            goal_callback=self.goal_callback,
            callback_group=ReentrantCallbackGroup(),
        )

    def goal_callback(self, goal_request: ExecuteTask.Goal) -> GoalResponse:
        if not goal_request.task_id or goal_request.device_id != self._device_id:
            return GoalResponse.REJECT
        if goal_request.deadline_unix_ms < 0:
            return GoalResponse.REJECT
        try:
            parse_payload(goal_request.primitive, goal_request.payload_json)
        except (InvalidPayload, UnsupportedPrimitive):
            return GoalResponse.REJECT
        return GoalResponse.ACCEPT

    def execute_callback(self, goal_handle) -> ExecuteTask.Result:
        request = goal_handle.request
        try:
            payload = parse_payload(request.primitive, request.payload_json)
            steps = execution_steps(request.primitive, payload)
        except InvalidPayload as error:
            goal_handle.abort()
            return self._result(goal_handle, 'failed', 'INVALID_PAYLOAD', str(error))
        except UnsupportedPrimitive as error:
            goal_handle.abort()
            return self._result(
                goal_handle, 'failed', 'UNSUPPORTED_PRIMITIVE', str(error)
            )

        for step_index, step in enumerate(steps, start=1):
            self.get_logger().info(
                f"executing task_id={request.task_id} "
                f"current_tag={step.details['current_tag']} "
                f"next_tag={step.details['next_tag']} "
                f"progress={step.progress:.3f} step_index={step_index}"
            )
            if self._step_delay_s > 0.0:
                time.sleep(self._step_delay_s)
            if self._deadline_expired(request.deadline_unix_ms):
                goal_handle.abort()
                return self._result(
                    goal_handle, 'failed', 'DEADLINE_EXCEEDED', 'Task deadline elapsed'
                )

            self._publish_feedback(goal_handle, 'running', step)

        goal_handle.succeed()
        return self._result(goal_handle, 'succeeded', '', 'Task completed')

    def _publish_feedback(self, goal_handle, state: str, step) -> None:
        feedback = ExecuteTask.Feedback()
        feedback.task_id = goal_handle.request.task_id
        feedback.state = state
        feedback.progress = max(0.0, min(1.0, step.progress))
        feedback.phase = step.phase
        feedback.details_json = json.dumps(
            step.details, separators=(',', ':'), sort_keys=True
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

    def _deadline_expired(self, deadline_unix_ms: int) -> bool:
        if deadline_unix_ms == 0:
            return False
        return time.time_ns() // 1_000_000 >= deadline_unix_ms

    def destroy_node(self) -> None:
        self._action_server.destroy()
        super().destroy_node()


def main(args=None) -> None:
    rclpy.init(args=args)
    node = MockExecLayerNode()
    executor = MultiThreadedExecutor()
    executor.add_node(node)
    try:
        executor.spin()
    except KeyboardInterrupt:
        pass
    finally:
        executor.shutdown()
        node.destroy_node()
        rclpy.shutdown()
