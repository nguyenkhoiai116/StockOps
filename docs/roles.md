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
| Xem danh mục SKU | ✓ | ✓ | ✓ | ✓ | ✓ |
| Thêm, xóa SKU | ✓ |  |  |  |  |
| Xem đơn mua (PO) | ✓ | ✓ | ✓ |  |  |
| Tạo đơn mua (PO) | ✓ |  |  |  |  |
| Nhận hàng vào kho theo lô | ✓ | ✓ |  |  |  |
| Xem sơ đồ kho 2D, 3D | ✓ | ✓ | ✓ | ✓ |  |
| Xem tồn kho theo lô, lịch sử giao dịch | ✓ | ✓ | ✓ | ✓ |  |
| Điều chỉnh số lượng tồn | ✓ |  | ✓ |  |  |
| Xuất file CSV tồn kho | ✓ |  | ✓ |  |  |
| Xem đơn bán và đội xe | ✓ |  |  | ✓ | ✓ |
| Tạo đơn bán | ✓ |  |  |  |  |
| Soạn hàng theo FEFO, soạn lại | ✓ |  |  | ✓ |  |
| Hủy đơn bán chưa xuất kho | ✓ |  |  | ✓ |  |
| Chọn xe và xuất kho | ✓ |  |  |  | ✓ |
| Xác nhận đã giao | ✓ |  |  |  | ✓ |
| Xem trang Phân tích | ✓ |  |  |  |  |

## Có trong sơ đồ nhưng phần mềm chưa làm

| Role | Việc còn thiếu |
|---|---|
| Quản trị | Trang quản lý tài khoản (hiện đặt mật khẩu bằng `users.py`, khóa hoặc đổi role phải sửa database) |
| Nhập kho | Màn hình giám sát riêng (hiện chỉ xem danh sách PO) |
| Lưu kho | Sắp xếp, chuyển hàng giữa các ô; nhật ký duy trì kho |
| Soạn hàng | Bước đóng gói |
| Xuất kho | Đối chiếu số lượng khi giao cho bên vận tải |
