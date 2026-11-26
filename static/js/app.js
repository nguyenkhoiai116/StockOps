// ===== APP: khởi động, gom các feature, trang chính =====
import { startRouter, icon, esc, api, can, setMe } from "./core.js";
import { page as dashboard } from "./features/dashboard.js";
import { page as products } from "./features/products.js";
import { page as inbound } from "./features/inbound.js";
import { page as layout } from "./features/layout.js";
import { page as inventory } from "./features/inventory.js";
import { page as picking } from "./features/picking.js";
import { page as shipping } from "./features/shipping.js";
import { page as analytics } from "./features/analytics.js";
import { loginPage, userBox } from "./features/auth.js";
import { mountChat } from "./chat.js";

// Danh sách chức năng. Thêm feature mới: import ở trên rồi thêm vào đây.
// perm: các quyền mở được trang (có 1 trong số đó là đủ), khai báo ở cuối mỗi file feature.
const ALL = [dashboard, products, inbound, layout, inventory, picking, shipping, analytics];
let PAGES = [];   // các trang người đang đăng nhập được mở

// ---------- Trang chính: lưới ô chọn chức năng ----------
// Mỗi ô là 1 chức năng trong PAGES, bấm vào thì chuyển tới #/<id>
async function home() {
  return `<h1>Công việc trong kho</h1><p class="sub">Từ nhận hàng đến giao hàng, theo lô và hạn dùng</p>
    <div class="tiles">${PAGES.map((p) => `<a class="tile" href="#/${p.id}">
      ${icon(p.icon)}<b>${esc(p.name)}</b><small>${esc(p.desc)}</small></a>`).join("")}</div>`;
}

// ---------- Khởi động ----------
// Chưa đăng nhập -> trang đăng nhập. Đã đăng nhập -> mở các trang theo quyền.
async function start() {
  const view = document.getElementById("view");
  try {
    const { user } = await api("/me");
    if (!user) return loginPage(view);
    setMe(user);
  } catch (x) {
    view.innerHTML = `<div class="card empty"><p>Không kết nối được máy chủ: ${esc(x.message)}</p>
      <p>Kiểm tra đã chạy <b>python app.py</b> chưa</p><button class="btn" onclick="location.reload()">Thử lại</button></div>`;
    return;
  }
  PAGES = ALL.filter((p) => can(...p.perm));
  userBox(document.getElementById("userBtn"));
  startRouter(PAGES, home);              // bắt đầu điều hướng
  if (can("chat.use")) mountChat();      // khung chat góc phải dưới (xem chat.js)
}
start();
