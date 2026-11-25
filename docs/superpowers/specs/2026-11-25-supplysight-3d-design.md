# Bố cục kiểu SupplySight và kho 3D cơ bản

Mẫu tham khảo: bản SupplySight sáng màu tại https://nuel-inc-task.vercel.app (chỉ lấy cách bố trí, không chép code).

## Mục tiêu
- Bố cục sáng, rộng: thanh trên, chỉ số, biểu đồ xu hướng, bảng có bộ lọc, ngăn chi tiết bên phải.
- Trang Sơ đồ kho có 2D và 3D cơ bản; sau này thay bằng mô hình 3D cụ thể mà không sửa phần còn lại.

## Các cách đã cân nhắc cho 3D
1. **Three.js trong `static/` (đã chọn).** Không cần bước build; nạp từ CDN khi mở 3D, lỗi mạng thì về 2D.
2. Next.js + React Three Fiber trong `web/`. Hợp khi 3D phức tạp; với 48 ô thì thêm cả bộ công cụ mà chưa cần.
3. Vẽ giả 3D bằng CSS. Không nạp được mô hình GLB sau này.

## Quy ước 3D tạm thời
- Mỗi khu 12 ô xếp thành 2 kệ × 2 tầng × 3 ô. Đây chỉ là cách bày, chưa phải sơ đồ kho thật; nằm gọn trong `slot()` ở `static/js/wh3d.js`.
- Hàng và kệ được dựng bởi `makeRack()` và `makeLoad()`; mô hình GLB sau này thay 2 hàm này.
- Màu: hạn dùng theo từng ô, hoặc mức đầy theo khu. Không tô mức đầy từng ô vì database chưa có sức chứa ô.

## Backend
- `/api/dashboard?days=7|14|30`; giá trị khác thì dùng 7.
- `/api/dashboard` thêm `items` (tồn, khả dụng, tồn an toàn, trạng thái theo SKU). Luật trạng thái nằm ở `core.stock_status()`.
- Không đổi database.

## Không làm
- Không có mô hình GLB, kéo thả hàng, sức chứa từng ô, mô phỏng xe nâng.
