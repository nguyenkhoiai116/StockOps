// Feature: Sơ đồ kho - các khu, ô chứa, mức lấp đầy.
import { api, hbar, capCls, openModal, num, esc, dmy } from "../core.js";

let bins = {}; // nhớ thông tin từng ô để bấm vào xem chi tiết

async function render() {
  const d = await api("/layout");
  bins = {};
  const zone = (z) => {
    let cells = "";
    for (let i = 1; i <= d.bins; i++) {
      const b = z.bins.find((x) => x.bin === i);
      if (!b) { cells += `<button class="bin" disabled>${i}</button>`; continue; }
      bins[z.code + i] = { ...b, zone: z };
      const cls = b.exp < d.today ? "bad" : b.exp <= d.near ? "warn" : "ok";
      cells += `<button class="bin has ${cls}" onclick="binShow('${z.code + i}')">${esc(b.sku.replace("SKU-", ""))}<br>${num(b.qty)}</button>`;
    }
    const tOk = z.temp >= z.tmin && z.temp <= z.tmax;
    return `<div class="card"><div class="head" style="margin-bottom:10px"><h2 style="margin:0">${esc(z.name)}</h2>
      <span class="tag ${tOk ? "ok" : "bad"}">${z.temp}°C · ${z.hum}%</span></div>
      ${hbar("Lấp đầy " + num(z.used) + " / " + num(z.cap) + " thùng, còn trống " + num(z.cap - z.used), z.pct, z.pct + "%", capCls(z.pct))}
      <div class="bins">${cells}</div></div>`;
  };
  return `<h1>Sơ đồ kho</h1><p class="sub">Bấm vào ô có hàng để xem chi tiết.
    <span class="tag ok">Còn hạn</span> <span class="tag warn">Cận date</span> <span class="tag bad">Hết hạn</span></p>
    <div class="cols2">${d.zones.map(zone).join("")}</div>`;
}

function binShow(key) {
  const b = bins[key];
  openModal(`<h2>Ô ${b.zone.code}-${String(b.bin).padStart(2, "0")} · ${esc(b.zone.name)}</h2>
    <p><b>${esc(b.sku)}</b> ${esc(b.name)}</p><p>Số lô: <b>${esc(b.batch_no)}</b></p><p>Hạn dùng: <b>${dmy(b.exp)}</b></p>
    <p>Thực có: <b>${num(b.qty)}</b> · Đã giữ: <b>${num(b.reserved)}</b> · Khả dụng: <b>${num(b.qty - b.reserved)}</b></p>
    <p>Nhiệt độ khu: ${b.zone.temp}°C · Độ ẩm: ${b.zone.hum}%</p>
    <div class="acts"><button class="btn" onclick="closeModal()">Đóng</button></div>`);
}
Object.assign(window, { binShow });

export const page = { id: "map", name: "Sơ đồ kho", desc: "Vị trí và mức lấp đầy", icon: "map", render };
