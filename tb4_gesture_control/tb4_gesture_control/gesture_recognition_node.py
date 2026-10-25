import collections
import json
import math
import os
import sys
import threading
import time

import cv2
import numpy as np
import rclpy
import yaml
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
except ImportError as exc:
    raise ImportError(
        'mediapipe is required by gesture_recognition_node. '
        'Install it with: pip install mediapipe'
    ) from exc

_RECOGNIZED_MODEL_LABELS = {
    CLOSED_FIST,
    OPEN_PALM,
    POINTING_UP,
    VICTORY,
    THUMB_UP,
    NONE_GESTURE,
}

_DEFAULT_MODEL_RELATIVE_PATH = os.path.join('models', 'gesture_recognizer.task')
_DEFAULT_CONFIG_RELATIVE_PATH = os.path.join('config', 'gesture.yaml')
DEFAULT_MIN_CONFIDENCE = 0.55
_DEFAULT_BEST_FRAMES_DIR = os.path.expanduser('~/gesture_report_data/best_frames')
_IMAGE_EXTENSIONS = ('.jpg', '.jpeg', '.png', '.bmp')

DEFAULT_ROI = (0.0, 0.0, 1.0, 1.0)
DEFAULT_PRIVACY_MODE = 'hand_only'
PRIVACY_MODES = ('off', 'crop', 'blur_outside', 'black_outside', 'hand_only', 'skeleton')
MODE_LABELS = {
    'crop': 'HAND ROI',
    'blur_outside': 'HAND ROI',
    'black_outside': 'HAND ROI',
    'hand_only': 'HAND ONLY',
    'skeleton': 'SKELETON',
}

HAND_CONNECTIONS = (
    (0, 1), (1, 2), (2, 3), (3, 4),
    (0, 5), (5, 6), (6, 7), (7, 8),
    (0, 9), (9, 10), (10, 11), (11, 12),
    (0, 13), (13, 14), (14, 15), (15, 16),
    (0, 17), (17, 18), (18, 19), (19, 20),
    (5, 9), (9, 13), (13, 17),
)

DEFAULT_WAVE_PARAMS = {
    'window_sec': 1.5,
    'min_reversals': 2,
    'min_amplitude': 0.06,
    'lost_timeout_sec': 0.5,
    'hold_after_sec': 0.8,
    'move_window_sec': 0.5,
    'move_threshold': 0.03,
    'min_swing': 0.03,
    'min_avg_speed': 0.05,
}
DEFAULT_STABILIZER_PARAMS = {
    'enter_confidence': 0.55,
    'exit_confidence': 0.40,
    'enter_consecutive': 3,
    'exit_none_frames': 3,
}


def _find_default_path(relative_path):
    here = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.join(here, '..', relative_path),
        os.path.join(here, '..', '..', relative_path),
        os.path.join(os.getcwd(), relative_path),
    ]
    try:
        from ament_index_python.packages import get_package_share_directory
        candidates.insert(
            0,
            os.path.join(get_package_share_directory('tb4_gesture_control'), relative_path),
        )
    except Exception:
        pass
    for candidate in candidates:
        candidate = os.path.abspath(candidate)
        if os.path.isfile(candidate):
            return candidate
    return os.path.abspath(candidates[0])


def _find_default_model_path():
    return _find_default_path(_DEFAULT_MODEL_RELATIVE_PATH)


def _find_default_config_path():
    return _find_default_path(_DEFAULT_CONFIG_RELATIVE_PATH)


def default_config_write_path():
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.abspath(os.path.join(here, '..', _DEFAULT_CONFIG_RELATIVE_PATH))


def load_gesture_config(path=None):
    path = path or _find_default_config_path()
    if path and os.path.isfile(path):
        with open(path) as f:
            data = yaml.safe_load(f) or {}
        params = (data.get('gesture_recognition_node') or {}).get('ros__parameters') or {}
        return dict(params)
    return {}


def validate_roi(roi):
    if len(roi) != 4:
        raise ValueError(f'roi phai co 4 gia tri (x, y, w, h), nhan duoc: {roi}')
    x, y, w, h = (float(v) for v in roi)
    if not (0.0 <= x <= 1.0 and 0.0 <= y <= 1.0 and 0.0 < w <= 1.0 and 0.0 < h <= 1.0):
        raise ValueError(f'roi khong hop le (x,y trong [0,1], w,h trong (0,1]): {roi}')
    if x + w > 1.0 + 1e-6 or y + h > 1.0 + 1e-6:
        raise ValueError(f'roi vuot ra ngoai khung hinh (x+w<=1, y+h<=1): {roi}')
    return (x, y, w, h)


def resolve_privacy_mode(mode):
    if mode not in PRIVACY_MODES:
        raise ValueError(f'privacy_mode khong hop le: {mode} (chon tu {PRIVACY_MODES})')
    return mode


