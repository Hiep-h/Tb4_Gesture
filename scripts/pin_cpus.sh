#!/bin/bash
set -uo pipefail

GESTURE_CORES="0-5"
GAZEBO_CORES="6-11"
WAIT_TIMEOUT_S=120

wait_for_pids() {
    local pattern="$1"
    local waited=0
    local pids=""
    while [ "$waited" -lt "$WAIT_TIMEOUT_S" ]; do
        pids=$(pgrep -f "$pattern" | tr '\n' ' ')
        if [ -n "$pids" ]; then
            echo "$pids"
            return 0
        fi
        sleep 2
        waited=$((waited + 2))
    done
    echo ""
    return 1
}

echo "=== Cho tien trinh gesture_recognition_node (toi da ${WAIT_TIMEOUT_S}s) ==="
GESTURE_PIDS=$(wait_for_pids "lib/tb4_gesture_control/gesture_recognition_node")
if [ -z "$GESTURE_PIDS" ]; then
    echo "LOI: khong thay gesture_recognition_node sau ${WAIT_TIMEOUT_S}s"
    exit 1
fi
echo "gesture_recognition_node PID: $GESTURE_PIDS"

echo "=== Cho tien trinh robot_behavior_node (toi da ${WAIT_TIMEOUT_S}s) ==="
BEHAVIOR_PIDS=$(wait_for_pids "lib/tb4_gesture_control/robot_behavior_node")
if [ -z "$BEHAVIOR_PIDS" ]; then
    echo "LOI: khong thay robot_behavior_node sau ${WAIT_TIMEOUT_S}s"
    exit 1
fi
echo "robot_behavior_node PID: $BEHAVIOR_PIDS"

echo "=== Cho tien trinh ign gazebo (toi da ${WAIT_TIMEOUT_S}s) ==="
GAZEBO_PIDS=$(wait_for_pids "ign gazebo")
if [ -z "$GAZEBO_PIDS" ]; then
    echo "LOI: khong thay ign gazebo sau ${WAIT_TIMEOUT_S}s"
    exit 1
fi
echo "ign gazebo PID: $GAZEBO_PIDS"

echo "=== Ghim gesture + behavior node vao loi ${GESTURE_CORES} (mọi luong, -a) ==="
for pid in $GESTURE_PIDS $BEHAVIOR_PIDS; do
    taskset -a -cp "$GESTURE_CORES" "$pid"
done

echo "=== Ghim ign gazebo vao loi ${GAZEBO_CORES} (mọi luong, -a) ==="
for pid in $GAZEBO_PIDS; do
    taskset -a -cp "$GAZEBO_CORES" "$pid"
done

echo "=== Xac nhan affinity (PID chinh + vai luong con) ==="
for pid in $GESTURE_PIDS $BEHAVIOR_PIDS $GAZEBO_PIDS; do
    taskset -cp "$pid"
    task_dir="/proc/$pid/task"
    if [ -d "$task_dir" ]; then
        count=0
        for tid in "$task_dir"/*; do
            tid_num=$(basename "$tid")
            if [ "$tid_num" != "$pid" ]; then
                taskset -cp "$tid_num" 2>/dev/null
                count=$((count + 1))
                if [ "$count" -ge 2 ]; then
                    break
                fi
            fi
        done
    fi
done

echo "=== Hoan tat ghim CPU ==="
