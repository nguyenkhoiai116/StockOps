# Kho 3D theo mặt bằng chữ U (4.500 m²)

Ảnh tham chiếu: "Sơ đồ bố trí mặt bằng kho tổng FMCG chữ U (4.500 m²)" do chủ dự án gửi ngày 2026-11-26.
Thay cho phần "Quy ước 3D tạm thời" trong `2026-11-25-supplysight-3d-design.md`.

## Mục đích
Trang Sơ đồ kho ở chế độ 3D phải giống mặt bằng kho thật trong ảnh, gồm 12 khu, luồng xe chữ U, 4 cửa nhập và 4 cửa xuất.
Người xem phải nhìn một lần là thấy:
- hàng đang nằm ở đâu;
- xe nào đang chờ nhập, đơn nào đang chờ soạn hoặc chờ xuất;
- hàng nào hết hạn hoặc bị hỏng.

Ưu tiên của chủ dự án: **hiện nhanh và dễ hiểu**. Hình không cần giống ảnh render từng chi tiết.

## Mục tiêu
- Dựng mặt bằng 90 × 50 m. Hàng đi theo chữ U: nhập ở bên trái, chạy vòng ra phía sau, xuất ở bên phải. Có cả phần bên ngoài: bãi xe tải, bãi xe nhân viên, 2 cổng, đường và mũi tên luồng xe.
- Kệ có số dãy, số ô, số tầng **thật theo từng khu**, và mỗi ô vẽ ra là một ô có dữ liệu (cách B).
- Các khu ngoài kệ hiện dữ liệu thật đang có trong database (xem "Gắn dữ liệu").
- Cửa nhập N1–N4 và cửa xuất X1–X4 có đánh số. Xe được **tự xếp vào cửa khi hiển thị**.

## Không làm
- Không quản lý vị trí theo pallet, và một lô không nằm ở nhiều ô (cách C). Để dành đến khi cần.
- Không lưu số cửa vào database, không sửa màn hình Nhận hàng và Giao hàng.
- Xe nâng, người, xe tải chỉ đứng yên làm cảnh, không có chuyển động.
- Không dùng mô hình GLB, không kéo thả hàng.
- Không đổi lưới 2D: vẫn là lưới ô theo khu như hiện tại, chỉ có thêm ô.
- Không thêm trạng thái "đã nhận, chờ lên kệ" (khu 1B chỉ làm cảnh).

## Điều không được xảy ra (dù chạy được)
- Hình vẽ khác dữ liệu, ví dụ ô có hàng mà 3D vẽ trống, hoặc ngược lại.
- Lộ dữ liệu cho role không có quyền xem. Ví dụ role `storage` không có `so.view`, nên không được thấy đơn bán qua trang sơ đồ.
- Trang 3D mở chậm hoặc giật trên laptop thường.
- Người xem tưởng số cửa là dữ liệu thật.

## Các cách đã cân nhắc (ô kệ)
| Cách | Nội dung | Được | Mất |
|---|---|---|---|
| A | Giữ 12 ô mỗi khu, vẽ kệ thật làm nền | Không sửa backend | Mỗi khu vẫn chỉ chứa 12 lô; phần kệ trống dễ bị hiểu nhầm là còn chỗ |
| **B (đã chọn)** | Số ô theo từng khu, khai báo trong migration; 1 lô vẫn là 1 ô | Quy mô đúng như ảnh, hết giới hạn 12 lô, sửa backend ít | Ô vẫn chứa không giới hạn số thùng (giới hạn chỉ tính theo khu) |
| C | Bảng vị trí theo pallet, một lô nằm nhiều ô | Đúng chuẩn WMS | Phải sửa nhận hàng, FEFO, tồn kho; quá lớn cho lần này |

Cách gán xe vào cửa: chọn **tự xếp khi hiển thị**. Cách còn lại (lưu số cửa vào PO và đơn bán) bị loại vì phải sửa thêm 2 màn hình và nghiệp vụ.