def compute_roi_box(frame_shape, roi):
    h, w = frame_shape[:2]
    x, y, rw, rh = roi
    x0 = int(round(x * w))
    y0 = int(round(y * h))
    x1 = int(round((x + rw) * w))
    y1 = int(round((y + rh) * h))
    x0 = max(0, min(x0, w - 1))
    y0 = max(0, min(y0, h - 1))
    x1 = max(x0 + 1, min(x1, w))
    y1 = max(y0 + 1, min(y1, h))
    return x0, y0, x1, y1


def draw_hand_skeleton(img, landmarks, point_color=(0, 165, 255), line_color=(0, 255, 0),
                        thickness=2, radius=4):
    if not landmarks:
        return img
    h, w = img.shape[:2]
    pts = [(int(x * w), int(y * h)) for x, y in landmarks]
    for a, b in HAND_CONNECTIONS:
        cv2.line(img, pts[a], pts[b], line_color, thickness)
    for p in pts:
        cv2.circle(img, p, radius, point_color, -1)
    return img


class PrivacyProcessor:

    def __init__(self, roi, mode, mask_margin_px=18, feather_ksize=21):
        self.roi = validate_roi(roi)
        self.mode = resolve_privacy_mode(mode)
        self.mask_margin_px = max(1, int(mask_margin_px))
        self.feather_ksize = feather_ksize if feather_ksize % 2 == 1 else feather_ksize + 1

    @property
    def needs_landmarks(self):
        return self.mode in ('hand_only', 'skeleton')

    def process(self, frame):
        if self.mode == 'off':
            return frame
        x0, y0, x1, y1 = compute_roi_box(frame.shape, self.roi)
        if self.mode == 'crop':
            return frame[y0:y1, x0:x1].copy()
        if self.mode == 'black_outside':
            out = np.zeros_like(frame)
            out[y0:y1, x0:x1] = frame[y0:y1, x0:x1]
            return out
        if self.mode == 'blur_outside':
            blurred = cv2.GaussianBlur(frame, (99, 99), 30)
            blurred[y0:y1, x0:x1] = frame[y0:y1, x0:x1]
            return blurred
        raise ValueError(f'process() khong ap dung cho mode {self.mode}')

    def render(self, frame, landmarks, draw_skeleton=True):
        if self.mode == 'skeleton':
            canvas = np.zeros_like(frame)
            draw_hand_skeleton(canvas, landmarks)
            return canvas
        if self.mode == 'hand_only':
            return self._render_hand_only(frame, landmarks, draw_skeleton=draw_skeleton)
        raise ValueError(f'render() khong ap dung cho mode {self.mode}')

    def _render_hand_only(self, frame, landmarks, draw_skeleton=True):
        h, w = frame.shape[:2]
        if not landmarks:
            return np.zeros_like(frame)
        pts = np.array([[int(x * w), int(y * h)] for x, y in landmarks], dtype=np.int32)
        hull = cv2.convexHull(pts)
        mask = np.zeros((h, w), dtype=np.uint8)
        cv2.fillConvexPoly(mask, hull, 255)
        m = self.mask_margin_px
        kernel = np.ones((m * 2 + 1, m * 2 + 1), np.uint8)
        mask = cv2.dilate(mask, kernel)
        mask = cv2.GaussianBlur(mask, (self.feather_ksize, self.feather_ksize), 0)
        alpha = (mask.astype(np.float32) / 255.0)[..., None]
        out = (frame.astype(np.float32) * alpha).astype(np.uint8)
        if draw_skeleton:
            draw_hand_skeleton(out, landmarks, thickness=1, radius=2)
        return out

    def mark_mode_label(self, frame):
        label = MODE_LABELS.get(self.mode)
        if not label:
            return frame
        cv2.putText(
            frame, label, (10, frame.shape[0] - 15),
            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2,
        )
        return frame


def scale_for_display(frame, target_width=640, max_scale=4.0):
    h, w = frame.shape[:2]
    if w == 0:
        return frame
    scale = target_width / float(w)
    scale = max(1.0, min(scale, max_scale))
    if scale == 1.0:
        return frame
    return cv2.resize(frame, (int(round(w * scale)), int(round(h * scale))), interpolation=cv2.INTER_LINEAR)


_CASCADE_SEARCH_DIRS = (
    cv2.data.haarcascades,
    '/usr/share/opencv4/haarcascades/',
    '/usr/share/opencv/haarcascades/',
)


def _find_cascade_path(filename):
    for cascade_dir in _CASCADE_SEARCH_DIRS:
        candidate = os.path.join(cascade_dir, filename)
        if os.path.isfile(candidate):
            return candidate
    raise RuntimeError(
        f'Khong tim thay cascade "{filename}" trong {_CASCADE_SEARCH_DIRS}. '
        'Can goi "apt install opencv-data" hoac tuong duong.'
    )


