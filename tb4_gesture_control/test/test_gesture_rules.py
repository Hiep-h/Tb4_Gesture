import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

from tb4_gesture_control.gesture_recognition_node import is_pointing_up_shape, is_victory_shape

WRIST = (0.5, 0.9)


def _finger(straight, x, mcp_y=0.65, pip_y=0.5, curl_back=0.07):
    mcp = (x, mcp_y)
    pip = (x, pip_y)
    if straight:
        tip = (x, pip_y - 0.15)
        dip = (x, (pip_y + tip[1]) / 2)
    else:
        tip = (x, pip_y + curl_back)
        dip = (x + 0.01, pip_y + curl_back / 2)
    return mcp, pip, dip, tip


def _make_hand(index_straight, middle_straight, ring_straight, pinky_straight, tip_separation=0.08):
    lm = [None] * 21
    lm[0] = WRIST
    for i in range(1, 5):
        lm[i] = (0.4, 0.85 - i * 0.02)
    index_mcp, index_pip, index_dip, index_tip = _finger(index_straight, 0.45)
    middle_mcp, middle_pip, middle_dip, middle_tip = _finger(middle_straight, 0.45 + tip_separation)
    ring_mcp, ring_pip, ring_dip, ring_tip = _finger(ring_straight, 0.55 + tip_separation)
    pinky_mcp, pinky_pip, pinky_dip, pinky_tip = _finger(pinky_straight, 0.60 + tip_separation)
    lm[5], lm[6], lm[7], lm[8] = index_mcp, index_pip, index_dip, index_tip
    lm[9], lm[10], lm[11], lm[12] = middle_mcp, middle_pip, middle_dip, middle_tip
    lm[13], lm[14], lm[15], lm[16] = ring_mcp, ring_pip, ring_dip, ring_tip
    lm[17], lm[18], lm[19], lm[20] = pinky_mcp, pinky_pip, pinky_dip, pinky_tip
    return lm


def test_victory_pose_detected():
    hand = _make_hand(True, True, False, False, tip_separation=0.08)
    assert is_victory_shape(hand) is True


def test_victory_false_for_pointing_up_pose():
    hand = _make_hand(True, False, False, False)
    assert is_victory_shape(hand) is False
    assert is_pointing_up_shape(hand) is True


def test_victory_false_for_open_palm_pose():
    hand = _make_hand(True, True, True, True)
    assert is_victory_shape(hand) is False


def test_victory_false_for_closed_fist_pose():
    hand = _make_hand(False, False, False, False)
    assert is_victory_shape(hand) is False
    assert is_pointing_up_shape(hand) is False


def test_victory_false_when_index_and_middle_tips_touching():
    hand = _make_hand(True, True, False, False, tip_separation=0.01)
    assert is_victory_shape(hand) is False


def test_victory_shape_none_landmarks():
    assert is_victory_shape(None) is False
    assert is_victory_shape([]) is False
