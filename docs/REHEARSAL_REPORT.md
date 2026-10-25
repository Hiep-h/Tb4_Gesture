# Tong duyet toan tuyen cuoi cung - chuan bi quay (2026-10-25)

Log chinh: rehearsal_20261025_124611.log (webcam thuc, chi nguoi dung
lam cu chi, khong fake_gesture). Cau hinh A + `scripts/pin_cpus.sh`
(taskset -a, gesture+behavior -> loi 0-5, ign gazebo -> loi 6-11),
`signal_timeout_s=3.0s`, `selection_timeout_s=30.0s`. Tom tat tu dong:
~/gesture_report_data/rehearsal_summary.md.

## 1. scripts/pin_cpus.sh

Da viet, kiem thu: cho toi 120s cac tien trinh gesture_recognition_node,
robot_behavior_node, ign gazebo (server+gui) xuat hien, ghim bang
`taskset -a -cp` (moi luong) - gesture+behavior vao loi 0-5, gazebo
vao loi 6-11, in PID/affinity xac nhan. Da chay 2 lan lien tiep (idempotent),
ket qua giong nhau ca hai lan.

## 2. So sanh taskset tay (khong -a) vs pin_cpus.sh (-a, moi luong)

Do 3 phut chay `circle`, may nguoi truoc moi lan do:

| Cach | Nhiet do dau->cuoi | FPS min | FPS p5 | FPS median | RTF |
|---|---|---|---|---|---|
| taskset tay (khong -a, luong chinh) | khong ghi | 7.7 | 18.0 | 18.5 | khong do cung luc |
| pin_cpus.sh (-a, moi luong) | 45C -> 72-75C | 9.9 | 11.0 | 19.8 | 0.1286 / 0.1524 |

Co khac biet nhung khong theo mot huong ro ret: `-a` cho FPS min va
median cao hon (gan sat FPS khong tranh chap ~19.8-20) nhung FPS p5
thap hon (11.0 so 18.0) - co the do khac biet tai nen giua hai lan do
(khong do dong thoi) hon la do rieng co `-a`. Ca hai deu vuot xa
baseline khong ghim (p5=6.6, xem bao cao truoc). RTF giam khi ghim
CPU (0.13-0.15 so 0.17-0.20 khong ghim) vi Gazebo chi con 6 loi.

## 3. Y nghia signal_timeout_s=3.0s

Robot thuc 0.2 m/s: 3.0s = toi da 0.6m truoc khi watchdog dung (gioi
han tren, bumper/scan van hoat dong doc lap). Trong sim, quang duong
phu thuoc thoi gian mo phong (RTF thap ~0.13-0.20), nen 3.0s thuc chi
~0.4-0.6s mo phong, tuc toi da ~0.2 x 0.15 x 3.0 = 0.09m (~9cm) - nho
hon nhieu so 0.6m o robot thuc. Da ghi vao README.

## 4. Tong duyet toan tuyen (chi nguoi dung lam cu chi, webcam thuc)

### 4.1 [DA BI THAY THE BOI MUC 7.2] Tung cu chi rieng le (>=3 lan/cu
chi), do bang cach doc truc tiep /detected_gesture trong 12s moi lan
thu