## Database và backend
**Migration `wms/migrations/003_racks.sql`:**
- `ALTER TABLE zones` thêm 3 cột `racks` (số dãy), `bays`, `levels` (không đặt tên `rows` vì trùng từ khóa SQL và trùng tên hàm `rows()`) (INTEGER NOT NULL, có CHECK > 0). Mặc định 2, 2, 3, tức 12 ô, nên database cũ vẫn chạy đúng.
- `UPDATE` theo mã khu:

  | Khu | Dãy × ô × tầng | Số ô |
  |---|---|---|
  | DRY | 4 × 6 × 4 | 96 |
  | COS | 3 × 5 × 4 | 60 |
  | CHL | 2 × 4 × 3 | 24 |
  | FRZ | 2 × 4 × 3 | 24 |

- Tăng `cap` cho hợp quy mô (*quyết định của mình*): DRY 20.000, COS 6.000, CHL 3.000, FRZ 2.000 thùng. Chỉ `UPDATE` khi `cap` vẫn đang là giá trị mẫu cũ, để không ghi đè số người dùng đã sửa.

**Các chỗ sửa khác:**
- `wms/seed.py`: câu `INSERT INTO zones` hiện chèn theo vị trí 8 cột. Sau migration bảng có 11 cột, nên phải đổi sang ghi rõ tên cột và kèm `racks/bays/levels/cap` mới. Đây là sửa dữ liệu mẫu, không phải sửa schema. Lý do phải sửa: seed chạy sau migrate, nên `UPDATE` trong migration không chạm được vào database mới tạo.
- `wms/db.py`: bỏ hằng `BINS`.
- `wms/core.py`: thêm `zone_bins(z)` trả về `racks*bays*levels`. `free_bin(con, code)` tự đọc số ô của khu, không nhận tham số `bins` nữa. Sửa lời gọi trong `inbound.py`.
- **Cách đánh số ô** (chỉ có một quy ước, dùng chung cho 3D, 2D và tooltip): `bin = ((dãy−1)·bays + (ô−1))·levels + tầng`, đếm từ 1. Các ô cùng một cột kệ nằm liền số nhau.
- **Mã vị trí giữ dạng số** `DRY-42` ở mọi trang (`loc()` không đổi) (*quyết định của mình*, xem phần cuối). Riêng trang sơ đồ hiện thêm "dãy B · ô 3 · tầng 2". Dãy đặt tên bằng chữ A, B, C…

**`GET /api/layout`** (chỉ đọc, quyền `map.view` giữ nguyên):
- Mỗi khu trả thêm `racks, bays, levels, bins`.
- Bỏ `bins` ở cấp ngoài cùng.
- Thêm `flow`. Mỗi phần trong `flow` **chỉ có khi role có quyền tương ứng** (kiểm bằng `roles.can(g.user["role"], …)`); không có quyền thì bỏ hẳn key đó:
  - `inbound` (cần `po.view`): các PO `pending` có `eta <= hôm nay`, sắp theo `eta, id`, gồm `po_no, sku, qty, eta`.
  - `topick` (cần `so.view`): đơn `new`, gồm `so_no, customer, sku, qty, due`.
  - `staged` (cần `so.view`): đơn `picked`.
  - `shipping` (cần `so.view`): đơn `shipping`, có `plate`.
  - `fleet` (cần `so.view`): các xe trong `vehicles`, kèm cờ đang bận (có đơn `shipping`).
  - `quarantine`: luôn có danh sách lô hết hạn còn hàng (đã thuộc `map.view`). Phần `dmg` (tổng số hỏng của PO đã nhận, kèm `po_no`) chỉ có khi role có `po.view`.

Không thêm API mới, nên `PERMS` không đổi.

