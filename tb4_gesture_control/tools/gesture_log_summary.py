#!/usr/bin/env python3
import argparse
import collections
import glob
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

DEFAULT_LOG_DIR = os.path.expanduser('~/gesture_report_data')
DEFAULT_MD = os.path.join(DEFAULT_LOG_DIR, 'gesture_summary.md')
DEFAULT_ROS_LOG_ROOT = os.path.expanduser('~/.ros/log')

GESTURE_LINE_RE = re.compile(r'Gesture -> (?P<label>\S+) \((?P<conf>[0-9.]+)\)')
FSM_LINE_RE = re.compile(r'\[(?P<iso>[0-9T:.\-]+)\] FSM event=(?P<event>\S+)(?P<rest>.*)')
KV_RE = re.compile(r'(\w+)=(\S+)')

ACCEPTED_EVENTS = ('selected', 'started', 'cancelled', 'cancel_noop', 'emergency_stop')


def latest_ros_log_session(ros_log_root):
    latest_link = os.path.join(ros_log_root, 'latest')
    if os.path.islink(latest_link) or os.path.isdir(latest_link):
        return os.path.realpath(latest_link)
    sessions = [d for d in glob.glob(os.path.join(ros_log_root, '*')) if os.path.isdir(d)]
    if not sessions:
        return None
    return max(sessions, key=os.path.getmtime)


def find_node_log(session_dir, node_name):
    matches = sorted(glob.glob(os.path.join(session_dir, f'{node_name}*.log')), key=os.path.getmtime)
    return matches[-1] if matches else None


def parse_kv(rest):
    return dict(KV_RE.findall(rest))


def parse_gesture_log(path):
    rows = []
    if not path or not os.path.isfile(path):
        return rows
    with open(path, errors='replace') as f:
        for line in f:
            m = GESTURE_LINE_RE.search(line)
            if m:
                rows.append((m.group('label'), float(m.group('conf'))))
    return rows


def parse_behavior_log(path):
    events = []
    if not path or not os.path.isfile(path):
        return events
    with open(path, errors='replace') as f:
        for line in f:
            m = FSM_LINE_RE.search(line)
            if m:
                kv = parse_kv(m.group('rest'))
                events.append((m.group('iso'), m.group('event'), kv))
    return events


def summarize_gesture_rows(rows):
    counts = collections.Counter(label for label, _conf in rows)
    conf_by_label = collections.defaultdict(list)
    for label, conf in rows:
        conf_by_label[label].append(conf)
    stats = {}
    for label, confs in conf_by_label.items():
        stats[label] = (sum(confs) / len(confs), min(confs), max(confs))
    return counts, stats


def summarize_behavior_events(events):
    accepted = sum(1 for _iso, event, _kv in events if event in ACCEPTED_EVENTS)
    ignored_reasons = collections.Counter(
        kv.get('reason', 'unknown') for _iso, event, kv in events if event == 'ignored')
    emergency_stops = sum(1 for _iso, event, _kv in events if event == 'emergency_stop')
    signal_lost = sum(1 for _iso, event, _kv in events if event == 'signal_lost')
    aborted_by_reason = collections.Counter(
        kv.get('reason', 'unknown') for _iso, event, kv in events if event == 'aborted')
    timeouts = sum(1 for _iso, event, _kv in events if event == 'timeout')

    latencies = []
    pending_start = None
    for iso, event, kv in events:
        if event == 'started':
            pending_start = (iso, kv.get('behavior'))
        elif event == 'moving' and pending_start is not None:
            started_iso, started_behavior = pending_start
            if kv.get('behavior') == started_behavior:
                latencies.append(_iso_diff_seconds(started_iso, iso))
            pending_start = None

    return {
        'accepted': accepted,
        'ignored_reasons': ignored_reasons,
        'emergency_stops': emergency_stops,
        'signal_lost': signal_lost,
        'aborted_by_reason': aborted_by_reason,
        'timeouts': timeouts,
        'thumb_up_to_moving_latencies': latencies,
    }


def _iso_diff_seconds(iso_a, iso_b):
    import datetime
    fmt = '%Y-%m-%dT%H:%M:%S.%f'

    def parse(iso):
        if '.' not in iso:
            iso = iso + '.000'
        return datetime.datetime.strptime(iso, fmt)

    return (parse(iso_b) - parse(iso_a)).total_seconds()


