"""ROS 2 publisher for deterministic physiological sensor samples."""

import random

import rclpy
from physio_interfaces.msg import PhysioSample
from rclpy.node import Node
from rclpy.qos import HistoryPolicy, QoSProfile, ReliabilityPolicy

from .model import SENSOR_SPECS, sample_value


class PhysioMockPublisher(Node):
    """Publish reproducible samples for all supported sensor sources."""

    def __init__(self) -> None:
        super().__init__('physio_mock_publisher')
        self.declare_parameter('scenario', 'normal')
        self.declare_parameter('rate_hz', 1.0)
        self.declare_parameter('random_seed', 0)

        rate_hz = float(self.get_parameter('rate_hz').value)
        if rate_hz <= 0.0:
            self.get_logger().warning('rate_hz must be positive; falling back to 1.0 Hz')
            rate_hz = 1.0

        random_seed = int(self.get_parameter('random_seed').value)
        self._rng = random.Random(random_seed)
        qos = QoSProfile(
            history=HistoryPolicy.KEEP_LAST,
            reliability=ReliabilityPolicy.RELIABLE,
            depth=10,
        )
        self._publishers = {
            spec: self.create_publisher(
                PhysioSample,
                f'/physio/{spec.data_src}',
                qos,
            )
            for spec in SENSOR_SPECS
        }
        self._timer = self.create_timer(1.0 / rate_hz, self._publish_samples)

    def _publish_samples(self) -> None:
        scenario = str(self.get_parameter('scenario').value)
        for spec, publisher in self._publishers.items():
            message = PhysioSample()
            message.timestamp = self.get_clock().now().to_msg()
            message.data_src = spec.data_src
            message.data_type = spec.data_type
            message.data = sample_value(spec, scenario, self._rng)
            message.valid = True
            publisher.publish(message)


def main(args=None) -> None:
    rclpy.init(args=args)
    node = PhysioMockPublisher()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()
