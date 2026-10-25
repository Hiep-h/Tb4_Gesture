import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

from tb4_gesture_control.behavior_fsm import (
    BEHAVIOR_CIRCLE,
    BEHAVIOR_FORWARD_BACKWARD,
    BEHAVIOR_WAVE,
    CIRCLE_TARGET_ANGLE,
    FORWARD_BACKWARD_DISTANCE,
    FORWARD_BACKWARD_REPEATS,
    MAX_ANGULAR_SPEED,
    MAX_LINEAR_SPEED,
    STATE_IDLE,
    STATE_RUNNING,
    STATE_SELECTED,
    BehaviorFSM,
    CIRCLE_ANGULAR_SPEED,
    CIRCLE_LINEAR_SPEED,
    LINEAR_SPEED,
    WAVE_ANGULAR_SPEED,
)
from tb4_gesture_control.gesture_types import (
    CLOSED_FIST,
    NONE_GESTURE,
    OPEN_PALM,
    POINTING_UP,
    THUMB_UP,
    VICTORY,
    WAVE,
)


def _events_collector():
    events = []
    return events, (lambda event, **kwargs: events.append((event, kwargs)))


def _hold_until_trigger(fsm, gesture, start_now, step=0.05, max_steps=400):
    now = start_now
    for _ in range(max_steps):
        result = fsm.handle_gesture(gesture, now)
        if result is not None:
            return result, now
        now += step
    return None, now


def test_configured_speeds_within_limits():
    assert LINEAR_SPEED <= MAX_LINEAR_SPEED
    assert CIRCLE_LINEAR_SPEED <= MAX_LINEAR_SPEED
    assert WAVE_ANGULAR_SPEED <= MAX_ANGULAR_SPEED
    assert CIRCLE_ANGULAR_SPEED <= MAX_ANGULAR_SPEED


def test_pointing_up_selected_without_thumb_up_does_not_run():
    fsm = BehaviorFSM()
    result, _now = _hold_until_trigger(fsm, POINTING_UP, 0.0)
    assert result == POINTING_UP
    assert fsm.state == STATE_SELECTED
    assert fsm.pending_behavior == BEHAVIOR_FORWARD_BACKWARD


def test_thumb_up_ignored_when_nothing_selected():
    events, on_event = _events_collector()
    fsm = BehaviorFSM(on_event=on_event)
    result, _now = _hold_until_trigger(fsm, THUMB_UP, 0.0)
    assert result == THUMB_UP
    assert fsm.state == STATE_IDLE
    reasons = [kw.get('reason') for e, kw in events if e == 'ignored']
    assert 'nothing_selected' in reasons


def test_switch_selection_between_pointing_up_and_victory():
    fsm = BehaviorFSM(cooldown_s=0.0)
    result, now = _hold_until_trigger(fsm, POINTING_UP, 0.0)
    assert result == POINTING_UP
    assert fsm.pending_behavior == BEHAVIOR_FORWARD_BACKWARD
    fsm.handle_gesture(NONE_GESTURE, now + 0.05)
    result2, _now2 = _hold_until_trigger(fsm, VICTORY, now + 0.1)
    assert result2 == VICTORY
    assert fsm.state == STATE_SELECTED
    assert fsm.pending_behavior == BEHAVIOR_CIRCLE


def test_gesture_ignored_when_hold_too_short():
    events, on_event = _events_collector()
    fsm = BehaviorFSM(hold_s=0.6, on_event=on_event)
    fsm.handle_gesture(VICTORY, 0.0)
    fsm.handle_gesture(VICTORY, 0.1)
    result = fsm.handle_gesture(NONE_GESTURE, 0.2)
    assert result is None
    assert fsm.state == STATE_IDLE
    reasons = [kw.get('reason') for e, kw in events if e == 'ignored']
    assert 'not_enough_hold' in reasons