## Gắn dữ liệu vào khu
| Khu trong ảnh | Hiện gì | Nguồn |
|---|---|---|
| Cửa N1–N4 + 1A kiểm đếm | Xe tải đỗ ở cửa, biển trên xe ghi `PO-xxx · SKU`. Hơn 4 xe thì xe dư xếp ở bãi 9 phía trái, kèm nhãn "+n chờ cửa" | `flow.inbound` |
| 1B chờ lên kệ, chỗ đỗ xe nâng nhập | Làm cảnh | — |
| 2 Kho đông & mát | Chia 2 phòng, CHL và FRZ, kệ và hàng theo dữ liệu | `zones`, lô |
| 3 Hàng khô (TP, đồ uống) | Khu DRY | `zones`, lô |
| 4 Hàng khô (hóa mỹ phẩm) | Khu COS | `zones`, lô |
| 5 Soạn lẻ & đóng gói | Bàn soạn, mỗi đơn chờ soạn là 1 thùng (tối đa 12, quá thì ghi "+n"); nhãn "n đơn chờ soạn" | `flow.topick` |
| 6 Xuất & tập kết | Mỗi đơn đã soạn là 1 pallet trên làn tập kết; nhãn "n đơn chờ xe" | `flow.staged` |
| Cửa X1–X4 | Mỗi biển số có đơn `shipping` là 1 xe đỗ ở cửa (1 xe có thể chở nhiều đơn), ghi biển số và các `SO-xxx`. Hơn 4 xe thì xe dư chờ ở bãi 9 | `flow.shipping` |
| 9 Bãi chờ xe tải | Xe rảnh trong `fleet` đỗ ở bãi phía phải | `flow.fleet` |
| 7 Sạc xe nâng, 10 Bãi xe nhân viên, cổng, đường | Làm cảnh | — |
| 8 Hàng lỗi, trả về & văn phòng | Bảng số liệu "n lô hết hạn (đang ở kệ) · m thùng hỏng khi nhận". Mỗi PO có hàng hỏng là 1 pallet đỏ. Lô hết hạn **không** vẽ thêm ở khu 8, vì database ghi lô đó vẫn nằm trên kệ (ở kệ nó đã được tô đỏ) | `flow.quarantine` |

**Hàng đã soạn:** theo nghiệp vụ hiện tại, hàng của đơn đã soạn vẫn tính tồn ở ô kệ (dạng "đã giữ") cho tới khi xuất. Vì vậy pallet ở khu 6 là ký hiệu cho đơn, không phải hàng đã rời kệ. Tooltip của pallet ghi rõ điều này.

**Xếp cửa:** việc gán xe vào cửa làm ở `layout.js`, theo thứ tự trong danh sách. Phần tử thứ i vào cửa N(i+1) hoặc X(i+1); từ phần tử thứ 5 trở đi xếp vào hàng chờ.

**Thông báo trên màn hình:** dòng ghi chú góc khung đổi thành "Số cửa và chỗ đỗ là minh họa, xe xếp theo thứ tự. Kéo để xoay, cuộn để phóng to".

**Khi thiếu quyền:** role không có quyền xem phần nào thì khu đó chỉ còn cảnh, không có nhãn số liệu.

**Bấm vào đối tượng:** bấm xe, bàn soạn, pallet tập kết hoặc pallet đỏ thì khung chi tiết bên phải hiện danh sách tương ứng (số PO/SO, SKU, số lượng, hạn). Bấm vào hàng trên kệ thì giữ như cũ.

## Mặt bằng 3D (`static/js/wh3d.js`)
Toạ độ tính bằng mét. Gốc ở tâm nhà kho; x tăng sang phải; z âm là phía sau, z dương là mặt trước có cửa. Các số dưới đây **ước lượng từ ảnh**, người làm được chỉnh cho đẹp, miễn giữ đúng vị trí tương đối giữa các khu.

| Khu | x | z |
|---|---|---|
| 2 Kho lạnh (CHL trái, FRZ phải, có vách ngăn) | −45…−20 | −25…−5 |
| 3 DRY | −18…12 | −25…−5 |
| 4 COS | 14…45 | −25…−8 |
| 7 Sạc xe nâng | 34…45 | −8…2 |
| 8 Hàng lỗi + văn phòng | −45…−30 | −5…25 |
| 1B Chờ lên kệ + đỗ xe nâng nhập | −30…−18 | −5…25 |
| 5 Soạn lẻ | −16…12 | −3…25 |
| 6 Tập kết xuất | 14…45 | 2…25 |
| Cửa N1–N4 (tường trước) | −30…−8 | 25 |
| Cửa X1–X4 (tường trước) | 18…42 | 25 |
| 1A Kiểm đếm (sân trước cửa nhập) | −30…−8 | 25…33 |
| 9 Bãi xe tải | −5…45 | 27…45 |
| 10 Bãi xe nhân viên | −62…−32 | 27…45 |
| Cổng nhập / cổng xuất | ≈ −20 / ≈ 30 | 50 |

