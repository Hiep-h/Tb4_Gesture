#!/usr/bin/env python3
import argparse
import collections
import datetime
import os
import sys
import time

import cv2

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

from tb4_gesture_control.gesture_recognition_node import (
    DEFAULT_MIN_CONFIDENCE,
    DEFAULT_PRIVACY_MODE,
    DEFAULT_ROI,
    PrivacyProcessor,
    build_classifier_from_config,
    build_face_guard_from_config,
    load_gesture_config,
    process_frame,
    scale_for_display,
)
from tb4_gesture_control.gesture_types import NONE_GESTURE, WAVE

LABELS_TO_CHECK = ['Open_Palm', 'Closed_Fist', 'Pointing_Up', 'Victory', 'Thumb_Up', WAVE, NONE_GESTURE]
PREP_SECONDS = 3.0
TEST_SECONDS = 6.0
WEBCAM_WARMUP_SECONDS = 5.0
LOW_ACCURACY_THRESHOLD = 0.6
WINDOW_NAME = 'Live check cu chi'
DEFAULT_LOG_PATH = os.path.expanduser('~/gesture_report_data/live_check_runs.md')


HAND_WAIT_MAX_SECONDS = 8.0
HAND_WAIT_REQUIRED_CONTINUOUS = 0.5


def read_and_process(cap, classifier, privacy, mirror, face_guard):
    ok, frame = cap.read()
    if not ok:
        return False, None, None, None, False
    if mirror:
        frame = cv2.flip(frame, 1)
    now = time.time()
    result = process_frame(frame, classifier, privacy, now, face_guard=face_guard)
    display_frame, _model_label, _model_conf, _raw_label, _raw_conf, eff_label, eff_conf, landmarks, _ro = result
    hand_present = bool(landmarks) and len(landmarks) >= 21
    return True, display_frame, eff_label, eff_conf, hand_present


