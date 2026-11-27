# Vai trò và quyền

Nguồn gốc: `wms/roles.py`. Sửa quyền ở đó rồi chạy `python -m wms.roles` để lấy lại bảng dưới.
Việc chặn nằm ở `guard()` trong `wms/features/auth.py`: chưa đăng nhập trả 401, sai quyền trả 403.

## Tài khoản mẫu

Tên người là giả. Tài khoản mẫu không có mật khẩu sẵn; đặt bằng `python users.py passwd <tài khoản>`.

| Role | Mã role | Tài khoản |
|---|---|---|
| Quản trị | `admin` | `admin` |
| Nhập kho | `inbound` | `nhap01`, `nhap02` |
| Lưu kho | `storage` | `luu01`, `luu02` |
| Soạn hàng | `picking` | `soan01`, `soan02` |
| Xuất kho | `shipping` | `xuat01`, `xuat02` |

## Chức năng đã có trong phần mềm

| Chức năng | Quản trị | Nhập kho | Lưu kho | Soạn hàng | Xuất kho |
|---|:---:|:---:|:---:|:---:|:---:|
| Xem Tổng quan: chỉ số, cảnh báo | ✓ | ✓ | ✓ | ✓ | ✓ |
| Hỏi trợ lý Kvis | ✓ | ✓ | ✓ | ✓ | ✓ |
| Chat nội bộ và xem nhật ký thao tác liên phòng ban | ✓ | ✓ | ✓ | ✓ | ✓ |
| Xem danh mục SKU | ✓ | ✓ | ✓ | ✓ | ✓ |
| Thêm, xóa SKU | ✓ |  |  |  |  |
| Xem đơn mua (PO), kế hoạch nhập và biên bản từ chối tại Dock | ✓ | ✓ | ✓ |  |  |
| Tạo đơn mua (PO) và tải file Excel/CSV PO | ✓ | ✓ | ✓ |  |  |
| Lập kế hoạch ASN/Dock, cấp thẻ cổng, nhận hàng và từ chối tại Dock | ✓ | ✓ |  |  |  |
| Xem sơ đồ kho 2D, 3D | ✓ | ✓ | ✓ | ✓ |  |
| Xem tồn kho, phân tích Slotting/ROP/SLOB và gợi ý vị trí | ✓ | ✓ | ✓ | ✓ |  |
| Điều chỉnh tồn, kiểm kê ABC/RCA, đổi QC và điều chuyển 2 đầu | ✓ |  | ✓ |  |  |
| Xuất file CSV tồn kho | ✓ |  | ✓ |  |  |
| Xem đơn bán, đội xe và bảng điều phối xuất | ✓ |  |  | ✓ | ✓ |
| Tạo đơn bán (SO) và bóc tách file đơn hàng | ✓ |  |  |  | ✓ |
| Soạn hàng theo FEFO | ✓ |  |  | ✓ |  |
| Đối chiếu 3 chiều, ghép chuyến LIFO, xếp Dock, quét QR và xuất kho | ✓ |  |  |  | ✓ |
| Xác nhận đã giao (e-POD) và xử lý cảnh báo giao vận | ✓ |  |  |  | ✓ |
| Xem trang Phân tích | ✓ |  |  |  |  |

## Có trong sơ đồ nhưng phần mềm chưa làm

| Role | Việc còn thiếu |
|---|---|
| Quản trị | Trang quản lý tài khoản (hiện đặt mật khẩu bằng `users.py`, khóa hoặc đổi role phải sửa database) |
| Soạn hàng | Bước đóng gói & in nhãn kiện riêng tại bàn đóng gói |
