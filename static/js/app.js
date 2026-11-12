// ===== APP: khởi động, gom các feature, trang chính =====
import { startRouter, icon, esc } from "./core.js";
import { page as dashboard } from "./features/dashboard.js";
import { page as products } from "./features/products.js";
import { page as inbound } from "./features/inbound.js";
import { page as layout } from "./features/layout.js";
import { page as inventory } from "./features/inventory.js";
import { page as picking } from "./features/picking.js";
import { page as shipping } from "./features/shipping.js";
import { page as analytics } from "./features/analytics.js";
import { showLogin } from "./features/auth.js";
import { mountChat } from "./chat.js";

// Danh sách chức năng. Thêm feature mới: import ở trên rồi thêm vào đây.
const PAGES = [dashboard, products, inbound, layout, inventory, picking, shipping, analytics];

// ---------- Trang chính: lưới ô chọn chức năng ----------
// Mỗi ô là 1 chức năng trong PAGES, bấm vào thì chuyển tới #/<id>
async function home() {
  return `<h1>Xin chào 👋</h1><p class="sub">Chọn chức năng bạn muốn làm việc.</p>
    <div class="tiles">${PAGES.map((p) => `<a class="tile" href="#/${p.id}">
      <div class="iconwrap">${icon(p.icon)}</div><b>${esc(p.name)}</b><small>${esc(p.desc)}</small></a>`).join("")}</div>`;
}

// ---------- Khởi động ----------
document.getElementById("loginBtn").onclick = showLogin;
startRouter(PAGES, home);    // bắt đầu điều hướng
mountChat();                 // khung chat góc phải dưới (xem chat.js)
