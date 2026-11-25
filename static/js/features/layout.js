// Feature: Sơ đồ kho 2D / 3D - khu, ô chứa, mức đầy, tìm vị trí hàng.
import { api, loc, hbar, capCls, expTag, seg, segSet, params, plain, toast, num, esc, dmy } from "../core.js";

let d = null;          // dữ liệu /api/layout
let bins = {};         // key (vd DRY3) -> thông tin ô có hàng, kèm khu
let mode = "3d";       // 2d | 3d
let color = "exp";     // exp: theo hạn dùng | fill: theo mức đầy của khu
let zone = "", q = "", sel = null;   // khu đang xem, từ khóa tìm, ô đang chọn
let view3d = null, turn = 0;         // cảnh 3D đang mở; số lượt vẽ để bỏ lượt tải 3D cũ
try { mode = localStorage.getItem("whMode") === "2d" ? "2d" : "3d"; } catch { /* trình duyệt chặn lưu trữ */ }

const EXP = { ok: ["#2f9e72", "Còn hạn"], warn: ["#e0a12b", "Cận date"], bad: ["#d24d4d", "Hết hạn"] };
const RAMP = [[214, 225, 248], [47, 98, 214]];   // mức đầy thấp -> cao (dưới 80%)
const no = (i) => String(i).padStart(2, "0");    // số ô 2 chữ số, khớp với nhãn kệ
const code = (b) => b.zone.code + "-" + no(b.bin);

// Màu theo mức đầy của khu: xanh nhạt -> đậm, từ 80% vàng, từ 90% đỏ (cùng ngưỡng với capCls)
function fillColor(p) {
  const c = capCls(p);
  if (c) return EXP[c][0];
  const k = Math.min(1, p / 80);
  return `rgb(${RAMP[0].map((a, i) => Math.round(a + (RAMP[1][i] - a) * k)).join(",")})`;
}
const expOf = (b) => (b.exp < d.today ? "bad" : b.exp <= d.near ? "warn" : "ok");
const colorOf = (key) => (color === "exp" ? EXP[expOf(bins[key])][0] : fillColor(bins[key].zone.pct));

// Các ô khớp từ khóa (mã, tên, số lô, vị trí); không tìm gì thì trả null
function found() {
  const t = plain(q.trim());
  return t ? new Set(Object.keys(bins).filter((k) => {
    const b = bins[k];
    return plain([b.sku, b.name, b.batch_no, code(b)].join(" ")).includes(t);
  })) : null;
}

const legend = () => (color === "exp"
  ? Object.values(EXP).map(([c, t]) => `<span><i style="background:${c}"></i>${t}</span>`).join("")
  : `<span>0% <i class="ramp" style="background:linear-gradient(90deg,${fillColor(0)},${fillColor(79.9)})"></i> 80%</span>
     <span><i style="background:${EXP.warn[0]}"></i>Từ 80%</span><span><i style="background:${EXP.bad[0]}"></i>Từ 90%</span><span>Mức đầy tính theo khu</span>`)
  + `<span><i class="no"></i>Ô trống</span>`;

// Danh sách khu bên trái
const zoneList = () => `<button type="button" aria-pressed="${!zone}" onclick="whZone('')"><span class="nm" style="margin:0">Toàn kho</span></button>`
  + d.zones.map((z) => `<button type="button" aria-pressed="${zone === z.code}" onclick="whZone('${z.code}')">
    <span class="nm"><span>${esc(z.name)}</span>${loc(z.code)}</span><div class="track"><div class="fill ${capCls(z.pct)}" style="width:${Math.min(z.pct, 100)}%"></div></div>
    <small>${num(z.used)} / ${num(z.cap)} thùng, ${num(z.pct)}%</small>
    <small class="${z.temp >= z.tmin && z.temp <= z.tmax ? "" : "bad"}">${num(z.temp)}°C, ẩm ${num(z.hum)}%${z.temp >= z.tmin && z.temp <= z.tmax ? "" : ", ngoài ngưỡng"}</small></button>`).join("");

// Khung chi tiết bên phải: ô đang chọn, hoặc kết quả tìm, hoặc hướng dẫn
function info() {
  const b = bins[sel], f = found();
  if (b) return `<h2>${loc(b.zone.code, b.bin)} ${esc(b.zone.name)}</h2>
    <dl class="kv"><dt>Sản phẩm</dt><dd><b>${esc(b.sku)}</b> ${esc(b.name)}</dd><dt>Số lô</dt><dd>${esc(b.batch_no)}</dd>
    <dt>Hạn dùng</dt><dd>${dmy(b.exp)} ${expTag(b.exp, d.today, d.near)}</dd><dt>Thực có</dt><dd>${num(b.qty)} thùng</dd><dt>Đã giữ</dt><dd>${num(b.reserved)} thùng</dd>
    <dt>Khả dụng</dt><dd><b>${num(b.qty - b.reserved)} thùng</b></dd></dl>
    <h3>Khu ${esc(b.zone.name)}</h3>${hbar("Mức đầy", b.zone.pct, num(b.zone.pct) + "%", capCls(b.zone.pct))}
    <dl class="kv"><dt>Nhiệt độ</dt><dd>${num(b.zone.temp)}°C</dd><dt>Độ ẩm</dt><dd>${num(b.zone.hum)}%</dd></dl>`;
  if (f) return `<h2>Tìm thấy ${f.size} ô</h2>${[...f].map((k) => `<button class="found" onclick="whPick('${k}')"><span><b>${esc(bins[k].sku)}</b> ${num(bins[k].qty)} thùng</span>${loc(bins[k].zone.code, bins[k].bin)}</button>`).join("")
    || `<p class="note">Không có ô nào khớp từ khóa</p>`}`;
  return `<h2>Chi tiết ô</h2><p class="note" style="margin:0">Bấm vào một khối hàng để xem lô, hạn dùng và số lượng, hoặc tìm theo mã, tên, số lô</p>`;
}

