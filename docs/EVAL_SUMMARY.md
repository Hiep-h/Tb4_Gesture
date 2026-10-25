# Ket qua danh gia do chinh xac nhan dien cu chi

Bo du lieu: `~/gesture_report_data/dataset_final` (thu muc ngoai repo) - do nguoi dung tu chup bang webcam qua `tools/capture_gestures.py` (anh tinh: Closed_Fist=35, Open_Palm=35, Pointing_Up=35, Victory=35, Thumb_Up=35, None=35, Wave la 3 video 3s). KHONG phai anh tai tu Internet.

Nguong min_confidence dung de danh gia: 0.55 (giong gesture_recognition_node).

### Mo hinh MediaPipe thuan (model_label/model_conf, truoc quy tac phu)

| Cu chi | So mau | Du doan dung | Accuracy | Nham nhieu nhat thanh |
|---|---|---|---|---|
| Closed_Fist | 35 | 35 | 1.00 | - |
| Open_Palm | 35 | 35 | 1.00 | - |
| Pointing_Up | 35 | 0 | 0.00 | None |
| Victory | 35 | 27 | 0.77 | None |
| Thumb_Up | 35 | 35 | 1.00 | - |
| None | 35 | 35 | 1.00 | - |
| Wave | 0 | 0 | nan | - |

### Sau lop bo sung (final_label/final_conf: Wave-override, Pointing_Up/Victory landmark fallback)

| Cu chi | So mau | Du doan dung | Accuracy | Nham nhieu nhat thanh |
|---|---|---|---|---|
| Closed_Fist | 35 | 35 | 1.00 | - |
| Open_Palm | 35 | 35 | 1.00 | - |
| Pointing_Up | 35 | 19 | 0.54 | None |
| Victory | 35 | 29 | 0.83 | None |
| Thumb_Up | 35 | 35 | 1.00 | - |
| None | 35 | 34 | 0.97 | Victory |
| Wave | 3 | 3 | 1.00 | - |

## Quy tac phu da kich hoat bao nhieu lan

| Cu chi | So anh co quy tac phu kich hoat / tong |
|---|---|
| Closed_Fist | 0/35 |
| Open_Palm | 0/35 |
| Pointing_Up | 23/35 |
| Victory | 2/35 |
| Thumb_Up | 0/35 |
| None | 1/35 |

Pointing_Up (va Victory neu co) chi dat duoc nho quy tac phu dua tren landmark (is_pointing_up_shape / is_victory_shape), KHONG phai mo hinh MediaPipe nhan ra truc tiep - xem bang "Mo hinh MediaPipe thuan" o tren.

## Do tin cay cua du doan dung (sau lop bo sung, khong tinh nhan None)

- Trung binh: 0.706
- Thap nhat: 0.553
- Cao nhat: 0.978

## Wave - danh gia rieng tren video

- So video nhan dung Wave / tong so video: 3/3

Bo anh/video do mot nguoi tu chup bang webcam trong mot dieu kien anh sang, vung ROI co dinh, khong khai quat cho moi nguoi dung.


## So sanh phu: nhan cuoi luc chup (capture_log.csv) vs. nhan dien lai tren anh da luu

- So mau doi chieu duoc: 210. Dung khop: 180. Khac nhau: 30.

- Day chi la so lieu phu de kiem tra mat na co lam sai nhan khong. So lieu chinh thuc cua bao cao (hai bang o tren) luon lay tu capture_log.csv, tuc nhan MediaPipe dua ra NGAY LUC CHUP tren khung goc trong bo nho - truoc khi dung lai thanh anh nen den. Khac biet (neu co) o day la do nhan dien lai tren anh da qua mat na (co the mat mot phan ngu canh ngoai ban tay) khong phai do pipeline chinh bi loi.

- Vi du khac nhau (nhan/luc_chup -> nhan/anh_da_luu_nhan_dien_lai):
  - Pointing_Up/Pointing_Up_01.jpg: Pointing_Up -> None
  - Pointing_Up/Pointing_Up_02.jpg: Pointing_Up -> None
  - Pointing_Up/Pointing_Up_03.jpg: Pointing_Up -> None
  - Pointing_Up/Pointing_Up_04.jpg: Pointing_Up -> None
  - Pointing_Up/Pointing_Up_05.jpg: Pointing_Up -> None
  - Pointing_Up/Pointing_Up_06.jpg: Pointing_Up -> None
  - Pointing_Up/Pointing_Up_07.jpg: Pointing_Up -> None
  - Pointing_Up/Pointing_Up_08.jpg: Pointing_Up -> None
  - Pointing_Up/Pointing_Up_09.jpg: Pointing_Up -> None
  - Pointing_Up/Pointing_Up_10.jpg: Pointing_Up -> None

## Kiem tra rieng tu (tools/check_video_privacy.py + script tuong tu cho anh tinh)

- 3 video Wave: 46-50 khung quet moi video, **3 moc nghi co mat**
  (`check_video_privacy.py` dung Haar cascade, co the bao sai). Da
  xem lai bang mat: ca 3 deu la **nhan sai tren chinh ban tay**
  (long ban tay/ngon tay bi hieu nham la mat), khong co mat that,
  phong nen chi co mot dai nho tuong/cua (khong dinh danh duoc).
- 210 anh tinh: **4 anh nghi co mat** (Pointing_Up_27, Victory_07,
  Victory_09, Victory_10), da xem lai bang mat: ca 4 deu la nhan sai
  tren ban tay/ngon tay, khong co mat that.
- Ket luan: khong anh/video nao lo mat hoac phong nen dinh danh
  duoc; `privacy_mode=hand_only` hoat dong dung (chi con ban tay
  tren nen den, mot dai nho tuong/cua o vien mat na khong du de
  nhan dang). Toan bo du lieu luu ngoai repo tai
  `~/gesture_report_data/dataset_final/`, khong dua vao git.
