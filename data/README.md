# Dữ liệu mẫu StockOps (CSV)

Thư mục này chứa **toàn bộ dữ liệu mẫu** của bản demo. Mỗi file `.csv` là 1 bảng, mở được bằng Excel.
App vẫn chạy trên database SQLite (`wms.db`). Các file CSV là nơi để bạn **xem và sửa** dữ liệu mà không cần biết SQL.

## 3 lệnh cần nhớ

Chạy trong thư mục dự án:

| Muốn | Lệnh |
|---|---|
| Dựng lại database từ các file CSV này (TẮT server trước: Ctrl+C) | `python database.py reset` |
| Xem database đang chạy (sau khi đã thao tác trên web) | `python database.py export` → mở thư mục `exports/<ngày-giờ>/` |
| Lấy trạng thái hiện tại làm bộ mẫu mới | `python database.py export data` (ghi đè các file ở đây) |

`reset` luôn sao lưu `wms.db` cũ vào `backups/` trước khi xóa.

## Sửa dữ liệu bằng Excel

1. Mở file, ví dụ `products.csv`, bằng Excel.
2. Sửa ô, thêm dòng, xóa dòng. **Không đổi tên cột ở dòng 1.**
3. Lưu: File > Save As > chọn kiểu **CSV UTF-8 (Comma delimited) (\*.csv)**.
4. Tắt server, chạy `python database.py reset`.

Nếu file sai, `reset` báo đúng file, dòng và cột, rồi không nạp gì cả. Ví dụ: `batches.csv dòng 7: SKU 'SKU-099' chưa có trong products.csv`. Sửa xong chạy lại.

### Lỗi hay gặp với Excel

| Thấy | Lý do | Cách sửa |
|---|---|---|
| `mã vạch '8.93E+12' phải toàn chữ số` | Excel tự đổi số dài sang dạng số mũ | Bôi đen cột `barcode` > Format Cells > Text, gõ lại mã |
| `không đọc được tiếng Việt` | Lưu kiểu "CSV" thường thay vì "CSV UTF-8" | Save As lại, chọn đúng **CSV UTF-8** |

Không cần lo 3 chuyện sau, lệnh nạp tự hiểu:
- Excel máy tiếng Việt lưu dấu `;` thay cho dấu `,`.
- Số thập phân viết bằng dấu phẩy (`27,5`).
- Ngày dạng `27/11/2026` thay cho `2026-11-27`.

## Những quy ước cần biết

- **Dùng mã SKU, không dùng số id sản phẩm.** Trong `batches`, `pos`, `sos`, `txs`, cột `sku` cho biết hàng nào.
- **Cột `id` chỉ có ở `batches` và `sos`**, vì `picks` và `txs` trỏ vào chúng (`batch_id`, `so_id`). Thêm lô mới thì cho `id` một số chưa dùng. Các bảng khác tự đánh số theo thứ tự dòng.
- **Ô trống = giá trị mặc định** (ví dụ `reserved` trống = 0, `active` trống = 1).
- **Ngày tự dời cho mới.** File `ngay_goc.txt` ghi ngày tạo bộ dữ liệu. Khi nạp, ngày đó thành hôm nay và mọi ngày khác dời theo cùng số ngày. Nạp lại tuần sau thì lô "còn 5 ngày hết hạn" vẫn còn 5 ngày.
- **Sổ giao dịch tự cân.** Nếu bạn sửa `qty` của 1 lô trong `batches.csv` mà không sửa `txs.csv`, lệnh nạp ghi thêm 1 dòng điều chỉnh (`ADJ`, ghi chú "Cân sổ khi nạp từ file CSV") cho khớp tồn.
- **Mật khẩu không nằm trong file nào.** Sau `reset`, lệnh sẽ hỏi 1 mật khẩu demo dùng chung cho mọi tài khoản. Đặt riêng từng người: `python users.py passwd <tên>`.

## Các file và ý nghĩa từng cột

Thứ tự nạp: khu → sản phẩm → xe → tài khoản → lô → PO → đơn bán → picks → sổ giao dịch.

**zones.csv** (khu kho): `code` mã khu · `name` tên · `storage` loại kho · `cap` sức chứa (thùng) · `tmin`, `tmax` ngưỡng nhiệt độ · `temp`, `hum` nhiệt độ, độ ẩm hiện tại · `racks` × `bays` × `levels` = số dãy kệ × số ô mỗi dãy × số tầng = số ô của khu.
Kho mát đang để 9.1°C, cố ý vượt ngưỡng 8°C để Dashboard có cảnh báo nhiệt độ.

