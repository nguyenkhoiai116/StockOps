// Feature: Đăng nhập, tài khoản. Kiểm tra mật khẩu và chặn quyền nằm ở wms/features/auth.py.
import { api, me, icon, openModal, closeModal, toast, esc } from "../core.js";

// Vẽ trang đăng nhập. Thành công thì tải lại trang để mở đúng chức năng của người dùng
export function loginPage(view) {
  view.innerHTML = `<form class="card login" id="lg"><h1>Đăng nhập</h1><p class="sub">Dùng tài khoản được quản trị kho cấp</p>
    <label>Tài khoản<input name="user" required autocomplete="username" autocapitalize="none" spellcheck="false"></label>
    <label>Mật khẩu<input name="pass" type="password" required autocomplete="current-password"></label>
    <p class="err" id="lgErr" role="alert"></p><button class="btn">Đăng nhập</button></form>`;
  const f = document.getElementById("lg"), err = document.getElementById("lgErr"), btn = f.querySelector(".btn");
  f.user.focus();
  f.onsubmit = async (e) => {
    e.preventDefault();
    err.textContent = "";
    btn.disabled = true;
    try {
      await api("/login", "POST", Object.fromEntries(new FormData(f)));
      location.reload();
    } catch (x) {
      err.textContent = x.message;
      btn.disabled = false;
      f.pass.value = "";
      f.pass.focus();
    }
  };
}

// Nút tài khoản ở thanh trên: tên, role; bấm vào để đổi mật khẩu hoặc đăng xuất
export function userBox(btn) {
  btn.innerHTML = `${icon("user")} <span class="tx">${esc(me.name)}<small>${esc(me.role_name)}</small></span>`;
  btn.hidden = false;
  btn.onclick = () => openModal(`<h2>Tài khoản</h2>
    <dl class="kv"><dt>Họ tên</dt><dd>${esc(me.name)}</dd><dt>Tài khoản</dt><dd>${esc(me.username)}</dd><dt>Vai trò</dt><dd>${esc(me.role_name)}</dd></dl>
    <div class="acts"><button class="btn ghost" onclick="closeModal()">Đóng</button><button class="btn ghost" onclick="pwForm()">Đổi mật khẩu</button>
      <button class="btn" onclick="logout()">Đăng xuất</button></div>`);
}

// Form tự đổi mật khẩu
function pwForm() {
  openModal(`<h2>Đổi mật khẩu</h2><form id="pw">
    <label>Mật khẩu hiện tại<input name="old" type="password" required autocomplete="current-password"></label>
    <label>Mật khẩu mới (từ 8 ký tự)<input name="new" type="password" required minlength="8" maxlength="256" autocomplete="new-password"></label>
    <label>Nhập lại mật khẩu mới<input name="again" type="password" required autocomplete="new-password"></label>
    <div class="acts"><button type="button" class="btn ghost" onclick="closeModal()">Hủy</button><button class="btn">Đổi mật khẩu</button></div></form>`);
  document.getElementById("pw").onsubmit = async (e) => {
    e.preventDefault();
    const v = Object.fromEntries(new FormData(e.target));
    if (v.new !== v.again) return toast("Hai lần nhập không giống nhau", false);
    try {
      await api("/password", "POST", { old: v.old, new: v.new });
      closeModal();
      toast("Đã đổi mật khẩu");
    } catch (x) { toast(x.message, false); }
  };
}

// Đăng xuất rồi tải lại, xóa hết dữ liệu của người cũ khỏi trang
async function logout() {
  try {
    await api("/logout", "POST");
    location.hash = "#/";
    location.reload();
  } catch (x) { toast(x.message, false); }
}
Object.assign(window, { pwForm, logout });
