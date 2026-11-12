// Feature: Dashboard tổng quan vận hành.
import { api, hbar, kpi, capCls, vnd, num, esc } from "../core.js";

// Vẽ Dashboard: thẻ KPI, biểu đồ nhập/xuất 7 ngày, sức chứa theo khu, cảnh báo, gợi ý và hoạt động gần đây
async function render() {
  const d = await api("/dashboard"), k = d.kpi;
  const max = Math.max(1, ...d.flow.map((f) => Math.max(f.inb, f.out)));
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
      <div class="card"><h2>Nhập / xuất 7 ngày (thùng)</h2>
        <div class="chart">${d.flow.map((f) => `<div class="col"><div class="bars">
          <div class="bar inb" style="height:${(f.inb / max) * 100}%" title="Nhập ${f.inb}"></div>
          <div class="bar out" style="height:${(f.out / max) * 100}%" title="Xuất ${f.out}"></div></div><div class="day">${f.day}</div></div>`).join("")}</div>
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