def test_edge_trigger_requires_release_before_retrigger():
    events, on_event = _events_collector()
    fsm = BehaviorFSM(hold_s=0.2, cooldown_s=0.0, on_event=on_event)
    result, now = _hold_until_trigger(fsm, VICTORY, 0.0)
    assert result == VICTORY
    result2 = fsm.handle_gesture(VICTORY, now + 0.05)
    assert result2 is None
    reasons = [kw.get('reason') for e, kw in events if e == 'ignored']
    assert 'not_released' in reasons

    fsm.handle_gesture(NONE_GESTURE, now + 0.3)
    result3, _now3 = _hold_until_trigger(fsm, VICTORY, now + 0.4)
    assert result3 == VICTORY


def test_cooldown_blocks_immediate_retrigger():
    events, on_event = _events_collector()
    fsm = BehaviorFSM(hold_s=0.3, cooldown_s=1.0, on_event=on_event)
    result, now = _hold_until_trigger(fsm, VICTORY, 0.0)
    assert result == VICTORY
    fsm.handle_gesture(NONE_GESTURE, now + 0.05)
    result2, _now2 = _hold_until_trigger(fsm, VICTORY, now + 0.1)
    assert result2 is None
    reasons = [kw.get('reason') for e, kw in events if e == 'ignored']
    assert 'cooldown' in reasons


def test_open_palm_keeps_selection():
    fsm = BehaviorFSM(hold_s=0.2, stop_hold_s=0.1, cooldown_s=0.0)
    result, now = _hold_until_trigger(fsm, POINTING_UP, 0.0)
    assert result == POINTING_UP
    fsm.handle_gesture(NONE_GESTURE, now + 0.05)
    result2, now2 = _hold_until_trigger(fsm, THUMB_UP, now + 0.1)
    assert result2 == THUMB_UP
    assert fsm.state == STATE_RUNNING
    fsm.handle_gesture(NONE_GESTURE, now2 + 0.05)
    result3, _now3 = _hold_until_trigger(fsm, OPEN_PALM, now2 + 0.1)
    assert result3 == OPEN_PALM
    assert fsm.state == STATE_SELECTED
    assert fsm.pending_behavior == BEHAVIOR_FORWARD_BACKWARD


def test_closed_fist_clears_selection():
    fsm = BehaviorFSM(hold_s=0.2, stop_hold_s=0.1, cooldown_s=0.0)
    result, now = _hold_until_trigger(fsm, POINTING_UP, 0.0)
    assert result == POINTING_UP
    fsm.handle_gesture(NONE_GESTURE, now + 0.05)
    result2, _now2 = _hold_until_trigger(fsm, CLOSED_FIST, now + 0.1)
    assert result2 == CLOSED_FIST
    assert fsm.state == STATE_IDLE
    assert fsm.pending_behavior is None


def test_selection_expires_after_timeout():
    events, on_event = _events_collector()
    fsm = BehaviorFSM(hold_s=0.2, selection_timeout_s=15.0, on_event=on_event)
    result, now = _hold_until_trigger(fsm, POINTING_UP, 0.0)
    assert result == POINTING_UP
    assert fsm.check_selection_timeout(now + 14.0) is False
    assert fsm.state == STATE_SELECTED
    assert fsm.check_selection_timeout(now + 15.1) is True
    assert fsm.state == STATE_IDLE
    assert fsm.pending_behavior is None
    reasons = [e for e, _kw in events if e == 'selection_timeout']
    assert reasons


def test_signal_lost_resets_to_idle():
    events, on_event = _events_collector()
    fsm = BehaviorFSM(hold_s=0.2, cooldown_s=0.0, on_event=on_event)
    result, now = _hold_until_trigger(fsm, POINTING_UP, 0.0)
    assert result == POINTING_UP
    fsm.handle_gesture(NONE_GESTURE, now + 0.05)
    result2, _now2 = _hold_until_trigger(fsm, THUMB_UP, now + 0.1)
    assert result2 == THUMB_UP
    assert fsm.state == STATE_RUNNING
    changed = fsm.signal_lost()
    assert changed is True
    assert fsm.state == STATE_IDLE
    assert fsm.active_sequence == []
    reasons = [kw.get('reason') for e, kw in events if e == 'signal_lost']
    assert 'MAT TIN HIEU' in reasons


