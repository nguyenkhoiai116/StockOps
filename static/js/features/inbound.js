// Feature: Nhập hàng - PO và nhận hàng theo lô.
import { api, table, form, dmy, num, esc } from "../core.js";

let pos = [];

async function render() {
  pos = await api("/pos");
  const body = pos.map((o) => `<tr><td><b>${o.po_no}</b></td><td>${esc(o.sku)} ${esc(o.name)}<small>${esc(o.supplier)}</small></td>
    <td class="r">${num(o.qty)}</td><td>${dmy(o.eta)}</td>
    <td>${o.status === "pending" ? `<span class="tag warn">Chờ nhận</span>` : `<span class="tag ok">Đã nhận ${num(o.recv)}</span>${o.dmg ? ` <span class="tag bad">Hỏng ${o.dmg}</span>` : ""}`}</td>
    <td class="r">${o.status === "pending" ? `<button class="btn sm" onclick="poRecv(${o.id})">Nhận hàng</button>` : ""}</td></tr>`).join("");
  return `<div class="head"><div><h1>Nhập hàng</h1><p class="sub">Nhận hàng sẽ tạo lô mới và cộng tồn kho</p></div>
    <button class="btn" onclick="poAdd()">+ Tạo PO</button></div>
    <div class="card">${table(["PO", "Sản phẩm", "SL đặt*", "Ngày đến", "Trạng thái", ""], body)}</div>`;
}

async function poAdd() {
  const products = await api("/products");
  form("Tạo đơn mua hàng (PO)", [
    { k: "product_id", label: "Sản phẩm", opts: products.map((p) => [p.id, p.sku + " " + p.name]) },
    { k: "qty", label: "Số lượng đặt (thùng)", type: "number", val: 100 }, { k: "eta", label: "Ngày dự kiến đến", type: "date", opt: 1 },
  ], (v) => api("/pos", "POST", v));
}
function poRecv(id) {
  const o = pos.find((x) => x.id === id);
  form("Nhận hàng " + o.po_no, [
    { k: "batch_no", label: "Số lô (Batch)", val: "L" + Date.now().toString().slice(-5) },
    { k: "exp", label: "Hạn sử dụng", type: "date" },
    { k: "qty", label: "Số lượng đạt (thùng)", type: "number", val: o.qty },
    { k: "dmg", label: "Số lượng hỏng (không nhập kho)", type: "number", val: 0 },
  ], (v) => api(`/pos/${id}/receive`, "POST", v), "Nhận vào kho");
}
Object.assign(window, { poAdd, poRecv });

export const page = { id: "inb", name: "Nhập hàng", desc: "PO và nhận hàng theo lô", icon: "inb", render };
