// Feature: Soạn hàng - đơn bán theo kênh khách hàng, FEFO, đơn bị trả về và lộ trình lấy hàng tối ưu.
import { api, can, table, form, soTag, pickList, loc, dmy, num, esc } from "../core.js";

const CH_NAME = { sieuthi: "Siêu thị", daily: "Đại lý", taphoa: "Tạp hóa" };

async function render() {
  const d = await api("/orders");
  const returned = d.orders.filter((o) => o.audit_status === "returned");
  const body = d.orders.map((o) => {
    const chTag = `<span class="tag">${CH_NAME[o.channel] || o.channel} ≥${o.min_shelf_pct || 40}% HSD</span>`;
    const retNote = o.audit_status === "returned"
      ? `<small style="color:var(--bad)"><b>Xuất kho trả về:</b> ${esc(o.audit_note || "Cần soạn lại / hoán đổi lô")}</small>` : "";
    return `<tr><td><b>${o.so_no}</b><small>${esc(o.customer)} · Tuyến ${esc(o.route_zone || "Q1")}</small>${chTag}</td>
      <td>${esc(o.sku)} ${esc(o.name)}${pickList(o)}${retNote}</td><td class="r">${num(o.qty)}</td><td>${dmy(o.due)}</td><td>${soTag(o.status)}</td>
      <td class="r">${o.status === "new" && can("so.pick") ? `<button class="btn sm" onclick="run(() => api('/orders/${o.id}/pick', 'POST'), 'Đã chọn lô theo FEFO')">Soạn FEFO</button>` : ""}</td></tr>`;
  }).join("");

  const routeRows = (d.routes || []).map((r) => `<tr><td><b>#${r.step}</b></td><td><span class="tag ${r.zone === "CHL" || r.zone === "FRZ" ? "info" : ""}">${esc(r.phase)}</span></td>
    <td>${loc(r.zone, r.bin)}<small>${esc(r.spot)}</small></td><td><b>${esc(r.so_no)}</b> · ${esc(r.sku)} (${esc(r.batch_no)})</td><td class="r"><b>${num(r.qty)}</b></td></tr>`).join("");

  return `<div class="head"><div><h1>Soạn hàng & Đóng gói</h1>
    <p class="sub">FEFO tự chọn lô hết hạn sớm nhất (loại lô hết hạn/cách ly), theo dõi chuẩn % HSD từng kênh và tối ưu lộ trình lấy hàng</p></div>
    ${can("so.create") ? `<button class="btn" onclick="soAdd()">Tạo đơn bán</button>` : ""}</div>
    ${returned.length ? `<div class="callout bad"><b>Có ${returned.length} đơn bị bộ phận Xuất kho trả về:</b> kiểm tra cột sản phẩm bên dưới để đổi lô đạt chuẩn % HSD kênh khách hàng.</div>` : ""}
    <div class="card"><h2>Danh sách đơn bán (SO)</h2>${table(["Đơn / Kênh", "Sản phẩm / Lô FEFO", "SL*", "Hạn giao", "Trạng thái", ""], body)}</div>
    <div class="card"><h2>Lộ trình lấy hàng tối ưu (S-Shape: Khô trước → Hàng lạnh lấy cuối)</h2>
      ${table(["Thứ tự", "Chặng", "Vị trí kệ", "Đơn / Lô", "SL*"], routeRows)}</div>`;
}

async function soAdd() {
  const [products, ord] = await Promise.all([api("/products"), api("/orders")]);
  const custOpts = (ord.customers || []).map((c) => [c.name, `${c.name} (${CH_NAME[c.channel]} ≥${c.min_shelf_pct}% HSD · ${c.route_zone})`]);
  form("Tạo đơn bán hàng (SO)", [
    custOpts.length ? { k: "customer", label: "Khách hàng (tự áp chuẩn % HSD kênh)", opts: custOpts } : { k: "customer", label: "Khách hàng" },
    { k: "product_id", label: "Sản phẩm", opts: products.map((p) => [p.id, p.sku + " " + p.name]) },
    { k: "qty", label: "Số lượng (thùng)", type: "number", val: 20 },
    { k: "due", label: "Hạn giao (SLA)", type: "date", opt: 1 },
  ], (v) => api("/orders", "POST", { ...v, strict_stock: true }));
}
Object.assign(window, { soAdd });

export const page = { perm: ["so.pick", "so.create"], id: "pick", name: "Soạn hàng", desc: "Đơn bán, FEFO & lộ trình", icon: "pick", render };
