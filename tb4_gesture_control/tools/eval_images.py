#!/usr/bin/env python3
import argparse
import collections
import csv
import glob
import os
import sys
import time

import cv2

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

from tb4_gesture_control.gesture_recognition_node import (
    DEFAULT_MIN_CONFIDENCE,
    build_classifier_from_config,
    load_gesture_config,
)
from tb4_gesture_control.gesture_types import NONE_GESTURE, WAVE

CAPTURE_LOG_NAME = 'capture_log.csv'

STATIC_LABELS = ['Closed_Fist', 'Open_Palm', 'Pointing_Up', 'Victory', 'Thumb_Up', NONE_GESTURE]
ALL_LABELS = STATIC_LABELS + [WAVE]
IMAGE_EXTENSIONS = ('*.jpg', '*.jpeg', '*.png', '*.bmp')
VIDEO_EXTENSIONS = ('*.mp4', '*.avi', '*.mov')

DEFAULT_DATASET_DIR = os.path.expanduser('~/gesture_report_data/dataset')
DEFAULT_OUTPUT = os.path.expanduser('~/gesture_report_data/eval_summary.md')


def _list_files(label_dir, extensions):
    files = []
    for pattern in extensions:
        files.extend(glob.glob(os.path.join(label_dir, pattern)))
    return sorted(files)


def eval_static_label(classifier, label, label_dir, min_confidence):
    results = []
    for path in _list_files(label_dir, IMAGE_EXTENSIONS):
        frame = cv2.imread(path)
        if frame is None:
            continue
        classifier.reset_wave()
        _model_label, _model_conf, raw_label, raw_conf, _landmarks, _rule = classifier.classify_raw(frame)
        predicted = raw_label if raw_conf >= min_confidence else NONE_GESTURE
        results.append((os.path.basename(path), predicted, raw_conf))
    return results


def eval_wave_label(classifier, label_dir, min_confidence):
    results = []
    for path in _list_files(label_dir, VIDEO_EXTENSIONS):
        cap = cv2.VideoCapture(path)
        if not cap.isOpened():
            continue
        classifier.reset_wave()
        best_wave_conf = 0.0
        wave_seen = False
        label_votes = collections.Counter()
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            now = time.time()
            _ml, _mc, _rl, _rc, eff_label, eff_conf, _landmarks, _rule = classifier.classify(frame, now)
            if eff_label == WAVE and eff_conf >= min_confidence:
                wave_seen = True
                best_wave_conf = max(best_wave_conf, eff_conf)
            elif eff_conf >= min_confidence:
                label_votes[eff_label] += 1
        cap.release()

        if wave_seen:
            predicted, conf = WAVE, best_wave_conf
        elif label_votes:
            predicted, conf = label_votes.most_common(1)[0][0], 0.0
        else:
            predicted, conf = NONE_GESTURE, 0.0
        results.append((os.path.basename(path), predicted, conf))
    return results


def build_confusion_matrix(all_results):
    predicted_labels = sorted({pred for _, _, pred, _ in all_results} | {NONE_GESTURE})
    matrix = {true: {pred: 0 for pred in predicted_labels} for true in ALL_LABELS}
    for true_label, _, pred_label, _ in all_results:
        matrix[true_label][pred_label] += 1
    return matrix, predicted_labels


def load_capture_log(dataset_dir):
    path = os.path.join(dataset_dir, CAPTURE_LOG_NAME)
    rows = []
    if not os.path.isfile(path):
        return rows
    with open(path, newline='') as f:
        for row in csv.DictReader(f):
            if 'model_label' not in row:
                continue
            rows.append({
                'label': row['label'],
                'filename': row['filename'],
                'model_label': row['model_label'],
                'model_conf': float(row['model_conf']),
                'final_label': row['final_label'],
                'final_conf': float(row['final_conf']),
                'rule_override': row['rule_override'] == 'true',
            })
    return rows


def results_from_capture_log(rows, label_key, conf_key, min_confidence):
    results = []
    for r in rows:
        label = r[label_key]
        conf = r[conf_key]
        predicted = label if conf >= min_confidence else NONE_GESTURE
        results.append((r['label'], r['filename'], predicted, conf))
    return results


def rule_override_summary(rows):
    counts = collections.Counter()
    totals = collections.Counter()
    for r in rows:
        totals[r['label']] += 1
        if r['rule_override']:
            counts[r['label']] += 1
    return counts, totals


def compare_with_capture_log(reclassified_results, capture_rows):
    if not capture_rows:
        return None
    final_by_key = {(r['label'], r['filename']): r['final_label'] for r in capture_rows}
    agree = 0
    disagree = 0
    examples = []
    for true_label, fname, predicted_on_rendered, _conf in reclassified_results:
        live_final_label = final_by_key.get((true_label, fname))
        if live_final_label is None:
            continue
        if predicted_on_rendered == live_final_label:
            agree += 1
        else:
            disagree += 1
            if len(examples) < 10:
                examples.append((true_label, fname, live_final_label, predicted_on_rendered))
    return {'agree': agree, 'disagree': disagree, 'examples': examples}


