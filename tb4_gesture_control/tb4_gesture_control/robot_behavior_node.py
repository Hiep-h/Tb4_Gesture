"""ROS 2 node: turns recognized hand gestures into TurtleBot 4 behaviors.

Subscribes to /detected_gesture (std_msgs/msg/String, JSON payload from
gesture_recognition_node) and drives the robot on /cmd_vel
(geometry_msgs/msg/Twist) through a small state machine:

    IDLE --Pointing_Up/Victory--> SELECTED --Thumb_Up--> RUNNING --> IDLE
      ^                              |                      |
      |                              +-----Closed_Fist------+
      |                                                      |
      +------------------ Open_Palm (any state) --------------+

* Wave always plays an immediate "wave back" response while IDLE and does
  not require confirmation.
* Open_Palm is an emergency stop from any state.
* Closed_Fist cancels the current selection/behavior and returns to IDLE.
* A watchdog stops the robot if /detected_gesture goes silent, so losing
  the camera or the recognition process never leaves the robot moving.
* A gesture only fires an action once per continuous hold (it must drop
  back to "None"/change before the same gesture can fire again), plus a
  minimum time between actions -- this is the anti-noise mechanism the
  assignment asks for, so a flicker in the classifier can't spam
  commands.
"""

import json
import time

import rclpy
from geometry_msgs.msg import Twist
from rclpy.node import Node
from std_msgs.msg import String

from tb4_gesture_control.gesture_types import (
    CLOSED_FIST,
    KEY_CONFIDENCE,
    KEY_GESTURE,
    NONE_GESTURE,
    OPEN_PALM,
    POINTING_UP,
    THUMB_UP,
    VICTORY,
    WAVE,
)

STATE_IDLE = 'IDLE'
STATE_SELECTED = 'SELECTED'
STATE_RUNNING = 'RUNNING'

BEHAVIOR_FORWARD_BACKWARD = 'forward_backward'
BEHAVIOR_CIRCLE = 'circle'
BEHAVIOR_WAVE = 'wave'

LINEAR_SPEED = 0.15   # m/s, conservative for a bounded sim arena
ANGULAR_SPEED = 0.5   # rad/s


def _wave_sequence():
    """4 wave cycles: alternate turning left/right."""
    seg = (0.0, ANGULAR_SPEED, 0.5)
    seg_rev = (0.0, -ANGULAR_SPEED, 0.5)
    return [seg, seg_rev] * 4


def _forward_backward_sequence():
    """Drive forward then backward, 4 times."""
    fwd = (LINEAR_SPEED, 0.0, 1.0)
    bwd = (-LINEAR_SPEED, 0.0, 1.0)
    return [fwd, bwd] * 4


def _circle_sequence():
    """Constant linear + angular velocity traces a circular path."""
    return [(LINEAR_SPEED, ANGULAR_SPEED, 10.0)]


_BEHAVIOR_SEQUENCES = {
    BEHAVIOR_WAVE: _wave_sequence,
    BEHAVIOR_FORWARD_BACKWARD: _forward_backward_sequence,
    BEHAVIOR_CIRCLE: _circle_sequence,
}


class GestureEdgeTracker:
    """Turns a noisy, continuously-published gesture stream into one-shot
    triggers: a gesture only fires once per continuous hold, and must pass
    through "None" (or change) before it can fire again."""

    def __init__(self, required_consecutive=3, min_trigger_interval=0.5):
        self.required_consecutive = required_consecutive
        self.min_trigger_interval = min_trigger_interval
        self._last_gesture = NONE_GESTURE
        self._consecutive = 0
        self._armed_gesture = None  # gesture that has already fired this hold
        self._last_trigger_time = 0.0

    def process(self, gesture, now):
        if gesture != self._last_gesture:
            self._last_gesture = gesture
            self._consecutive = 1
        else:
            self._consecutive += 1

        if gesture == NONE_GESTURE:
            self._armed_gesture = None
            return None

        if (
            self._consecutive >= self.required_consecutive
            and gesture != self._armed_gesture
            and (now - self._last_trigger_time) >= self.min_trigger_interval
        ):
            self._armed_gesture = gesture
            self._last_trigger_time = now
            return gesture
        return None


