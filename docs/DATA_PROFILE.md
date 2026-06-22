# Data Profile

Generated: 2026-06-20T12:00:47

## Repository Snapshot

The repository started as a data-only workspace with three Excel files at the root. No source code was present before this implementation.

## Workbooks and Sheets

### EntryTransaction_20260203_164943.xlsx / Report

- Table name: `entrytransaction_20260203_164943_report_0ec1e3`
- Source path: `EntryTransaction_20260203_164943.xlsx`
- Header row: 35
- Data start row: 36
- Rows imported: 1,294
- Columns imported: 18
- Issues: Dropped all-null columns: col_8

| Original | Normalized | Type | Role | Null ratio | Unique | Min | Max | Samples |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| No. | no | int64 |  | 0.0 | 1294 | 1 | 1294 | 1, 2, 3 |
| Cổng | cong | object |  | 0.0 | 2 |  |  | Cổng 1, Cổng 2 |
| Loại truy cập | loai_truy_cap | object |  | 0.0 | 2 |  |  | Ra, Vào |
| Mã đăng ký | ma_dang_ky | object |  | 0.2141 | 455 |  |  | xCpTVH, Fjfe9B, 8yt08G |
| Thời gian thực thi | thoi_gian_thuc_thi | datetime64[ns] |  | 0.0 | 1294 | 2026-02-03T00:00:09.379000 | 2026-02-03T16:48:37.841000 | 2026-02-03 16:48:37.841, 2026-02-03 16:48:34.368, 2026-02-03 16:48:28.964 |
| Vai trò truy cập | vai_tro_truy_cap | object |  | 0.0495 | 5 |  |  | Nhân viên, Tài xế, Khách |
| Họ và tên | ho_va_ten | object |  | 0.1128 | 517 |  |  | Nguyễn Lê Xuân Giang, Lư trí cao, Nguyễn Viết Hải |
| Số CMND/CCCD | so_cmnd_cccd | object |  | 0.1468 | 488 |  |  | 056091006620, 0460740000541, 0937660113 |
| Công ty chủ quản | cong_ty_chu_quan | object |  | 0.4042 | 110 |  |  | Fpt, APC, LICONIN |
| Công ty vận tải | cong_ty_van_tai | object |  | 0.813 | 25 |  |  | Bình Vinh, Thành Mỹ, Hòa Phát |
| Biển số xe (OCR) | bien_so_xe_ocr | object |  | 0.0896 | 476 |  |  | 59D160530, 79C16663, 59P308944 |
| Biển số xe đã chỉnh | bien_so_xe_da_chinh | object |  | 0.391 | 15 |  |  | , 51L46822, 50H19817 |
| Loại xe | loai_xe | object |  | 0.0 | 4 |  |  | Xe gắn máy, Xe tải, Xe ôtô |
| Giá trị cân | gia_tri_can | float64 |  | 0.7604 | 220 | 0.0 | 51720.0 | 20050.0, 50670.0, 50870.0 |
|  | _source_file | object |  | 0.0 | 1 |  |  | EntryTransaction_20260203_164943.xlsx |
|  | _source_sheet | object |  | 0.0 | 1 |  |  | Report |
|  | _source_row | int64 |  | 0.0 | 1294 | 36 | 1329 | 36, 37, 38 |
|  | _import_id | object |  | 0.0 | 1 |  |  | d48fe88a-478b-44e1-b4c1-1956ce38ac29 |


- Candidate primary keys: no, thoi_gian_thuc_thi, _source_row
- Datetime columns: thoi_gian_thuc_thi
- Duration columns: None detected

### Loss_Assignment_20260203_100840.xlsx / Report

- Table name: `loss_assignment_20260203_100840_report_2a7588`
- Source path: `Loss_Assignment_20260203_100840.xlsx`
- Header row: 35
- Data start row: 36
- Rows imported: 36,309
- Columns imported: 13
- Issues: Dropped all-null columns: note, col_8; Added parsed duration seconds column: thoi_luong_seconds

| Original | Normalized | Type | Role | Null ratio | Unique | Min | Max | Samples |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| No. | no | int64 |  | 0.0 | 36309 | 1 | 36309 | 1, 2, 3 |
| Máy | may | object | machine | 0.0 | 11 |  |  | Flexo 2, Máy 3A, Máy 29 |
| Thời gian bắt đầu | thoi_gian_bat_dau | datetime64[ns] | start_time | 0.0 | 36292 | 2025-11-03T09:35:56.342000 | 2026-02-03T10:07:17.606000 | 2026-02-03 10:07:17.606, 2026-02-03 10:07:16.625, 2026-02-03 10:04:54.064 |
| Thời gian kết thúc | thoi_gian_ket_thuc | datetime64[ns] | end_time | 0.0 | 36295 | 2025-11-03T10:10:49.918000 | 2026-02-03T10:08:36.166000 | 2026-02-03 10:08:36.166, 2026-02-03 10:08:35.645, 2026-02-03 10:06:36.126 |
| Thời lượng | thoi_luong | object | duration | 0.0 | 3191 |  |  | 00:01:18, 00:01:19, 00:01:42 |
| Tên tổn thất | ten_ton_that | object | loss_name | 0.0023 | 30 |  |  | IN MÀU BỊ LỖI, VẬN HÀNH KHÔNG KHAI BÁO, SETUP MÁY |
| Nhóm tổn thất | nhom_ton_that | object | loss_group | 0.0023 | 2 |  |  | Sản xuất, Bảo trì |
| Loại tổn thất | loai_ton_that | object | loss_type | 0.0023 | 2 |  |  | Dừng vận hành, Dừng do máy |
|  | _source_file | object |  | 0.0 | 1 |  |  | Loss_Assignment_20260203_100840.xlsx |
|  | _source_sheet | object |  | 0.0 | 1 |  |  | Report |
|  | _source_row | int64 |  | 0.0 | 36309 | 36 | 36344 | 36, 37, 38 |
|  | _import_id | object |  | 0.0 | 1 |  |  | 751b7a55-11ca-4748-91cc-0e4703df0cf4 |
|  | thoi_luong_seconds | float64 | duration_seconds | 0.0 | 3191 | 5.0 | 164766.0 | 78.0, 79.0, 102.0 |


