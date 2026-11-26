// Feature: Dashboard tổng quan vận hành.
import { api, can, hbar, kpi, capCls, seg, segSet, table, openDrawer, expTag, loc, plain, STAT, toast, vnd, num, dmy, dmyt, esc } from "../core.js";
import { flowChart } from "../chart.js";

let d = null;        // số liệu Dashboard đang hiện
let days = "7";      // số ngày của biểu đồ: 7 | 14 | 30
let mode = "line";   // kiểu biểu đồ: line (đường) | bar (cột) | table (bảng)
let stop = null;     // hàm dọn dẹp của biểu đồ
try { mode = { bar: "bar", table: "table" }[localStorage.getItem("flowMode")] || "line"; } catch { /* trình duyệt chặn lưu trữ */ }

// Vẽ lại biểu đồ theo số ngày và kiểu đang chọn
function draw() {
  const box = document.getElementById("flowChart");
  if (!box) return;
  if (stop) stop();
  stop = flowChart(box, d.flow, mode);
}

// Đổi kiểu biểu đồ và nhớ lựa chọn cho lần sau
function flowMode(v) {
  mode = v;
  try { localStorage.setItem("flowMode", v); } catch { /* bỏ qua nếu không lưu được */ }
  segSet(document.getElementById("modeSeg"), v);
  draw();
}

// Đổi số ngày: chỉ tải lại số liệu biểu đồ; nếu bấm nhiều lần thì chỉ lấy lần cuối
async function flowDays(v) {
  days = v;
  segSet(document.getElementById("daySeg"), v);
  try {
    const x = await api("/dashboard?days=" + v);
    if (days !== v) return;
    d.flow = x.flow;
    draw();
  } catch (x) { toast(x.message, false); }
}

// Nhãn trạng thái tồn của SKU
const stTag = (s) => `<span class="tag ${STAT[s][1]}">${STAT[s][0]}</span>`;

// Vẽ bảng hàng theo từ khóa, khu và trạng thái đang lọc
function itemFilter() {
  const v = (id) => document.getElementById(id).value, q = plain(v("itQ"));
  const list = d.items.filter((p) => plain(p.sku + " " + p.name).includes(q)
    && (!v("itZ") || p.zones.includes(v("itZ"))) && (!v("itS") || p.status === v("itS")));
  document.getElementById("items").innerHTML = table(["Sản phẩm", "Khu", "Thực có*", "Khả dụng*", "Tồn an toàn*", "Trạng thái"], list.map((p) =>
    `<tr class="pick" data-sku="${esc(p.sku)}"><td><button class="lnk">${esc(p.sku)}</button><small>${esc(p.name)}</small></td>
      <td>${p.zones.map((z) => loc(z)).join(" ") || "-"}</td><td class="r">${num(p.qty)}</td><td class="r"><b>${num(p.av)}</b></td>
      <td class="r">${num(p.safety)}</td><td>${stTag(p.status)}</td></tr>`).join(""));
}

// Mở ngăn chi tiết 1 SKU: tồn và các lô đang có
async function itemShow(sku) {
  const p = d.items.find((x) => x.sku === sku);
  let inv = null;   // role không được xem tồn theo lô thì chỉ hiện số tổng
  if (can("inv.view")) try { inv = await api("/inventory"); } catch (x) { return toast(x.message, false); }
  const lots = inv ? inv.batches.filter((b) => b.sku === sku) : [];
  openDrawer(sku, `<dl class="kv"><dt>Sản phẩm</dt><dd>${esc(p.name)}</dd><dt>Trạng thái</dt><dd>${stTag(p.status)}</dd>
    <dt>Thực có</dt><dd>${num(p.qty)} thùng</dd><dt>Khả dụng</dt><dd><b>${num(p.av)} thùng</b></dd><dt>Tồn an toàn</dt><dd>${num(p.safety)} thùng</dd></dl>
    ${inv ? `<h3>Các lô đang có</h3><ul class="list">${lots.map((b) => `<li>${loc(b.zone, b.bin)} <b>${esc(b.batch_no)}</b> ${expTag(b.exp, inv.today, inv.near)}
      <small>${num(b.qty)} thùng, hạn dùng ${dmy(b.exp)}</small></li>`).join("") || "<li>Không còn lô nào</li>"}</ul>` : ""}
    ${lots.length && can("map.view") ? `<div class="acts"><a class="btn" href="#/map?q=${encodeURIComponent(sku)}">Xem trong kho</a></div>` : ""}`);
}
Object.assign(window, { flowMode, flowDays, itemFilter });

