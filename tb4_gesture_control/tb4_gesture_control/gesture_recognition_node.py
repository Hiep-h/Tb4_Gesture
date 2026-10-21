"""ROS 2 node: webcam hand-gesture recognition with MediaPipe + OpenCV.

Reads frames from a webcam, runs MediaPipe's Gesture Recognizer, overlays
the recognized gesture name and confidence on the preview window, and
publishes a debounced result on /detected_gesture as a JSON-encoded
std_msgs/msg/String: {"gesture": <name>, "confidence": <0..1>, "stamp":
<unix time>}.

MediaPipe's bundled model natively classifies: None, Closed_Fist,
Open_Palm, Pointing_Up, Victory, Thumb_Up, Thumb_Down, ITSign. "Wave" is
not one of those categories, so it is derived here on top of the model
output: while the model reports an open hand (Open_Palm), the node tracks
the wrist's horizontal position over a short sliding window and flags a
"Wave" when it sees enough left-right oscillation. Together with the five
native categories used by this assignment (Pointing_Up, Victory,
Thumb_Up, Open_Palm, Closed_Fist) this yields six distinguishable
gestures, above the minimum of five required.
"""

import collections
import json
import os
import time

import cv2
import rclpy
from rclpy.node import Node
from std_msgs.msg import String

from tb4_gesture_control.gesture_types import (
    CLOSED_FIST,
    KEY_CONFIDENCE,
    KEY_GESTURE,
    KEY_STAMP,
    NONE_GESTURE,
    OPEN_PALM,
    POINTING_UP,
    THUMB_UP,
    VICTORY,
    WAVE,
)

try:
    import mediapipe as mp
    from mediapipe.tasks import python as mp_python
    from mediapipe.tasks.python import vision as mp_vision
except ImportError as exc:  # pragma: no cover - import-time environment check
    raise ImportError(
        'mediapipe is required by gesture_recognition_node. '
        'Install it with: pip install mediapipe'
    ) from exc

# Gesture categories that MediaPipe's default model is allowed to report;
# anything else (e.g. "ITSign") is treated as noise for this assignment.
_RECOGNIZED_MODEL_LABELS = {
    CLOSED_FIST,
    OPEN_PALM,
    POINTING_UP,
    VICTORY,
    THUMB_UP,
    NONE_GESTURE,
}

_DEFAULT_MODEL_RELATIVE_PATH = os.path.join('models', 'gesture_recognizer.task')


def _find_default_model_path():
    """Best-effort lookup of gesture_recognizer.task next to this package."""
    here = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.join(here, '..', _DEFAULT_MODEL_RELATIVE_PATH),
        os.path.join(here, '..', '..', _DEFAULT_MODEL_RELATIVE_PATH),
        os.path.join(os.getcwd(), _DEFAULT_MODEL_RELATIVE_PATH),
    ]
    try:
        from ament_index_python.packages import get_package_share_directory
        candidates.insert(
            0,
            os.path.join(
                get_package_share_directory('tb4_gesture_control'),
                'models', 'gesture_recognizer.task',
            ),
        )
    except Exception:
        pass
    for candidate in candidates:
        candidate = os.path.abspath(candidate)
        if os.path.isfile(candidate):
            return candidate
    return os.path.abspath(candidates[-1])


class WaveDetector:
    """Flags a side-to-side wave from a short history of wrist x positions."""

    def __init__(self, window_sec=1.2, min_reversals=3, min_amplitude=0.08):
        self.window_sec = window_sec
        self.min_reversals = min_reversals
        self.min_amplitude = min_amplitude
        self._history = collections.deque()  # (timestamp, x)

    def reset(self):
        self._history.clear()

    def update(self, wrist_x, now):
        self._history.append((now, wrist_x))
        while self._history and now - self._history[0][0] > self.window_sec:
            self._history.popleft()

    def is_waving(self):
        if len(self._history) < 4:
            return False
        xs = [x for _, x in self._history]
        amplitude = max(xs) - min(xs)
        if amplitude < self.min_amplitude:
            return False
        reversals = 0
        direction = 0
        for prev, cur in zip(xs, xs[1:]):
            delta = cur - prev
            if abs(delta) < 1e-4:
                continue
            new_direction = 1 if delta > 0 else -1
            if direction != 0 and new_direction != direction:
                reversals += 1
            direction = new_direction
        return reversals >= self.min_reversals


