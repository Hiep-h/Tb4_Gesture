import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

from tb4_gesture_control.robot_behavior_node import is_signal_lost


def test_signal_not_lost_when_gap_below_timeout():
    assert is_signal_lost(now_mono=10.0, last_msg_time=8.0, signal_timeout_s=3.0) is False


def test_signal_not_lost_exactly_at_timeout():
    assert is_signal_lost(now_mono=11.0, last_msg_time=8.0, signal_timeout_s=3.0) is False


def test_signal_lost_when_gap_exceeds_timeout():
    assert is_signal_lost(now_mono=11.1, last_msg_time=8.0, signal_timeout_s=3.0) is True


def test_slow_but_alive_gap_not_lost_at_new_default():
    assert is_signal_lost(now_mono=102.9, last_msg_time=100.0, signal_timeout_s=3.0) is False


def test_old_default_would_have_flagged_slow_gap_as_lost():
    assert is_signal_lost(now_mono=102.9, last_msg_time=100.0, signal_timeout_s=1.0) is True