class RobotBehaviorNode(Node):

    def __init__(self):
        super().__init__('robot_behavior_node')

        self.declare_parameter('signal_timeout', 2.0)
        self.declare_parameter('required_consecutive', 3)
        self.declare_parameter('min_trigger_interval', 0.5)
        self.declare_parameter('control_rate_hz', 20.0)

        self.signal_timeout = float(self.get_parameter('signal_timeout').value)
        control_rate_hz = float(self.get_parameter('control_rate_hz').value)

        self._edge_tracker = GestureEdgeTracker(
            required_consecutive=int(self.get_parameter('required_consecutive').value),
            min_trigger_interval=float(self.get_parameter('min_trigger_interval').value),
        )

        self.cmd_pub = self.create_publisher(Twist, '/cmd_vel', 10)
        self.create_subscription(String, '/detected_gesture', self._on_gesture_msg, 10)

        self._state = STATE_IDLE
        self._pending_behavior = None     # staged, waiting for Thumb_Up
        self._active_sequence = []
        self._active_index = 0
        self._segment_start = 0.0
        self._running_kind = None

        self._last_msg_time = None
        self._signal_lost = False

        self.create_timer(1.0 / control_rate_hz, self._control_step)

        self.get_logger().info('robot_behavior_node ready, state=IDLE')

    # ---- gesture handling -------------------------------------------------

    def _on_gesture_msg(self, msg):
        now = time.time()
        self._last_msg_time = now
        if self._signal_lost:
            self.get_logger().info('Gesture signal recovered')
        self._signal_lost = False

        try:
            payload = json.loads(msg.data)
            gesture = payload.get(KEY_GESTURE, NONE_GESTURE)
            confidence = float(payload.get(KEY_CONFIDENCE, 0.0))
        except (json.JSONDecodeError, TypeError, ValueError):
            self.get_logger().warning(f'Malformed /detected_gesture payload: {msg.data!r}')
            return

        triggered = self._edge_tracker.process(gesture, now)
        if triggered is None:
            return

        self.get_logger().info(f'Action trigger: {triggered} (confidence={confidence:.2f})')
        self._handle_action(triggered)

    def _handle_action(self, gesture):
        if gesture == OPEN_PALM:
            self._emergency_stop()
        elif gesture == CLOSED_FIST:
            self._cancel()
        elif gesture == WAVE:
            if self._state == STATE_IDLE:
                self._start_behavior(BEHAVIOR_WAVE)
            else:
                self.get_logger().info('Ignoring Wave while busy')
        elif gesture == POINTING_UP:
            if self._state == STATE_IDLE:
                self._select(BEHAVIOR_FORWARD_BACKWARD)
            else:
                self.get_logger().info('Ignoring Pointing_Up: not IDLE')
        elif gesture == VICTORY:
            if self._state == STATE_IDLE:
                self._select(BEHAVIOR_CIRCLE)
            else:
                self.get_logger().info('Ignoring Victory: not IDLE')
        elif gesture == THUMB_UP:
            if self._state == STATE_SELECTED:
                self._start_behavior(self._pending_behavior)
            else:
                self.get_logger().info('Ignoring Thumb_Up: nothing selected')

    def _select(self, behavior):
        self._pending_behavior = behavior
        self._state = STATE_SELECTED
        self.get_logger().info(
            f'Selected "{behavior}", show Thumb_Up to confirm or Closed_Fist to cancel'
        )

    def _start_behavior(self, behavior):
        self._pending_behavior = None
        self._active_sequence = _BEHAVIOR_SEQUENCES[behavior]()
        self._active_index = 0
        self._segment_start = time.time()
        self._running_kind = behavior
        self._state = STATE_RUNNING
        self.get_logger().info(f'Running behavior "{behavior}"')

    def _cancel(self):
        if self._state == STATE_IDLE:
            self.get_logger().info('Already idle, nothing to cancel')
            return
        self.get_logger().info(f'Cancelling (was {self._state}/{self._running_kind})')
        self._reset_to_idle()

    def _emergency_stop(self):
        self.get_logger().warning('Open_Palm: emergency stop')
        self._reset_to_idle()

    def _reset_to_idle(self):
        self._state = STATE_IDLE
        self._pending_behavior = None
        self._active_sequence = []
        self._active_index = 0
        self._running_kind = None
        self.cmd_pub.publish(Twist())

    # ---- control loop -------------------------------------------------

    def _control_step(self):
        now = time.time()

        if self._last_msg_time is not None and (now - self._last_msg_time) > self.signal_timeout:
            if not self._signal_lost:
                self.get_logger().warning(
                    f'No /detected_gesture for {self.signal_timeout:.1f}s, stopping'
                )
                self._signal_lost = True
                self._reset_to_idle()
            return

        if self._state != STATE_RUNNING:
            return

        if self._active_index >= len(self._active_sequence):
            self.get_logger().info(f'Behavior "{self._running_kind}" complete')
            self._reset_to_idle()
            return

        linear_x, angular_z, duration = self._active_sequence[self._active_index]
        if now - self._segment_start >= duration:
            self._active_index += 1
            self._segment_start = now
            if self._active_index >= len(self._active_sequence):
                self.get_logger().info(f'Behavior "{self._running_kind}" complete')
                self._reset_to_idle()
                return
            linear_x, angular_z, duration = self._active_sequence[self._active_index]

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
        node.cmd_pub.publish(Twist())
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