class GestureRecognitionNode(Node):

    def __init__(self):
        super().__init__('gesture_recognition_node')

        self.declare_parameter('model_path', _find_default_model_path())
        self.declare_parameter('camera_index', 0)
        self.declare_parameter('min_confidence', 0.6)
        self.declare_parameter('debounce_window', 8)
        self.declare_parameter('debounce_min_votes', 6)
        self.declare_parameter('show_preview', True)
        self.declare_parameter('num_hands', 1)

        model_path = self.get_parameter('model_path').value
        camera_index = self.get_parameter('camera_index').value
        self.min_confidence = float(self.get_parameter('min_confidence').value)
        self.debounce_window = int(self.get_parameter('debounce_window').value)
        self.debounce_min_votes = int(self.get_parameter('debounce_min_votes').value)
        self.show_preview = bool(self.get_parameter('show_preview').value)
        num_hands = int(self.get_parameter('num_hands').value)

        if not os.path.isfile(model_path):
            self.get_logger().error(
                f'Gesture model not found at "{model_path}". '
                'Run tb4_gesture_control/models/download_model.sh first, '
                'or set the model_path parameter.'
            )
            raise FileNotFoundError(model_path)

        base_options = mp_python.BaseOptions(model_asset_path=model_path)
        options = mp_vision.GestureRecognizerOptions(
            base_options=base_options,
            running_mode=mp_vision.RunningMode.IMAGE,
            num_hands=num_hands,
            min_hand_detection_confidence=0.5,
            min_hand_presence_confidence=0.5,
            min_tracking_confidence=0.5,
        )
        self._recognizer = mp_vision.GestureRecognizer.create_from_options(options)
        self._mp_image_cls = mp.Image
        self._mp_format = mp.ImageFormat.SRGB

        self.publisher_ = self.create_publisher(String, '/detected_gesture', 10)

        self._cap = cv2.VideoCapture(camera_index)
        if not self._cap.isOpened():
            self.get_logger().error(f'Could not open webcam index {camera_index}')
            raise RuntimeError(f'Could not open webcam index {camera_index}')

        self._history = collections.deque(maxlen=self.debounce_window)
        self._wave_detector = WaveDetector()
        self._last_published_label = None

        self.get_logger().info(
            f'gesture_recognition_node ready (model={model_path}, '
            f'camera={camera_index}). Press q or ESC in the preview '
            'window to stop.'
        )

    def destroy_node(self):
        try:
            self._cap.release()
        except Exception:
            pass
        try:
            cv2.destroyAllWindows()
        except Exception:
            pass
        try:
            self._recognizer.close()
        except Exception:
            pass
        super().destroy_node()

    def _classify_frame(self, frame_bgr):
        """Runs MediaPipe on one frame; returns (label, confidence, wrist_xy)."""
        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        mp_image = self._mp_image_cls(image_format=self._mp_format, data=rgb)
        result = self._recognizer.recognize(mp_image)

        if not result.gestures or not result.gestures[0]:
            return NONE_GESTURE, 0.0, None

        top = result.gestures[0][0]
        label = top.category_name if top.category_name else NONE_GESTURE
        confidence = float(top.score)

        wrist_xy = None
        if result.hand_landmarks and result.hand_landmarks[0]:
            wrist = result.hand_landmarks[0][0]
            wrist_xy = (wrist.x, wrist.y)

        if label not in _RECOGNIZED_MODEL_LABELS:
            label = NONE_GESTURE
            confidence = 0.0

        return label, confidence, wrist_xy

    def _apply_wave_override(self, label, confidence, wrist_xy, now):
        if wrist_xy is None or label != OPEN_PALM:
            self._wave_detector.reset()
            return label, confidence

        self._wave_detector.update(wrist_xy[0], now)
        if self._wave_detector.is_waving():
            return WAVE, confidence
        return label, confidence

    def _debounced_label(self, label, confidence):
        """Majority vote over a short history to reject one-frame noise."""
        accepted = label if confidence >= self.min_confidence else NONE_GESTURE
        self._history.append(accepted)

        if len(self._history) < self._history.maxlen:
            return NONE_GESTURE, 0.0

        counts = collections.Counter(self._history)
        best_label, best_count = counts.most_common(1)[0]
        if best_label == NONE_GESTURE or best_count < self.debounce_min_votes:
            return NONE_GESTURE, 0.0
        return best_label, confidence

    def _draw_overlay(self, frame, raw_label, raw_conf, stable_label):
        text_color = (0, 255, 0) if stable_label != NONE_GESTURE else (0, 165, 255)
        cv2.putText(
            frame, f'Gesture: {raw_label} ({raw_conf:.2f})', (10, 30),
            cv2.FONT_HERSHEY_SIMPLEX, 0.8, text_color, 2,
        )
        cv2.putText(
            frame, f'Stable: {stable_label}', (10, 60),
            cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 0), 2,
        )
        return frame

    def spin_once_cycle(self):
        """Grabs one frame, classifies it, publishes, and updates the preview."""
        ok, frame = self._cap.read()
        if not ok:
            self.get_logger().warning('Failed to read frame from webcam')
            return True

        frame = cv2.flip(frame, 1)  # mirror for a natural "selfie" view
        now = time.time()

        raw_label, raw_conf, wrist_xy = self._classify_frame(frame)
        eff_label, eff_conf = self._apply_wave_override(
            raw_label, raw_conf, wrist_xy, now,
        )
        stable_label, stable_conf = self._debounced_label(eff_label, eff_conf)

        msg = String()
        msg.data = json.dumps({
            KEY_GESTURE: stable_label,
            KEY_CONFIDENCE: round(stable_conf, 3),
            KEY_STAMP: now,
        })
        self.publisher_.publish(msg)

        if stable_label != self._last_published_label:
            self.get_logger().info(f'Gesture -> {stable_label} ({stable_conf:.2f})')
            self._last_published_label = stable_label

        if self.show_preview:
            display_label = eff_label if eff_label != NONE_GESTURE else raw_label
            self._draw_overlay(frame, display_label, raw_conf, stable_label)
            cv2.imshow('TB4 Gesture Recognition', frame)
            key = cv2.waitKey(1) & 0xFF
            if key in (ord('q'), 27):
                return False
        return True


def main(args=None):
    rclpy.init(args=args)
    node = GestureRecognitionNode()
    try:
        running = True
        while rclpy.ok() and running:
            running = node.spin_once_cycle()
            rclpy.spin_once(node, timeout_sec=0.0)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
