# Báo cáo Bài tập 6 — Giao tiếp phi ngôn ngữ và điều khiển TurtleBot 4 bằng cử chỉ tay

> Khung báo cáo này export sang PDF để nộp (ví dụ mở trong trình soạn
> thảo Markdown hỗ trợ "Export to PDF", hoặc dùng `pandoc REPORT.md -o
> REPORT.pdf`). Điền các mục còn để trống (`[...]`) trước khi nộp.

**Sinh viên:** [Họ tên] — [MSSV]
**Môn học / Bài tập:** Bài tập 6 — Giao tiếp phi ngôn ngữ và điều khiển TurtleBot 4 bằng cử chỉ tay
**Ngày:** [...]

## 1. Sơ đồ kiến trúc hệ thống

(Chèn ảnh chụp sơ đồ kiến trúc — có thể render từ mermaid trong
`README.md` của repo: flowchart Webcam → `gesture_recognition_node` →
`/detected_gesture` → `robot_behavior_node` → `/cmd_vel` → TurtleBot 4.)

[... chèn hình ...]

## 2. Các ROS 2 Node, Topic và luồng xử lý

### 2.1 `gesture_recognition_node`

* **Input:** khung hình webcam (OpenCV `VideoCapture`).
* **Xử lý:** MediaPipe Gesture Recognizer phân loại cử chỉ theo khung
  hình (`Closed_Fist`, `Open_Palm`, `Pointing_Up`, `Victory`,
  `Thumb_Up`, ...); một bộ phát hiện "Wave" chạy thêm trên vị trí x của
  cổ tay để nhận ra cử chỉ vẫy tay (không có trong nhãn gốc của
  MediaPipe); kết quả được lọc nhiễu bằng debounce theo đa số phiếu
  trên N khung hình gần nhất.
* **Output:** topic `/detected_gesture` (`std_msgs/msg/String`, payload
  JSON gồm `gesture`, `confidence`, `stamp`); cửa sổ preview OpenCV
  hiển thị nhãn thô + nhãn ổn định.

### 2.2 `robot_behavior_node`

* **Input:** topic `/detected_gesture`.
* **Xử lý:** `GestureEdgeTracker` biến luồng cử chỉ liên tục thành các
  sự kiện kích hoạt một-lần-mỗi-lượt-giữ (chống nhiễu); một state
  machine (`IDLE` → `SELECTED` → `RUNNING`) chọn, xác nhận, hoặc hủy
  hành vi; một watchdog theo thời gian giám sát mất tín hiệu.
* **Output:** topic `/cmd_vel` (`geometry_msgs/msg/Twist`), phát ở tần
  số cố định từ một chuỗi đoạn vận tốc (segment) theo thời gian cho mỗi
  hành vi.

### 2.3 Luồng xử lý tổng quát

```
Webcam → OpenCV → MediaPipe Gesture Recognizer → Wave detector → Debounce
   → /detected_gesture (JSON) → Edge tracker + cooldown → State machine
   → chuỗi vận tốc theo thời gian → /cmd_vel → TurtleBot 4 (Gazebo)
```

## 3. Bảng ánh xạ cử chỉ tay ↔ hành vi robot

| Cử chỉ | Nhãn nhận diện | Hành vi | Cần xác nhận? |
|---|---|---|---|
| Vẫy tay (Wave) | `Wave` (suy luận) | Xoay trái–phải chào lại | Không |
| Giơ 1 ngón (Pointing Up) | `Pointing_Up` | Chọn: tiến–lùi 4 lần | Có (Thumb_Up) |
| Giơ 2 ngón (Victory) | `Victory` | Chọn: di chuyển quỹ đạo tròn | Có (Thumb_Up) |
| Giơ ngón cái (Thumbs Up) | `Thumb_Up` | Xác nhận & thực hiện hành vi đã chọn | — |
| Xòe bàn tay (Open Palm) | `Open_Palm` | Dừng ngay lập tức | Không |
| Nắm tay (Closed Fist) | `Closed_Fist` | Hủy hành vi hiện tại, về IDLE | Không |

## 4. Hình ảnh minh họa kết quả thực nghiệm

[... chèn ảnh chụp màn hình: cửa sổ webcam nhận diện từng cử chỉ, và
Gazebo với TurtleBot 4 đang thực hiện hành vi tương ứng ...]

## 5. Link video demo và GitHub repository

* **Video demo (Google Drive, công khai):** [...]
* **GitHub repository (public):** [...]
