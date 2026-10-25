#!/usr/bin/env python3
import argparse
import csv
import os
import sys
import time

import cv2

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

from tb4_gesture_control.gesture_recognition_node import (
    DEFAULT_PRIVACY_MODE,
    DEFAULT_ROI,
    PrivacyProcessor,
    build_classifier_from_config,
    build_face_guard_from_config,
    load_gesture_config,
    process_frame,
    scale_for_display,
)

LABELS_STATIC = ['Closed_Fist', 'Open_Palm', 'Pointing_Up', 'Victory', 'Thumb_Up']
LABEL_NONE = 'None'
LABEL_WAVE = 'Wave'
IMAGES_PER_LABEL = 15
NONE_IMAGES = 15
WAVE_VIDEO_COUNT = 3
WAVE_VIDEO_SECONDS = 3.0
PREP_SECONDS = 4.0
BETWEEN_SECONDS = 3.0
IMAGE_CAPTURE_INTERVAL = 0.4
WEBCAM_WARMUP_SECONDS = 5.0
HAND_WAIT_MAX_SECONDS = 8.0
HAND_WAIT_REQUIRED_CONTINUOUS = 0.5
MAX_CAPTURE_ATTEMPTS_PER_IMAGE = 40
WINDOW_NAME = 'Thu thap du lieu cu chi'
DEFAULT_OUTPUT_DIR = os.path.expanduser('~/gesture_report_data/dataset')
CAPTURE_LOG_NAME = 'capture_log.csv'


def open_camera(camera_index):
    cap = cv2.VideoCapture(camera_index)
    if not cap.isOpened():
        print(f'Khong mo duoc webcam index {camera_index}', file=sys.stderr)
        sys.exit(1)
    return cap


def read_and_process(cap, classifier, privacy, mirror, face_guard):
    ok, frame = cap.read()
    if not ok:
        return False, None, None, 0.0, None, 0.0, False, False
    if mirror:
        frame = cv2.flip(frame, 1)
    now = time.time()
    (display_frame, model_label, model_conf, raw_label, raw_conf, _eff_label, _eff_conf,
     landmarks, rule_override) = process_frame(
        frame, classifier, privacy, now, draw_skeleton=False, face_guard=face_guard)
    hand_present = bool(landmarks) and len(landmarks) >= 21
    return True, display_frame, model_label, model_conf, raw_label, raw_conf, rule_override, hand_present


def wait_for_hand(cap, classifier, privacy, mirror, face_guard, label):
    start = time.time()
    present_since = None
    while True:
        elapsed = time.time() - start
        if elapsed > HAND_WAIT_MAX_SECONDS:
            return False
        result = read_and_process(cap, classifier, privacy, mirror, face_guard)
        if not result[0]:
            continue
        frame, hand_present = result[1], result[7]
        now = time.time()
        if hand_present:
            if present_since is None:
                present_since = now
            elif now - present_since >= HAND_WAIT_REQUIRED_CONTINUOUS:
                return True
        else:
            present_since = None
        show_frame(
            privacy, frame,
            ['BAT DAU SAU 3 GIAY', f'San sang: {label}', f'Cho toi da {HAND_WAIT_MAX_SECONDS - elapsed:.1f}s'],
            [(0, 0, 255), (0, 255, 255), (255, 255, 0)],
        )


