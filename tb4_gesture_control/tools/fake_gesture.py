#!/usr/bin/env python3
import argparse
import json
import os
import sys
import time

import rclpy
from rclpy.node import Node
from std_msgs.msg import String

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

from tb4_gesture_control.gesture_types import (
    DETECTED_GESTURE_TOPIC,
    KEY_CONFIDENCE,
    KEY_GESTURE,
    KEY_STAMP,
    NONE_GESTURE,
)

DEFAULT_RATE_HZ = 15.0
DEFAULT_CONFIDENCE = 0.9


def parse_step(s):
    gesture, duration = s.split(':')
    return gesture, float(duration)


class FakeGestureNode(Node):

    def __init__(self, steps, rate_hz, confidence):
        super().__init__('fake_gesture_node')
        self.pub = self.create_publisher(String, DETECTED_GESTURE_TOPIC, 10)
        self.steps = steps
        self.confidence = confidence
        self.index = 0
        self.step_start = time.time()
        self.create_timer(1.0 / rate_hz, self._tick)

    def _current_gesture(self):
        if self.index >= len(self.steps):
            return NONE_GESTURE
        gesture, duration = self.steps[self.index]
        if time.time() - self.step_start >= duration:
            self.index += 1
            self.step_start = time.time()
            if self.index >= len(self.steps):
                return NONE_GESTURE
            gesture, _duration = self.steps[self.index]
        return gesture

    def _tick(self):
        gesture = self._current_gesture()
        msg = String()
        msg.data = json.dumps({
            KEY_GESTURE: gesture,
            KEY_CONFIDENCE: self.confidence if gesture != NONE_GESTURE else 0.0,
            KEY_STAMP: time.time(),
        })
        self.pub.publish(msg)
        if gesture != NONE_GESTURE:
            self.get_logger().info(f'fake_gesture -> {gesture}')


def main():
    parser = argparse.ArgumentParser(
        description='Phat /detected_gesture gia lap theo kich ban, dung de kiem thu '
                     'robot_behavior_node (FSM + /odom) khong can webcam that.')
    parser.add_argument('--sequence', nargs='+', required=True,
                         help='Danh sach "Gesture:giay", vd Wave:3 None:1 Pointing_Up:2 None:1 Thumb_Up:2 None:2')
    parser.add_argument('--rate-hz', type=float, default=DEFAULT_RATE_HZ)
    parser.add_argument('--confidence', type=float, default=DEFAULT_CONFIDENCE)
    args = parser.parse_args()

    steps = [parse_step(s) for s in args.sequence]
    total_duration = sum(d for _, d in steps) + 1.0

    rclpy.init()
    node = FakeGestureNode(steps, args.rate_hz, args.confidence)
    end_time = time.time() + total_duration
    try:
        while rclpy.ok() and time.time() < end_time:
            rclpy.spin_once(node, timeout_sec=0.1)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