def show(privacy, frame, lines, colors):
    display = frame.copy()
    if privacy.mode == 'crop':
        display = scale_for_display(display)
    y = 30
    for text, color in zip(lines, colors):
        cv2.putText(display, text, (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.9, color, 2)
        y += 40
    privacy.mark_mode_label(display)
    cv2.imshow(WINDOW_NAME, display)
    cv2.waitKey(1)


def countdown(cap, classifier, privacy, mirror, face_guard, seconds, label):
    start = time.time()
    while time.time() - start < seconds:
        ok, frame, _el, _ec, _hp = read_and_process(cap, classifier, privacy, mirror, face_guard)
        if not ok:
            continue
        remaining = seconds - (time.time() - start)
        show(privacy, frame, [f'Chuan bi: {label}', f'{remaining:.1f}s'], [(0, 255, 255), (0, 0, 255)])


def wait_for_hand(cap, classifier, privacy, mirror, face_guard, label):
    start = time.time()
    present_since = None
    while True:
        elapsed = time.time() - start
        if elapsed > HAND_WAIT_MAX_SECONDS:
            return False
        ok, frame, _el, _ec, hand_present = read_and_process(cap, classifier, privacy, mirror, face_guard)
        if not ok:
            continue
        now = time.time()
        if hand_present:
            if present_since is None:
                present_since = now
            elif now - present_since >= HAND_WAIT_REQUIRED_CONTINUOUS:
                return True
        else:
            present_since = None
        show(
            privacy, frame,
            ['BAT DAU SAU 3 GIAY', f'San sang: {label}', f'Cho toi da {HAND_WAIT_MAX_SECONDS - elapsed:.1f}s'],
            [(0, 0, 255), (0, 255, 255), (255, 255, 0)],
        )


def check_label(cap, classifier, privacy, mirror, face_guard, label):
    classifier.reset_wave()
    total = 0
    correct = 0
    hand_frames = 0
    hand_correct = 0
    confidences = []
    wrong_votes = collections.Counter()
    start = time.time()
    while time.time() - start < TEST_SECONDS:
        ok, frame, eff_label, eff_conf, hand_present = read_and_process(cap, classifier, privacy, mirror, face_guard)
        if not ok:
            continue
        predicted = eff_label if eff_conf >= DEFAULT_MIN_CONFIDENCE else NONE_GESTURE
        total += 1
        if hand_present:
            hand_frames += 1
        if predicted == label:
            correct += 1
            confidences.append(eff_conf)
            if hand_present:
                hand_correct += 1
        else:
            wrong_votes[predicted] += 1
        remaining = TEST_SECONDS - (time.time() - start)
        show(
            privacy, frame,
            [f'Kiem tra: {label}', f'{remaining:.1f}s', f'Du doan: {predicted}'],
            [(0, 255, 0), (0, 0, 255), (255, 255, 0)],
        )
    ratio = correct / total if total else 0.0
    hand_ratio = hand_frames / total if total else 0.0
    hand_correct_ratio = hand_correct / hand_frames if hand_frames else 0.0
    avg_conf = sum(confidences) / len(confidences) if confidences else 0.0
    worst = wrong_votes.most_common(1)[0][0] if wrong_votes else '-'
    return {
        'label': label,
        'ratio': ratio,
        'avg_conf': avg_conf,
        'worst_confused': worst,
        'total': total,
        'correct': correct,
        'hand_frames': hand_frames,
        'hand_ratio': hand_ratio,
        'hand_correct': hand_correct,
        'hand_correct_ratio': hand_correct_ratio,
    }


def print_table(results):
    print()
    print(f'{"Cu chi":<12} {"Dung/Tong":<12} {"Ty le":<8} {"Do tin cay TB":<15} {"Nham nhieu nhat":<15} '
          f'{"Khung co tay":<14} {"Dung/khung co tay":<18}')
    for r in results:
        fraction = f'{r["correct"]}/{r["total"]}'
        hand_fraction = f'{r["hand_frames"]}/{r["total"]} ({r["hand_ratio"]:.2f})'
        hand_correct_fraction = f'{r["hand_correct"]}/{r["hand_frames"]} ({r["hand_correct_ratio"]:.2f})'
        print(f'{r["label"]:<12} {fraction:<12} {r["ratio"]:<8.2f} {r["avg_conf"]:<15.2f} {r["worst_confused"]:<15} '
              f'{hand_fraction:<14} {hand_correct_fraction:<18}')
    print()
    low = [r for r in results if r['ratio'] < LOW_ACCURACY_THRESHOLD]
    if low:
        print('CANH BAO: cac cu chi duoi 60%:', ', '.join(r['label'] for r in low))


def append_run_log(log_path, results, config_params, label=''):
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    is_new = not os.path.isfile(log_path)
    timestamp = datetime.datetime.now().isoformat(timespec='seconds')
    lines = []
    if is_new:
        lines.append('# Ket qua tung lan chay live_check.py\n')
    header = f'## {timestamp}' + (f' ({label})' if label else '')
    lines.append(header)
    lines.append(
        f'privacy_mode={config_params.get("privacy_mode")}, '
        f'enter_confidence={config_params.get("enter_confidence")}, '
        f'exit_confidence={config_params.get("exit_confidence")}'
    )
    lines.append('')
    lines.append('| Cu chi | Dung/Tong (tat ca khung) | Ty le (tat ca khung) | Do tin cay TB | '
                  'Nham nhieu nhat | Khung co tay/Tong | Dung/Khung co tay |')
    lines.append('|---|---|---|---|---|---|---|')
    for r in results:
        lines.append(
            f'| {r["label"]} | {r["correct"]}/{r["total"]} | {r["ratio"]:.2f} | '
            f'{r["avg_conf"]:.2f} | {r["worst_confused"]} | '
            f'{r["hand_frames"]}/{r["total"]} ({r["hand_ratio"]:.2f}) | '
            f'{r["hand_correct"]}/{r["hand_frames"]} ({r["hand_correct_ratio"]:.2f}) |'
        )
    lines.append('')
    with open(log_path, 'a') as f:
        f.write('\n'.join(lines) + '\n')


def run_once(cap, classifier, privacy, mirror, face_guard, labels):
    results = []
    for label in labels:
        countdown(cap, classifier, privacy, mirror, face_guard, PREP_SECONDS, label)
        if label != NONE_GESTURE:
            ready = wait_for_hand(cap, classifier, privacy, mirror, face_guard, label)
            if not ready:
                print(f'{label}: KHONG THAY TAY, CHAY LAI (bo qua lan nay, khong tinh vao bang)')
                continue
        result = check_label(cap, classifier, privacy, mirror, face_guard, label)
        results.append(result)
        print(
            f'{label}: {result["correct"]}/{result["total"]} ({result["ratio"]:.2f}), '
            f'do tin cay TB={result["avg_conf"]:.2f}, nham nhieu nhat={result["worst_confused"]}, '
            f'khung co tay={result["hand_frames"]}/{result["total"]} ({result["hand_ratio"]:.2f}), '
            f'dung/khung co tay={result["hand_correct"]}/{result["hand_frames"]} ({result["hand_correct_ratio"]:.2f})'
        )
    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--camera-index', type=int, default=0)
    parser.add_argument('--labels', nargs='*', default=None,
                         help='Danh sach cu chi can kiem tra (mac dinh: tat ca).')
    parser.add_argument('--repeat', type=int, default=1, help='So lan lap lai lien tiep.')
    parser.add_argument('--log-path', default=DEFAULT_LOG_PATH)
    parser.add_argument('--run-label', default='')
    parser.add_argument('--no-log', action='store_true')
    args = parser.parse_args()

    labels = args.labels if args.labels else LABELS_TO_CHECK

    config_params = load_gesture_config()
    roi = list(config_params.get('roi', DEFAULT_ROI))
    privacy_mode = config_params.get('privacy_mode', DEFAULT_PRIVACY_MODE)
    mask_margin_px = int(config_params.get('mask_margin_px', 18))
    privacy = PrivacyProcessor(roi, privacy_mode, mask_margin_px=mask_margin_px)
    face_guard = build_face_guard_from_config(config_params) if privacy.needs_landmarks else None
    mirror = True

    print('Chuan bi chay live_check.py, dung vao vi tri')
    time.sleep(WEBCAM_WARMUP_SECONDS)

    cap = cv2.VideoCapture(args.camera_index)
    if not cap.isOpened():
        print(f'Khong mo duoc webcam index {args.camera_index}', file=sys.stderr)
        sys.exit(1)

    classifier = build_classifier_from_config(config_params)

    for run_idx in range(args.repeat):
        if args.repeat > 1:
            print(f'--- Lan chay {run_idx + 1}/{args.repeat} ---')
        results = run_once(cap, classifier, privacy, mirror, face_guard, labels)
        print_table(results)
        if not args.no_log:
            append_run_log(args.log_path, results, config_params, label=args.run_label)
            print(f'Da ghi ket qua vao {args.log_path}')

    classifier.close()
    cap.release()
    cv2.destroyAllWindows()


if __name__ == '__main__':
    main()