**Luu y (2026-10-25)**: so 17/18 (94%) o muc nay duoc do TRUOC KHI
sua loi `LabelStabilizer` (muc 4.2/7.1) va it nhat 1 lan (Open_Palm
#1) bi nhan nham do chinh loi do gay ra, khong phai do mo hinh/luat
phu. Xem ket qua do lai sau khi sua o **muc 7.2**; giu nguyen bang
duoi day chi de doi chieu lich su, khong dung lam so lieu cuoi cung.

| Cu chi | So lan thu | So lan dung | Nhan nham thanh | Ghi chu |
|---|---|---|---|---|
| Wave | 3 | 3 | - | Can vay RONG, CHAM (>=6% chieu rong khung); vay nho/nhanh bi bo qua (da biet tu truoc) |
| Pointing_Up | 3 | 3 | - | |
| Victory | 3 | 2 | Pointing_Up (1 lan) | Lan 1 hai ngon chua tach du xa, bi hieu la Pointing_Up |
| Thumb_Up | 3 | 3 | - | |
| Open_Palm | 3 | 3 | - | Lan 1 ket qua tron voi Thumb_Up con lai tu truoc (do trong 12s ngay sau mot cu chi khac) |
| Closed_Fist | 3 | 3 | - | |

**Tong: 17/18 (94%) dung ngay lan dau khi giu cu chi on dinh ~2s.**
Khong co lan nao Pointing_Up bi nhan nham thanh Wave hay nguoc lai
trong phien nay; truong hop nham duy nhat la Victory -> Pointing_Up.

### 4.2 [DA BI THAY THE BOI MUC 7.1 - LOI DA SUA] Phat hien quan
trong: nhan on dinh KHONG tu ve None khi tay roi khoi khung

**Luu y (2026-10-25)**: loi mo ta duoi day DA DUOC SUA, xem muc 7.1
(them `_none_streak` + tham so `exit_none_frames`). Giu nguyen doan
mo ta goc de lam ho so loi, khong con la trang thai hien tai cua code.

Trong luc test kich ban "chua xac nhan", phat hien `LabelStabilizer.update()`
(gesture_recognition_node.py) chi dat lai `self._state` ve None qua
nhanh "exit_confidence" khi **nhan moi == nhan hien tai** nhung do tin
cay thap; neu nhan moi la **None** (tay roi khung, khac nhan hien tai),
code di vao nhanh else va **khong dong gi den self._state** - nhan on
dinh tren `/detected_gesture` giu nguyen cu chi cuoi cung **vo han**
cho den khi co mot cu chi KHAC (khong phai None) du 3 khung lien tiep
>=0.55 do tin cay. Da xac nhan thuc nghiem: nhan "Pointing_Up" duoc
publish lien tuc hang tram giay du nguoi dung dua tay ra khoi khung
nhieu lan. Day la ly do cac lan thu "de yen tay 20s" ban dau khong tao
duoc "selected" moi - phai lam MOT cu chi khac truoc de "giai phong".
Khong sua trong lan nay (ngoai pham vi yeu cau), ghi lai de xu ly sau.

### 4.3 Chay tron ven forward_backward, circle, wave

| Hanh vi | Ket qua | Thoi gian thuc | FPS thap nhat | So lan watchdog |
|---|---|---|---|---|
| forward_backward | **completed** | 127.1s | 10.5 | 0 |
| circle | **completed** | 91.2s | 10.0 | 0 |
| wave | **completed** | 51.5s | 9.2 | 0 |

Ca ba hanh vi hoan thanh tron ven, khong watchdog gia nao kich hoat.

### 4.4 Kich ban mat tin hieu (chu dich, SIGINT PID)

SIGINT gui luc 1792908747.379 (sau khi forward_backward dang "moving").
`robot_behavior_node` log "No /detected_gesture for 3.0s, stopping" +
"FSM event=signal_lost reason=MAT TIN HIEU" luc 1792908750.545 -
**do tre 3.166s**, dung dung thiet ke (signal_timeout_s=3.0s).

### 4.5 Kich ban "chua xac nhan thi khong chay"

Pointing_Up duoc chon (`selected` luc 1792908650.399) nhung khong co
Thumb_Up theo sau; `selection_timeout` kich hoat luc 1792908680.479
(**30.08s**, dung nguong 30.0s moi). `/cmd_vel` do lien tuc trong
suot 45s: **luon bang 0**, xac nhan robot KHONG chay khi chua xac nhan.

### 4.6 Do tre cu chi -> FSM event (tat ca lan chap nhan trong phien)

| Loai cu chi | So mau | Do tre trung binh | Thap nhat | Cao nhat |
|---|---|---|---|---|
| Chon hanh vi (Pointing_Up/Victory/Wave, hold_s=0.6s) | 10 | 0.656s | 0.603s | 0.703s |
| Dung ngay (Open_Palm/Closed_Fist, stop_hold_s=0.2s) | 4 | 0.235s | 0.224s | 0.243s |

Do tre do tu luc nhan on dinh xuat hien (`Gesture ->` log) den luc
`robot_behavior_node` ghi FSM event tuong ung (selected/started/
emergency_stop/cancel_noop). Khop voi thiet ke (`hold_s=0.6s`,
`stop_hold_s=0.2s`) + do tre xu ly/log nho.

## 5. Tom tat tu dong (gesture_log_summary.py)

- 17 lenh duoc chap nhan (selected/started/cancelled/cancel_noop/
  emergency_stop) trong toan bo log.
- Ly do bi bo qua: not_released 22 lan, nothing_selected 3 lan, busy
  2 lan - deu dung thiet ke (edge-triggered, tu choi khi dang chay).
- An toan: 3 lan Open_Palm emergency_stop duoc chap nhan, 1 lan MAT
  TIN HIEU (chu dich, kich ban 4.4), 0 lan TIMEOUT mot luot hanh vi.
- Do tre Thumb_Up (started) -> moving: trung binh 0.081s (4 mau,
  0.017-0.112s) - nhanh, khong dang ke so voi do tre chon/xac nhan.

## 6. [DA BI THAY THE BOI MUC 7 - XEM MUC 7.2/7.3 DE CO SO LIEU DUNG]
Ket luan truoc khi quay

**Luu y (2026-10-25)**: cac gach dau dong duoi day dua tren so lieu
muc 4.1/4.2 (truoc khi sua loi `LabelStabilizer`). So 17/18 va "hitch
con ton tai" khong con dung - xem **muc 7** cho ket luan cap nhat.

- Nhan dien 6 cu chi: 17/18 (94%) dung ngay lan dau, 1 lan nham Victory
  thanh Pointing_Up (do hai ngon chua tach du). Can nhac nguoi quay:
  **tach ro ngon tro-giua khi lam Victory**, **vay RONG CHAM khi lam
  Wave**.
- Ca 3 hanh vi dai (forward_backward, circle, wave) hoan thanh tron
  ven, 0 watchdog gia trong phien nay (voi `pin_cpus.sh` + nguong
  3.0s moi).
- Hai lop an toan (mat tin hieu, chua xac nhan) hoat dong dung thiet
  ke, do duoc so cu the.
- **Hitch con ton tai (muc 4.2)**: nhan on dinh khong tu het han khi
  tay roi khung - khong anh huong toi cac kich ban quay thuc te (luon
  co cu chi moi tiep theo) nhung can luu y khi dung lau giua cac lan
  quay.

## 7. Cap nhat sau khi sua LabelStabilizer (2026-10-25, ban bo sung)

### 7.1 Da sua loi muc 4.2

`LabelStabilizer.update()` (`gesture_recognition_node.py`) nay theo
doi so khung lien tiep co nhan tho `None` (`_none_streak`). Khi nhan
hien tai khac `None` va `_none_streak >= exit_none_frames` (tham so
moi, mac dinh `3`, khai bao trong `gesture.yaml` va
`declare_parameter` cua node), trang thai duoc dat lai ve `None` ngay
ca khi khong co cu chi KHAC nao xuat hien sau do. Nhan nhap nhay ngan
(1-2 khung `None`) khong lam reset vi chua du `exit_none_frames`
khung lien tiep. Cu chi lap lai sau khi tha tay duoc nhan lai binh
thuong vi bo dem candidate/trang thai da ve `None` truoc do.

Da them `tb4_gesture_control/test/test_label_stabilizer.py` (3 test
don vi, dung `LabelStabilizer` truc tiep, khong can ROS/webcam):
`test_none_for_exit_none_frames_resets_to_none`,
`test_short_none_blip_does_not_reset`,
`test_same_gesture_recognized_again_after_hand_released`. Chay
`pytest` toan bo package: **33 passed** (30 test cu + 3 test moi),
khong test nao fail.

### 7.2 Do lai do chinh xac tung cu chi (sau khi sua, webcam thuc)

**Dieu kien do la DIEU KHIEN DUOC, khong phai do tin cay tong quat
cua mo hinh**: 1 nguoi dung duy nhat (nguoi quen quy trinh), anh sang
trong phong on dinh, khoang cach/goc tay da luyen tap truoc, chi 35
lan thu tong (5 lan x 6 cu chi, Victory 10 lan) - co mau nho, khong
dai dien cho nguoi dung moi, anh sang khac, nen phuc tap, hay tay
lech goc. Ket qua **gom ca luat phu rung (rule-based fallback)**
`pointing_up_fallback`/`victory_fallback` trong `GestureClassifier`
(muc `classify_raw`) - tuc nhan cuoi la nhan SAU KHI co luat phu de
sua hinh dang tay, khong phai do chinh xac thuan cua mo hinh
MediaPipe goc. Xem **muc 3 cua eval_summary_final.md** (dataset anh
rieng, 2026-10-25) cho so sanh rieng mo hinh tho vs co luat phu.

Quy trinh: moi lan thu bat dau bang doc truc tiep `/detected_gesture`
(subscriber rieng co ghi wall-clock), cho nhan ve `None` on dinh
**>=1s** roi moi yeu cau nguoi dung lam cu chi, ghi nhan nhan on dinh
dau tien xuat hien sau do. 5 lan/cu chi, Victory 10 lan.

| Cu chi yeu cau | So lan thu | Nhan nhan duoc (tat ca lan) | So lan dung | Ti le dung |
|---|---|---|---|---|
| Wave | 5 | Wave x5 | 5 | 100% |
| Pointing_Up | 5 | Pointing_Up x5 | 5 | 100% |
| Victory | 10 | Victory x10 | 10 | 100% |
| Thumb_Up | 5 | Thumb_Up x5 | 5 | 100% |
| Open_Palm | 5 | Open_Palm x5 | 5 | 100% |
| Closed_Fist | 5 | Closed_Fist x5 | 5 | 100% |

**Ma tran nham lan**: khong co o ngoai duong cheo - moi cu chi yeu
cau deu duoc nhan dung ngay lan dau trong toan bo 35/35 lan thu
(100%), khong lan nao nhan nham sang cu chi khac, khong lan nao
khong nhan duoc (None/timeout).

**So voi so cu 17/18 (94%, muc 4.1)**: so cu bi anh huong boi dung
loi nay o it nhat 1 diem: ghi chu lan thu Open_Palm #1 "ket qua tron
voi Thumb_Up con lai tu truoc (do trong 12s ngay sau mot cu chi
khac)" chinh la hau qua truc tiep cua loi muc 4.2 (nhan on dinh cu
Thumb_Up khong tu het han khi tay roi khung, con sot lai khi do
Open_Palm). Lan nham Victory->Pointing_Up (muc 4.1) la do hinh dang
tay (hai ngon chua tach du xa), khong lien quan toi loi stabilizer,
nen van co the lap lai neu nguoi dung lam Victory khong chuan - lan
do nay (10/10 Victory dung) khong du de loai tru hoan toan nhung
khong ghi nhan lai trong phien nay.

