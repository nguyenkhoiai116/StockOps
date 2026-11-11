// Feature: Soạn hàng - đơn bán và FEFO.
import { api, table, form, soTag, pickList, dmy, num, esc } from "../core.js";

async function render() {
  const d = await api("/orders");
  const body = d.orders.map((o) => `<tr><td><b>${o.so_no}</b><small>${esc(o.customer)}</small></td>
    <td>${esc(o.sku)} ${esc(o.name)}${pickList(o)}</td><td class="r">${num(o.qty)}</td><td>${dmy(o.due)}</td><td>${soTag(o.status)}</td>
    <td class="r">${o.status === "new" ? `<button class="btn sm" onclick="run(() => api('/orders/${o.id}/pick', 'POST'), 'Đã chọn lô theo FEFO')">Soạn FEFO</button>` : ""}</td></tr>`).join("");
  return `<div class="head"><div><h1>Soạn hàng</h1><p class="sub">FEFO: hệ thống tự chọn lô hết hạn sớm nhất, bỏ lô hết hạn, có thể chia nhiều lô</p></div>
    <button class="btn" onclick="soAdd()">+ Tạo đơn bán</button></div>
    <div class="card">${table(["Đơn", "Sản phẩm / lô được chọn", "SL*", "Hạn giao", "Trạng thái", ""], body)}</div>`;
}

async function soAdd() {
  const products = await api("/products");
  form("Tạo đơn bán hàng (SO)", [
    { k: "customer", label: "Khách hàng" }, { k: "product_id", label: "Sản phẩm", opts: products.map((p) => [p.id, p.sku + " " + p.name]) },
    { k: "qty", label: "Số lượng (thùng)", type: "number", val: 10 }, { k: "due", label: "Hạn giao", type: "date", opt: 1 },
  ], (v) => api("/orders", "POST", v));
}
Object.assign(window, { soAdd });

export const page = { id: "pick", name: "Soạn hàng", desc: "Đơn bán và FEFO", icon: "pick", render };