def write_markdown(md_path, gesture_log_path, behavior_log_path, gesture_counts, gesture_stats,
                    behavior_summary):
    lines = ['# Tom tat log gesture_recognition_node + robot_behavior_node\n']
    lines.append(f'Nguon log gesture_recognition_node: `{gesture_log_path or "khong tim thay"}`')
    lines.append(f'Nguon log robot_behavior_node: `{behavior_log_path or "khong tim thay"}`\n')

    lines.append('## So khung theo nhan (gesture_recognition_node)\n')
    if gesture_counts:
        lines.append('| Cu chi | So lan ghi nhan | Do tin cay TB | Thap nhat | Cao nhat |')
        lines.append('|---|---|---|---|---|')
        for label, count in gesture_counts.most_common():
            avg, lo, hi = gesture_stats.get(label, (0.0, 0.0, 0.0))
            lines.append(f'| {label} | {count} | {avg:.2f} | {lo:.2f} | {hi:.2f} |')
    else:
        lines.append('Khong tim thay dong log "Gesture -> ..." nao.')
    lines.append('')

    lines.append('## Lenh bi bo qua theo ly do (robot_behavior_node)\n')
    if behavior_summary['ignored_reasons']:
        lines.append('| Ly do | So lan |')
        lines.append('|---|---|')
        for reason, count in behavior_summary['ignored_reasons'].most_common():
            lines.append(f'| {reason} | {count} |')
    else:
        lines.append('Khong co lenh nao bi bo qua trong log.')
    lines.append('')

    lines.append('## An toan: dung khan cap / mat tin hieu / huy do an toan\n')
    lines.append(f'- So lan Open_Palm (emergency_stop) duoc chap nhan: {behavior_summary["emergency_stops"]}')
    lines.append(f'- So lan dung do mat tin hieu (MAT TIN HIEU): {behavior_summary["signal_lost"]}')
    lines.append(f'- So lan timeout mot luot hanh vi (TIMEOUT): {behavior_summary["timeouts"]}')
    if behavior_summary['aborted_by_reason']:
        lines.append('- Huy do lop an toan /scan hoac /hazard_detection, theo ly do:')
        for reason, count in behavior_summary['aborted_by_reason'].most_common():
            lines.append(f'  - {reason}: {count}')
    lines.append('')

    lines.append('## So lan cu chi duoc chap nhan (edge-triggered)\n')
    lines.append(f'Tong so lenh duoc chap nhan (selected/started/cancelled/cancel_noop/emergency_stop): '
                 f'{behavior_summary["accepted"]}\n')

    lines.append('## Thoi gian tu Thumb_Up (started) toi khi robot bat dau chay (moving)\n')
    latencies = behavior_summary['thumb_up_to_moving_latencies']
    if latencies:
        lines.append(f'- So lan do duoc: {len(latencies)}')
        lines.append(f'- Trung binh: {sum(latencies) / len(latencies):.3f} s')
        lines.append(f'- Thap nhat: {min(latencies):.3f} s')
        lines.append(f'- Cao nhat: {max(latencies):.3f} s')
    else:
        lines.append('Khong co cap started/moving nao de do.')
    lines.append('')

    lines.append('Tom tat nay doc truc tiep tu log hai node (khong phu thuoc dataset anh/video).\n')

    os.makedirs(os.path.dirname(md_path), exist_ok=True)
    with open(md_path, 'w') as f:
        f.write('\n'.join(lines) + '\n')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--ros-log-root', default=DEFAULT_ROS_LOG_ROOT)
    parser.add_argument('--session-dir', default=None,
                         help='Thu muc session ~/.ros/log/<timestamp> cu the, bo qua tim kiem tu dong.')
    parser.add_argument('--gesture-log-path', default=None)
    parser.add_argument('--behavior-log-path', default=None)
    parser.add_argument('--md-path', default=DEFAULT_MD)
    args = parser.parse_args()

    session_dir = args.session_dir or latest_ros_log_session(args.ros_log_root)

    gesture_log_path = args.gesture_log_path
    behavior_log_path = args.behavior_log_path
    if session_dir:
        gesture_log_path = gesture_log_path or find_node_log(session_dir, 'gesture_recognition_node')
        behavior_log_path = behavior_log_path or find_node_log(session_dir, 'robot_behavior_node')

    gesture_rows = parse_gesture_log(gesture_log_path)
    behavior_events = parse_behavior_log(behavior_log_path)

    gesture_counts, gesture_stats = summarize_gesture_rows(gesture_rows)
    behavior_summary = summarize_behavior_events(behavior_events)

    write_markdown(args.md_path, gesture_log_path, behavior_log_path,
                    gesture_counts, gesture_stats, behavior_summary)
    print(f'Da doc {len(gesture_rows)} dong log gesture, {len(behavior_events)} dong log FSM')
    print(f'Da ghi tom tat vao {args.md_path}')


if __name__ == '__main__':
    main()
