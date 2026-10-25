import datetime
import json
import math
import time

import rclpy
from geometry_msgs.msg import Twist
from nav_msgs.msg import Odometry
from rclpy.node import Node
from sensor_msgs.msg import LaserScan
from std_msgs.msg import String

from tb4_gesture_control.behavior_fsm import (
    BehaviorFSM,
    CIRCLE_DIRECTION_LEFT,
    CIRCLE_DIRECTION_RIGHT,
    STATE_RUNNING,
)
from tb4_gesture_control.gesture_types import KEY_CONFIDENCE, KEY_GESTURE, KEY_STAMP, NONE_GESTURE

try:
    from irobot_create_msgs.msg import HazardDetection, HazardDetectionVector
    HAZARD_MSGS_AVAILABLE = True
except ImportError:
    HAZARD_MSGS_AVAILABLE = False


def quaternion_to_yaw(q):
    return math.atan2(2.0 * (q.w * q.z + q.x * q.y), 1.0 - 2.0 * (q.y * q.y + q.z * q.z))


def wrap_angle(angle):
    while angle > math.pi:
        angle -= 2.0 * math.pi
    while angle < -math.pi:
        angle += 2.0 * math.pi
    return angle


def is_signal_lost(now_mono, last_msg_time, signal_timeout_s):
    return now_mono - last_msg_time > signal_timeout_s


def circle_direction_from_param(value):
    return CIRCLE_DIRECTION_RIGHT if str(value).lower() == 'right' else CIRCLE_DIRECTION_LEFT


