#!/usr/bin/env python3
import argparse
import os
import sys

import cv2

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

from tb4_gesture_control.gesture_recognition_node import FaceGuard

DEFAULT_OUTPUT_DIR = os.path.expanduser('~/gesture_report_data/privacy_check')
SAMPLE_INTERVAL_SEC = 0.5


def main():
    parser = argparse.ArgumentParser(
        description='Quet video de tim cac moc thoi gian nghi co mat nguoi, dung cho kiem tra rieng tu '
                     'truoc khi chia se video demo quay man hinh. Bo phat hien co the bo sot mat '
                     '(goc nghieng, anh sang yeu, mat bi che mot phan) nen van PHAI xem lai bang mat.')
    parser.add_argument('video_path')
    parser.add_argument('--output-dir', default=DEFAULT_OUTPUT_DIR)
    parser.add_argument('--interval', type=float, default=SAMPLE_INTERVAL_SEC)
    args = parser.parse_args()

    if not os.path.isfile(args.video_path):
        print(f'Khong thay video: {args.video_path}', file=sys.stderr)
        sys.exit(1)

    cap = cv2.VideoCapture(args.video_path)
    if not cap.isOpened():
        print(f'Khong mo duoc video: {args.video_path}', file=sys.stderr)
        sys.exit(1)

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    frame_step = max(1, int(round(fps * args.interval)))
    os.makedirs(args.output_dir, exist_ok=True)

    guard = FaceGuard()
    suspects = []
    frame_idx = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        if frame_idx % frame_step == 0:
            timestamp_sec = frame_idx / fps
            boxes, detected = guard.detect(frame, timestamp_sec)
            if detected and boxes:
                for i, (x, y, bw, bh) in enumerate(boxes):
                    ex = int(bw * guard.expand_ratio)
                    ey = int(bh * guard.expand_ratio)
                    h, w = frame.shape[:2]
                    x0 = max(0, x - ex)
                    y0 = max(0, y - ey)
                    x1 = min(w, x + bw + ex)
                    y1 = min(h, y + bh + ey)
                    crop = frame[y0:y1, x0:x1]
                    fname = f'suspect_{timestamp_sec:07.2f}s_{i}.jpg'
                    cv2.imwrite(os.path.join(args.output_dir, fname), crop)
                    suspects.append((timestamp_sec, fname))
        frame_idx += 1
    cap.release()

    print(f'Da quet {frame_idx} khung ({frame_idx / fps:.1f}s), cach nhau {args.interval:.1f}s moi lan kiem tra.')
    print(f'So moc thoi gian nghi co mat: {len(suspects)}')
    for t, fname in suspects:
        print(f'  {t:.2f}s -> {os.path.join(args.output_dir, fname)}')
    print(
        'GIOI HAN: bo phat hien Haar cascade co the BO SOT mat (goc nghieng manh, anh sang yeu, '
        'mat bi che mot phan boi tay/toc). Danh sach tren chi la goi y, van phai xem lai toan bo '
        'video bang mat truoc khi chia se.'
    )


if __name__ == '__main__':
    main()