def test_wave_needs_confirm_true_requires_thumb_up():
    fsm = BehaviorFSM(hold_s=0.2, wave_needs_confirm=True)
    result, _now = _hold_until_trigger(fsm, WAVE, 0.0)
    assert result == WAVE
    assert fsm.state == STATE_SELECTED
    assert fsm.pending_behavior == BEHAVIOR_WAVE


def test_wave_needs_confirm_false_runs_immediately():
    fsm = BehaviorFSM(hold_s=0.2, wave_needs_confirm=False)
    result, _now = _hold_until_trigger(fsm, WAVE, 0.0)
    assert result == WAVE
    assert fsm.state == STATE_RUNNING
    assert fsm.running_kind == BEHAVIOR_WAVE


def test_advance_forward_backward_completes_after_total_distance():
    fsm = BehaviorFSM()
    fsm.start_behavior(BEHAVIOR_FORWARD_BACKWARD)
    assert len(fsm.active_sequence) == FORWARD_BACKWARD_REPEATS * 2
    command = None
    for _ in range(len(fsm.active_sequence) * 11):
        command = fsm.advance(FORWARD_BACKWARD_DISTANCE / 10.0, 0.0)
        if fsm.state == STATE_IDLE:
            break
    assert fsm.state == STATE_IDLE
    assert command is None


def test_advance_does_not_progress_segment_without_motion():
    fsm = BehaviorFSM()
    fsm.start_behavior(BEHAVIOR_FORWARD_BACKWARD)
    command = None
    for _ in range(50):
        command = fsm.advance(0.0, 0.0)
    assert fsm.state == STATE_RUNNING
    assert command == (LINEAR_SPEED, 0.0)


def test_advance_circle_completes_after_target_angle():
    fsm = BehaviorFSM()
    fsm.start_behavior(BEHAVIOR_CIRCLE)
    steps = 0
    command = fsm.advance(0.0, 0.0)
    while fsm.state == STATE_RUNNING and steps < 1000:
        command = fsm.advance(0.0, CIRCLE_TARGET_ANGLE / 50.0)
        steps += 1
    assert fsm.state == STATE_IDLE
    assert command is None
    assert steps <= 51


def test_advance_wave_alternates_direction_per_segment():
    fsm = BehaviorFSM()
    fsm.start_behavior(BEHAVIOR_WAVE)
    first_command = fsm.advance(0.0, 0.0)
    assert first_command[1] > 0.0
    command = first_command
    for _ in range(50):
        command = fsm.advance(0.0, 0.1)
        if fsm.active_index == 1:
            break
    assert command[1] < 0.0


def test_advance_run_timeout_aborts_to_idle():
    events, on_event = _events_collector()
    fsm = BehaviorFSM(run_timeout_s=5.0, on_event=on_event)
    fsm.start_behavior(BEHAVIOR_CIRCLE)
    command = fsm.advance(0.0, 0.0, sim_now=100.0)
    assert command is not None
    command = fsm.advance(0.0, 0.0, sim_now=106.0)
    assert command is None
    assert fsm.state == STATE_IDLE
    reasons = [kw.get('reason') for e, kw in events if e == 'timeout']
    assert 'TIMEOUT' in reasons


def test_coalesced_stamps_still_trigger_after_enough_hold_span():
    fsm = BehaviorFSM(cooldown_s=0.0)
    start_now = 1000.0
    stamps = [start_now + i * 0.05 for i in range(20)]
    results = [fsm.handle_gesture(POINTING_UP, stamp) for stamp in stamps]
    assert stamps[-1] - stamps[0] >= 0.6
    assert POINTING_UP in results
    assert fsm.state == STATE_SELECTED
    assert fsm.pending_behavior == BEHAVIOR_FORWARD_BACKWARD


