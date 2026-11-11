// ===== CORE: công cụ dùng chung cho mọi feature =====
// Gồm: gọi API, thông báo, hộp thoại, form, các mảnh giao diện dùng lại, và bộ điều hướng.
// Mỗi file trong js/features/ sẽ import những thứ cần từ đây.

// ---------- Hằng số dùng chung ----------
export const STORE = { dry: "Kho khô", chilled: "Kho mát", frozen: "Kho đông", cosmetics: "Mỹ phẩm" };
export const SO = { new: ["Mới", "warn"], picked: ["Đã soạn", "info"], shipping: ["Đang giao", "info"], delivered: ["Đã giao", "ok"] };

// ---------- Hàm định dạng ----------
export const num = (n) => Number(n || 0).toLocaleString("vi-VN");
export const vnd = (n) => (n >= 1e9 ? (n / 1e9).toFixed(2) + " tỷ" : n >= 1e6 ? (n / 1e6).toFixed(1) + " triệu" : num(n) + " đ");
export const dmy = (s) => s.slice(8, 10) + "/" + s.slice(5, 7) + "/" + s.slice(0, 4);
// esc: chống chèn mã độc khi hiển thị chữ do người dùng nhập
export const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

// ---------- Gọi API của Python ----------
export async function api(path, method = "GET", body) {
  const r = await fetch("/api" + path, {
    method,
    headers: body ? { "Content-Type": "application/json" } : {},
    body: body ? JSON.stringify(body) : undefined,
  });
  const d = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(d.error || "Lỗi " + r.status);   // ném đúng lời giải thích của server
  return d;
}

// ---------- Icon (ảnh SVG tự vẽ trong /icons/) ----------
export const iconSrc = (key) => `/icons/${key}.svg`;
export const icon = (key, cls = "ic") => `<img class="${cls}" src="${iconSrc(key)}" alt="">`;

// ---------- Thông báo nhỏ (toast), tự ẩn sau 3 giây ----------
let tm;
export function toast(msg, ok = true) {
  const t = document.getElementById("toast");
  t.textContent = msg;
  t.className = "toast show" + (ok ? "" : " err");
  clearTimeout(tm);
  tm = setTimeout(() => (t.className = "toast"), 3000);
}

// ---------- Hộp thoại (modal) ----------
export function openModal(html) {
  const m = document.getElementById("modal");
  m.innerHTML = `<div class="box">${html}</div>`;
  m.classList.add("show");
}
export function closeModal() { document.getElementById("modal").classList.remove("show"); }
window.addEventListener("click", (e) => { if (e.target.id === "modal") closeModal(); });

// Tạo form trong hộp thoại. fields: [{k, label, type, val, opts:[[giá trị,chữ]], opt:bỏ-bắt-buộc}]
export function form(title, fields, onOk, okText = "Lưu") {
  const inputs = fields.map((f) => `<label>${f.label}${f.opts
    ? `<select name="${f.k}">${f.opts.map((o) => `<option value="${esc(o[0])}">${esc(o[1])}</option>`).join("")}</select>`
    : `<input name="${f.k}" type="${f.type || "text"}" value="${esc(f.val ?? "")}" ${f.opt ? "" : "required"}>`}</label>`).join("");
  openModal(`<h2>${title}</h2><form id="f">${inputs}
    <div class="acts"><button type="button" class="btn ghost" onclick="closeModal()">Hủy</button><button class="btn">${okText}</button></div></form>`);
  document.getElementById("f").onsubmit = async (e) => {
    e.preventDefault();
    try {
      await onOk(Object.fromEntries(new FormData(e.target)));
      closeModal(); toast("Đã lưu"); route();
    } catch (x) { toast(x.message, false); }
  };
}

// Hộp xác nhận trước thao tác quan trọng
export function confirmBox(text, fn) {
  openModal(`<h2>Xác nhận</h2><p>${text}</p><div class="acts">
    <button class="btn ghost" onclick="closeModal()">Hủy</button><button class="btn red" id="yes">Đồng ý</button></div>`);
  document.getElementById("yes").onclick = () => { closeModal(); run(fn, "Đã thực hiện"); };
}

// Chạy 1 thao tác rồi vẽ lại trang; lỗi thì hiện thông báo đỏ
export async function run(fn, msg) {
  try { await fn(); toast(msg); route(); } catch (x) { toast(x.message, false); }
}

// ---------- Mảnh giao diện dùng lại ----------
export const table = (heads, body) => body
  ? `<div class="scroll"><table><thead><tr>${heads.map((h) => `<th class="${h.endsWith("*") ? "r" : ""}">${h.replace("*", "")}</th>`).join("")}</tr></thead><tbody>${body}</tbody></table></div>`
  : `<div class="empty">Chưa có dữ liệu</div>`;
export const kpi = (lb, val, ht) => `<div class="card kpi"><div class="lb">${lb}</div><div class="val">${val}</div><div class="ht">${ht}</div></div>`;
export const hbar = (name, pct, txt, cls = "") => `<div class="hb"><div class="t"><span>${esc(name)}</span><b>${txt}</b></div>
  <div class="track"><div class="fill ${cls}" style="width:${Math.min(pct, 100)}%"></div></div></div>`;
export const capCls = (p) => (p >= 90 ? "bad" : p >= 80 ? "warn" : "");
export const expTag = (exp, today, near) => exp < today ? `<span class="tag bad">Hết hạn</span>`
  : exp <= near ? `<span class="tag warn">Cận date</span>` : `<span class="tag ok">Còn hạn</span>`;
export const soTag = (s) => `<span class="tag ${SO[s][1]}">${SO[s][0]}</span>`;
export const pickList = (o) => o.picks.map((k) =>
  `<small>Lô ${esc(k.batch_no)} · HSD ${dmy(k.exp)} · ô ${k.zone}-${String(k.bin).padStart(2, "0")} · ${num(k.qty)} thùng</small>`).join("");

// ---------- Điều hướng (router) ----------
// Đọc phần sau dấu # trên địa chỉ (vd #/sku) rồi vẽ trang tương ứng vào <main>.
let PAGES = [], home;
export function startRouter(pages, homeFn) {
  PAGES = pages; home = homeFn;
  window.onhashchange = () => { document.getElementById("view").innerHTML = ""; window.scrollTo(0, 0); route(); };
  route();
}

export async function route() {
  const id = location.hash.slice(2) || "home";
  const page = PAGES.find((p) => p.id === id);
  const view = document.getElementById("view");
  // Trang chính không cần dải menu; trong chức năng thì hiện menu để nhảy nhanh
  document.getElementById("nav").innerHTML = !page ? "" :
    `<a href="#/">🏠 Trang chính</a>`.replace("🏠", `<img src="${iconSrc("logo")}" width="18">`) +
    PAGES.map((p) => `<a href="#/${p.id}" class="${p.id === id ? "on" : ""}">${icon(p.icon, "")} ${p.name}</a>`).join("");
  if (!view.innerHTML) view.innerHTML = `<div class="skel"></div><div class="skel"></div>`;
  try {
    view.innerHTML = page ? await page.render() : await home();
  } catch (x) {
    view.innerHTML = `<div class="card empty"><p>Không tải được dữ liệu: ${esc(x.message)}</p>
      <p>Hãy kiểm tra đã chạy <b>python app.py</b> chưa.</p><button class="btn" onclick="route()">Thử lại</button></div>`;
  }
}

// Cho phép onclick="..." trong HTML gọi được các hàm này
Object.assign(window, { route, closeModal, run, api });
