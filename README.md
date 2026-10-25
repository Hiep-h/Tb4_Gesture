# Tb4_Gesture — Điều khiển TurtleBot 4 bằng cử chỉ tay

## 1. Giới thiệu

Gói ROS 2 (`tb4_gesture_control`) nhận diện cử chỉ tay qua webcam
(OpenCV + MediaPipe Gesture Recognizer) và điều khiển TurtleBot 4 mô
phỏng trong Ignition Gazebo (world `small_house`): chọn hành vi, xác
nhận bằng Thumb_Up, dừng khẩn cấp/hủy bằng Open_Palm/Closed_Fist.
Toàn bộ số liệu đo trong tài liệu này lấy từ
`docs/REHEARSAL_REPORT.md` và `docs/EVAL_SUMMARY.md`

## 2. Yêu cầu hệ thống

- Ubuntu 22.04, ROS 2 Humble, Python 3.10.
- Ignition Gazebo Fortress (cài cùng `ros-humble-turtlebot4-ignition-bringup`).
- Webcam (OpenCV `VideoCapture`, mặc định `camera_index=0`).
- Không cần GPU — mặc định chạy `LIBGL_ALWAYS_SOFTWARE=1` (software
  rendering, RTF mô phỏng ~0.13–0.20, xem mục 12).

## 3. Cài đặt

Các gói ROS 2 TurtleBot 4 + Ignition (cần `sudo`, **tự chạy bước này**,
ngoài phạm vi script của repo):

```bash
sudo apt install ros-humble-turtlebot4-ignition-bringup \
    ros-humble-turtlebot4-description ros-humble-irobot-create-nodes \
    ros-humble-irobot-create-ignition-toolbox
rosdep install --from-paths src --ignore-src -r -y
```

Thư viện Python nhận diện cử chỉ (không có trong rosdep, cài bằng pip
từ `requirements.txt` ở gốc repo, không cần `sudo` nếu dùng `--user`
hoặc venv):

```bash
pip install -r requirements.txt
```

Tải model `gesture_recognizer.task` (MediaPipe, không kèm trong repo —
`.gitignore` loại trừ `*.task`) về đúng thư mục
`tb4_gesture_control/models/`:

```bash
bash tb4_gesture_control/models/download_model.sh
```

Script tải từ
`https://storage.googleapis.com/mediapipe-models/gesture_recognizer/gesture_recognizer/float16/1/gesture_recognizer.task`
về `tb4_gesture_control/models/gesture_recognizer.task`. Nếu thiếu
model, `gesture_recognition_node` báo lỗi rõ ràng ngay khi khởi động
(đường dẫn đã tìm + gợi ý chạy script trên) thay vì traceback khó hiểu.

## 4. Build

```bash
cd ~/tb4_ws   # workspace chứa src/Tb4_Gesture
colcon build --packages-select tb4_gesture_control --symlink-install
source install/setup.bash
```

## 5. Chạy demo

```bash
bash scripts/stop_all.sh                       # dọn tiến trình cũ, tránh node trùng
ros2 launch tb4_gesture_control gesture_demo.launch.py show_preview:=true
```