### 7.3 Chay lai kich ban "chua xac nhan thi khong chay" (KHONG dung
cu chi khac de giai phong)

Khac muc 4.5 (co the da lam cu chi khac truoc do), lan nay: lam
Pointing_Up de chon hanh vi, **chi ha tay ra khoi khung va giu yen**
(khong lam them cu chi nao), khong dung "meo giai phong bang cu chi
khac".

- `selected behavior=forward_backward` luc `2026-10-25T17:27:11.759`
  (log `robot_behavior_node`).
- Nhan on dinh tren `/detected_gesture` ve `None` ngay sau khi ha
  tay (xac nhan truc tiep tren subscriber rieng, khong con nhan
  `Pointing_Up` sot lai - dung voi hanh vi da sua o muc 7.1).
- `/cmd_vel` doc lien tuc tu luc `selected` den sau khi
  `selection_timeout`: **197 mau, 0 mau khac 0** - robot khong chay
  dù chưa xác nhận.
- `selection_timeout behavior=forward_backward` kich hoat luc
  `2026-10-25T17:27:41.888`, tuc **30.13s** sau `selected` - dung
  thiet ke `selection_timeout_s=30.0s` (+ sai so chu ky dieu khien
  20Hz).

Ket luan: lop an toan "chua xac nhan thi khong chay" hoat dong dung
thiet ke ca khi khong dung meo giai phong bang cu chi khac - nguoi
dung chi can ha tay ra khoi khung.

