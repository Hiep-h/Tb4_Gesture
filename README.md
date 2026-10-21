# TB4 Gesture Control

Bài tập 6 — Giao tiếp phi ngôn ngữ và điều khiển TurtleBot 4 bằng cử chỉ tay.
Nhận diện cử chỉ tay qua webcam (OpenCV + MediaPipe Gesture Recognizer) và
dùng kết quả để điều khiển hành vi của TurtleBot 4 trong Gazebo qua ROS 2.

## 1. Kiến trúc hệ thống

```mermaid
flowchart LR
    subgraph Webcam["Webcam laptop"]
        CAM[("Camera")]
    end

    subgraph GR["gesture_recognition_node"]
        CAM --> OCV[OpenCV capture] --> MP[MediaPipe\nGesture Recognizer] --> WV[Wave detector\n(wrist x oscillation)]
        WV --> DB[Debounce\n(majority vote)]
    end

    DB -- "/detected_gesture\n(std_msgs/String, JSON)" --> RB

    subgraph RB["robot_behavior_node"]
        EDGE[Edge trigger +\nanti-noise cooldown] --> FSM["State machine\nIDLE → SELECTED → RUNNING"]
        WD[Watchdog\n(signal timeout)] --> FSM
        FSM --> SEQ[Segmented\nvelocity sequence]
    end

    SEQ -- "/cmd_vel\n(geometry_msgs/Twist)" --> TB4[("TurtleBot 4\n(Gazebo simulation)")]
```

Hai node độc lập, chỉ ghép qua topic ROS 2:

| Node | Input | Output | Vai trò |
|---|---|---|---|
| `gesture_recognition_node` | Webcam (OpenCV) | `/detected_gesture` (`std_msgs/String`, JSON) | Phát hiện & phân loại cử chỉ tay, hiển thị tên + độ tin cậy trên cửa sổ preview |
| `robot_behavior_node` | `/detected_gesture` | `/cmd_vel` (`geometry_msgs/Twist`) | State machine chọn/xác nhận/hủy hành vi, phát lệnh vận tốc, watchdog an toàn |

Payload của `/detected_gesture` là JSON trong một `std_msgs/String`, ví dụ:

```json
{"gesture": "Open_Palm", "confidence": 0.93, "stamp": 1732000000.12}
```

## 2. Cử chỉ tay → Hành vi robot

| Cử chỉ | Nhãn MediaPipe | Hành vi robot |
|---|---|---|
| Vẫy tay (Wave) | suy ra từ `Open_Palm` + dao động vị trí cổ tay | Xoay trái–phải để chào lại (ngay lập tức, không cần xác nhận) |
| Giơ 1 ngón tay (Pointing Up) | `Pointing_Up` | **Chọn** hành vi tiến–lùi 4 lần (chờ xác nhận) |
| Giơ 2 ngón tay (Victory) | `Victory` | **Chọn** hành vi di chuyển theo quỹ đạo tròn (chờ xác nhận) |
| Giơ ngón cái (Thumbs Up) | `Thumb_Up` | **Xác nhận** và thực hiện hành vi đã chọn |
| Xòe bàn tay (Open Palm) | `Open_Palm` | Dừng ngay lập tức (mọi trạng thái) |
| Nắm tay (Closed Fist) | `Closed_Fist` | Hủy lựa chọn/hành vi hiện tại, về trạng thái chờ (IDLE) |

MediaPipe's bundled model đã phân loại sẵn `Closed_Fist`, `Open_Palm`,
`Pointing_Up`, `Victory`, `Thumb_Up` (và `Thumb_Down`, `None`, `ITSign`
không dùng trong bài này). `Wave` không có trong danh sách nhãn gốc, nên
`gesture_recognition_node` tự suy luận nó: khi mô hình báo `Open_Palm`,
node theo dõi vị trí x của cổ tay (landmark 0) trong một cửa sổ trượt
~1.2s; nếu thấy đủ số lần đổi hướng và biên độ di chuyển ngang, gán lại
nhãn thành `Wave`. Tổng cộng 6 cử chỉ phân biệt được, vượt yêu cầu tối
thiểu 5.

### State machine của `robot_behavior_node`

```
IDLE --Pointing_Up--> SELECTED(forward_backward) --Thumb_Up--> RUNNING --(hết chuỗi)--> IDLE
IDLE --Victory------> SELECTED(circle)            --Thumb_Up--> RUNNING --(hết chuỗi)--> IDLE
(mọi trạng thái) --Open_Palm--> IDLE (dừng ngay, publish Twist() rỗng)
(SELECTED/RUNNING) --Closed_Fist--> IDLE (hủy, dừng)
IDLE --Wave--> phát chuỗi xoay chào, rồi tự về IDLE
```

### Cơ chế chống nhiễu (anti-noise)

Có hai lớp lọc độc lập:

1. **Trong `gesture_recognition_node`**: mỗi khung hình được phân loại
   riêng, nhưng chỉ công bố nhãn "ổn định" khi nó chiếm đa số phiếu
   trong N khung gần nhất (debounce theo đa số, mặc định N=8, cần ≥6
   phiếu giống nhau) và độ tin cậy ≥ ngưỡng (mặc định 0.6).