// Sơ đồ 2D: mỗi khu 1 lưới ô
function html2d() {
  const f = found();
  return `<div class="wh-2d">${d.zones.filter((z) => !zone || z.code === zone).map((z) => {
    let cells = "";
    for (let i = 1; i <= d.bins; i++) {
      const k = z.code + i, b = bins[k];
      cells += b ? `<button class="bin has ${f && !f.has(k) ? "dim" : ""}" aria-pressed="${sel === k}" style="--c:${colorOf(k)}" onclick="whPick('${k}')"
          title="${esc(b.name)}, ${EXP[expOf(b)][1].toLowerCase()}"><span class="no">${no(i)}</span><span><span class="sk">${esc(b.sku)}</span><span class="q">${num(b.qty)}</span></span></button>`
        : `<button class="bin" disabled><span class="no">${no(i)}</span></button>`;
    }
    return `<section><h2>${esc(z.name)} ${loc(z.code)}</h2><div class="bins">${cells}</div></section>`;
  }).join("")}</div>`;
}

// Cập nhật phần chữ quanh khung (khu, chi tiết, chú giải, nút chọn)
function sync() {
  const set = (id, h) => { document.getElementById(id).innerHTML = h; };
  set("whZones", zoneList()); set("whInfo", info()); set("whLegend", legend());
  segSet(document.getElementById("whMode"), mode); segSet(document.getElementById("whColor"), color);
}
// Áp màu, kết quả tìm và ô đang chọn lên khung đang hiện
function apply() {
  if (view3d) { view3d.paint(colorOf); view3d.dim(found()); view3d.select(sel); }
  else if (mode === "2d") document.getElementById("whStage").innerHTML = html2d();
  sync();
}

// Dọn cảnh 3D đang mở
function drop() { turn++; if (view3d) view3d.dispose(); view3d = null; }

// Vẽ khung giữa theo chế độ đang chọn; 3D không chạy được thì về 2D
async function stage() {
  drop();
  const my = turn, el = document.getElementById("whStage");
  el.classList.toggle("is3d", mode === "3d");
  if (mode === "2d") return apply();
  el.innerHTML = `<div class="wh-load">Đang tải mô hình 3D</div>`;
  sync();
  try {
    const { mount, slot } = await import("../wh3d.js");
    if (my !== turn || !el.isConnected) return;   // đã chuyển trang hoặc đổi chế độ trong lúc tải
    el.innerHTML = "";
    view3d = mount(el, {
      bins: d.bins,
      zones: d.zones.map((z) => ({ code: z.code, name: z.name, sub: `${z.code}  ${num(z.pct)}%` })),
      loads: Object.entries(bins).map(([key, b]) => {
        const s = slot(b.bin);
        return { key, zone: b.zone.code, bin: b.bin, tip: `${code(b)}, kệ ${s.rack} tầng ${s.level}: ${b.sku}, ${num(b.qty)} thùng` };
      }),
    }, whPick);
    el.insertAdjacentHTML("beforeend", `<div class="wh-note">Cách xếp kệ, tầng là minh họa. Kéo để xoay, cuộn để phóng to</div>`);
    if (zone) view3d.focus(zone);
    apply();
  } catch (x) {
    if (my !== turn || !el.isConnected) return;
    console.warn("Không mở được 3D:", x);
    mode = "2d";
    el.classList.remove("is3d");
    toast("Không mở được 3D, đang hiện sơ đồ 2D", false);
    apply();
  }
}

// ---------- Thao tác (gọi từ onclick trong HTML) ----------
function whMode(v) {
  if (v === mode) return;
  mode = v;
  try { localStorage.setItem("whMode", v); } catch { /* bỏ qua nếu không lưu được */ }
  stage();
}
function whColor(v) { color = v; apply(); }
function whZone(v) {
  zone = v;
  if (bins[sel] && v && bins[sel].zone.code !== v) sel = null;
  if (view3d) view3d.focus(v);
  apply();
}
function whPick(k) { sel = k === sel ? null : k; apply(); }
function whFind(v) { q = v; sel = null; apply(); }
Object.assign(window, { whMode, whColor, whZone, whPick, whFind });

// Vẽ khung trang: thanh công cụ, danh sách khu, khung 2D/3D, chi tiết
async function render() {
  d = await api("/layout");
  bins = {};
  for (const z of d.zones) for (const b of z.bins) bins[z.code + b.bin] = { ...b, zone: z };
  q = params().get("q") ?? "";
  zone = ""; sel = null;
  return `<div class="wh-bar"><h1>Sơ đồ kho</h1>
      <input type="search" value="${esc(q)}" placeholder="Tìm mã, tên, số lô" aria-label="Tìm mã, tên, số lô" oninput="whFind(this.value)">
      <span id="whColor">${seg("Tô màu theo", [["exp", "Hạn dùng"], ["fill", "Mức đầy"]], color, "whColor")}</span>
      <span id="whMode">${seg("Chế độ xem", [["2d", "2D"], ["3d", "3D"]], mode, "whMode")}</span></div>
    <div class="wh"><nav class="card wh-zones" id="whZones" aria-label="Khu kho"></nav>
      <div class="card wh-view"><div class="wh-stage" id="whStage"></div><div class="wh-legend" id="whLegend"></div></div>
      <aside class="card wh-info" id="whInfo" aria-live="polite"></aside></div>`;
}

export const page = { id: "map", name: "Sơ đồ kho", desc: "Vị trí hàng 2D, 3D", icon: "map", wide: true, render, after: stage, leave: drop };