## 8. Chuoi dau-cuoi voi LabelStabilizer moi (2026-10-25, chi nguoi
dung lam cu chi, khong fake_gesture, co `pin_cpus.sh`)

Ba chuoi lien tiep trong cung 1 phien (sim + gesture + behavior,
`exit_none_frames=3`):

| Chuoi | Cac buoc | Ket qua |
|---|---|---|
| A | Wave -> Thumb_Up | `selected behavior=wave` (17:38:31.385) -> `started` (17:38:42.031) -> **`completed`** (17:39:38.309), chay 56.28s |
| B | Pointing_Up -> Thumb_Up -> Open_Palm (giua luc chay) -> Closed_Fist | `selected forward_backward` (17:39:52.913) -> `started` (17:40:05.914) -> **`emergency_stop behavior=forward_backward`** (17:40:32.803, dung giua chay sau 26.89s) -> **`cancelled state=SELECTED behavior=wave`** (17:40:40.268, xem ghi chu duoi) |
| C | Victory -> Thumb_Up | `selected behavior=circle` (17:41:52.498) -> `started` (17:41:58.866) -> **`completed`** (17:43:36.491), chay 97.62s |

**Ghi chu chuoi B**: giua luc Open_Palm dang giu (sau khi da kich
hoat `emergency_stop`) va truoc khi lam `Closed_Fist`, `WaveDetector`
bat duoc dao dong tay trong luc chuyen dong tac (ha Open_Palm) va tra
ve nhan `Wave` ~1.6s (17:40:38.232-17:40:39.856, do tin cay 0.5-0.85),
kich hoat `selected behavior=wave` (de "ghi de" `pending_behavior` tu
`forward_backward` sang `wave` vi FSM dang o `STATE_SELECTED`, khong
`busy`). Vi vay lenh `Closed_Fist` ngay sau do huy nham `wave` thay
vi `forward_backward` dinh huy. **Day KHONG phai loi `exit_none_frames`**
- la tuong tac giua `WaveDetector` (phat hien dao dong tay) va FSM
chap nhan chon lai hanh vi o trang thai `SELECTED`; ngoai pham vi sua
lan nay, ghi lai de luu y khi quay video (tranh chuyen dong tay lon
giua Open_Palm va Closed_Fist).

