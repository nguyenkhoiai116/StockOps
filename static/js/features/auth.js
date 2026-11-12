// Feature: Đăng nhập (giữ chỗ). Nút "Đăng nhập" ở thanh trên gọi showLogin().
import { api, openModal, closeModal, toast } from "../core.js";

// Mở hộp thoại đăng nhập và gửi tài khoản / mật khẩu lên /api/login
export function showLogin() {
  openModal(`<h2>Đăng nhập</h2><form id="lg">
    <label>Tài khoản<input name="user" required autocomplete="username"></label>
    <label>Mật khẩu<input name="pass" type="password" required autocomplete="current-password"></label>
    <div class="acts"><button type="button" class="btn ghost" onclick="closeModal()">Đóng</button><button class="btn">Đăng nhập</button></div></form>`);
  document.getElementById("lg").onsubmit = async (e) => {
    e.preventDefault();
    // Hiện tại backend trả "chưa hỗ trợ". Khi làm thật, xử lý đăng nhập ở đây.
    try { await api("/login", "POST", Object.fromEntries(new FormData(e.target))); }
    catch (x) { toast(x.message, false); }
  };
}
