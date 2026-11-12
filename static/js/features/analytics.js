// Feature: Phân tích - KPI và báo cáo.
import { api, hbar, kpi, capCls, SO, vnd, num } from "../core.js";

// Vẽ trang Phân tích: 4 thẻ KPI và các biểu đồ thanh ngang theo nhóm hàng, SKU, trạng thái đơn, khu kho
async function render() {
  const d = await api("/analytics"), k = d.kpi;
  // vẽ danh sách thanh ngang, dài theo tỉ lệ với giá trị lớn nhất
  const bars = (arr, fmt, name = (x) => x.name) => {
    const m = Math.max(1, ...arr.map((x) => x.val));
    return arr.map((x) => hbar(name(x), (x.val / m) * 100, fmt(x.val))).join("");
  };
  return `<div class="head"><div><h1>Phân tích vận hành</h1><p class="sub">Tổng hợp từ dữ liệu hiện tại</p></div>
    <a class="btn ghost" href="/api/export/inventory.csv">⬇ Xuất CSV tồn kho</a></div>
    <div class="grid">${kpi("OTIF", k.otif + "%", "Đúng hạn / đã giao")}${kpi("Fulfillment", k.fill + "%", "Đơn đã đáp ứng")}
      ${kpi("Sử dụng kho", k.cap_pct + "%", "Warehouse Utilization")}${kpi("Giá trị hàng hết hạn", vnd(k.expired_value), "Nguy cơ hủy (write-off)")}</div>
    <div class="cols2">
      <div class="card"><h2>Giá trị tồn theo nhóm hàng</h2>${bars(d.by_cat, vnd)}</div>
      <div class="card"><h2>Tồn theo SKU (thùng)</h2>${bars(d.by_sku, num)}</div>
      <div class="card"><h2>Đơn bán theo trạng thái</h2>${bars(d.by_status, num, (x) => SO[x.name][0])}</div>
      <div class="card"><h2>Mức lấp đầy theo khu</h2>${d.by_zone.map((z) => hbar(z.name, z.val, z.val + "%", capCls(z.val))).join("")}</div>
    </div>`;
}

export const page = { id: "ana", name: "Phân tích", desc: "KPI và báo cáo", icon: "ana", render };