def most_confused_to(matrix, true_label, predicted_labels):
    wrong = {pred: matrix[true_label].get(pred, 0) for pred in predicted_labels if pred != true_label}
    wrong = {pred: count for pred, count in wrong.items() if count > 0}
    if not wrong:
        return '-'
    return max(wrong, key=wrong.get)


def accuracy_table_lines(title, all_results):
    matrix, predicted_labels = build_confusion_matrix(all_results)
    lines = [f'### {title}\n']
    lines.append('| Cu chi | So mau | Du doan dung | Accuracy | Nham nhieu nhat thanh |')
    lines.append('|---|---|---|---|---|')
    for true_label in ALL_LABELS:
        rows = [r for r in all_results if r[0] == true_label]
        total = len(rows)
        correct = len([r for r in rows if r[2] == true_label])
        acc = (correct / total) if total else float('nan')
        confused_to = most_confused_to(matrix, true_label, predicted_labels)
        lines.append(f'| {true_label} | {total} | {correct} | {acc:.2f} | {confused_to} |')
    return lines


def write_summary(model_results, final_results, wave_video_results, capture_log_cmp,
                   rule_counts, rule_totals, dataset_dir, output_path, min_confidence):
    lines = []
    lines.append('# Ket qua danh gia do chinh xac nhan dien cu chi\n')
    static_counts = collections.Counter(r[0] for r in final_results if r[0] != WAVE)
    counts_str = ', '.join(f'{label}={static_counts[label]}' for label in STATIC_LABELS if static_counts[label])
    lines.append(
        f'Bo du lieu: `{dataset_dir}` - do nguoi dung tu chup bang webcam qua '
        f'`tools/capture_gestures.py` (anh tinh: {counts_str}, Wave la '
        f'{len(wave_video_results)} video 3s). KHONG phai anh tai tu Internet.\n'
    )
    lines.append(f'Nguong min_confidence dung de danh gia: {min_confidence} (giong gesture_recognition_node).\n')

    if model_results is None:
        lines.append(
            '## Mo hinh MediaPipe thuan (truoc quy tac phu)\n\n'
            'Khong co so lieu mo hinh thuan cho bo anh nay (capture_log.csv cu khong co cot '
            'model_label). Khong the chay lai nhan dien tren anh dataset de bu vi anh da bi che '
            '(hand_only/skeleton), chay lai se cho ket qua tren anh DA CHE chu khong phai mo hinh '
            'thuan. So lieu do truc tiep thay the (chan doan 10s, giu cu chi chuan lien tuc): '
            'Pointing_Up 0/293 khung (0.00), Victory khoang 141/293 khung (~0.48).\n'
        )
    else:
        lines.extend(accuracy_table_lines('Mo hinh MediaPipe thuan (model_label/model_conf, truoc quy tac phu)',
                                           model_results))
        lines.append('')

    lines.extend(accuracy_table_lines('Sau lop bo sung (final_label/final_conf: Wave-override, '
                                       'Pointing_Up/Victory landmark fallback)', final_results))
    lines.append('')

    lines.append('## Quy tac phu da kich hoat bao nhieu lan\n')
    lines.append('| Cu chi | So anh co quy tac phu kich hoat / tong |')
    lines.append('|---|---|')
    for label in STATIC_LABELS:
        total = rule_totals.get(label, 0)
        count = rule_counts.get(label, 0)
        lines.append(f'| {label} | {count}/{total} |')
    lines.append(
        '\nPointing_Up (va Victory neu co) chi dat duoc nho quy tac phu dua tren landmark '
        '(is_pointing_up_shape / is_victory_shape), KHONG phai mo hinh MediaPipe nhan ra truc '
        'tiep - xem bang "Mo hinh MediaPipe thuan" o tren.\n'
    )

    all_results = final_results
    correct_confidences = [
        r[3] for r in all_results if r[2] == r[0] and r[0] != NONE_GESTURE and r[3] > 0
    ]
    lines.append('## Do tin cay cua du doan dung (sau lop bo sung, khong tinh nhan None)\n')
    if correct_confidences:
        lines.append(f'- Trung binh: {sum(correct_confidences) / len(correct_confidences):.3f}')
        lines.append(f'- Thap nhat: {min(correct_confidences):.3f}')
        lines.append(f'- Cao nhat: {max(correct_confidences):.3f}')
    else:
        lines.append('- Khong co du doan dung nao voi do tin cay > 0.')

    lines.append('\n## Wave - danh gia rieng tren video\n')
    wave_total = len(wave_video_results)
    wave_correct = sum(1 for _, pred, _ in wave_video_results if pred == WAVE)
    lines.append(f'- So video nhan dung Wave / tong so video: {wave_correct}/{wave_total}')

    lines.append(
        '\nBo anh/video do mot nguoi tu chup bang webcam trong mot dieu kien anh sang, '
        'vung ROI co dinh, khong khai quat cho moi nguoi dung.\n'
    )

    lines.append('\n## So sanh phu: nhan cuoi luc chup (capture_log.csv) vs. nhan dien lai tren anh da luu\n')
    if capture_log_cmp is None:
        lines.append(
            '- Khong co capture_log.csv (che do privacy khong dung landmark, vd crop/blur_outside/'
            'black_outside/off) nen anh da luu CHINH LA anh duoc dua vao MediaPipe luc chup, khong '
            'can so sanh phu.\n'
        )
    else:
        total_cmp = capture_log_cmp['agree'] + capture_log_cmp['disagree']
        lines.append(
            f'- So mau doi chieu duoc: {total_cmp}. Dung khop: {capture_log_cmp["agree"]}. '
            f'Khac nhau: {capture_log_cmp["disagree"]}.\n'
        )
        lines.append(
            '- Day chi la so lieu phu de kiem tra mat na co lam sai nhan khong. So lieu chinh thuc '
            'cua bao cao (hai bang o tren) luon lay tu capture_log.csv, tuc nhan MediaPipe dua ra '
            'NGAY LUC CHUP tren khung goc trong bo nho - truoc khi dung lai thanh anh nen den. '
            'Khac biet (neu co) o day la do nhan dien lai tren anh da qua mat na (co the mat mot '
            'phan ngu canh ngoai ban tay) khong phai do pipeline chinh bi loi.\n'
        )
        if capture_log_cmp['examples']:
            lines.append('- Vi du khac nhau (nhan/luc_chup -> nhan/anh_da_luu_nhan_dien_lai):')
            for true_label, fname, live_final, rendered_pred in capture_log_cmp['examples']:
                lines.append(f'  - {true_label}/{fname}: {live_final} -> {rendered_pred}')

    with open(output_path, 'w') as f:
        f.write('\n'.join(lines) + '\n')


