#!/usr/bin/env python3
import argparse
import os
import sys
import time

import cv2

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

from tb4_gesture_control.gesture_recognition_node import (
    _landmark_dist,
    _pip_bend_angle_deg,
    build_classifier_from_config,
    is_victory_shape,
    load_gesture_config,
)
from tb4_gesture_control.gesture_types import NONE_GESTURE, VICTORY

WEBCAM_WARMUP_SECONDS = 5.0
WINDOW_NAME = 'Chan doan Victory'
HAND_WAIT_MAX_SECONDS = 8.0
HAND_WAIT_REQUIRED_CONTINUOUS = 0.5
LOW_RATIO_THRESHOLD = 0.3

FINGER_JOINTS = (
    ('trỏ', 5, 6, 8),
    ('giữa', 9, 10, 12),
    ('áp út', 13, 14, 16),
    ('út', 17, 18, 20),
)


def read_frame(cap, classifier, mirror):
    ok, frame = cap.read()
    if not ok:
        return False, None, None, 0.0, None
    if mirror:
        frame = cv2.flip(frame, 1)
    _model_label, _model_conf, raw_label, raw_conf, landmarks, _rule = classifier.classify_raw(frame)
    return True, frame, raw_label, raw_conf, landmarks


def wait_for_hand(cap, classifier, mirror):
    start = time.time()
    present_since = None
    while True:
        elapsed = time.time() - start
        if elapsed > HAND_WAIT_MAX_SECONDS:
            return False
        ok, frame, _raw_label, _raw_conf, landmarks = read_frame(cap, classifier, mirror)
        if not ok:
            continue
        hand_present = bool(landmarks) and len(landmarks) >= 21
        now = time.time()
        if hand_present:
            if present_since is None:
                present_since = now
            elif now - present_since >= HAND_WAIT_REQUIRED_CONTINUOUS:
                return True
        else:
            present_since = None
        cv2.putText(frame, 'BAT DAU SAU 3 GIAY', (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 255), 2)
        cv2.putText(frame, f'Cho toi da {HAND_WAIT_MAX_SECONDS - elapsed:.1f}s', (10, 65),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 0), 2)
        cv2.imshow(WINDOW_NAME, frame)
        cv2.waitKey(1)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--camera-index', type=int, default=0)
    parser.add_argument('--seconds', type=float, default=10.0)
    args = parser.parse_args()

    config_params = load_gesture_config()
    classifier = build_classifier_from_config(config_params)
    mirror = True

    print('Chuan bi chay victory_diagnose.py, dung vao vi tri')
    time.sleep(WEBCAM_WARMUP_SECONDS)

    cap = cv2.VideoCapture(args.camera_index)
    if not cap.isOpened():
        print(f'Khong mo duoc webcam index {args.camera_index}', file=sys.stderr)
        sys.exit(1)

    ready = wait_for_hand(cap, classifier, mirror)
    if not ready:
        print('KHONG THAY TAY, CHAY LAI')
        classifier.close()
        cap.release()
        cv2.destroyAllWindows()
        sys.exit(1)

    rows = []
    start = time.time()
    while time.time() - start < args.seconds:
        ok, frame, raw_label, raw_conf, landmarks = read_frame(cap, classifier, mirror)
        if not ok:
            continue
        hand_present = bool(landmarks) and len(landmarks) >= 21
        victory_shape = is_victory_shape(landmarks)
        angles = None
        tip_dist = None
        if hand_present:
            angles = tuple(
                _pip_bend_angle_deg(landmarks, mcp_idx, pip_idx, tip_idx)
                for _name, mcp_idx, pip_idx, tip_idx in FINGER_JOINTS
            )
            tip_dist = _landmark_dist(landmarks[8], landmarks[12])
        rows.append((raw_label, raw_conf, hand_present, victory_shape, angles, tip_dist))

        cv2.putText(frame, 'Giu Victory (chu V) ON DINH', (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 255), 2)
        cv2.putText(frame, f'mediapipe_raw={raw_label} ({raw_conf:.2f})', (10, 65),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 165, 255), 2)
        cv2.putText(frame, f'hand_present={hand_present}', (10, 95),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 0), 2)
        cv2.putText(frame, f'is_victory_shape={victory_shape}', (10, 125),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
        remaining = args.seconds - (time.time() - start)
        cv2.putText(frame, f'{remaining:.1f}s', (10, 155), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)
        cv2.imshow(WINDOW_NAME, frame)
        cv2.waitKey(1)

    classifier.close()
    cap.release()
    cv2.destroyAllWindows()

    total_frames = len(rows)
    hand_rows = [r for r in rows if r[2]]
    total_with_hand = len(hand_rows)
    hand_ratio = total_with_hand / total_frames if total_frames else 0.0
    print(f'Tong so khung: {total_frames}')
    print(f'So khung co tay (hand_present): {total_with_hand}/{total_frames} ({hand_ratio:.2f})')

    if not hand_rows:
        print('Khong co khung nao co tay, khong the tinh ty le is_victory_shape dung.')
        return

    victory_correct = sum(1 for r in hand_rows if r[3])
    victory_ratio = victory_correct / total_with_hand
    print(f'is_victory_shape dung TRONG SO khung co tay: {victory_correct}/{total_with_hand} ({victory_ratio:.2f})')

    raw_victory = sum(1 for r in hand_rows if r[0] == VICTORY)
    raw_none = sum(1 for r in hand_rows if r[0] == NONE_GESTURE)
    raw_other = total_with_hand - raw_victory - raw_none
    raw_victory_ratio = raw_victory / total_with_hand
    print(f'MediaPipe raw top-1 == Victory TRONG SO khung co tay: {raw_victory}/{total_with_hand} '
          f'({raw_victory_ratio:.2f})')
    print(f'MediaPipe raw top-1 == None TRONG SO khung co tay: {raw_none}/{total_with_hand} '
          f'({raw_none / total_with_hand:.2f})')
    print(f'MediaPipe raw top-1 == nhan khac TRONG SO khung co tay: {raw_other}/{total_with_hand} '
          f'({raw_other / total_with_hand:.2f})')

    if raw_victory_ratio < LOW_RATIO_THRESHOLD and victory_ratio < LOW_RATIO_THRESHOLD:
        print()
        print('CANH BAO: ca mo hinh tho va is_victory_shape deu thap (<30%). '
              'In chi tiet goc gap PIP (do) va khoang cach dau ngon tro-giua tung khung co tay:')
        header = 'idx  goc_tro  goc_giua  goc_ap_ut  goc_ut  khoang_cach_tro_giua  is_victory_shape'
        print(header)
        for i, r in enumerate(hand_rows):
            a_tro, a_giua, a_aput, a_ut = r[4]
            print(f'{i:<4} {a_tro:<8.1f} {a_giua:<9.1f} {a_aput:<10.1f} {a_ut:<7.1f} {r[5]:<20.4f} {r[3]}')


if __name__ == '__main__':
    main()