Lệnh trên mở: Ignition Gazebo (world `small_house`, robot TurtleBot 4
chuẩn), `gesture_recognition_node` (webcam, cửa sổ preview "TB4
Gesture Recognition" nếu `show_preview:=true`), `robot_behavior_node`.
Ở **terminal khác**, sau khi các tiến trình trên đã lên (script tự
chờ tối đa 120s nếu chạy sớm), ghim CPU để ổn định FPS:

```bash
bash scripts/pin_cpus.sh
```

Kết thúc: `bash scripts/stop_all.sh` (leo thang SIGINT→SIGTERM→SIGKILL
theo PID của chính người dùng, không `sudo`, không `pkill -9`).

## 6. Kiến trúc

```
Webcam → OpenCV → MediaPipe Gesture Recognizer ┐
                                                ├→ LabelStabilizer → /detected_gesture (JSON)
         Wave detector (vị trí cổ tay theo t) ──┘        │
                                                          ▼
                              GestureEdgeTracker + cooldown → BehaviorFSM (IDLE→SELECTED→RUNNING)
                                                          │
                                                          ▼
                                            /cmd_vel (chuỗi vận tốc theo thời gian)
                                                          │
                                                          ▼
                                              TurtleBot 4 (Ignition Gazebo)
```

| Node | Sub | Pub | Vai trò |
|---|---|---|---|
| `gesture_recognition_node` | webcam (OpenCV, ngoài ROS) | `/detected_gesture` (`std_msgs/String`, JSON `{"gesture": str, "confidence": float, "stamp": float}`) | MediaPipe phân loại cử chỉ tĩnh + `WaveDetector` (dao động cổ tay) + `LabelStabilizer` (debounce `enter_consecutive`/`exit_none_frames` khung) → nhãn ổn định |
| `robot_behavior_node` | `/detected_gesture`, `/odom`, `/scan`, `/hazard_detection` | `/cmd_vel` (`geometry_msgs/Twist`) | `GestureEdgeTracker` (kích hoạt theo cạnh + cooldown) → `BehaviorFSM` (chọn/xác nhận/chạy) → chuỗi vận tốc theo thời gian; 3 lớp an toàn độc lập (mục 9) |

Tham số chính (đầy đủ: `config/gesture.yaml`, `config/behavior.yaml`):

| Tham số | Giá trị | Node |
|---|---|---|
| `enter_confidence` / `exit_confidence` / `enter_consecutive` | 0.55 / 0.40 / 3 | gesture |
| `exit_none_frames` | 3 | gesture |
| `privacy_mode` | `hand_only` | gesture |
| `hold_s` / `stop_hold_s` / `cooldown_s` | 0.6s / 0.2s / 1.0s | behavior |
| `selection_timeout_s` / `signal_timeout_s` / `run_timeout_s` | 30.0s / 3.0s / 40.0s | behavior |
| `wave_needs_confirm` / `wave_refractory_s` | `true` / 8.0s | behavior |

## 7. Cử chỉ → hành vi

| Cử chỉ | Hành vi | Cần Thumb_Up? |
|---|---|---|
| Wave | Chào: xoay trái 30°, phải 60°, trái 30°, lặp 2 lần | **Có** (`wave_needs_confirm: true` mặc định) |
| Pointing_Up | CHỌN tiến–lùi 0.5m×4 lượt | Có |
| Victory | CHỌN vòng tròn 2π, v=0.2 m/s ω=0.4 rad/s | Có |
| Thumb_Up | XÁC NHẬN hành vi đã chọn | — |
| Open_Palm | Dừng ngay, **giữ** lựa chọn (về `SELECTED`) | Không |
| Closed_Fist | Hủy, xóa lựa chọn, về `IDLE` | Không |

**Pointing_Up và Victory là phần mở rộng ngoài MediaPipe**: mô hình
Gesture Recognizer gốc không có nhãn cho hai cử chỉ này; node áp dụng
thêm luật hình học trên landmark bàn tay (`is_pointing_up_shape`,
`is_victory_shape` — góc gập khớp PIP) làm
fallback. Đo trên bộ ảnh riêng (`tools/eval_images.py`,
**1 người, 1 điều kiện ánh
sáng**, 35 ảnh/cử chỉ, không đại diện cho người dùng khác):

| Cử chỉ | Mô hình thô | Có luật phụ |
|---|---|---|
| Pointing_Up | 0/35 (0.00) | 19/35 (0.54) |
| Victory | 27/35 (0.77) | 29/35 (0.83) |
| None | 35/35 (1.00) | 34/35 (0.97) |

Chi tiết đầy đủ (ma trận nhầm lẫn, Closed_Fist/Open_Palm/Thumb_Up/Wave):
`docs/EVAL_SUMMARY.md`.

## 8. FSM (`behavior_fsm.py`)

`IDLE` → (Pointing_Up/Victory/Wave) → `SELECTED` → (Thumb_Up) →
`RUNNING` → hoàn thành/timeout → `IDLE`. `Open_Palm` lúc `RUNNING` đưa
về `SELECTED` (giữ lựa chọn); `Closed_Fist` ở bất kỳ trạng thái nào
(trừ `IDLE`) đưa về `IDLE`. `GestureEdgeTracker` chỉ kích hoạt khi cử
chỉ đổi nhãn/được giữ đủ `hold_s`/`stop_hold_s`, không lặp lại khi giữ
nguyên cử chỉ (kích hoạt theo cạnh).

## 9. Các lớp an toàn

| Lớp | Điều kiện | Hành động |
|---|---|---|
| Cử chỉ `Open_Palm` | Giữ ≥`stop_hold_s=0.2s` | Dừng ngay, về `SELECTED` |
| Cử chỉ `Closed_Fist` | Giữ ≥`stop_hold_s=0.2s` | Dừng, hủy, về `IDLE` |
| Mất tín hiệu | `/detected_gesture` im lặng ≥`signal_timeout_s=3.0s` | Dừng, về `IDLE`, log "MAT TIN HIEU" |
| `/scan` guard | Vật cản <0.35m trong cung ±25° trước/sau | Dừng, hủy, log `SCAN_FRONT`/`SCAN_REAR`; tự tắt nếu `/scan` toàn 0.0 (vd. `dev_fast`) |
| Bumper `/hazard_detection` | `HazardDetection.type == BUMP` | Dừng ngay, hủy, độc lập với `/scan` |
| `run_timeout_s=40s` | Một lượt hành vi chạy quá lâu (sim time) | Hủy, log "TIMEOUT" |

## 10. Quyền riêng tư

`privacy_mode: hand_only` (mặc định, `config/gesture.yaml`): mọi khung
hình xử lý/hiển thị/lưu đều đã bị che — chỉ giữ vùng bàn tay trên nền
đen, không hiện mặt/phông nền. `FaceGuard` (Haar cascade) phát hiện và
che vùng mặt trước khi vẽ overlay, kể cả khi `hand_only` không bắt hết
nền. Node **không lưu khung hình thô** nào; tùy chọn
`best_frames_dir` chỉ lưu khung **đã qua privacy mask** có độ tin cậy
cao nhất mỗi cử chỉ (tắt được). `tools/check_video_privacy.py` dùng để
quét video/ảnh demo tìm dấu hiệu lộ mặt trước khi chia sẻ.

## 11. Test

```bash
cd tb4_gesture_control
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest test/ -q
```

37 test (`test_behavior_fsm`, `test_gesture_rules`,
`test_label_stabilizer`, `test_robot_behavior_signal`), tất cả thuần
Python (không cần ROS/webcam chạy).

## 12. Giới hạn đã biết

- Độ chính xác đo được (mục 7) là điều kiện **điều khiển được** (1
  người, 1 ánh sáng, 35 lần/cử chỉ) — không phải độ tin cậy tổng quát.
- RTF mô phỏng thấp (~0.13–0.20, software rendering, không GPU rời).
- Độ chính xác nhận diện Victory dao động giữa các lần chạy
  `tools/live_check.py` — chưa xác định nguyên nhân.

## 13. Nguồn và giấy phép

- **World `small_house`**: bộ model AWS RoboMaker Residential Objects,
  Copyright Amazon.com Inc. hoặc các chi nhánh, giấy phép **MIT-0**
  (toàn văn: `tb4_gesture_control/worlds/LICENSE-AWS-small-house`).
- **`turtlebot4_spawn_no_dock.launch.py`**: bản sửa từ
  `turtlebot4_spawn.launch.py` của gói `turtlebot4_ignition_bringup`
  (bỏ include dock + Node spawn dock, giữ nguyên phần còn lại) — gói
  gốc ghi giấy phép **Apache 2.0** trong `package.xml` (đã đọc trực
  tiếp, không đoán).
- **Model MediaPipe** (`gesture_recognizer.task`): tải trực tiếp từ
  Google (`storage.googleapis.com/mediapipe-models/...`) bằng
  `tb4_gesture_control/models/download_model.sh`, không kèm trong
  repo (xem mục 3).
- **Gói `tb4_gesture_control`** (mã trong repo này): giấy phép
  **Apache-2.0** (`tb4_gesture_control/package.xml`).