class FaceGuard:

    def __init__(self, expand_ratio=0.4, hold_sec=1.0, scale_factor=1.1, min_neighbors=5,
                 detect_scale=0.5):
        self._frontal = cv2.CascadeClassifier(_find_cascade_path('haarcascade_frontalface_default.xml'))
        self._profile = cv2.CascadeClassifier(_find_cascade_path('haarcascade_profileface.xml'))
        self.expand_ratio = expand_ratio
        self.hold_sec = hold_sec
        self.scale_factor = scale_factor
        self.min_neighbors = min_neighbors
        self.detect_scale = detect_scale
        self._last_boxes = []
        self._last_seen = None

    def detect(self, frame_bgr, now):
        gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
        if self.detect_scale != 1.0:
            gray = cv2.resize(gray, (0, 0), fx=self.detect_scale, fy=self.detect_scale)
        boxes = []
        boxes.extend(tuple(b) for b in self._frontal.detectMultiScale(
            gray, self.scale_factor, self.min_neighbors))
        boxes.extend(tuple(b) for b in self._profile.detectMultiScale(
            gray, self.scale_factor, self.min_neighbors))
        w_img = gray.shape[1]
        flipped_gray = cv2.flip(gray, 1)
        for (x, y, bw, bh) in self._profile.detectMultiScale(
                flipped_gray, self.scale_factor, self.min_neighbors):
            boxes.append((w_img - x - bw, y, bw, bh))

        if self.detect_scale != 1.0:
            inv = 1.0 / self.detect_scale
            boxes = [(int(x * inv), int(y * inv), int(bw * inv), int(bh * inv))
                     for (x, y, bw, bh) in boxes]

        if boxes:
            self._last_boxes = boxes
            self._last_seen = now
            return boxes, True
        if self._last_seen is not None and now - self._last_seen <= self.hold_sec:
            return self._last_boxes, False
        self._last_boxes = []
        return [], False

    def black_out(self, frame, boxes):
        if not boxes:
            return frame
        h, w = frame.shape[:2]
        for (x, y, bw, bh) in boxes:
            ex = int(bw * self.expand_ratio)
            ey = int(bh * self.expand_ratio)
            x0 = max(0, x - ex)
            y0 = max(0, y - ey)
            x1 = min(w, x + bw + ex)
            y1 = min(h, y + bh + ey)
            frame[y0:y1, x0:x1] = 0
        return frame


def process_frame(frame, classifier, privacy, now, draw_skeleton=True, face_guard=None):
    if privacy.needs_landmarks:
        model_label, model_conf, raw_label, raw_conf, eff_label, eff_conf, landmarks, rule_override = (
            classifier.classify(frame, now))
        display_frame = privacy.render(frame, landmarks, draw_skeleton=draw_skeleton)
        if face_guard is not None:
            boxes, _detected = face_guard.detect(frame, now)
            display_frame = face_guard.black_out(display_frame, boxes)
    else:
        display_frame = privacy.process(frame)
        model_label, model_conf, raw_label, raw_conf, eff_label, eff_conf, landmarks, rule_override = (
            classifier.classify(display_frame, now))
    return (display_frame, model_label, model_conf, raw_label, raw_conf, eff_label, eff_conf,
            landmarks, rule_override)


class WebcamSource:

    def __init__(self, camera_index, width=0, height=0):
        self._cap = cv2.VideoCapture(camera_index)
        if not self._cap.isOpened():
            raise RuntimeError(f'Could not open webcam index {camera_index}')
        if width > 0:
            self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        if height > 0:
            self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        self._lock = threading.Lock()
        self._latest_frame = None
        self._latest_capture_time = None
        self._stop = False
        self._thread = threading.Thread(target=self._grab_loop, daemon=True)
        self._thread.start()

    def _grab_loop(self):
        while not self._stop:
            ok, frame = self._cap.read()
            if not ok:
                continue
            t = time.time()
            with self._lock:
                self._latest_frame = frame
                self._latest_capture_time = t

    def read(self):
        with self._lock:
            frame = self._latest_frame
            capture_time = self._latest_capture_time
        if frame is None:
            return False, None, None
        return True, frame, capture_time

    def release(self):
        self._stop = True
        self._thread.join(timeout=2.0)
        self._cap.release()


class VideoFileSource:

    def __init__(self, path):
        if not os.path.isfile(path):
            raise RuntimeError(f'Video file not found: {path}')
        self._cap = cv2.VideoCapture(path)
        if not self._cap.isOpened():
            raise RuntimeError(f'Could not open video file: {path}')

    def read(self):
        ok, frame = self._cap.read()
        if not ok:
            self._cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ok, frame = self._cap.read()
        return ok, frame, time.time()

    def release(self):
        self._cap.release()


class ImageDirSource:

    def __init__(self, path):
        if not os.path.isdir(path):
            raise RuntimeError(f'Image directory not found: {path}')
        self._dir = path
        self._files = sorted(
            f for f in os.listdir(path) if f.lower().endswith(_IMAGE_EXTENSIONS)
        )
        if not self._files:
            raise RuntimeError(f'No images found in directory: {path}')
        self._idx = 0

    def read(self):
        fname = self._files[self._idx]
        self._idx = (self._idx + 1) % len(self._files)
        frame = cv2.imread(os.path.join(self._dir, fname))
        return frame is not None, frame, time.time()

    def release(self):
        pass


