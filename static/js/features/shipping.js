// Feature: Xuất kho & vận chuyển - chọn xe, giao hàng.
import { api, table, soTag, STORE, dmy, num, esc } from "../core.js";

async function render() {
  const d = await api("/orders");
  const VK = { dry: "Xe thường", cold: "Xe lạnh" };
  const os = d.orders.filter((o) => o.status !== "new");
  const body = os.map((o) => {
    let act = "";
    if (o.status === "picked") act = `<select id="v${o.id}">${d.vehicles.map((v) => `<option value="${v.plate}">${v.plate} (${VK[v.kind]})</option>`).join("")}</select>
      <button class="btn sm" onclick="run(() => api('/orders/${o.id}/ship', 'POST', { plate: document.getElementById('v${o.id}').value }), 'Đã xuất kho')">Xuất kho</button>`;
    if (o.status === "shipping") act = `<button class="btn sm" onclick="run(() => api('/orders/${o.id}/deliver', 'POST'), 'Đã xác nhận giao')">Xác nhận đã giao</button>`;
    if (o.status === "delivered") act = o.on_time ? `<span class="tag ok">Đúng hạn</span>` : `<span class="tag bad">Trễ hạn</span>`;
    return `<tr><td><b>${o.so_no}</b><small>${esc(o.customer)}</small></td><td>${esc(o.sku)} ${esc(o.name)}<small>${STORE[o.storage]} · ${num(o.qty)} thùng</small></td>
      <td>${dmy(o.due)}</td><td>${o.plate || "-"}</td><td>${soTag(o.status)}</td><td class="r"><div class="tools" style="justify-content:flex-end">${act}</div></td></tr>`;
  }).join("");
  return `<h1>Xuất kho và vận chuyển</h1><p class="sub">Hàng mát / đông lạnh chỉ được xếp lên xe lạnh. Xuất kho mới trừ tồn thật.</p>
    <div class="card">${table(["Đơn", "Hàng", "Hạn giao", "Xe", "Trạng thái", ""], body)}</div>
    <div class="card"><h2>Đội xe</h2>${table(["Biển số", "Tài xế", "Loại"], d.vehicles.map((v) =>
      `<tr><td><b>${v.plate}</b></td><td>${esc(v.driver)}</td><td><span class="tag info">${VK[v.kind]}</span></td></tr>`).join(""))}</div>`;
}

export const page = { id: "ship", name: "Xuất kho", desc: "Xe và giao hàng", icon: "ship", render };
