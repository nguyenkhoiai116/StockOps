# Làm phẳng giao diện StockOps theo Unslop

Nguồn phương pháp: [heydamir/unslop](https://github.com/heydamir/unslop) của Damir Sokolovsky, CC BY 4.0.

## Mục tiêu
- Bỏ neumorphism; giao diện phẳng, dễ đọc khi nhìn bảng cả ngày.
- Mọi chữ đạt tương phản 4,5:1 trở lên.
- Một cách viết thống nhất: tiếng Việt, số kiểu Việt Nam, không emoji.

## Không làm
- Không đổi backend, API, database, tên sản phẩm, tính năng hay thứ tự các phần.
- Không thêm thư viện, không thêm bước build.
- Không thay trang trí cũ bằng trang trí mới (kính mờ, gradient, phát sáng).

## Các cách đã cân nhắc
1. **Bỏ neumorphism, làm phẳng (đã chọn).** Dễ đọc, dữ liệu nổi lên; diện mạo đổi nhiều.
2. Giữ neumorphism, chỉ sửa lỗi. Ít đổi hơn nhưng mọi khối vẫn nổi như nhau.

## Hướng thiết kế
- Sản phẩm: phần mềm kho giúp thủ kho xuất hàng theo lô và hạn dùng.
- Tính cách: tỉnh táo, chính xác, mát như kho lạnh.
- Chất liệu: kệ hàng, nhãn thùng, nhiệt kế. Nền xám trung tính, màu nhấn `#2f62d6`.
- Điểm nhấn: Sơ đồ kho, ô tô màu theo hạn dùng.
- Chi tiết riêng: mã vị trí (`FRZ-02`) luôn hiện dạng nhãn kệ.
- Chữ: IBM Plex Sans, số liệu phụ và mã vị trí dùng IBM Plex Mono; độ đậm 400 đến 600.

## Kế hoạch
1. `theme.css`, `base.css`, `components.css`, `chat.css`: token mới, lưới 4px, viền mảnh.
2. `index.html`, `core.js`, `icons/`: icon dùng `mask` để theo màu chữ, menu dạng tab, hàm `loc()`.
3. `app.js`, `features/*.js`, `chat.js`: câu chữ, dạng số, dải KPI 4 cột, nhãn kệ.
4. Kiểm tra: chạy bản sao, xem đủ 9 màn hình ở desktop và điện thoại, console không lỗi, đo lại tương phản.