def _build_source(kind, camera_index, source_path, width=0, height=0):
    if kind == 'webcam':
        return WebcamSource(camera_index, width=width, height=height)
    if kind == 'video':
        return VideoFileSource(source_path)
    if kind == 'image_dir':
        return ImageDirSource(source_path)
    raise RuntimeError(f'Unknown source kind "{kind}" (expected webcam/video/image_dir)')


def _landmark_dist(a, b):
    return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5


def _finger_extended(landmarks, tip_idx, pip_idx, mcp_idx):
    wrist = landmarks[0]
    d_tip = _landmark_dist(wrist, landmarks[tip_idx])
    d_pip = _landmark_dist(wrist, landmarks[pip_idx])
    d_mcp = _landmark_dist(wrist, landmarks[mcp_idx])
    return d_tip > d_pip > d_mcp


def _pip_bend_angle_deg(landmarks, mcp_idx, pip_idx, tip_idx):
    pip = landmarks[pip_idx]
    mcp = landmarks[mcp_idx]
    tip = landmarks[tip_idx]
    v1 = (mcp[0] - pip[0], mcp[1] - pip[1])
    v2 = (tip[0] - pip[0], tip[1] - pip[1])
    n1 = (v1[0] ** 2 + v1[1] ** 2) ** 0.5
    n2 = (v2[0] ** 2 + v2[1] ** 2) ** 0.5
    if n1 == 0.0 or n2 == 0.0:
        return 180.0
    cos_angle = max(-1.0, min(1.0, (v1[0] * v2[0] + v1[1] * v2[1]) / (n1 * n2)))
    return math.degrees(math.acos(cos_angle))


def _finger_extended_by_angle(landmarks, mcp_idx, pip_idx, tip_idx, straight_threshold_deg=140.0):
    return _pip_bend_angle_deg(landmarks, mcp_idx, pip_idx, tip_idx) >= straight_threshold_deg


def is_pointing_up_shape(landmarks):
    if not landmarks or len(landmarks) < 21:
        return False
    index_ext = _finger_extended(landmarks, 8, 6, 5)
    middle_curled = not _finger_extended(landmarks, 12, 10, 9)
    ring_curled = not _finger_extended(landmarks, 16, 14, 13)
    pinky_curled = not _finger_extended(landmarks, 20, 18, 17)
    return index_ext and middle_curled and ring_curled and pinky_curled


_VICTORY_MIN_TIP_SEPARATION = 0.03


def is_victory_shape(landmarks):
    if not landmarks or len(landmarks) < 21:
        return False
    index_ext = _finger_extended_by_angle(landmarks, 5, 6, 8)
    middle_ext = _finger_extended_by_angle(landmarks, 9, 10, 12)
    ring_curled = not _finger_extended_by_angle(landmarks, 13, 14, 16)
    pinky_curled = not _finger_extended_by_angle(landmarks, 17, 18, 20)
    tips_separated = _landmark_dist(landmarks[8], landmarks[12]) >= _VICTORY_MIN_TIP_SEPARATION
    return index_ext and middle_ext and ring_curled and pinky_curled and tips_separated


def count_zigzag_reversals(values, min_swing):
    if len(values) < 2:
        return 0
    reversals = 0
    extreme = values[0]
    direction = 0
    for v in values[1:]:
        if direction == 0:
            delta = v - extreme
            if abs(delta) >= min_swing:
                direction = 1 if delta > 0 else -1
                extreme = v
        elif direction == 1:
            if v > extreme:
                extreme = v
            elif extreme - v >= min_swing:
                reversals += 1
                direction = -1
                extreme = v
        else:
            if v < extreme:
                extreme = v
            elif v - extreme >= min_swing:
                reversals += 1
                direction = 1
                extreme = v
    return reversals