2. **Trong `robot_behavior_node`**: `GestureEdgeTracker` chỉ cho một cử
   chỉ "bắn" hành động **một lần** mỗi lượt giữ cử chỉ liên tục (phải
   cần ≥3 bản tin liên tiếp giống nhau, và phải quay lại `None`/đổi cử
   chỉ khác trước khi cùng một cử chỉ có thể bắn lại), cộng thêm một
   khoảng cách thời gian tối thiểu giữa hai lần kích hoạt.

### An toàn khi mất tín hiệu

`robot_behavior_node` có watchdog: nếu không nhận được bản tin
`/detected_gesture` nào trong `signal_timeout` giây (mặc định 2.0s —
ví dụ webcam bị tắt, node nhận diện bị crash, hoặc không có tay trong
khung hình quá lâu), robot tự động dừng (`Twist()` rỗng) và trở về
`IDLE`.

## 3. Cài đặt

Yêu cầu: Ubuntu 22.04, ROS 2 Humble, TurtleBot 4 simulation đã cài theo
các bài thực hành trước, Python 3, webcam.

```bash
# 1. Đặt package vào workspace ROS 2 của bạn
cd ~/turtlebot4_ws/src   # hoặc workspace bạn đang dùng cho TB4
ln -s /path/to/Tb4_Gesture/tb4_gesture_control .

# 2. Cài phụ thuộc Python (ngoài rosdep)
cd /path/to/Tb4_Gesture
pip install -r requirements.txt

# 3. Tải model MediaPipe Gesture Recognizer
bash tb4_gesture_control/models/download_model.sh

# 4. Build package
cd ~/turtlebot4_ws
rosdep install --from-paths src --ignore-src -r -y
colcon build --packages-select tb4_gesture_control
source install/setup.bash
```

## 4. Chạy demo

Terminal 1 — khởi chạy TurtleBot 4 trong Gazebo (theo bài thực hành
trước, ví dụ):

```bash
ros2 launch turtlebot4_ignition_bringup turtlebot4_ignition.launch.py
```

Kiểm tra robot nhận lệnh vận tốc:

```bash
ros2 topic pub -1 /cmd_vel geometry_msgs/msg/Twist \
  "{linear: {x: 0.1}, angular: {z: 0.0}}"
```

Terminal 2 — chạy node nhận diện + điều khiển hành vi:

```bash
source install/setup.bash
ros2 launch tb4_gesture_control gesture_control.launch.py
```

Hoặc chạy riêng từng node để debug:

```bash
ros2 run tb4_gesture_control gesture_recognition_node
ros2 run tb4_gesture_control robot_behavior_node
```

Theo dõi topic nhận diện:

```bash
ros2 topic echo /detected_gesture
```

Trong lúc demo, cửa sổ webcam preview hiển thị cử chỉ thô theo từng
khung hình và nhãn "ổn định" đã qua debounce. Nhấn `q` hoặc `Esc` trong
cửa sổ preview để dừng node nhận diện.

### Tham số có thể chỉnh

`gesture_recognition_node` (`ros2 run ... --ros-args -p <tên>:=<giá trị>`):

| Tham số | Mặc định | Ý nghĩa |
|---|---|---|
| `camera_index` | `0` | Chỉ số webcam cho OpenCV |
| `model_path` | tự tìm `models/gesture_recognizer.task` | Đường dẫn model MediaPipe |
| `min_confidence` | `0.6` | Ngưỡng tin cậy tối thiểu để chấp nhận một khung hình |
| `debounce_window` / `debounce_min_votes` | `8` / `6` | Số khung hình & số phiếu tối thiểu để công bố nhãn ổn định |
| `show_preview` | `true` | Bật/tắt cửa sổ OpenCV |

`robot_behavior_node`:

| Tham số | Mặc định | Ý nghĩa |
|---|---|---|
| `signal_timeout` | `2.0` (s) | Thời gian mất tín hiệu trước khi tự dừng |
| `required_consecutive` | `3` | Số bản tin liên tiếp cần để chấp nhận một cử chỉ |
| `min_trigger_interval` | `0.5` (s) | Khoảng cách thời gian tối thiểu giữa 2 lần kích hoạt |
| `control_rate_hz` | `20.0` | Tần số vòng lặp điều khiển / publish `/cmd_vel` |

## 5. Cấu trúc repository

```
Tb4_Gesture/
├── README.md
├── requirements.txt
├── docs/
│   └── REPORT_TEMPLATE.md      # khung báo cáo PDF
└── tb4_gesture_control/        # ROS 2 package (ament_python)
    ├── package.xml
    ├── setup.py / setup.cfg
    ├── launch/gesture_control.launch.py
    ├── models/download_model.sh
    └── tb4_gesture_control/
        ├── gesture_types.py            # hằng số cử chỉ & schema JSON dùng chung
        ├── gesture_recognition_node.py
        └── robot_behavior_node.py
```

## 6. Giới hạn đã biết

* Chỉ xử lý một bàn tay tại một thời điểm (`num_hands=1`), đủ cho yêu
  cầu demo của bài tập.
* `Wave` là suy luận heuristic trên chuỗi vị trí cổ tay, không phải
  nhãn gốc của MediaPipe, nên nhạy với tốc độ vẫy tay và khoảng cách
  tới webcam — điều chỉnh `WaveDetector` trong
  `gesture_recognition_node.py` nếu cần.
* Các vận tốc (`LINEAR_SPEED`, `ANGULAR_SPEED` trong
  `robot_behavior_node.py`) được chọn ở mức an toàn cho khu vực mô
  phỏng vừa phải; tăng/giảm tuỳ kích thước world Gazebo đang dùng.
