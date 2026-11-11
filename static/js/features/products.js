// Feature: SKU Master - danh mục sản phẩm.
import { api, table, form, confirmBox, STORE, num, esc } from "../core.js";

let ps = []; // giữ tạm danh sách để các nút dùng lại

async function render() {
  ps = await api("/products");
  const body = ps.map((p) => `<tr data-q="${esc((p.sku + " " + p.name + " " + p.cat + " " + p.storage).toLowerCase())}">
    <td><b>${esc(p.sku)}</b></td><td>${esc(p.name)}<small>${esc(p.supplier)}</small></td><td>${esc(p.cat)}</td>
    <td><span class="tag info">${STORE[p.storage]}</span></td><td class="r">${num(p.price)}</td><td class="r">${num(p.safety)}</td>
    <td class="r">${num(p.stock)}</td><td class="r"><button class="btn sm ghost" onclick="skuDel(${p.id})">Xóa</button></td></tr>`).join("");
  return `<div class="head"><div><h1>SKU Master</h1><p class="sub">${ps.length} sản phẩm</p></div>
    <div class="tools"><input placeholder="Tìm mã, tên..." oninput="skuFind()" id="q">
      <select id="st" onchange="skuFind()"><option value="">Mọi loại kho</option>${Object.entries(STORE).map(([k, v]) => `<option value="${k}">${v}</option>`).join("")}</select>
      <button class="btn" onclick="skuAdd()">+ Thêm SKU</button></div></div>
    <div class="card">${table(["SKU", "Tên", "Nhóm", "Loại kho", "Giá vốn*", "Tồn an toàn*", "Tồn*", ""], body)}</div>`;
}

// Lọc ngay trên trình duyệt: ẩn dòng không khớp từ khóa / loại kho
function skuFind() {
  const q = document.getElementById("q").value.toLowerCase(), st = document.getElementById("st").value;
  document.querySelectorAll("tbody tr").forEach((tr) => (tr.hidden = !(tr.dataset.q.includes(q) && tr.dataset.q.includes(st))));
}
function skuAdd() {
  form("Thêm sản phẩm", [
    { k: "sku", label: "Mã SKU", val: "SKU-0" + (ps.length + 1) }, { k: "name", label: "Tên sản phẩm" },
    { k: "cat", label: "Nhóm hàng", opt: 1 }, { k: "storage", label: "Loại kho", opts: Object.entries(STORE) },
    { k: "price", label: "Giá vốn (đ/thùng)", type: "number", val: 100000 }, { k: "safety", label: "Tồn an toàn", type: "number", val: 50 },
    { k: "supplier", label: "Nhà cung cấp", opt: 1 },
  ], (v) => api("/products", "POST", v));
}
const skuDel = (id) => confirmBox("Xóa sản phẩm này?", () => api("/products/" + id, "DELETE"));
Object.assign(window, { skuFind, skuAdd, skuDel }); // cho onclick trong HTML gọi được

export const page = { id: "sku", name: "SKU Master", desc: "Danh mục sản phẩm", icon: "sku", render };