// Vẽ Dashboard: chỉ số, biểu đồ nhập/xuất, sức chứa, bảng hàng, cảnh báo, gợi ý và hoạt động gần đây
async function render() {
  d = await api("/dashboard?days=" + days);
  const k = d.kpi, KIND = { IN: "Nhập", OUT: "Xuất", ADJ: "Điều chỉnh" };
  return `<h1>Tổng quan vận hành</h1><p class="sub">Số liệu tính trực tiếp từ dữ liệu kho</p>
    <div class="kpis">
      ${kpi("Tổng tồn kho", num(k.total), `Thùng, chiếm ${num(k.cap_pct)}% của ${num(k.cap)}`)}
      ${kpi("Tỷ lệ đáp ứng", num(k.fill) + "%", "Đơn đã đáp ứng / tổng đơn")}
      ${kpi("OTIF", num(k.otif) + "%", "Giao đúng hạn và đủ hàng")}
      ${kpi("Cảnh báo", d.alerts.length, "Tồn kho, hạn dùng, nhiệt độ").replace('class="val"', `class="val ${d.alerts.length ? "bad" : ""}"`)}
    </div>
    <div class="grid">
      ${kpi("Giá trị tồn kho", vnd(k.value), "Theo giá vốn")}
      ${kpi("Tỷ lệ cận date", num(k.near_pct) + "%", "Hàng cận date / tổng tồn")}
      ${kpi("PO chờ nhận", num(k.po_wait), "Đơn mua chưa nhận hàng")}
      ${kpi("Đơn đang xử lý", num(k.so_open), "Đơn bán chưa giao xong")}
    </div>
    <div class="cols">
      <div class="card"><div class="head card-head"><h2>Nhập và xuất (thùng)</h2><div class="tools">
          <span id="daySeg">${seg("Số ngày", [["7", "7 ngày"], ["14", "14 ngày"], ["30", "30 ngày"]], days, "flowDays")}</span>
          <span id="modeSeg">${seg("Kiểu biểu đồ", [["line", "Đường"], ["bar", "Cột"], ["table", "Bảng"]], mode, "flowMode")}</span></div></div>
        <div id="flowChart" class="plot"></div>
        <div class="legend"><span><i class="inb"></i>Nhập</span><span><i class="out"></i>Xuất</span></div></div>
      <div class="card"><h2>Sức chứa theo khu</h2>${d.zones.map((z) => hbar(z.name, z.pct, num(z.pct) + "%", capCls(z.pct))).join("")}</div>
    </div>
    <div class="card"><h2>Tồn theo sản phẩm</h2>
      <div class="filters"><input id="itQ" type="search" placeholder="Tìm mã, tên" aria-label="Tìm mã, tên sản phẩm" oninput="itemFilter()">
        <select id="itZ" aria-label="Khu kho" onchange="itemFilter()"><option value="">Mọi khu</option>${d.zones.map((z) => `<option value="${z.code}">${esc(z.name)}</option>`).join("")}</select>
        <select id="itS" aria-label="Trạng thái" onchange="itemFilter()"><option value="">Mọi trạng thái</option>${Object.entries(STAT).map(([v, t]) => `<option value="${v}">${t[0]}</option>`).join("")}</select></div>
      <div id="items"></div></div>
    <div class="cols3">
      <div class="card"><h2>Cảnh báo</h2><ul class="list">${d.alerts.map((a) =>
        `<li class="al"><span class="tag ${a.level === "high" ? "bad" : "warn"}">${a.level === "high" ? "Cao" : "Vừa"}</span><span>${esc(a.msg)}</span></li>`).join("") || `<li>Không có cảnh báo</li>`}</ul></div>
      <div class="card"><h2>Gợi ý xử lý</h2><ul class="list">${d.tips.map((t) => `<li><b>${esc(t.title)}</b><small>${esc(t.detail)}</small></li>`).join("") || `<li>Không có gợi ý</li>`}</ul>
        <p class="note">Gợi ý theo luật, cần bạn xác nhận trước khi làm</p></div>
      <div class="card"><h2>Hoạt động gần đây</h2><ul class="list">${d.acts.map((a) =>
        `<li>${KIND[a.kind]} ${a.qty > 0 ? "+" : ""}${num(a.qty)} · ${esc(a.sku)}<small>${esc(a.note)} · ${dmyt(a.ts)}</small></li>`).join("")}</ul></div>
    </div>`;
}

// Sau khi HTML lên trang: vẽ biểu đồ, bảng và gắn thao tác bấm dòng
function after() {
  draw();
  itemFilter();
  document.getElementById("items").onclick = (e) => {
    const tr = e.target.closest("tr.pick");
    if (tr) itemShow(tr.dataset.sku);
  };
}
function leave() { if (stop) stop(); stop = null; }

export const page = { perm: ["dash.view"], id: "dash", name: "Tổng quan", desc: "Chỉ số và cảnh báo", icon: "dashboard", render, after, leave };
