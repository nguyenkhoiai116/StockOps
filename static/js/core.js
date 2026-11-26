// ===== CORE: công cụ dùng chung cho mọi feature =====
// Gồm: gọi API, thông báo, hộp thoại, form, các mảnh giao diện dùng lại, và bộ điều hướng.
// Mỗi file trong js/features/ sẽ import những thứ cần từ đây.

// ---------- Hằng số dùng chung ----------
// STORE: tên hiển thị của loại kho. SO: trạng thái đơn bán -> [chữ hiển thị, màu tag]
export const STORE = { dry: "Kho khô", chilled: "Kho mát", frozen: "Kho đông", cosmetics: "Mỹ phẩm" };
export const SO = { new: ["Mới", "warn"], picked: ["Đã soạn", "info"], shipping: ["Đang giao", "info"], delivered: ["Đã giao", "ok"] };

// ---------- Hàm định dạng ----------
// num: số có dấu phân cách hàng nghìn kiểu Việt Nam (1.234.567)
export const num = (n) => Number(n || 0).toLocaleString("vi-VN");
// vnd: tiền rút gọn theo tỷ / triệu / đồng
export const vnd = (n) => (n >= 1e9 ? num((n / 1e9).toFixed(2)) + " tỷ" : n >= 1e6 ? num((n / 1e6).toFixed(1)) + " triệu" : num(n) + " đ");
// dmy: đổi ngày "YYYY-MM-DD" sang "DD/MM/YYYY"
export const dmy = (s) => s.slice(8, 10) + "/" + s.slice(5, 7) + "/" + s.slice(0, 4);
// dmyt: đổi "YYYY-MM-DDTHH:MM:SS" sang "DD/MM/YYYY HH:MM"
export const dmyt = (s) => dmy(s) + " " + s.slice(11, 16);
// esc: chống chèn mã độc khi hiển thị chữ do người dùng nhập
export const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

// ---------- Người đang đăng nhập ----------
// me: { username, name, role, role_name, perms } hoặc null. Ẩn nút chỉ để gọn mắt; chặn thật nằm ở backend.
export let me = null;
export const setMe = (u) => { me = u; };
// can: người đang đăng nhập có ít nhất 1 trong các quyền này không
export const can = (...ps) => !!me && ps.some((p) => me.perms.includes(p));

// ---------- Gọi API của Python ----------
// Gửi request tới /api + path, tự đóng gói body thành JSON; lỗi thì ném Error kèm thông báo của server
export async function api(path, method = "GET", body) {
  const r = await fetch("/api" + path, {
    method,
    headers: body ? { "Content-Type": "application/json" } : {},
    body: body ? JSON.stringify(body) : undefined,
  });
  // Hết phiên giữa chừng: tải lại trang để về màn hình đăng nhập
  if (r.status === 401 && me) { location.reload(); return new Promise(() => {}); }
  const d = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(d.error || "Lỗi " + r.status);   // ném đúng lời giải thích của server
  return d;
}

// ---------- Icon ----------
// iconSrc: đường dẫn file icon trong /icons/. icon: thẻ icon, màu theo chữ xung quanh (xem .ic trong base.css)
export const iconSrc = (key) => `/icons/${key}.svg`;
export const icon = (key) => `<span class="ic" style="--i:url(${iconSrc(key)})" aria-hidden="true"></span>`;

// ---------- Thông báo nhỏ (toast), tự ẩn sau 3 giây ----------
let tm;
// Hiện thông báo ở cuối màn hình; ok = false thì hiện màu đỏ (lỗi)
export function toast(msg, ok = true) {
  const t = document.getElementById("toast");
  t.textContent = msg;
  t.className = "toast show" + (ok ? "" : " err");
  clearTimeout(tm);
  tm = setTimeout(() => (t.className = "toast"), 3000);
}

// ---------- Hộp thoại (modal) ----------
// Mở hộp thoại với nội dung HTML cho trước
export function openModal(html) {
  const m = document.getElementById("modal");
  m.innerHTML = `<div class="box">${html}</div>`;
  m.classList.add("show");
}
// Đóng hộp thoại; bấm ra vùng tối bên ngoài hộp cũng đóng
export function closeModal() { document.getElementById("modal").classList.remove("show"); }
window.addEventListener("click", (e) => { if (e.target.id === "modal") closeModal(); });