**products.csv** (danh mục SKU, lấy từ file `StockOps_DanhMuc_FMCG-v2.xlsx`): `sku` · `name` · `cat` ngành hàng · `unit` đơn vị · `storage` loại kho · `price` giá vốn (đ/thùng) · `safety` tồn an toàn (thùng) · `supplier` nhà cung cấp · `barcode` mã vạch EAN-13 · `pack` số đơn vị lẻ/thùng · `dims` kích thước thùng (cm) · `vol` thể tích thùng (m³) · `tmin`, `tmax` nhiệt độ bảo quản · `shelf` hạn sử dụng (ngày) · `fefo` ngưỡng cảnh báo FEFO (ngày) · `qc` 1 = phải kiểm QC khi nhập · `abc` hạng A/B/C.
Khác với file Excel: "Kho thường" và "Kho khô" cùng vào khu DRY (`storage` = `dry`), nhiệt độ riêng của từng loại vẫn giữ ở `tmin`/`tmax`. Excel không có `safety` và `supplier` nên đã tự đặt (tên nhà cung cấp là tên giả).

**vehicles.csv** (đội xe): `plate` biển số · `driver` tài xế · `kind` `dry` = xe thường, `cold` = xe lạnh (hàng mát/đông phải đi xe lạnh).

**users.csv** (tài khoản): `username` · `name` · `role` · `active` 1 = dùng được, 0 = khóa · `created_at` ngày tạo. Quyền từng role xem `docs/roles.md`.

**batches.csv** (lô hàng): `id` · `sku` · `batch_no` số lô · `exp` hạn dùng · `qty` thực có (thùng) · `reserved` đang giữ cho đơn đã soạn · `zone` khu · `bin` ô kệ (1 tới số ô của khu; mỗi ô chỉ 1 lô còn hàng).

**pos.csv** (đơn mua): `po_no` · `sku` · `qty` số đặt · `eta` ngày dự kiến về · `status` · `recv` số thùng đạt · `dmg` số thùng hỏng.

**sos.csv** (đơn bán): `id` · `so_no` · `customer` khách · `sku` · `qty` · `due` hạn giao · `status` · `plate` xe chở · `on_time` 1 = giao đúng hạn, 0 = trễ.

**picks.csv** (hàng đã soạn cho đơn, lô nào bao nhiêu): `so_id` · `batch_id` · `qty` · `released` 1 = đã trả lại lô (hủy đơn hoặc soạn lại).

**txs.csv** (sổ giao dịch kho): `ts` thời điểm · `kind` · `sku` · `batch_no` · `qty` số dương = nhập, số âm = xuất · `note` · `batch_id` · `who` người làm (trống = hệ thống).

### Giá trị hợp lệ

| Cột | Giá trị |
|---|---|
| `storage` | `dry` kho khô · `chilled` kho mát · `frozen` kho đông · `cosmetics` hóa mỹ phẩm |
| `role` | `admin` · `inbound` nhập kho · `storage` lưu kho · `picking` soạn hàng · `shipping` xuất kho |
| `pos.status` | `pending` chờ nhận · `received` đã nhận |
| `sos.status` | `new` mới · `picked` đã soạn · `shipping` đang giao · `delivered` đã giao · `cancelled` đã hủy |
| `txs.kind` | `IN` nhập · `OUT` xuất · `ADJ` điều chỉnh |

`reserved` của 1 lô phải bằng tổng `picks.qty` (với `released` = 0) của các đơn đang `picked`. Sai chỗ này thì lệnh nạp báo lỗi.

## Bộ mẫu hiện tại có gì

14 ngày vận hành của 35 SKU FMCG, tạo bằng đúng các hàm nghiệp vụ của app nên số liệu khớp nhau. Có sẵn các tình huống để demo:

- **Lô và hết hạn:** lô chả lụa SKU-005 đã hết hạn nhưng còn hàng (nằm ở khu cách ly), cùng vài lô sữa và bánh mì cận date.
- **Tồn kho:** 4 SKU dưới tồn an toàn. 2 SKU đã có PO chờ nhận, 2 SKU chưa có nên Dashboard gợi ý đặt hàng.
- **PO:** 2 PO về hôm nay, 1 PO trễ hẹn (dầu ăn SKU-026), 2 lần nhận có thùng hỏng.
- **Đơn bán:** có đơn mới, đã soạn, đang giao (1 xe thường, 1 xe lạnh) và 1 đơn đã hủy. Riêng đơn há cảo 400 thùng không đủ hàng, nên bấm soạn sẽ bị từ chối.
- **Kiểm kê:** 2 lần điều chỉnh tồn (vỡ 2 thùng, đếm dư 1 thùng).
