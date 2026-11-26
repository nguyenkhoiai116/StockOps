// Feature: Tồn kho - theo lô, điều chỉnh, lịch sử, xuất CSV.
import { api, can, icon, loc, table, form, expTag, dmy, dmyt, num, esc } from "../core.js";

let bs = []; // giữ danh sách lô để nút "Điều chỉnh" lấy lại thông tin

// Vẽ bảng tồn kho theo lô (thực có, đã giữ, khả dụng) và lịch sử giao dịch gần nhất
async function render() {
  const d = await api("/inventory");
  bs = d.batches;
  const KIND = { IN: ["Nhập", "ok"], OUT: ["Xuất", "info"], ADJ: ["Điều chỉnh", "warn"] };
  const body = d.batches.map((b) => `<tr><td><b>${esc(b.sku)}</b><small>${esc(b.name)}</small></td><td>${esc(b.batch_no)}</td>
    <td>${dmy(b.exp)} ${expTag(b.exp, d.today, d.near)}</td><td>${loc(b.zone, b.bin)}</td>
    <td class="r">${num(b.qty)}</td><td class="r">${num(b.reserved)}</td><td class="r"><b>${num(b.qty - b.reserved)}</b></td>
    <td class="r">${can("inv.adjust") ? `<button class="btn sm ghost" onclick="invAdj(${b.id})">Điều chỉnh</button>` : ""}</td></tr>`).join("");
  const hist = d.txs.map((t) => `<tr><td>${dmyt(t.ts)}</td><td><span class="tag ${KIND[t.kind][1]}">${KIND[t.kind][0]}</span></td>
    <td>${esc(t.sku)}</td><td>${esc(t.batch_no)}</td><td class="r">${t.qty > 0 ? "+" : ""}${num(t.qty)}</td><td>${esc(t.note)}</td>
    <td>${esc(t.who || "Hệ thống")}</td></tr>`).join("");
  return `<div class="head"><div><h1>Tồn kho</h1><p class="sub">Khả dụng bằng thực có trừ đã giữ cho đơn, xếp theo hạn dùng gần nhất</p></div>
    ${can("inv.export") ? `<a class="btn ghost" href="/api/export/inventory.csv">${icon("download")} Xuất CSV</a>` : ""}</div>
    <div class="card">${table(["Sản phẩm", "Lô", "Hạn dùng", "Vị trí", "Thực có*", "Đã giữ*", "Khả dụng*", ""], body)}</div>
    <div class="card"><h2>Lịch sử giao dịch kho</h2>${table(["Thời gian", "Loại", "SKU", "Lô", "SL*", "Ghi chú", "Người làm"], hist)}</div>`;
}

// Mở form điều chỉnh số lượng của 1 lô (số âm để giảm) kèm lý do
function invAdj(id) {
  const b = bs.find((x) => x.id === id);
  form(`Điều chỉnh lô ${b.batch_no} (đang có ${b.qty})`, [
    { k: "delta", label: "Số thay đổi (âm để giảm, vd -5)", type: "number", val: -1 },
    { k: "note", label: "Lý do", val: "Kiểm kê lệch" },
  ], (v) => api(`/inventory/${id}/adjust`, "POST", v));
}
Object.assign(window, { invAdj });

export const page = { perm: ["inv.view"], id: "inv", name: "Tồn kho", desc: "Theo lô, hạn dùng", icon: "inv", render };