- Candidate primary keys: no, _source_row
- Datetime columns: thoi_gian_bat_dau, thoi_gian_ket_thuc
- Duration columns: thoi_luong, thoi_luong_seconds

### Machine_Downtime_20260203_100753.xlsx / Report

- Table name: `machine_downtime_20260203_100753_report_3c3f6d`
- Source path: `Machine_Downtime_20260203_100753.xlsx`
- Header row: 35
- Data start row: 36
- Rows imported: 9,151
- Columns imported: 13
- Issues: Dropped all-null columns: note, col_8; Added parsed duration seconds column: thoi_luong_seconds

| Original | Normalized | Type | Role | Null ratio | Unique | Min | Max | Samples |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| No. | no | int64 |  | 0.0 | 9151 | 1 | 9151 | 1, 2, 3 |
| Máy | may | object | machine | 0.0 | 9 |  |  | Máy 11, Máy 29, Máy 30 |
| Thời gian bắt đầu | thoi_gian_bat_dau | datetime64[ns] | start_time | 0.0 | 9151 | 2025-11-03T09:57:29.892000 | 2026-02-03T07:54:23.731000 | 2026-02-03 07:54:23.731, 2026-02-03 07:41:21.220, 2026-02-03 07:22:59.135 |
| Thời gian kết thúc | thoi_gian_ket_thuc | datetime64[ns] | end_time | 0.0 | 9151 | 2025-11-03T10:16:13.227000 | 2026-02-03T07:57:17.734000 | 2026-02-03 07:57:17.734, 2026-02-03 07:52:06.301, 2026-02-03 07:34:18.435 |
| Thời lượng | thoi_luong | object | duration | 0.0 | 2402 |  |  | 00:02:54, 00:10:45, 00:11:19 |
| Tên tổn thất | ten_ton_that | object | loss_name | 0.0 | 13 |  |  | MÁY LỖI PHẦN CƠ, RỈ ĐƯỜNG HÀN ĐÁY, KẸT ĐÁY LIÊN TỤC |
| Nhóm tổn thất | nhom_ton_that | object | loss_group | 0.0 | 1 |  |  | Bảo trì |
| Loại tổn thất | loai_ton_that | object | loss_type | 0.0 | 1 |  |  | Dừng do máy |
|  | _source_file | object |  | 0.0 | 1 |  |  | Machine_Downtime_20260203_100753.xlsx |
|  | _source_sheet | object |  | 0.0 | 1 |  |  | Report |
|  | _source_row | int64 |  | 0.0 | 9151 | 36 | 9186 | 36, 37, 38 |
|  | _import_id | object |  | 0.0 | 1 |  |  | 4c091cb1-878f-4cb0-8235-338158251026 |
|  | thoi_luong_seconds | float64 | duration_seconds | 0.0 | 2402 | 5.0 | 33269.0 | 174.0, 645.0, 679.0 |


- Candidate primary keys: no, thoi_gian_bat_dau, thoi_gian_ket_thuc, _source_row
- Datetime columns: thoi_gian_bat_dau, thoi_gian_ket_thuc
- Duration columns: thoi_luong, thoi_luong_seconds

## Candidate Relationships

| left_table | left_column | right_table | right_column | overlap_count | overlap_ratio | name_similarity | confidence | evidence |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| loss_assignment_20260203_100840_report_2a7588 | may | machine_downtime_20260203_100753_report_3c3f6d | may | 9 | 1.0 | 1.0 | 1.0 | compatible sampled values and similar column names |
| loss_assignment_20260203_100840_report_2a7588 | ten_ton_that | machine_downtime_20260203_100753_report_3c3f6d | ten_ton_that | 12 | 0.923 | 1.0 | 0.942 | compatible sampled values and similar column names |

## Relationship Notes

- `loss_assignment` and `machine_downtime` have strong overlap on `may` and `ten_ton_that`; these are useful for comparison and filtering, but not enough to prove a row-level foreign-key relationship.

- `No.` columns are report row numbers and are intentionally excluded from relationships.

- Duration overlaps are intentionally excluded from relationships because equal durations do not prove business linkage.