def show_frame(privacy, frame, overlay_lines, overlay_colors):
    display_frame = frame.copy()
    if privacy.mode == 'crop':
        display_frame = scale_for_display(display_frame)
    y = 30
    for text, color in zip(overlay_lines, overlay_colors):
        cv2.putText(display_frame, text, (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)
        y += 35
    privacy.mark_mode_label(display_frame)
    cv2.imshow(WINDOW_NAME, display_frame)
    cv2.waitKey(1)


def countdown(cap, classifier, privacy, mirror, face_guard, seconds, message):
    start = time.time()
    while time.time() - start < seconds:
        result = read_and_process(cap, classifier, privacy, mirror, face_guard)
        if not result[0]:
            continue
        frame = result[1]
        remaining = seconds - (time.time() - start)
        show_frame(privacy, frame, [message, f'{remaining:.1f}s'], [(0, 255, 255), (0, 0, 255)])


def append_capture_log(log_path, label, filename, model_label, model_conf,
                        final_label, final_conf, rule_override, hand_present):
    is_new = not os.path.isfile(log_path)
    with open(log_path, 'a', newline='') as f:
        writer = csv.writer(f)
        if is_new:
            writer.writerow(['label', 'filename', 'model_label', 'model_conf',
                              'final_label', 'final_conf', 'rule_override', 'hand_present'])
        writer.writerow([
            label, filename, model_label, f'{model_conf:.4f}',
            final_label, f'{final_conf:.4f}', 'true' if rule_override else 'false',
            'true' if hand_present else 'false',
        ])


def capture_images(cap, classifier, privacy, mirror, face_guard, label, out_dir, count, log_path,
                    require_hand=True):
    label_dir = os.path.join(out_dir, label)
    os.makedirs(label_dir, exist_ok=True)
    captured = 0
    attempts = 0
    while captured < count and attempts < count * MAX_CAPTURE_ATTEMPTS_PER_IMAGE:
        attempts += 1
        ok, frame, model_label, model_conf, final_label, final_conf, rule_override, hand_present = (
            read_and_process(cap, classifier, privacy, mirror, face_guard))
        if not ok:
            continue
        if require_hand and not hand_present:
            show_frame(privacy, frame, [f'{label}: khong thay tay, bo qua anh nay'], [(0, 0, 255)])
            continue
        fname = f'{label}_{captured + 1:02d}.jpg'
        cv2.imwrite(os.path.join(label_dir, fname), frame)
        if privacy.needs_landmarks:
            append_capture_log(log_path, label, fname, model_label, model_conf,
                                final_label, final_conf, rule_override, hand_present)
        captured += 1
        show_frame(privacy, frame, [f'{label}: chup {captured}/{count}'], [(0, 255, 0)])
        time.sleep(IMAGE_CAPTURE_INTERVAL)
    if captured < count:
        print(f'CANH BAO: chi chup duoc {captured}/{count} anh cho "{label}" (het so lan thu).')
    return label_dir


def capture_wave_videos(cap, classifier, privacy, mirror, face_guard, out_dir):
    label_dir = os.path.join(out_dir, LABEL_WAVE)
    os.makedirs(label_dir, exist_ok=True)
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    fps = 20.0
    ok, probe, *_ = read_and_process(cap, classifier, privacy, mirror, face_guard)
    height, width = probe.shape[:2] if ok else (480, 640)

    for v in range(WAVE_VIDEO_COUNT):
        countdown(cap, classifier, privacy, mirror, face_guard, PREP_SECONDS,
                  f'San sang Wave video {v + 1}/{WAVE_VIDEO_COUNT}')
        ready = wait_for_hand(cap, classifier, privacy, mirror, face_guard, f'Wave video {v + 1}')
        if not ready:
            print(f'Wave video {v + 1}/{WAVE_VIDEO_COUNT}: KHONG THAY TAY, CHAY LAI. Bo qua video nay.')
            continue
        fname = os.path.join(label_dir, f'wave_{v + 1:02d}.mp4')
        writer = cv2.VideoWriter(fname, fourcc, fps, (width, height))
        start = time.time()
        while time.time() - start < WAVE_VIDEO_SECONDS:
            result = read_and_process(cap, classifier, privacy, mirror, face_guard)
            if not result[0]:
                continue
            frame = result[1]
            writer.write(frame)
            show_frame(privacy, frame, [f'DANG QUAY Wave {v + 1}/{WAVE_VIDEO_COUNT}'], [(0, 0, 255)])
        writer.release()
        print(f'Da luu {fname}')
        if v < WAVE_VIDEO_COUNT - 1:
            time.sleep(BETWEEN_SECONDS)
    return label_dir


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--camera-index', type=int, default=0)
    parser.add_argument('--output-dir', default=DEFAULT_OUTPUT_DIR)
    parser.add_argument('--only-wave', action='store_true',
                         help='Chi quay lai video Wave (danh cho truong hop phai quay bu).')
    parser.add_argument('--images-per-label', type=int, default=IMAGES_PER_LABEL)
    parser.add_argument('--none-images', type=int, default=NONE_IMAGES)
    parser.add_argument('--labels', default=None,
                         help='Danh sach cu chi tinh can chup, ngan cach boi dau phay '
                              '(mac dinh: tat ca ' + ','.join(LABELS_STATIC) + ').')
    parser.add_argument('--static-only', action='store_true',
                         help='Chi chup cu chi tinh (bo qua Wave va None), danh cho chup bu.')
    args = parser.parse_args()
    images_per_label = args.images_per_label
    none_images = args.none_images
    labels_static = args.labels.split(',') if args.labels else LABELS_STATIC

    config_params = load_gesture_config()
    roi = list(config_params.get('roi', DEFAULT_ROI))
    privacy_mode = config_params.get('privacy_mode', DEFAULT_PRIVACY_MODE)
    mask_margin_px = int(config_params.get('mask_margin_px', 18))
    privacy = PrivacyProcessor(roi, privacy_mode, mask_margin_px=mask_margin_px)
    classifier = build_classifier_from_config(config_params)
    face_guard = build_face_guard_from_config(config_params) if privacy.needs_landmarks else None
    mirror = True
    log_path = os.path.join(args.output_dir, CAPTURE_LOG_NAME)

    print('Chuan bi chay capture_gestures.py, dung vao vi tri')
    time.sleep(WEBCAM_WARMUP_SECONDS)

    cap = open_camera(args.camera_index)

    print('Thu tu cu chi:', ', '.join(labels_static + [LABEL_WAVE, LABEL_NONE]))
    print(f'privacy_mode={privacy.mode}, roi={privacy.roi}, face_guard={"on" if face_guard else "off"}')
    print(f'Cu chi tinh: chuan bi {PREP_SECONDS:.0f}s roi chup {images_per_label} anh, '
          f'cach nhau {IMAGE_CAPTURE_INTERVAL:.1f}s, nghi {BETWEEN_SECONDS:.0f}s.')
    print(f'Wave: chuan bi {PREP_SECONDS:.0f}s roi quay {WAVE_VIDEO_COUNT} video '
          f'{WAVE_VIDEO_SECONDS:.0f}s moi video, nghi {BETWEEN_SECONDS:.0f}s giua cac video.')
    print(f'None: chup {none_images} anh (tay ha xuong hoac ngoai khung).')
    print(f'Luu vao: {args.output_dir}')

    os.makedirs(args.output_dir, exist_ok=True)

    if args.only_wave:
        print('Che do --only-wave: chi quay lai video Wave, giu tay xa mat (thap hon vai hoac sang mot ben).')
        out = capture_wave_videos(cap, classifier, privacy, mirror, face_guard, args.output_dir)
        print(f'Da quay {WAVE_VIDEO_COUNT} video Wave -> {out}')
    else:
        for label in labels_static:
            countdown(cap, classifier, privacy, mirror, face_guard, PREP_SECONDS, f'San sang cu chi: {label}')
            ready = wait_for_hand(cap, classifier, privacy, mirror, face_guard, label)
            if not ready:
                print(f'{label}: KHONG THAY TAY, CHAY LAI. Bo qua cu chi nay.')
                continue
            out = capture_images(cap, classifier, privacy, mirror, face_guard, label,
                                  args.output_dir, images_per_label, log_path, require_hand=True)
            print(f'Da chup anh cho "{label}" -> {out}')
            time.sleep(BETWEEN_SECONDS)

        if not args.static_only:
            out = capture_wave_videos(cap, classifier, privacy, mirror, face_guard, args.output_dir)
            print(f'Da quay video Wave -> {out}')

            countdown(cap, classifier, privacy, mirror, face_guard, PREP_SECONDS, f'San sang cu chi: {LABEL_NONE}')
            out = capture_images(cap, classifier, privacy, mirror, face_guard, LABEL_NONE,
                                  args.output_dir, none_images, log_path, require_hand=False)
            print(f'Da chup {none_images} anh cho "{LABEL_NONE}" -> {out}')

    classifier.close()
    cap.release()
    cv2.destroyAllWindows()
    print('Hoan tat thu thap du lieu.')


if __name__ == '__main__':
    main()
