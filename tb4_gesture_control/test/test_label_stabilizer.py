import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

from tb4_gesture_control.gesture_recognition_node import LabelStabilizer
from tb4_gesture_control.gesture_types import NONE_GESTURE, VICTORY


def _enter_gesture(stabilizer, label, confidence=0.9, count=3):
    state = None
    for _ in range(count):
        state, _ = stabilizer.update(label, confidence)
    return state


def test_none_for_exit_none_frames_resets_to_none():
    stabilizer = LabelStabilizer(enter_consecutive=3, exit_none_frames=3)
    assert _enter_gesture(stabilizer, VICTORY) == VICTORY

    state, _ = stabilizer.update(NONE_GESTURE, 0.0)
    assert state == VICTORY
    state, _ = stabilizer.update(NONE_GESTURE, 0.0)
    assert state == VICTORY
    state, _ = stabilizer.update(NONE_GESTURE, 0.0)
    assert state == NONE_GESTURE


def test_short_none_blip_does_not_reset():
    stabilizer = LabelStabilizer(enter_consecutive=3, exit_none_frames=3)
    assert _enter_gesture(stabilizer, VICTORY) == VICTORY

    state, _ = stabilizer.update(NONE_GESTURE, 0.0)
    assert state == VICTORY
    state, _ = stabilizer.update(NONE_GESTURE, 0.0)
    assert state == VICTORY

    state, conf = stabilizer.update(VICTORY, 0.9)
    assert state == VICTORY
    assert conf == 0.9


def test_same_gesture_recognized_again_after_hand_released():
    stabilizer = LabelStabilizer(enter_consecutive=3, exit_none_frames=3)
    assert _enter_gesture(stabilizer, VICTORY) == VICTORY

    for _ in range(3):
        state, _ = stabilizer.update(NONE_GESTURE, 0.0)
    assert state == NONE_GESTURE

    assert _enter_gesture(stabilizer, VICTORY) == VICTORY