class RobotBehaviorNode(Node):

    def __init__(self):
        super().__init__('robot_behavior_node')

        self.declare_parameter('control_rate_hz', 20.0)
        self.declare_parameter('hold_s', 0.6)
        self.declare_parameter('stop_hold_s', 0.2)
        self.declare_parameter('cooldown_s', 1.0)
        self.declare_parameter('selection_timeout_s', 30.0)
        self.declare_parameter('signal_timeout_s', 3.0)
        self.declare_parameter('run_timeout_s', 40.0)
        self.declare_parameter('wave_needs_confirm', True)
        self.declare_parameter('wave_refractory_s', 8.0)
        self.declare_parameter('linear_speed', 0.2)
        self.declare_parameter('wave_angular_speed', 0.5)
        self.declare_parameter('circle_linear_speed', 0.2)
        self.declare_parameter('circle_angular_speed', 0.4)
        self.declare_parameter('circle_direction', 'left')
        self.declare_parameter('scan_guard_enabled', True)
        self.declare_parameter('scan_obstacle_distance', 0.35)
        self.declare_parameter('scan_front_half_angle', 0.4363)
        self.declare_parameter('scan_rear_half_angle', 0.4363)
        self.declare_parameter('scan_angle_offset', 1.5707963267948966)

        self.signal_timeout_s = float(self.get_parameter('signal_timeout_s').value)
        control_rate_hz = float(self.get_parameter('control_rate_hz').value)
        self.scan_guard_enabled = bool(self.get_parameter('scan_guard_enabled').value)
        self.scan_obstacle_distance = float(self.get_parameter('scan_obstacle_distance').value)
        self.scan_front_half_angle = float(self.get_parameter('scan_front_half_angle').value)
        self.scan_rear_half_angle = float(self.get_parameter('scan_rear_half_angle').value)
        self.scan_angle_offset = float(self.get_parameter('scan_angle_offset').value)

        self._scan_valid = None
        self._scan_obstacle_close_front = False
        self._scan_obstacle_close_rear = False
        self._scan_obstacle_range_front = None
        self._scan_obstacle_range_rear = None
        if self.scan_guard_enabled:
            self.create_subscription(LaserScan, '/scan', self._on_scan, 10)

        if HAZARD_MSGS_AVAILABLE:
            self.create_subscription(
                HazardDetectionVector, '/hazard_detection', self._on_hazard, 10)
        else:
            self.get_logger().warning(
                'irobot_create_msgs khong co san: bo qua lop an toan bumper /hazard_detection'
            )

        self.fsm = BehaviorFSM(
            hold_s=float(self.get_parameter('hold_s').value),
            stop_hold_s=float(self.get_parameter('stop_hold_s').value),
            cooldown_s=float(self.get_parameter('cooldown_s').value),
            selection_timeout_s=float(self.get_parameter('selection_timeout_s').value),
            run_timeout_s=float(self.get_parameter('run_timeout_s').value),
            wave_needs_confirm=bool(self.get_parameter('wave_needs_confirm').value),
            wave_refractory_s=float(self.get_parameter('wave_refractory_s').value),
            linear_speed=float(self.get_parameter('linear_speed').value),
            wave_angular_speed=float(self.get_parameter('wave_angular_speed').value),
            circle_linear_speed=float(self.get_parameter('circle_linear_speed').value),
            circle_angular_speed=float(self.get_parameter('circle_angular_speed').value),
            circle_direction=circle_direction_from_param(self.get_parameter('circle_direction').value),
            on_event=self._on_fsm_event,
        )
        self._run_first_command_logged = True

        self.cmd_pub = self.create_publisher(Twist, '/cmd_vel', 10)
        self.create_subscription(String, '/detected_gesture', self._on_gesture_msg, 50)
        self.create_subscription(Odometry, '/odom', self._on_odom, 10)

        self._last_msg_time = time.monotonic()
        self._signal_lost = False

        self._odom_pose = None
        self._last_control_pose = None

        self.create_timer(1.0 / control_rate_hz, self._control_step)

        self.get_logger().info('robot_behavior_node ready, state=IDLE')

    def _on_fsm_event(self, event, **kwargs):
        if event == 'started':
            self._run_first_command_logged = False
        stamp = datetime.datetime.now().isoformat(timespec='milliseconds')
        detail = ' '.join(f'{k}={v}' for k, v in kwargs.items())
        line = f'[{stamp}] FSM event={event} {detail}'.rstrip()
        if event in ('signal_lost', 'aborted', 'timeout'):
            self.get_logger().warning(line)
        else:
            self.get_logger().info(line)

    def _on_odom(self, msg):
        pos = msg.pose.pose.position
        yaw = quaternion_to_yaw(msg.pose.pose.orientation)
        self._odom_pose = (pos.x, pos.y, yaw)

    def _on_gesture_msg(self, msg):
        self._last_msg_time = time.monotonic()
        self._signal_lost = False

        try:
            payload = json.loads(msg.data)
            gesture = payload.get(KEY_GESTURE, NONE_GESTURE)
            confidence = float(payload.get(KEY_CONFIDENCE, 0.0))
            stamp = float(payload.get(KEY_STAMP, time.time()))
        except (json.JSONDecodeError, TypeError, ValueError):
            self.get_logger().warning(f'Malformed /detected_gesture payload: {msg.data!r}')
            return

        triggered = self.fsm.handle_gesture(gesture, stamp)
        if triggered is not None:
            self.get_logger().info(f'Gesture trigger: {triggered} (confidence={confidence:.2f})')

    def _on_scan(self, msg):
        if not any(r > 0.0 for r in msg.ranges):
            if self._scan_valid is not False:
                self.get_logger().warning(
                    'CANH BAO: /scan khong hop le (toan bo range = 0.0) '
                    '- tu TAT bo chong va cham theo /scan'
                )
            self._scan_valid = False
            self._scan_obstacle_close_front = False
            self._scan_obstacle_close_rear = False
            return
        self._scan_valid = True

        min_front = None
        min_rear = None
        angle = msg.angle_min
        for r in msg.ranges:
            if msg.range_min <= r <= msg.range_max:
                base_link_angle = math.atan2(
                    math.sin(angle + self.scan_angle_offset),
                    math.cos(angle + self.scan_angle_offset))
                if abs(base_link_angle) <= self.scan_front_half_angle:
                    if min_front is None or r < min_front:
                        min_front = r
                elif abs(abs(base_link_angle) - 3.14159265) <= self.scan_rear_half_angle:
                    if min_rear is None or r < min_rear:
                        min_rear = r
            angle += msg.angle_increment

        self._scan_obstacle_range_front = min_front
        self._scan_obstacle_range_rear = min_rear
        self._scan_obstacle_close_front = (
            min_front is not None and min_front < self.scan_obstacle_distance
        )
        self._scan_obstacle_close_rear = (
            min_rear is not None and min_rear < self.scan_obstacle_distance
        )

    def _on_hazard(self, msg):
        for d in msg.detections:
            if d.type == HazardDetection.BUMP:
                self.get_logger().warning('VA CHAM (bumper): dung ngay, huy luot dang chay, ve IDLE')
                self.fsm.abort('BUMP')
                self.cmd_pub.publish(Twist())
                break

    def _control_step(self):
        now_mono = time.monotonic()

        if is_signal_lost(now_mono, self._last_msg_time, self.signal_timeout_s):
            if not self._signal_lost:
                self.get_logger().warning(
                    f'No /detected_gesture for {self.signal_timeout_s:.1f}s, stopping'
                )
                self._signal_lost = True
                self.fsm.signal_lost()
            self.cmd_pub.publish(Twist())
            return

        self.fsm.check_selection_timeout(time.time())

        if self.fsm.state != STATE_RUNNING:
            self.cmd_pub.publish(Twist())
            return

        delta_distance = 0.0
        delta_angle = 0.0
        if self._odom_pose is not None:
            if self._last_control_pose is not None:
                x0, y0, yaw0 = self._last_control_pose
                x1, y1, yaw1 = self._odom_pose
                delta_distance = math.hypot(x1 - x0, y1 - y0)
                delta_angle = wrap_angle(yaw1 - yaw0)
            self._last_control_pose = self._odom_pose

        sim_now = self.get_clock().now().nanoseconds * 1e-9
        command = self.fsm.advance(delta_distance, delta_angle, sim_now=sim_now)
        if command is None:
            self.cmd_pub.publish(Twist())
            return

        linear_x, angular_z = command

        if self.scan_guard_enabled and self._scan_valid:
            if linear_x > 0.0 and self._scan_obstacle_close_front:
                self.get_logger().warning(
                    f'CHONG VA CHAM (scan): vat can phia truoc ~{self._scan_obstacle_range_front:.2f}m, '
                    'dung va huy hanh vi'
                )
                self.fsm.abort('SCAN_FRONT')
                self.cmd_pub.publish(Twist())
                return
            if linear_x < 0.0 and self._scan_obstacle_close_rear:
                self.get_logger().warning(
                    f'CHONG VA CHAM (scan, lui): vat can phia sau ~{self._scan_obstacle_range_rear:.2f}m, '
                    'dung va huy hanh vi'
                )
                self.fsm.abort('SCAN_REAR')
                self.cmd_pub.publish(Twist())
                return

        if not self._run_first_command_logged:
            self._on_fsm_event('moving', behavior=self.fsm.running_kind)
            self._run_first_command_logged = True

        twist = Twist()
        twist.linear.x = linear_x
        twist.angular.z = angular_z
        self.cmd_pub.publish(twist)


def main(args=None):
    rclpy.init(args=args)
    node = RobotBehaviorNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        for _ in range(5):
            node.cmd_pub.publish(Twist())
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
