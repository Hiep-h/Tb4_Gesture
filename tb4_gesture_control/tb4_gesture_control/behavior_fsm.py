import math

from tb4_gesture_control.gesture_types import (
    CLOSED_FIST,
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

BEHAVIOR_WAVE = 'wave'
BEHAVIOR_FORWARD_BACKWARD = 'forward_backward'
BEHAVIOR_CIRCLE = 'circle'

SEG_DISTANCE = 'distance'
SEG_ANGLE = 'angle'

MAX_LINEAR_SPEED = 0.25
MAX_ANGULAR_SPEED = 0.8

LINEAR_SPEED = 0.2
WAVE_ANGULAR_SPEED = 0.5
CIRCLE_LINEAR_SPEED = 0.2
CIRCLE_ANGULAR_SPEED = 0.4
CIRCLE_DIRECTION_LEFT = 1.0
CIRCLE_DIRECTION_RIGHT = -1.0

FORWARD_BACKWARD_DISTANCE = 0.5
FORWARD_BACKWARD_REPEATS = 4

WAVE_LEFT_DEG = 30.0
WAVE_RIGHT_DEG = 60.0
WAVE_REPEATS = 2

CIRCLE_TARGET_ANGLE = 2.0 * math.pi

HOLD_S = 0.6
STOP_HOLD_S = 0.2
COOLDOWN_S = 1.0
SELECTION_TIMEOUT_S = 30.0
SIGNAL_TIMEOUT_S = 1.0
RUN_TIMEOUT_S = 40.0
WAVE_REFRACTORY_S = 8.0

_STOP_GESTURES = (OPEN_PALM, CLOSED_FIST)


def _wave_sequence(angular_speed):
    left = math.radians(WAVE_LEFT_DEG)
    right = math.radians(WAVE_RIGHT_DEG)
    cycle = [
        (0.0, angular_speed, SEG_ANGLE, left),
        (0.0, -angular_speed, SEG_ANGLE, right),
        (0.0, angular_speed, SEG_ANGLE, left),
    ]
    return cycle * WAVE_REPEATS


def _forward_backward_sequence(linear_speed):
    forward = (linear_speed, 0.0, SEG_DISTANCE, FORWARD_BACKWARD_DISTANCE)
    backward = (-linear_speed, 0.0, SEG_DISTANCE, FORWARD_BACKWARD_DISTANCE)
    return [forward, backward] * FORWARD_BACKWARD_REPEATS


def _circle_sequence(linear_speed, angular_speed, direction):
    return [(linear_speed, angular_speed * direction, SEG_ANGLE, CIRCLE_TARGET_ANGLE)]


class GestureEdgeTracker:

    def __init__(self, hold_s=HOLD_S, stop_hold_s=STOP_HOLD_S, cooldown_s=COOLDOWN_S, on_log=None):
        self.hold_s = hold_s
        self.stop_hold_s = stop_hold_s
        self.cooldown_s = cooldown_s
        self._on_log = on_log or (lambda event, **kwargs: None)
        self._current_gesture = NONE_GESTURE
        self._hold_start = None
        self._trigger_resolved = True
        self._not_released_logged = False
        self._armed_gesture = None
        self._last_trigger_time = None

    def _required_hold(self, gesture):
        return self.stop_hold_s if gesture in _STOP_GESTURES else self.hold_s

    def _has_cooldown(self, gesture):
        return gesture not in _STOP_GESTURES

    def process(self, gesture, now):
        if gesture != self._current_gesture:
            prev_gesture = self._current_gesture
            prev_held = (now - self._hold_start) if self._hold_start is not None else 0.0
            if prev_gesture != NONE_GESTURE and not self._trigger_resolved:
                self._on_log('ignored', gesture=prev_gesture, reason='not_enough_hold',
                              held_s=round(prev_held, 3))
            self._current_gesture = gesture
            self._hold_start = now
            self._trigger_resolved = False
            self._not_released_logged = False
            if gesture != self._armed_gesture:
                self._armed_gesture = None

        if gesture == NONE_GESTURE:
            self._armed_gesture = None
            return None

        held = now - self._hold_start
        if held < self._required_hold(gesture):
            return None

        if gesture == self._armed_gesture:
            if not self._not_released_logged:
                self._on_log('ignored', gesture=gesture, reason='not_released')
                self._not_released_logged = True
            return None

        if self._trigger_resolved:
            return None
        self._trigger_resolved = True

        if self._has_cooldown(gesture) and self._last_trigger_time is not None:
            remaining = self.cooldown_s - (now - self._last_trigger_time)
            if remaining > 0.0:
                self._on_log('ignored', gesture=gesture, reason='cooldown', remaining_s=round(remaining, 3))
                return None

        self._armed_gesture = gesture
        self._last_trigger_time = now
        return gesture


class BehaviorFSM:

    def __init__(self, hold_s=HOLD_S, stop_hold_s=STOP_HOLD_S, cooldown_s=COOLDOWN_S,
                 selection_timeout_s=SELECTION_TIMEOUT_S, run_timeout_s=RUN_TIMEOUT_S,
                 wave_needs_confirm=True, linear_speed=LINEAR_SPEED,
                 wave_angular_speed=WAVE_ANGULAR_SPEED, circle_linear_speed=CIRCLE_LINEAR_SPEED,
                 circle_angular_speed=CIRCLE_ANGULAR_SPEED, circle_direction=CIRCLE_DIRECTION_LEFT,
                 wave_refractory_s=WAVE_REFRACTORY_S,
                 edge_tracker=None, on_event=None):
        self._on_event = on_event or (lambda event, **kwargs: None)
        self.edge_tracker = edge_tracker or GestureEdgeTracker(
            hold_s=hold_s, stop_hold_s=stop_hold_s, cooldown_s=cooldown_s, on_log=self._on_event)
        self.selection_timeout_s = selection_timeout_s
        self.run_timeout_s = run_timeout_s
        self.wave_needs_confirm = wave_needs_confirm
        self.linear_speed = linear_speed
        self.wave_angular_speed = wave_angular_speed
        self.circle_linear_speed = circle_linear_speed
        self.circle_angular_speed = circle_angular_speed
        self.circle_direction = circle_direction
        self.wave_refractory_s = wave_refractory_s

        self.state = STATE_IDLE
        self.pending_behavior = None
        self.active_sequence = []
        self.active_index = 0
        self.segment_progress = 0.0
        self.running_kind = None
        self._selected_at = None
        self._run_started_sim_at = None
        self._stop_gesture_accepted_at = None

    def _sequence_for(self, behavior):
        if behavior == BEHAVIOR_WAVE:
            return _wave_sequence(self.wave_angular_speed)
        if behavior == BEHAVIOR_FORWARD_BACKWARD:
            return _forward_backward_sequence(self.linear_speed)
        if behavior == BEHAVIOR_CIRCLE:
            return _circle_sequence(self.circle_linear_speed, self.circle_angular_speed, self.circle_direction)
        raise ValueError(behavior)

    def handle_gesture(self, gesture, now):
        triggered = self.edge_tracker.process(gesture, now)
        if triggered is None:
            return None
        self._handle_action(triggered, now)
        return triggered

    def _handle_action(self, gesture, now):
        if gesture == OPEN_PALM:
            self.emergency_stop(now)
            self._stop_gesture_accepted_at = now
        elif gesture == CLOSED_FIST:
            self.cancel()
            self._stop_gesture_accepted_at = now
        elif gesture == WAVE:
            if self.state == STATE_RUNNING:
                self._on_event('ignored', gesture=gesture, reason='busy')
            elif (self._stop_gesture_accepted_at is not None
                    and (now - self._stop_gesture_accepted_at) < self.wave_refractory_s):
                self._on_event('ignored', gesture=gesture, reason='wave_refractory')
            elif self.wave_needs_confirm:
                self.select(BEHAVIOR_WAVE, now)
            else:
                self.start_behavior(BEHAVIOR_WAVE)
        elif gesture == POINTING_UP:
            if self.state == STATE_RUNNING:
                self._on_event('ignored', gesture=gesture, reason='busy')
            else:
                self.select(BEHAVIOR_FORWARD_BACKWARD, now)
        elif gesture == VICTORY:
            if self.state == STATE_RUNNING:
                self._on_event('ignored', gesture=gesture, reason='busy')
            else:
                self.select(BEHAVIOR_CIRCLE, now)
        elif gesture == THUMB_UP:
            if self.state == STATE_SELECTED:
                self.start_behavior(self.pending_behavior)
            else:
                self._on_event('ignored', gesture=gesture, reason='nothing_selected')

    def select(self, behavior, now):
        self.pending_behavior = behavior
        self.state = STATE_SELECTED
        self._selected_at = now
        self._on_event('selected', behavior=behavior)

    def start_behavior(self, behavior):
        self.active_sequence = self._sequence_for(behavior)
        self.active_index = 0
        self.segment_progress = 0.0
        self.running_kind = behavior
        self.pending_behavior = behavior
        self.state = STATE_RUNNING
        self._selected_at = None
        self._run_started_sim_at = None
        self._on_event('started', behavior=behavior)

    def cancel(self):
        if self.state == STATE_IDLE:
            self._on_event('cancel_noop')
            return
        self._on_event('cancelled', state=self.state, behavior=self.running_kind or self.pending_behavior)
        self.reset_to_idle()

    def emergency_stop(self, now):
        if self.state == STATE_RUNNING:
            behavior = self.running_kind
            self.pending_behavior = behavior
            self.state = STATE_SELECTED
            self.active_sequence = []
            self.active_index = 0
            self.segment_progress = 0.0
            self.running_kind = None
            self._selected_at = now
            self._run_started_sim_at = None
            self._on_event('emergency_stop', behavior=behavior)
        else:
            self._on_event('emergency_stop', behavior=None)

    def abort(self, reason):
        behavior = self.running_kind
        self.reset_to_idle()
        self._on_event('aborted', behavior=behavior, reason=reason)

    def reset_to_idle(self):
        self.state = STATE_IDLE
        self.pending_behavior = None
        self.active_sequence = []
        self.active_index = 0
        self.segment_progress = 0.0
        self.running_kind = None
        self._selected_at = None
        self._run_started_sim_at = None

    def signal_lost(self):
        changed = self.state != STATE_IDLE
        self.reset_to_idle()
        self._on_event('signal_lost', reason='MAT TIN HIEU')
        return changed

    def check_selection_timeout(self, now):
        if self.state != STATE_SELECTED or self._selected_at is None:
            return False
        if now - self._selected_at < self.selection_timeout_s:
            return False
        behavior = self.pending_behavior
        self.reset_to_idle()
        self._on_event('selection_timeout', behavior=behavior)
        return True

    def current_segment(self):
        if self.state != STATE_RUNNING or self.active_index >= len(self.active_sequence):
            return None
        return self.active_sequence[self.active_index]

    def advance(self, delta_distance, delta_angle, sim_now=None):
        if self.state != STATE_RUNNING:
            return None

        if self._run_started_sim_at is None and sim_now is not None:
            self._run_started_sim_at = sim_now
        if (sim_now is not None and self._run_started_sim_at is not None
                and sim_now - self._run_started_sim_at > self.run_timeout_s):
            behavior = self.running_kind
            self.reset_to_idle()
            self._on_event('timeout', behavior=behavior, reason='TIMEOUT')
            return None

        if self.active_index >= len(self.active_sequence):
            behavior = self.running_kind
            self.reset_to_idle()
            self._on_event('completed', behavior=behavior)
            return None

        linear_x, angular_z, seg_type, target = self.active_sequence[self.active_index]
        progress_delta = abs(delta_distance) if seg_type == SEG_DISTANCE else abs(delta_angle)
        self.segment_progress += progress_delta

        if self.segment_progress >= target:
            self.active_index += 1
            self.segment_progress = 0.0
            if self.active_index >= len(self.active_sequence):
                behavior = self.running_kind
                self.reset_to_idle()
                self._on_event('completed', behavior=behavior)
                return None
            linear_x, angular_z, seg_type, target = self.active_sequence[self.active_index]

        return (linear_x, angular_z)
