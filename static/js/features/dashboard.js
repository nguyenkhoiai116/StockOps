// Feature: Dashboard tổng quan vận hành.
import { api, hbar, kpi, capCls, vnd, num, esc } from "../core.js";

let flow = [];   // số liệu nhập/xuất 7 ngày, giữ lại để đổi kiểu biểu đồ mà không phải tải lại
let mode = "bar"; // kiểu biểu đồ đang xem: "bar" (cột đôi) | "line" (đường)
try { mode = localStorage.getItem("flowMode") === "line" ? "line" : "bar"; } catch { /* trình duyệt chặn lưu trữ */ }

// Biểu đồ cột đôi: mỗi ngày 2 cột Nhập / Xuất, số liệu hiện trên đầu cột
function barChart(max) {
  return `<div class="chart">${flow.map((f) => `<div class="col"><div class="bars">
    <div class="bar inb" style="height:${(f.inb / max) * 100}%" title="Nhập ${num(f.inb)}"><span class="v">${num(f.inb)}</span></div>
    <div class="bar out" style="height:${(f.out / max) * 100}%" title="Xuất ${num(f.out)}"><span class="v">${num(f.out)}</span></div>
    </div><div class="day">${f.day}</div></div>`).join("")}</div>`;
}

// Biểu đồ đường (SVG): 2 đường Nhập / Xuất, mỗi điểm có số liệu; rê chuột vào 1 ngày để làm nổi điểm đó
function lineChart(max) {
  const W = 600, H = 230, top = 26, bottom = 30, h = H - top - bottom, step = W / flow.length;
  const x = (i) => step * (i + 0.5);
  const y = (v) => top + h * (1 - v / max);
  const pts = (k) => flow.map((f, i) => `${x(i)},${y(f[k])}`).join(" ");
  const days = flow.map((f, i) => {
    // Số lớn hơn đặt phía trên điểm, số nhỏ hơn đặt phía dưới để 2 nhãn không đè nhau
    const upIn = f.inb >= f.out;
    return `<g class="pt"><rect class="hit" x="${x(i) - step / 2}" y="0" width="${step}" height="${H}"></rect>
      <line class="guide" x1="${x(i)}" x2="${x(i)}" y1="${top - 8}" y2="${top + h}"></line>
      <circle class="dot inb" cx="${x(i)}" cy="${y(f.inb)}" r="4.5"></circle>
      <circle class="dot out" cx="${x(i)}" cy="${y(f.out)}" r="4.5"></circle>
      <text class="v inb" x="${x(i)}" y="${y(f.inb) + (upIn ? -10 : 19)}">${num(f.inb)}</text>
      <text class="v out" x="${x(i)}" y="${y(f.out) + (upIn ? 19 : -10)}">${num(f.out)}</text>
      <text class="day" x="${x(i)}" y="${H - 8}">${f.day}</text>
      <title>${f.day}: Nhập ${num(f.inb)} · Xuất ${num(f.out)}</title></g>`;
  }).join("");
  return `<svg class="chart-line" viewBox="0 0 ${W} ${H}" role="img" aria-label="Biểu đồ đường nhập xuất 7 ngày">
    <line class="axis" x1="0" x2="${W}" y1="${top + h}" y2="${top + h}"></line>
    <polygon class="area" points="${x(0)},${top + h} ${pts("inb")} ${x(flow.length - 1)},${top + h}"></polygon>
    <polyline class="ln inb" points="${pts("inb")}" pathLength="1"></polyline>
    <polyline class="ln out" points="${pts("out")}" pathLength="1"></polyline>${days}</svg>`;
}

// Vẽ biểu đồ nhập/xuất theo kiểu đang chọn
function flowChart() {
  const max = Math.max(1, ...flow.map((f) => Math.max(f.inb, f.out)));
  return mode === "line" ? lineChart(max) : barChart(max);
}