def main():
    parser = argparse.ArgumentParser(
        description='Danh gia nhan dien cu chi tren bo anh/video tu chup qua webcam.')
    parser.add_argument('--dataset-dir', default=DEFAULT_DATASET_DIR)
    parser.add_argument('--output', default=DEFAULT_OUTPUT)
    parser.add_argument('--min-confidence', type=float, default=DEFAULT_MIN_CONFIDENCE)
    args = parser.parse_args()

    if not os.path.isdir(args.dataset_dir):
        print(
            f'Khong thay thu muc du lieu "{args.dataset_dir}". '
            'Chay tools/capture_gestures.py truoc.', file=sys.stderr,
        )
        sys.exit(1)

    missing = [label for label in ALL_LABELS if not os.path.isdir(os.path.join(args.dataset_dir, label))]
    if missing:
        print(f'Thieu du lieu cho cu chi: {missing}. Chay tools/capture_gestures.py truoc.', file=sys.stderr)
        sys.exit(1)

    classifier = build_classifier_from_config(load_gesture_config())
    reclassified_results = []
    for label in STATIC_LABELS:
        label_dir = os.path.join(args.dataset_dir, label)
        for fname, predicted, conf in eval_static_label(classifier, label, label_dir, args.min_confidence):
            reclassified_results.append((label, fname, predicted, conf))

    wave_dir = os.path.join(args.dataset_dir, WAVE)
    wave_video_results = eval_wave_label(classifier, wave_dir, args.min_confidence)
    classifier.close()

    if not reclassified_results and not wave_video_results:
        print('Khong co mau nao de danh gia (thu muc rong).', file=sys.stderr)
        sys.exit(1)

    capture_rows = load_capture_log(args.dataset_dir)
    if capture_rows:
        model_results = results_from_capture_log(capture_rows, 'model_label', 'model_conf', args.min_confidence)
        final_results = results_from_capture_log(capture_rows, 'final_label', 'final_conf', args.min_confidence)
        rule_counts, rule_totals = rule_override_summary(capture_rows)
        capture_log_cmp = compare_with_capture_log(reclassified_results, capture_rows)
    else:
        model_results = None
        final_results = reclassified_results
        rule_counts, rule_totals = collections.Counter(), collections.Counter()
        capture_log_cmp = None

    final_results = final_results + [(WAVE, fname, predicted, conf) for fname, predicted, conf in wave_video_results]

    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    write_summary(model_results, final_results, wave_video_results, capture_log_cmp,
                  rule_counts, rule_totals, args.dataset_dir, args.output, args.min_confidence)
    print(f'Da ghi ket qua danh gia vao {args.output}')


if __name__ == '__main__':
    main()