class WaveDetector:

    def __init__(self, window_sec=1.5, min_reversals=2, min_amplitude=0.06,
                 lost_timeout_sec=0.5, hold_after_sec=0.8,
                 move_window_sec=0.5, move_threshold=0.03,
                 min_swing=0.03, min_avg_speed=0.05):
        self.window_sec = window_sec
        self.min_reversals = min_reversals
        self.min_amplitude = min_amplitude
        self.lost_timeout_sec = lost_timeout_sec
        self.hold_after_sec = hold_after_sec
        self.move_window_sec = move_window_sec
        self.move_threshold = move_threshold
        self.min_swing = min_swing
        self.min_avg_speed = min_avg_speed
        self._history = collections.deque()
        self._last_seen = None
        self._last_wave_time = None

    def reset(self):
        self._history.clear()
        self._last_seen = None
        self._last_wave_time = None

    def update(self, hand_x, now):
        if hand_x is None:
            if self._last_seen is not None and now - self._last_seen > self.lost_timeout_sec:
                self.reset()
            return
        self._last_seen = now
        self._history.append((now, hand_x))
        while self._history and now - self._history[0][0] > self.window_sec:
            self._history.popleft()

    def _windowed(self, seconds, now):
        return [x for t, x in self._history if now - t <= seconds]

    def recent_amplitude(self, now):
        xs = self._windowed(self.move_window_sec, now)
        if len(xs) < 2:
            return 0.0
        return max(xs) - min(xs)

    def is_moving(self, now):
        return self.recent_amplitude(now) >= self.move_threshold

    def is_waving(self, now):
        xs = [x for _, x in self._history]
        ts = [t for t, _ in self._history]
        waving = False
        if len(xs) >= 4:
            amplitude = max(xs) - min(xs)
            span = ts[-1] - ts[0]
            if amplitude >= self.min_amplitude and span > 0:
                reversals = count_zigzag_reversals(xs, self.min_swing)
                total_path = sum(abs(b - a) for a, b in zip(xs, xs[1:]))
                avg_speed = total_path / span
                waving = reversals >= self.min_reversals and avg_speed >= self.min_avg_speed
        if waving:
            self._last_wave_time = now
            return True
        return self._last_wave_time is not None and now - self._last_wave_time <= self.hold_after_sec


class LabelStabilizer:

    def __init__(self, enter_confidence=0.55, exit_confidence=0.40, enter_consecutive=3,
                 exit_none_frames=3):
        self.enter_confidence = enter_confidence
        self.exit_confidence = exit_confidence
        self.enter_consecutive = max(1, int(enter_consecutive))
        self.exit_none_frames = max(1, int(exit_none_frames))
        self._state = NONE_GESTURE
        self._state_confidence = 0.0
        self._candidate = None
        self._candidate_count = 0
        self._none_streak = 0

    def update(self, label, confidence):
        if label == NONE_GESTURE:
            self._none_streak += 1
        else:
            self._none_streak = 0

        if label == self._state:
            self._candidate = None
            self._candidate_count = 0
            self._state_confidence = confidence
            if self._state != NONE_GESTURE and confidence < self.exit_confidence:
                self._state = NONE_GESTURE
                self._state_confidence = 0.0
            return self._state, self._state_confidence

        if self._state != NONE_GESTURE and self._none_streak >= self.exit_none_frames:
            self._state = NONE_GESTURE
            self._state_confidence = 0.0
            self._candidate = None
            self._candidate_count = 0
            return self._state, self._state_confidence

        if label != NONE_GESTURE and confidence >= self.enter_confidence:
            if self._candidate == label:
                self._candidate_count += 1
            else:
                self._candidate = label
                self._candidate_count = 1
            if self._candidate_count >= self.enter_consecutive:
                self._state = label
                self._state_confidence = confidence
                self._candidate = None
                self._candidate_count = 0
        else:
            self._candidate = None
            self._candidate_count = 0

        return self._state, self._state_confidence


class GestureClassifier:

    def __init__(self, model_path, num_hands=1, wave_params=None,
                 pointing_up_fallback=True, pointing_up_fallback_confidence=0.6,
                 victory_fallback=True, victory_fallback_confidence=0.6):
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
        self.pointing_up_fallback = pointing_up_fallback
        self.pointing_up_fallback_confidence = pointing_up_fallback_confidence
        self.victory_fallback = victory_fallback
        self.victory_fallback_confidence = victory_fallback_confidence
        wave_params = dict(DEFAULT_WAVE_PARAMS, **(wave_params or {}))
        self._wave_detector = WaveDetector(**wave_params)

    def close(self):
        self._recognizer.close()

    def reset_wave(self):
        self._wave_detector.reset()

    def classify_raw(self, frame_bgr):
        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        mp_image = self._mp_image_cls(image_format=self._mp_format, data=rgb)
        result = self._recognizer.recognize(mp_image)

        landmarks = None
        if result.hand_landmarks and result.hand_landmarks[0]:
            landmarks = [(lm.x, lm.y) for lm in result.hand_landmarks[0]]

        model_label = NONE_GESTURE
        model_conf = 0.0
        if result.gestures and result.gestures[0]:
            top = result.gestures[0][0]
            model_label = top.category_name if top.category_name else NONE_GESTURE
            model_conf = float(top.score)

        label = model_label
        confidence = model_conf
        if label not in _RECOGNIZED_MODEL_LABELS:
            label = NONE_GESTURE
            confidence = 0.0

        rule_override = False
        if (self.pointing_up_fallback and label != POINTING_UP
                and is_pointing_up_shape(landmarks)):
            label = POINTING_UP
            confidence = max(confidence, self.pointing_up_fallback_confidence)
            rule_override = True
        elif (self.victory_fallback and label != VICTORY
                and is_victory_shape(landmarks)):
            label = VICTORY
            confidence = max(confidence, self.victory_fallback_confidence)
            rule_override = True

        return model_label, model_conf, label, confidence, landmarks, rule_override

    def apply_wave_override(self, label, confidence, landmarks, now):
        hand_x = None
        if landmarks:
            hand_x = sum(p[0] for p in landmarks) / len(landmarks)
        self._wave_detector.update(hand_x, now)

        if label in (OPEN_PALM, NONE_GESTURE) and self._wave_detector.is_waving(now):
            return WAVE, confidence if confidence > 0.0 else max(confidence, 0.5)

        if label == OPEN_PALM and self._wave_detector.is_moving(now):
            return NONE_GESTURE, 0.0

        return label, confidence

    def classify(self, frame_bgr, now):
        model_label, model_conf, raw_label, raw_conf, landmarks, rule_override = self.classify_raw(frame_bgr)
        eff_label, eff_conf = self.apply_wave_override(raw_label, raw_conf, landmarks, now)
        return model_label, model_conf, raw_label, raw_conf, eff_label, eff_conf, landmarks, rule_override