// ---------- Ngăn chi tiết bên phải (drawer) ----------
let back;   // phần tử đang được chọn trước khi mở ngăn, để trả con trỏ về khi đóng
// Mở ngăn với tiêu đề (chữ thường) và nội dung HTML
export function openDrawer(title, html) {
  const d = document.getElementById("drawer");
  if (d.hidden) back = document.activeElement;
  d.innerHTML = `<header><h2>${esc(title)}</h2><button class="iconbtn" aria-label="Đóng" onclick="closeDrawer()">${icon("close")}</button></header><div class="body">${html}</div>`;
  d.hidden = false;
  d.querySelector("button").focus({ preventScroll: true });
}
// Đóng ngăn; bấm phím Esc cũng đóng
export function closeDrawer() {
  const d = document.getElementById("drawer");
  if (d.hidden) return;
  d.hidden = true;
  if (back?.isConnected) back.focus({ preventScroll: true });
}
window.addEventListener("keydown", (e) => { if (e.key === "Escape") closeDrawer(); });

// Tạo form trong hộp thoại. fields: [{k, label, type, val, opts:[[giá trị,chữ]], opt:bỏ-bắt-buộc}]
// Bấm lưu -> gọi onOk(dữ liệu form); thành công thì đóng hộp, báo "Đã lưu" và vẽ lại trang
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
// table: bảng có tiêu đề; tên cột kết thúc bằng "*" thì canh phải. Không có dòng nào -> "Chưa có dữ liệu"
export const table = (heads, body) => body
  ? `<div class="scroll"><table><thead><tr>${heads.map((h) => `<th class="${h.endsWith("*") ? "r" : ""}">${h.replace("*", "")}</th>`).join("")}</tr></thead><tbody>${body}</tbody></table></div>`
  : `<div class="empty">Chưa có dữ liệu</div>`;
// kpi: ô chỉ số gồm nhãn, giá trị lớn và dòng giải thích
export const kpi = (lb, val, ht) => `<div class="kpi"><div class="lb">${lb}</div><div class="val">${val}</div><div class="ht">${ht}</div></div>`;
// hbar: thanh ngang dài theo phần trăm (tối đa 100%), kèm tên và chữ hiển thị
export const hbar = (name, pct, txt, cls = "") => `<div class="hb"><div class="t"><span>${esc(name)}</span><b>${txt}</b></div>
  <div class="track"><div class="fill ${cls}" style="width:${Math.min(pct, 100)}%"></div></div></div>`;
// seg: nhóm nút chọn 1 trong nhiều. opts: [[giá trị, chữ]], fn: tên hàm gọi khi bấm, nhận giá trị
export const seg = (label, opts, val, fn) => `<div class="seg" role="group" aria-label="${label}">${opts.map(([v, t]) =>
  `<button type="button" aria-pressed="${v === val}" data-v="${v}" onclick="${fn}('${v}')">${t}</button>`).join("")}</div>`;
// segSet: đánh dấu lại nút đang chọn trong nhóm seg nằm trong phần tử el
export const segSet = (el, val) => el.querySelectorAll(".seg button").forEach((b) => b.setAttribute("aria-pressed", b.dataset.v === String(val)));
// capCls: màu thanh sức chứa (>= 90% đỏ, >= 80% vàng)
export const capCls = (p) => (p >= 90 ? "bad" : p >= 80 ? "warn" : "");
// expTag: nhãn hạn dùng Hết hạn / Cận date / Còn hạn
export const expTag = (exp, today, near) => exp < today ? `<span class="tag bad">Hết hạn</span>`
  : exp <= near ? `<span class="tag warn">Cận date</span>` : `<span class="tag ok">Còn hạn</span>`;