def test_wave_ignored_right_after_open_palm_refractory():
    events, on_event = _events_collector()
    fsm = BehaviorFSM(hold_s=0.2, stop_hold_s=0.1, cooldown_s=0.0, wave_refractory_s=8.0, on_event=on_event)
    fsm.start_behavior(BEHAVIOR_FORWARD_BACKWARD)
    result, stop_now = _hold_until_trigger(fsm, OPEN_PALM, 0.0)
    assert result == OPEN_PALM
    assert fsm.state == STATE_SELECTED
    assert fsm.pending_behavior == BEHAVIOR_FORWARD_BACKWARD

    result, _now = _hold_until_trigger(fsm, WAVE, stop_now + 1.0)
    assert result == WAVE
    assert fsm.state == STATE_SELECTED
    assert fsm.pending_behavior == BEHAVIOR_FORWARD_BACKWARD
    reasons = [kw.get('reason') for e, kw in events if e == 'ignored' and kw.get('gesture') == WAVE]
    assert 'wave_refractory' in reasons


def test_wave_ignored_right_after_closed_fist_refractory():
    events, on_event = _events_collector()
    fsm = BehaviorFSM(hold_s=0.2, stop_hold_s=0.1, cooldown_s=0.0, wave_refractory_s=8.0, on_event=on_event)
    fsm.select(BEHAVIOR_CIRCLE, 0.0)
    result, stop_now = _hold_until_trigger(fsm, CLOSED_FIST, 0.0)
    assert result == CLOSED_FIST
    assert fsm.state == STATE_IDLE

    result, _now = _hold_until_trigger(fsm, WAVE, stop_now + 2.0)
    assert result == WAVE
    assert fsm.state == STATE_IDLE
    reasons = [kw.get('reason') for e, kw in events if e == 'ignored' and kw.get('gesture') == WAVE]
    assert 'wave_refractory' in reasons


def test_wave_selectable_after_refractory_elapses():
    fsm = BehaviorFSM(hold_s=0.2, stop_hold_s=0.1, cooldown_s=0.0, wave_refractory_s=8.0)
    result, stop_now = _hold_until_trigger(fsm, OPEN_PALM, 0.0)
    assert result == OPEN_PALM

    result, _now = _hold_until_trigger(fsm, WAVE, stop_now + 8.5)
    assert result == WAVE
    assert fsm.state == STATE_SELECTED
    assert fsm.pending_behavior == BEHAVIOR_WAVE


def test_pointing_up_and_victory_not_affected_by_wave_refractory():
    fsm1 = BehaviorFSM(hold_s=0.2, stop_hold_s=0.1, cooldown_s=0.0, wave_refractory_s=8.0)
    result, stop_now = _hold_until_trigger(fsm1, OPEN_PALM, 0.0)
    assert result == OPEN_PALM
    result, _now = _hold_until_trigger(fsm1, POINTING_UP, stop_now + 0.5)
    assert result == POINTING_UP
    assert fsm1.state == STATE_SELECTED
    assert fsm1.pending_behavior == BEHAVIOR_FORWARD_BACKWARD

    fsm2 = BehaviorFSM(hold_s=0.2, stop_hold_s=0.1, cooldown_s=0.0, wave_refractory_s=8.0)
    result, stop_now2 = _hold_until_trigger(fsm2, OPEN_PALM, 0.0)
    assert result == OPEN_PALM
    result, _now2 = _hold_until_trigger(fsm2, VICTORY, stop_now2 + 0.5)
    assert result == VICTORY
    assert fsm2.state == STATE_SELECTED
    assert fsm2.pending_behavior == BEHAVIOR_CIRCLE