def build_classifier_from_config(config_params, model_path=None, num_hands=1):
    model_path = model_path or _find_default_model_path()
    wave_params = {
        key: type(default)(config_params.get(f'wave_{key}', default))
        for key, default in DEFAULT_WAVE_PARAMS.items()
    }
    return GestureClassifier(
        model_path, num_hands=num_hands, wave_params=wave_params,
        pointing_up_fallback=bool(config_params.get('pointing_up_fallback', True)),
        pointing_up_fallback_confidence=float(config_params.get('pointing_up_fallback_confidence', 0.6)),
        victory_fallback=bool(config_params.get('victory_fallback', True)),
        victory_fallback_confidence=float(config_params.get('victory_fallback_confidence', 0.6)),
    )


def build_face_guard_from_config(config_params):
    if not bool(config_params.get('face_guard_enabled', True)):
        return None
    return FaceGuard(
        expand_ratio=float(config_params.get('face_guard_expand_ratio', 0.4)),
        hold_sec=float(config_params.get('face_guard_hold_sec', 1.0)),
        detect_scale=float(config_params.get('face_guard_detect_scale', 0.5)),
    )


class GestureRecognitionNode(Node):

    def __init__(self):
        super().__init__('gesture_recognition_node')

        config_params = load_gesture_config()

        self.declare_parameter('model_path', _find_default_model_path())
        self.declare_parameter('camera_index', 0)
        self.declare_parameter('show_preview', True)
        self.declare_parameter('num_hands', 1)
        self.declare_parameter('source', 'webcam')
        self.declare_parameter('source_path', '')
        self.declare_parameter('fps_cap', 20.0)
        self.declare_parameter('best_frames_dir', _DEFAULT_BEST_FRAMES_DIR)
        self.declare_parameter('roi', list(config_params.get('roi', DEFAULT_ROI)))
        self.declare_parameter('privacy_mode', config_params.get('privacy_mode', DEFAULT_PRIVACY_MODE))
        self.declare_parameter('mask_margin_px', int(config_params.get('mask_margin_px', 18)))
        self.declare_parameter('enter_confidence',
                                float(config_params.get('enter_confidence',
                                                         DEFAULT_STABILIZER_PARAMS['enter_confidence'])))
        self.declare_parameter('exit_confidence',
                                float(config_params.get('exit_confidence',
                                                         DEFAULT_STABILIZER_PARAMS['exit_confidence'])))
        self.declare_parameter('enter_consecutive',
                                int(config_params.get('enter_consecutive',
                                                       DEFAULT_STABILIZER_PARAMS['enter_consecutive'])))
        self.declare_parameter('exit_none_frames',
                                int(config_params.get('exit_none_frames',
                                                       DEFAULT_STABILIZER_PARAMS['exit_none_frames'])))
        for key, default in DEFAULT_WAVE_PARAMS.items():
            self.declare_parameter(f'wave_{key}', type(default)(config_params.get(f'wave_{key}', default)))
        self.declare_parameter('pointing_up_fallback', bool(config_params.get('pointing_up_fallback', True)))
        self.declare_parameter('pointing_up_fallback_confidence',
                                float(config_params.get('pointing_up_fallback_confidence', 0.6)))
        self.declare_parameter('victory_fallback', bool(config_params.get('victory_fallback', True)))
        self.declare_parameter('victory_fallback_confidence',
                                float(config_params.get('victory_fallback_confidence', 0.6)))
        self.declare_parameter('face_guard_enabled', bool(config_params.get('face_guard_enabled', True)))
        self.declare_parameter('face_guard_expand_ratio',
                                float(config_params.get('face_guard_expand_ratio', 0.4)))
        self.declare_parameter('face_guard_hold_sec',
                                float(config_params.get('face_guard_hold_sec', 1.0)))
        self.declare_parameter('face_guard_detect_scale',
                                float(config_params.get('face_guard_detect_scale', 0.5)))
        self.declare_parameter('profile', False)
        self.declare_parameter('face_guard_every_n', 1)
        self.declare_parameter('camera_width', 0)
        self.declare_parameter('camera_height', 0)

        model_path = self.get_parameter('model_path').value
        camera_index = self.get_parameter('camera_index').value
        self.show_preview = bool(self.get_parameter('show_preview').value)
        num_hands = int(self.get_parameter('num_hands').value)
        source_kind = self.get_parameter('source').value
        source_path = self.get_parameter('source_path').value
        self.fps_cap = float(self.get_parameter('fps_cap').value)
        self.min_frame_interval = 1.0 / self.fps_cap if self.fps_cap > 0 else 0.0
        self.best_frames_dir = self.get_parameter('best_frames_dir').value
        roi = list(self.get_parameter('roi').value)
        privacy_mode = self.get_parameter('privacy_mode').value
        mask_margin_px = int(self.get_parameter('mask_margin_px').value)
        self._privacy = PrivacyProcessor(roi, privacy_mode, mask_margin_px=mask_margin_px)
        self._face_guard = None
        if self._privacy.needs_landmarks and bool(self.get_parameter('face_guard_enabled').value):
            self._face_guard = FaceGuard(
                expand_ratio=float(self.get_parameter('face_guard_expand_ratio').value),
                hold_sec=float(self.get_parameter('face_guard_hold_sec').value),
                detect_scale=float(self.get_parameter('face_guard_detect_scale').value),
            )

        wave_params = {
            key: self.get_parameter(f'wave_{key}').value for key in DEFAULT_WAVE_PARAMS
        }
        self._stabilizer = LabelStabilizer(
            enter_confidence=float(self.get_parameter('enter_confidence').value),
            exit_confidence=float(self.get_parameter('exit_confidence').value),
            enter_consecutive=int(self.get_parameter('enter_consecutive').value),
            exit_none_frames=int(self.get_parameter('exit_none_frames').value),
        )

        if not os.path.isfile(model_path):
            self.get_logger().error(
                f'Gesture model not found at "{model_path}". '
                'Run tb4_gesture_control/models/download_model.sh first '
                '(downloads into the source tree), then rebuild '
                '("colcon build --packages-select tb4_gesture_control") '
                'so the install/share copy picks it up, or set the '
                'model_path parameter to an existing .task file.'
            )
            raise FileNotFoundError(model_path)

        self._classifier = GestureClassifier(
            model_path, num_hands=num_hands, wave_params=wave_params,
            pointing_up_fallback=bool(self.get_parameter('pointing_up_fallback').value),
            pointing_up_fallback_confidence=float(
                self.get_parameter('pointing_up_fallback_confidence').value),
            victory_fallback=bool(self.get_parameter('victory_fallback').value),
            victory_fallback_confidence=float(self.get_parameter('victory_fallback_confidence').value),
        )

        self.publisher_ = self.create_publisher(String, '/detected_gesture', 10)

        self._cap = _build_source(
            source_kind, camera_index, source_path,
            width=int(self.get_parameter('camera_width').value),
            height=int(self.get_parameter('camera_height').value),
        )
        self.is_test_source = source_kind != 'webcam'
        if self.is_test_source:
            self.get_logger().warning(
                f'CANH BAO: source="{source_kind}" ({source_path}) - day la nguon '
                'TEST, KHONG phai webcam truc tiep. Khong dung ket qua tren nguon '
                'nay de bao cao la thuc nghiem webcam.'
            )

        self._last_published_label = None

        self._best_confidence = {}
        os.makedirs(self.best_frames_dir, exist_ok=True)

        self._frame_times = collections.deque(maxlen=60)
        self._last_fps_log_count = 0
        self._current_fps = 0.0

        self.profile = bool(self.get_parameter('profile').value)
        self._profile_samples = {
            k: [] for k in ('read', 'age', 'classify', 'mask', 'faceguard', 'draw', 'publish')
        }
        self.face_guard_every_n = max(1, int(self.get_parameter('face_guard_every_n').value))
        self._face_guard_frame_count = 0
        self._face_guard_last_boxes = []

        self.get_logger().info(
            f'gesture_recognition_node ready (model={model_path}, '
            f'source={source_kind}, fps_cap={self.fps_cap}, '
            f'privacy_mode={self._privacy.mode}, roi={self._privacy.roi}). '
            'Press q or ESC in the preview window to stop.'
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
            self._classifier.close()
        except Exception:
            pass
        super().destroy_node()

    def _maybe_save_best_frame(self, frame, label, confidence):
        if label == NONE_GESTURE:
            return
        if confidence > self._best_confidence.get(label, -1.0):
            self._best_confidence[label] = confidence
            out_path = os.path.join(self.best_frames_dir, f'{label}.jpg')
            cv2.imwrite(out_path, frame)

    def _log_profile_summary(self):
        parts = []
        for step, samples in self._profile_samples.items():
            if not samples:
                continue
            s = sorted(samples)
            mean_ms = (sum(s) / len(s)) * 1000.0
            p95_ms = s[int(0.95 * (len(s) - 1))] * 1000.0
            parts.append(f'{step}: mean={mean_ms:.2f}ms p95={p95_ms:.2f}ms')
            samples.clear()
        self.get_logger().info('PROFILE ' + ' | '.join(parts))

    def _log_actual_fps(self, now):
        self._frame_times.append(now)
        if len(self._frame_times) < 2:
            return
        span = self._frame_times[-1] - self._frame_times[0]
        if span <= 0:
            return
        self._current_fps = (len(self._frame_times) - 1) / span
        self._last_fps_log_count += 1
        if self._last_fps_log_count % 40 == 0:
            self.get_logger().info(f'FPS thuc te (trung binh {len(self._frame_times)} khung): {self._current_fps:.1f}')

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
        cv2.putText(
            frame, f'FPS: {self._current_fps:.1f}', (10, 90),
            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (200, 200, 200), 2,
        )
        if self.is_test_source:
            cv2.putText(
                frame, 'TEST SOURCE', (10, 120),
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2,
            )
        return frame

    def spin_once_cycle(self):
        loop_start = time.time()
        t_read = time.time()
        ok, frame, capture_time = self._cap.read()
        if not ok:
            self.get_logger().warning('Failed to read frame from source')
            return True
        if self.profile:
            self._profile_samples['read'].append(time.time() - t_read)
            self._profile_samples['age'].append(t_read - capture_time)

        frame = cv2.flip(frame, 1) if not self.is_test_source else frame
        now = time.time()
        self._log_actual_fps(now)

        if self.profile and self._privacy.needs_landmarks:
            t_classify = time.time()
            (model_label, model_conf, raw_label, raw_conf, eff_label, eff_conf,
             landmarks, rule_override) = self._classifier.classify(frame, now)
            self._profile_samples['classify'].append(time.time() - t_classify)
            t_mask = time.time()
            frame = self._privacy.render(frame, landmarks, draw_skeleton=True)
            self._profile_samples['mask'].append(time.time() - t_mask)
            t_faceguard = time.time()
            if self._face_guard is not None:
                self._face_guard_frame_count += 1
                if self._face_guard_frame_count % self.face_guard_every_n == 0:
                    self._face_guard_last_boxes, _detected = self._face_guard.detect(frame, now)
                frame = self._face_guard.black_out(frame, self._face_guard_last_boxes)
            self._profile_samples['faceguard'].append(time.time() - t_faceguard)
        else:
            (frame, _model_label, _model_conf, raw_label, raw_conf, eff_label, eff_conf,
             _landmarks, _rule_override) = process_frame(
                frame, self._classifier, self._privacy, now, face_guard=self._face_guard)

        stable_label, stable_conf = self._stabilizer.update(eff_label, eff_conf)

        report_frame = frame.copy()
        display_label = eff_label if eff_label != NONE_GESTURE else raw_label
        t_draw = time.time()
        self._draw_overlay(report_frame, display_label, raw_conf, stable_label)
        self._privacy.mark_mode_label(report_frame)
        if self.profile:
            self._profile_samples['draw'].append(time.time() - t_draw)

        self._maybe_save_best_frame(report_frame, eff_label, eff_conf)

        t_publish = time.time()
        msg = String()
        msg.data = json.dumps({
            KEY_GESTURE: stable_label,
            KEY_CONFIDENCE: round(stable_conf, 3),
            KEY_STAMP: now,
        })
        self.publisher_.publish(msg)
        if self.profile:
            self._profile_samples['publish'].append(time.time() - t_publish)
            if len(self._profile_samples['read']) >= 30:
                self._log_profile_summary()

        if stable_label != self._last_published_label:
            self.get_logger().info(f'Gesture -> {stable_label} ({stable_conf:.2f})')
            self._last_published_label = stable_label

        if self.show_preview:
            display_frame = report_frame
            if self._privacy.mode == 'crop':
                display_frame = scale_for_display(display_frame)
            cv2.imshow('TB4 Gesture Recognition', display_frame)
            key = cv2.waitKey(1) & 0xFF
            if key in (ord('q'), 27):
                return False

        if self.min_frame_interval > 0:
            elapsed = time.time() - loop_start
            remaining = self.min_frame_interval - elapsed
            if remaining > 0:
                time.sleep(remaining)
        return True


def main(args=None):
    rclpy.init(args=args)
    try:
        node = GestureRecognitionNode()
    except (RuntimeError, FileNotFoundError) as exc:
        print(f'gesture_recognition_node: loi khoi tao: {exc}', file=sys.stderr)
        if rclpy.ok():
            rclpy.shutdown()
        sys.exit(1)

    try:
        running = True
        while rclpy.ok() and running:
            running = node.spin_once_cycle()
            rclpy.spin_once(node, timeout_sec=0.0)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
