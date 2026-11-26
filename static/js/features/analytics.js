// Feature: Phân tích - KPI và báo cáo.
import { api, can, icon, hbar, kpi, capCls, SO, vnd, num } from "../core.js";

// Vẽ trang Phân tích: 4 thẻ KPI và các biểu đồ thanh ngang theo nhóm hàng, SKU, trạng thái đơn, khu kho
async function render() {
  const d = await api("/analytics"), k = d.kpi;
  // vẽ danh sách thanh ngang, dài theo tỉ lệ với giá trị lớn nhất (giá trị lớn nhất tô màu nhấn)
  const bars = (arr, fmt, name = (x) => x.name) => {
    const m = Math.max(1, ...arr.map((x) => x.val));
    return arr.map((x) => hbar(name(x), (x.val / m) * 100, fmt(x.val), x.val === m ? "top-v" : "")).join("");
  };
  return `<div class="head"><div><h1>Phân tích vận hành</h1><p class="sub">Tổng hợp từ dữ liệu hiện tại</p></div>
    ${can("inv.export") ? `<a class="btn ghost" href="/api/export/inventory.csv">${icon("download")} Xuất CSV tồn kho</a>` : ""}</div>
    <div class="grid">${kpi("OTIF", num(k.otif) + "%", "Đúng hạn / đã giao")}${kpi("Tỷ lệ đáp ứng", num(k.fill) + "%", "Đơn đã đáp ứng / tổng đơn")}
      ${kpi("Sức chứa kho", num(k.cap_pct) + "%", "Thùng đang chứa / sức chứa")}${kpi("Giá trị hàng hết hạn", vnd(k.expired_value), "Nguy cơ hủy")}</div>
    <div class="cols2">
      <div class="card"><h2>Giá trị tồn theo nhóm hàng</h2>${bars(d.by_cat, vnd)}</div>
      <div class="card"><h2>Tồn theo SKU (thùng)</h2>${bars(d.by_sku, num)}</div>
      <div class="card"><h2>Đơn bán theo trạng thái</h2>${bars(d.by_status, num, (x) => SO[x.name][0])}</div>
      <div class="card"><h2>Mức lấp đầy theo khu</h2>${d.by_zone.map((z) => hbar(z.name, z.val, num(z.val) + "%", capCls(z.val))).join("")}</div>
    </div>`;
}

export const page = { perm: ["ana.view"], id: "ana", name: "Phân tích", desc: "KPI và báo cáo", icon: "ana", render };
