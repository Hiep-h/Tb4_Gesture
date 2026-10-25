#!/usr/bin/env python3
import argparse
import os
import sys
import time

import cv2
import numpy as np
import yaml

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

from tb4_gesture_control.gesture_recognition_node import (
    GestureClassifier,
    _find_default_model_path,
    default_config_write_path,
    draw_hand_skeleton,
    load_gesture_config,
)

CAPTURE_SECONDS = 6.0
MIN_HAND_RATIO = 0.5
OUTLIER_PERCENTILE = 5.0
MARGIN_RATIO = 0.30
MIN_DIM = 0.4
TARGET_ASPECT = 4.0 / 3.0
WEBCAM_WARMUP_SECONDS = 5.0
WINDOW_NAME = 'Auto ROI (chi hien xuong ban tay, chi dung cho crop/blur_outside/black_outside)'
WINDOW_SIZE = (640, 480)


def draw_preview(points, message):
    canvas = np.zeros((WINDOW_SIZE[1], WINDOW_SIZE[0], 3), dtype=np.uint8)
    draw_hand_skeleton(canvas, points)
    cv2.putText(canvas, message, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
    cv2.putText(canvas, 'HAND ROI', (10, WINDOW_SIZE[1] - 15), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
    cv2.imshow(WINDOW_NAME, canvas)
    cv2.waitKey(1)


def clamp_range(lo, hi, min_v, max_v):
    size = min(hi - lo, max_v - min_v)
    lo = max(min_v, min(lo, max_v - size))
    return lo, lo + size


def compute_roi(all_points):
    xs = np.array([p[0] for frame_points in all_points for p in frame_points])
    ys = np.array([p[1] for frame_points in all_points for p in frame_points])
    x_lo, x_hi = (float(v) for v in np.percentile(xs, [OUTLIER_PERCENTILE, 100 - OUTLIER_PERCENTILE]))
    y_lo, y_hi = (float(v) for v in np.percentile(ys, [OUTLIER_PERCENTILE, 100 - OUTLIER_PERCENTILE]))

    margin_x = (x_hi - x_lo) * MARGIN_RATIO
    margin_y = (y_hi - y_lo) * MARGIN_RATIO
    x0, x1 = x_lo - margin_x, x_hi + margin_x
    y0, y1 = y_lo - margin_y, y_hi + margin_y

    w, h = x1 - x0, y1 - y0
    if w < MIN_DIM:
        cx = (x0 + x1) / 2.0
        x0, x1 = cx - MIN_DIM / 2.0, cx + MIN_DIM / 2.0
        w = MIN_DIM
    if h < MIN_DIM:
        cy = (y0 + y1) / 2.0
        y0, y1 = cy - MIN_DIM / 2.0, cy + MIN_DIM / 2.0
        h = MIN_DIM

    ratio = max(w, h) / min(w, h)
    if ratio > TARGET_ASPECT:
        if w > h:
            new_h = w / TARGET_ASPECT
            cy = (y0 + y1) / 2.0
            y0, y1 = cy - new_h / 2.0, cy + new_h / 2.0
        else:
            new_w = h / TARGET_ASPECT
            cx = (x0 + x1) / 2.0
            x0, x1 = cx - new_w / 2.0, cx + new_w / 2.0

    x0, x1 = clamp_range(x0, x1, 0.0, 1.0)
    y0, y1 = clamp_range(y0, y1, 0.0, 1.0)

    return [round(x0, 4), round(y0, 4), round(x1 - x0, 4), round(y1 - y0, 4)]


def write_roi_config(path, roi, privacy_mode=None):
    params = load_gesture_config(path)
    params['roi'] = roi
    if privacy_mode is not None:
        params['privacy_mode'] = privacy_mode
    content = {'gesture_recognition_node': {'ros__parameters': params}}
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w') as f:
        yaml.safe_dump(content, f, default_flow_style=None, sort_keys=False)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--camera-index', type=int, default=0)
    parser.add_argument('--config-path', default=None)
    parser.add_argument('--privacy-mode', default=None,
                         choices=['crop', 'blur_outside', 'black_outside', 'hand_only', 'skeleton', 'off'])
    args = parser.parse_args()

    config_path = args.config_path or default_config_write_path()

    print('Chuan bi chay auto_roi.py, dung vao vi tri')
    time.sleep(WEBCAM_WARMUP_SECONDS)

    cap = cv2.VideoCapture(args.camera_index)
    if not cap.isOpened():
        print(f'Khong mo duoc webcam index {args.camera_index}', file=sys.stderr)
        sys.exit(1)

    classifier = GestureClassifier(_find_default_model_path())

    all_points = []
    frame_count = 0
    hand_count = 0
    start = time.time()
    while time.time() - start < CAPTURE_SECONDS:
        ok, frame = cap.read()
        if not ok:
            continue
        frame = cv2.flip(frame, 1)
        frame_count += 1
        _model_label, _model_conf, _label, _conf, points, _rule = classifier.classify_raw(frame)
        remaining = CAPTURE_SECONDS - (time.time() - start)
        draw_preview(points, f'Dua tay qua lai vung muon dung: {remaining:.1f}s')
        if points is not None:
            hand_count += 1
            all_points.append(points)

    classifier.close()
    cap.release()
    cv2.destroyAllWindows()

    hand_ratio = hand_count / frame_count if frame_count else 0.0
    print(f'Ty le khung thay tay: {hand_ratio:.2f} ({hand_count}/{frame_count})')

    if hand_ratio < MIN_HAND_RATIO:
        print(
            f'LOI: ty le khung thay tay ({hand_ratio:.2f}) duoi nguong {MIN_HAND_RATIO:.2f}. '
            'Chay lai auto_roi.py va dua tay vao khung ro hon, du sang.', file=sys.stderr,
        )
        sys.exit(1)

    roi = compute_roi(all_points)
    write_roi_config(config_path, roi, args.privacy_mode)
    print(f'Da ghi roi={roi} vao {config_path}'
          + (f' (privacy_mode={args.privacy_mode})' if args.privacy_mode else ' (giu nguyen privacy_mode hien tai)'))


if __name__ == '__main__':
    main()
