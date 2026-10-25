#!/bin/bash
set -uo pipefail

EXCLUDE='claude|firefox|gnome-shell|Xwayland|warp-svc|vte-spawn|jetbrains|avahi-daemon|stop_all\.sh'

PATTERNS=(
    "tb4_gesture_control/gesture_recognition_node"
    "tb4_gesture_control/robot_behavior_node"
    "ros2 run tb4_gesture_control gesture_recognition_node"
    "ros2 run tb4_gesture_control robot_behavior_node"
    "ign gazebo"
    "gz sim"
    "ros_gz_bridge/parameter_bridge"
    "ros_gz_sim/create"
    "tf2_ros/static_transform_publisher"
    "robot_state_publisher/robot_state_publisher"
    "joint_state_publisher/joint_state_publisher"
    "controller_manager/spawner"
    "irobot_create_nodes"
    "irobot_create_ignition_toolbox"
    "turtlebot4_node"
    "turtlebot4_ignition"
    "rviz2"
    "ros2 launch"
)

matching_pids() {
    for pat in "${PATTERNS[@]}"; do
        pgrep -f "$pat" 2>/dev/null
    done | sort -un | while read -r pid; do
        cmd=$(ps -o cmd= -p "$pid" 2>/dev/null)
        [ -z "$cmd" ] && continue
        echo "$cmd" | grep -qE "$EXCLUDE" && continue
        echo "$pid"
    done
}

wait_for_clear() {
    local timeout_s="$1"
    for ((i = 0; i < timeout_s; i++)); do
        sleep 1
        [ -z "$(matching_pids)" ] && return 0
    done
    return 1
}

echo "=== Buoc 1: SIGINT theo PID ==="
pids=$(matching_pids)
if [ -n "$pids" ]; then
    echo "$pids" | xargs -r kill -INT
    echo "Da gui SIGINT toi: $(echo "$pids" | tr '\n' ' ')"
    wait_for_clear 15
else
    echo "Khong co tien trinh nao de dung"
fi

echo "=== Buoc 2: SIGTERM theo PID (neu con sot sau SIGINT) ==="
pids=$(matching_pids)
if [ -n "$pids" ]; then
    echo "$pids" | xargs -r kill -TERM
    echo "Da gui SIGTERM toi: $(echo "$pids" | tr '\n' ' ')"
    wait_for_clear 5
else
    echo "Khong con tien trinh sau SIGINT"
fi

echo "=== Buoc 3: SIGKILL theo PID (neu con sot sau SIGTERM) ==="
pids=$(matching_pids)
if [ -n "$pids" ]; then
    echo "$pids" | xargs -r kill -9
    echo "Da SIGKILL: $(echo "$pids" | tr '\n' ' ')"
    sleep 2
else
    echo "Khong con tien trinh sau SIGTERM"
fi

echo "=== Buoc 4: kiem tra tien trinh mo coi (PPID=1) ==="
orphans_ppid1=$(ps -eo pid,ppid,cmd --no-headers | awk '$2==1' | grep -viE "$EXCLUDE")
if [ -n "$orphans_ppid1" ]; then
    echo "CANH BAO: con tien trinh voi PPID=1:"
    echo "$orphans_ppid1"
else
    echo "Khong con tien trinh nao voi PPID=1"
fi

echo "=== Buoc 5: kiem tra cuoi cung bang ps aux loc theo ten node/tien trinh ==="
leftover=$(ps aux | grep -E "$(IFS='|'; echo "${PATTERNS[*]}")" | grep -viE "$EXCLUDE" | grep -v "grep -E")
if [ -n "$leftover" ]; then
    echo "CON SOT:"
    echo "$leftover"
else
    echo "SACH"
fi
