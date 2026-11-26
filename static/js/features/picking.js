// Feature: Soạn hàng - đơn bán và FEFO.
import { api, can, table, form, confirmBox, soTag, pickList, dmy, num, esc } from "../core.js";

// Các nút thao tác theo trạng thái đơn: Mới -> Soạn FEFO / Hủy; Đã soạn -> Soạn lại / Hủy
const acts = (o) => [
  o.status === "new" && can("so.pick") ? `<button class="btn sm" onclick="run(() => api('/orders/${o.id}/pick', 'POST'), 'Đã chọn lô theo FEFO')">Soạn FEFO</button>` : "",
  o.status === "picked" && can("so.pick") ? `<button class="btn sm ghost" onclick="run(() => api('/orders/${o.id}/unpick', 'POST'), 'Đã trả hàng giữ, đơn về Mới')">Soạn lại</button>` : "",
  ["new", "picked"].includes(o.status) && can("so.cancel") ? `<button class="btn sm ghost" onclick="soCancel(${o.id})">Hủy</button>` : "",
].join(" ");

// Vẽ bảng đơn bán kèm các lô đã chọn; đơn mới có nút "Soạn FEFO"
async function render() {
  const d = await api("/orders");
  const body = d.orders.map((o) => `<tr><td><b>${o.so_no}</b><small>${esc(o.customer)}</small></td>
    <td>${esc(o.sku)} ${esc(o.name)}${pickList(o)}</td><td class="r">${num(o.qty)}</td><td>${dmy(o.due)}</td><td>${soTag(o.status)}</td>
    <td class="r"><div class="tools" style="justify-content:flex-end">${acts(o)}</div></td></tr>`).join("");
  return `<div class="head"><div><h1>Soạn hàng</h1><p class="sub">FEFO: hệ thống tự chọn lô hết hạn sớm nhất, bỏ lô hết hạn, có thể chia nhiều lô</p></div>
    ${can("so.create") ? `<button class="btn" onclick="soAdd()">Tạo đơn bán</button>` : ""}</div>
    <div class="card">${table(["Đơn", "Sản phẩm / lô được chọn", "SL*", "Hạn giao", "Trạng thái", ""], body)}</div>`;
}

// Mở form tạo đơn bán mới (khách hàng, sản phẩm, số lượng, hạn giao)
async function soAdd() {
  const products = await api("/products");
  form("Tạo đơn bán hàng (SO)", [
    { k: "customer", label: "Khách hàng" }, { k: "product_id", label: "Sản phẩm", opts: products.map((p) => [p.id, p.sku + " " + p.name]) },
    { k: "qty", label: "Số lượng (thùng)", type: "number", val: 10 }, { k: "due", label: "Hạn giao", type: "date", opt: 1 },
  ], (v) => api("/orders", "POST", v));
}
// Hỏi xác nhận rồi hủy đơn; đơn đã soạn thì hàng đang giữ được trả về lô (xem core.do_cancel)
const soCancel = (id) => confirmBox("Hủy đơn này? Hàng đang giữ cho đơn sẽ được trả về kho.", () => api(`/orders/${id}/cancel`, "POST"));
Object.assign(window, { soAdd, soCancel });

export const page = { perm: ["so.pick", "so.create", "so.cancel"], id: "pick", name: "Soạn hàng", desc: "Đơn bán và FEFO", icon: "pick", render };