// Chữ trên nút chuyển: luôn ghi kiểu biểu đồ sẽ chuyển sang
const toggleText = () => (mode === "line" ? "📊 Dạng cột" : "📈 Dạng đường");

// Đổi qua lại cột đôi <-> đường, chỉ vẽ lại phần biểu đồ và nhớ lựa chọn cho lần sau
function flowToggle() {
  mode = mode === "line" ? "bar" : "line";
  try { localStorage.setItem("flowMode", mode); } catch { /* bỏ qua nếu không lưu được */ }
  document.getElementById("flowChart").innerHTML = flowChart();
  document.getElementById("flowBtn").textContent = toggleText();
}
Object.assign(window, { flowToggle });

// Vẽ Dashboard: thẻ KPI, biểu đồ nhập/xuất 7 ngày, sức chứa theo khu, cảnh báo, gợi ý và hoạt động gần đây
async function render() {
  const d = await api("/dashboard"), k = d.kpi;
  flow = d.flow;
  const KIND = { IN: "Nhập", OUT: "Xuất", ADJ: "Điều chỉnh" };
  return `<h1>Operations Dashboard</h1><p class="sub">Số liệu tính trực tiếp từ dữ liệu kho</p>
    <div class="grid">
      ${kpi("OTIF", k.otif + "%", "Giao đúng hạn và đủ hàng")}
      ${kpi("Fulfillment Rate", k.fill + "%", "Đơn đã đáp ứng / tổng đơn")}
      ${kpi("Giá trị tồn kho", vnd(k.value), "Theo giá vốn")}
      ${kpi("Near Expiry Rate", k.near_pct + "%", "Hàng cận date / tổng tồn")}
      ${kpi("Sức chứa kho", k.cap_pct + "%", num(k.total) + " / " + num(k.cap) + " thùng")}
      ${kpi("PO chờ nhận", k.po_wait, "Inbound")}
      ${kpi("Đơn đang xử lý", k.so_open, "Outbound")}
      ${kpi("Cảnh báo", d.alerts.length, "Tồn kho, hạn dùng, nhiệt độ")}
    </div>
    <div class="cols">
      <div class="card"><div class="head card-head"><h2>Nhập / xuất 7 ngày (thùng)</h2>
          <button class="btn sm ghost" id="flowBtn" onclick="flowToggle()">${toggleText()}</button></div>
        <div id="flowChart">${flowChart()}</div>
        <div class="legend"><i class="inb"></i>Nhập<i class="out"></i>Xuất</div></div>
      <div class="card"><h2>Sức chứa theo khu</h2>${d.zones.map((z) => hbar(z.name, z.pct, z.pct + "%", capCls(z.pct))).join("")}</div>
    </div>
    <div class="cols3">
      <div class="card"><h2>Trung tâm cảnh báo</h2><ul class="list">${d.alerts.map((a) =>
        `<li><span class="tag ${a.level === "high" ? "bad" : "warn"}">${a.level === "high" ? "Cao" : "Vừa"}</span> ${esc(a.msg)}</li>`).join("") || `<li>Không có cảnh báo</li>`}</ul></div>
      <div class="card ai"><h2>AI Smart Assistant</h2>${d.tips.map((t) => `<div class="tip"><b>${esc(t.title)}</b><p>${esc(t.detail)}</p></div>`).join("") || "<p>Mọi thứ đang ổn.</p>"}
        <p class="kpi ht">Gợi ý theo luật, cần bạn xác nhận trước khi làm.</p></div>
      <div class="card"><h2>Hoạt động gần đây</h2><ul class="list">${d.acts.map((a) =>
        `<li>${KIND[a.kind]} ${a.qty > 0 ? "+" : ""}${num(a.qty)} · ${esc(a.sku)}<small>${esc(a.note)} · ${a.ts.replace("T", " ")}</small></li>`).join("")}</ul></div>
    </div>`;
}

export const page = { id: "dash", name: "Dashboard", desc: "Tổng quan vận hành", icon: "dashboard", render };