**Kích thước kệ:** ô kệ rộng 2,7 m, mỗi tầng cao 1,5 m, sâu 1,1 m, lối đi giữa các dãy 3 m. Toàn bộ kệ phải nằm gọn trong khu của nó.

**Kiểu hình:** khối đơn giản, giữ màu nhạt như hiện tại. Tường cắt thấp khoảng 1,2 m để nhìn vào trong. Cửa có số ghi trên mặt tường. Mỗi khu có nhãn đánh số giống ảnh, ví dụ "3 · Hàng khô (TP & đồ uống)".

**Để hiện nhanh:**
- Kệ, pallet, hàng, xe và đồ trang trí dùng `InstancedMesh`, mỗi loại một mesh. Màu từng ô đặt qua `setColorAt`.
- Mục tiêu: dưới 150 lượt vẽ (draw call) mỗi khung hình. Bóng đổ chỉ bật cho kệ và hàng.
- Giữ cách chỉ vẽ lại khi có thay đổi (đang làm vậy).

**Bấm và rê chuột:** phải chạy đúng với InstancedMesh (dùng `instanceId`). Chức năng làm mờ khi tìm kiếm (`dim`) và viền ô đang chọn (`select`) vẫn phải chạy như trước. InstancedMesh không đặt được độ trong suốt riêng cho từng khối, nên khi làm mờ thì đổi màu khối sang gần màu nền, và bỏ qua khối đã mờ khi dò chuột.

**Giữ nguyên:**
- Three.js tải lúc mở 3D; không tải được thì về 2D.
- Camera bay tới khu khi chọn bên trái; góc nhìn ban đầu là toàn kho từ phía trước, trên cao, giống ảnh.
- Hàm `dispose()` dọn sạch.
- Hai kiểu tô màu: theo hạn dùng và theo mức đầy khu.

**Danh sách khu bên trái:** vẫn là "Toàn kho" và 4 khu chứa hàng.

## Trang 2D và các chỗ khác
- Lưới 2D lấy số ô theo từng khu thay vì `d.bins`. Tooltip ghi thêm dãy, ô, tầng.
- `docs/architecture.md`: sửa ADR-012 (mô tả sơ đồ kệ thật theo cách B, chữ "48 ô" thành 204 ô), thêm 1 dòng nhật ký thay đổi.

## Kiểm thử
- Migration chạy được trên database cũ (12 ô) và trên database mới. Kiểm số cột, số ô và `cap`.
- `free_bin` trả đúng ô trống thứ 13 trở đi của khu DRY (trước đây sẽ trả `None`).
- `/api/layout`: role `storage` không có `topick/staged/shipping/fleet` và không có `dmg`; role `admin` có đủ.
- `python -m unittest discover tests` phải qua.
- Kiểm tay trên trình duyệt:
  - 3D mở được, bấm được ô kệ, xe, bàn soạn;
  - tìm kiếm làm mờ đúng;
  - đổi 2D/3D không lỗi console;
  - 2D vẫn là lưới.

## Quyết định của mình (bạn kiểm giúp)
1. Số dãy, ô, tầng từng khu ở bảng trên. Ước lượng từ ảnh, tổng 204 ô.
2. Tăng `cap` khu: DRY 20.000, COS 6.000, CHL 3.000, FRZ 2.000 thùng.
3. **Mã vị trí giữ dạng `DRY-42`** ở mọi trang, chỉ trang sơ đồ hiện thêm "dãy B · ô 3 · tầng 2". Lần trước mình nói sẽ đổi sang `DRY-B03-2`. Mình đổi ý vì làm vậy phải sửa 7 chỗ ở frontend, file CSV và sổ giao dịch, trong khi lợi ích chỉ nằm ở trang sơ đồ.
4. Đơn `shipping` hiện ở cửa X (đang nhận hàng). Đơn `delivered` không hiện.
5. Toạ độ khu ở bảng mặt bằng.
6. Danh sách bên trái chỉ có 4 khu chứa hàng.
7. Khu 8 không vẽ lô hết hạn thành pallet riêng, chỉ hiện số liệu, để hình không khác dữ liệu.
8. Tên cột là `racks` chứ không phải `rows`.
9. Bản thiết kế này chưa commit, vì repo đang có nhiều thay đổi chưa commit của bạn trên `main`.