### 8.1 So lan FSM bo lenh vi `not_enough_hold` do reset boi
`exit_none_frames`

Dem toan bo log phien (ca luc khoi dong + 3 chuoi A/B/C):
**1 lan** `FSM event=ignored gesture=Victory reason=not_enough_hold
held_s=0.394` luc 17:37:32.446 - xay ra **truoc khi logger
`/detected_gesture` rieng (wall-clock) duoc khoi dong lai**, nen
**khong co du lieu nhan tho de xac dinh** co phai do `exit_none_frames`
reset hay do nguoi dung tu tha tay som. Lan nay nam ngoai 3 chuoi
A/B/C chinh thuc (xay ra luc khoi dong he thong).

### 8.2 So lan "mat cu chi khi giu" (nhan ve `None` roi quay lai
CUNG cu chi, trong toan bo log `/detected_gesture` cua phien)

Phan tich tu dong (quet toan bo file log, tim doan `None` nam giua
hai doan cung 1 nhan): **2 lan**, ca hai deu co do dai **24 va 29
khung lien tiep** (~2.7-3.0s) - **lon hon nhieu so voi nguong
`exit_none_frames=3`** (~0.2-0.3s o FPS 10-12), tuc la cac lan nay la
**tay thuc su roi khung/mat hoan toan** roi dua lai, khong phai hien
tuong nhap nhay ngan bi reset oan boi tham so moi. Khong tim thay
doan `None` nao co do dai gan nguong 3 khung xen giua cung 1 nhan
trong toan phien.