// loc: nhãn kệ ghi mã vị trí, vd FRZ-02 (bỏ bin thì chỉ ghi mã khu)
export const loc = (zone, bin) => `<span class="loc">${esc(zone)}${bin ? "-" + String(bin).padStart(2, "0") : ""}</span>`;
// slot: số ô -> dãy, ô, tầng (đếm từ 1) theo kích thước kệ của khu z {bays, levels}
//   bin − 1 = ((dãy−1)·bays + (ô−1))·levels + (tầng−1)
export const slot = (bin, z) => {
  const i = bin - 1;
  return { rack: Math.floor(i / (z.bays * z.levels)) + 1, bay: (Math.floor(i / z.levels) % z.bays) + 1, level: (i % z.levels) + 1 };
};
// spot: chữ ghi vị trí ô, vd "dãy B · ô 3 · tầng 2" (dãy ghi bằng chữ A, B, C…)
export const spot = (bin, z) => {
  const s = slot(bin, z);
  return `dãy ${String.fromCharCode(64 + s.rack)} · ô ${s.bay} · tầng ${s.level}`;
};
// STAT: trạng thái tồn của SKU -> [chữ hiển thị, màu tag] (luật tính nằm ở core.py)
export const STAT = { ok: ["Ổn định", "ok"], low: ["Thấp", "warn"], crit: ["Nguy cấp", "bad"] };
// plain: bỏ dấu tiếng Việt và viết thường, để tìm kiếm không cần gõ dấu
export const plain = (s) => String(s ?? "").normalize("NFD").replace(/[\u0300-\u036f]/g, "").replace(/[đĐ]/g, "d").toLowerCase();
// soTag: nhãn trạng thái đơn bán
export const soTag = (s) => `<span class="tag ${SO[s][1]}">${SO[s][0]}</span>`;
// pickList: danh sách các lô đã được chọn (FEFO) cho 1 đơn
export const pickList = (o) => o.picks.map((k) =>
  `<small>Lô ${esc(k.batch_no)} · HSD ${dmy(k.exp)} · ${loc(k.zone, k.bin)} · ${num(k.qty)} thùng</small>`).join("");

// ---------- Điều hướng (router) ----------
// Đọc phần sau dấu # trên địa chỉ (vd #/sku) rồi vẽ trang tương ứng vào <main>.
// page = { id, name, desc, icon, render, after?, leave?, wide? }
//   render(): trả HTML. after(view): chạy sau khi HTML đã lên trang. leave(): dọn dẹp trước khi vẽ trang khác.
let PAGES = [], home, cur, seq = 0;
// Khởi động router: lưu danh sách trang, vẽ lại mỗi khi địa chỉ # thay đổi
export function startRouter(pages, homeFn) {
  PAGES = pages; home = homeFn;
  window.onhashchange = () => { document.getElementById("view").innerHTML = ""; window.scrollTo(0, 0); route(); };
  route();
}

// params: phần sau dấu ? trên địa chỉ, vd #/map?q=SKU-004 -> params().get("q")
export const params = () => new URLSearchParams(location.hash.split("?")[1] || "");

// Vẽ trang ứng với địa chỉ hiện tại: dải menu + nội dung; lỗi tải dữ liệu thì hiện nút "Thử lại"
export async function route() {
  const my = ++seq;   // đánh số lượt vẽ, để lượt cũ tải xong muộn không đè lên trang mới
  const id = location.hash.slice(2).split("?")[0] || "home";
  const page = PAGES.find((p) => p.id === id);
  const view = document.getElementById("view"), nav = document.getElementById("nav");
  const link = (href, on, ic, name) => `<a href="${href}" ${on ? `class="on" aria-current="page"` : ""}>${icon(ic)} ${name}</a>`;
  nav.innerHTML = link("#/", !page, "logo", "Trang chính") + PAGES.map((p) => link("#/" + p.id, p.id === id, p.icon, p.name)).join("");
  nav.scrollLeft = nav.querySelector(".on").offsetLeft - 16;   // màn hình nhỏ: cuộn tới mục đang mở
  if (!view.innerHTML) view.innerHTML = `<div class="skel"></div><div class="skel"></div>`;
  let html, err;
  try {
    html = page ? await page.render() : await home();
  } catch (x) {
    err = true;
    html = `<div class="card empty"><p>Không tải được dữ liệu: ${esc(x.message)}</p>
      <p>Kiểm tra đã chạy <b>python app.py</b> chưa</p><button class="btn" onclick="route()">Thử lại</button></div>`;
  }
  if (my !== seq) return;
  if (cur?.leave) cur.leave();
  cur = err ? null : page;
  closeDrawer();
  document.body.classList.toggle("wide", !!cur?.wide);
  view.innerHTML = html;
  if (cur?.after) cur.after(view);
}

// Cho phép onclick="..." trong HTML gọi được các hàm này
Object.assign(window, { route, closeModal, closeDrawer, run, api });