**Ket luan**: khong co bang chung FSM bo lenh do `exit_none_frames`
reset nham mot cu chi dang duoc giu on dinh. Vi vay **khong dieu
chinh `exit_none_frames`** trong lan nay - gia tri mac dinh `3` van
phu hop voi du lieu do duoc (p95 so khung `None` xen giua cung 1
nhan = 29, nhung ca hai truong hop do deu la mat tay thuc, khong
phai flicker can tranh).

### 8.3 FPS va watchdog trong toan phien (3 chuoi + khoi dong,
`pin_cpus.sh` dang ghim CPU)

- FPS thap nhat ghi nhan: **8.6** (thap hon phien truoc 9.2-10.5, do
  2 lan khoi dong lai toan bo stack + preview + ghi log song song).
- FPS cao nhat: 14.6 (ngay sau khoi dong, truoc khi Gazebo tai het
  mo hinh).
- So lan watchdog gia (`signal_lost`): **0**.
- forward_backward hoan thanh mot phan (dung giua chung boi
  `emergency_stop` theo dung kich ban yeu cau, khong phai loi).

## 9. Sua loi Wave ghi de lua chon (phat hien o muc 8) - them
`wave_refractory_s` (2026-10-25)

### 9.1 Nguyen nhan va gia tri tham so

O muc 8, `WaveDetector` bat duoc dao dong tay luc chuyen tu
`Open_Palm` sang `Closed_Fist` (sau `emergency_stop`) va tra ve nhan
`Wave` trong ~1.6s, khien FSM goi `select(BEHAVIOR_WAVE, ...)` va ghi
de `pending_behavior` tu `forward_backward` sang `wave` - `Closed_Fist`
ngay sau do huy nham `wave`. Do thuc tu log: `emergency_stop` luc
`1792924832.804343576`, FSM chap nhan `selected behavior=wave` (nhan
Wave sai) luc `1792924838.876192807` - **khoang cach do duoc:
6.072s**. Them bien an toan (~2s) -> **`wave_refractory_s = 8.0`**
(tham so moi trong `behavior.yaml`, co the chinh).

### 9.2 Co che sua

`BehaviorFSM` ghi lai thoi diem `now` moi lan FSM **chap nhan**
(trigger qua `GestureEdgeTracker`) cu chi `Open_Palm` hoac
`Closed_Fist` (`_stop_gesture_accepted_at`). Trong nhanh xu ly `Wave`,
neu `now - _stop_gesture_accepted_at < wave_refractory_s` thi bo qua
cu chi Wave va ghi log `FSM event=ignored gesture=Wave
reason=wave_refractory`, **khong** goi `select`/`start_behavior`.
Logic nay **chi** nam trong nhanh `WAVE` cua `_handle_action` - khong
dung gi den nhanh `POINTING_UP`/`VICTORY`/`THUMB_UP`, va khong anh
huong luc chon Wave binh thuong (khi khong co Open_Palm/Closed_Fist
gan day).

### 9.3 Test don vi (4 ca, trong `test_behavior_fsm.py`)

Chay `pytest` toan bo package: **37 passed** (33 cu + 4 moi):

- `test_wave_ignored_right_after_open_palm_refractory`: Wave ngay
  sau Open_Palm (dang RUNNING forward_backward -> emergency_stop) bi
  bo qua, `pending_behavior` van la `forward_backward`.
- `test_wave_ignored_right_after_closed_fist_refractory`: Wave ngay
  sau Closed_Fist (huy ve IDLE) bi bo qua, state van IDLE.
- `test_wave_selectable_after_refractory_elapses`: Wave sau khi het
  `wave_refractory_s` (8.5s sau Open_Palm) van chon duoc binh thuong
  (`state=SELECTED`, `pending_behavior=wave`).
- `test_pointing_up_and_victory_not_affected_by_wave_refractory`:
  Pointing_Up va Victory ngay sau Open_Palm (chi 0.5s sau) van chon
  duoc binh thuong - xac nhan refractory khong anh huong hai cu chi
  nay.

### 9.4 Chay lai chuoi B 3 lan, webcam thuc, HA TAY TU NHIEN (khong
ne tranh)

Pointing_Up -> Thumb_Up -> Open_Palm (giua luc forward_backward dang
chay) -> Closed_Fist, lap 3 lan lien tiep, cung 1 phien (sim + gesture
+ behavior, `wave_refractory_s=8.0` xac nhan qua `ros2 param get`):

| Lan | selected | started | emergency_stop | Ket qua `Closed_Fist` | Dung? |
|---|---|---|---|---|---|
| 1 | 18:04:53.839 | 18:05:03.538 | 18:05:14.361 | `cancelled behavior=forward_backward` (18:05:23.953) | **Dung** |
| 2 | 18:06:36.423 | 18:06:47.641 | 18:06:58.409 | `cancelled behavior=forward_backward` (18:07:06.845) | **Dung** |
| 3 | 18:07:35.409 | 18:07:47.188 | 18:07:57.938 | `cancelled behavior=forward_backward` (18:08:05.392) | **Dung** |

**Ket qua: 3/3 (100%) dung** - `Closed_Fist` huy dung
`forward_backward` ca ba lan, khong lan nao bi doi nham sang `wave`.

**So lan `reason=wave_refractory`: 0/3**. Kiem tra log tho
`/detected_gesture` ca ba lan: khong lan nao nguoi dung vo tinh tao
ra dao dong tay du de `WaveDetector` nhan ra `Wave` (khac voi phien
muc 8, noi dieu nay xay ra tu nhien 1 lan trong nhieu lan thu). Vi
vay lan nay **khong co dip thuc te de kich hoat nhanh
`wave_refractory`** nhung co che da duoc xac nhan dung qua test don
vi muc 9.3 (mo phong chinh xac tinh huong da xay ra o muc 8) va
khong co su co "Closed_Fist huy nham wave" nao xay ra lai.

### 9.5 So lan `not_enough_hold` trong 3 lan chay nay

**1 lan**, trong lan 1:
`FSM event=ignored gesture=Thumb_Up reason=not_enough_hold held_s=0.564`
luc `18:05:21.873`. Log tho `/detected_gesture` quanh thoi diem nay:

```
1792926320.903  None       0.71
1792926321.045  None       0.71
1792926321.182  None       0.71
1792926321.330  Thumb_Up   0.695
1792926321.465  Thumb_Up   0.699
1792926321.613  Thumb_Up   0.699
1792926321.746  Thumb_Up   0.699
1792926321.876  None       0.0
1792926322.005  None       0.706
```

Nhan `Thumb_Up` chi xuat hien **0.416s** (321.330 -> 321.746) roi ve
`None` ngay - ngan hon `hold_s=0.6s` can thiet, tuc nguoi dung tha
tay Thumb_Up som (truot tay tu nhien), **khong lien quan den
`exit_none_frames` hay `wave_refractory`** (khong co doan `None` ngan
xen giua cung 1 nhan o day, nhan chi don gian chua giu du lau).
