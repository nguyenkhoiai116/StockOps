// Feature: Sơ đồ kho 2D / 3D - khu, ô chứa, mức đầy, tìm vị trí hàng.
import { api, loc, hbar, capCls, expTag, seg, segSet, params, plain, toast, num, esc, dmy, spot, table } from "../core.js";

let d = null;          // dữ liệu /api/layout
let bins = {};         // key (vd DRY3) -> thông tin ô có hàng, kèm khu
let fl = {};           // luồng hàng đã xếp cửa, đưa vào 3D (xem flows())
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

// ---------- Luồng hàng: xe, đơn, hàng lỗi ----------
const VK = { dry: "Xe thường", cold: "Xe lạnh" };   // loại xe (giống trang Giao hàng)
const DOCKS = 4;                                     // số cửa mỗi phía (N1–N4, X1–X4)

// Xếp xe vào cửa theo thứ tự: phần tử thứ i (từ 0) vào cửa prefix + (i + 1) khi i < 4, còn lại chờ cửa (đếm vào wait)
export function docks(list, prefix) {
  return { docks: list.slice(0, DOCKS).map((x, i) => ({ ...x, dock: prefix + (i + 1) })), wait: Math.max(0, list.length - DOCKS) };
}

// Các SO trên 1 xe, ghi gọn tối đa 3 số
const sos = (l) => l.slice(0, 3).map((s) => s.so_no).join(", ") + (l.length > 3 ? ` +${l.length - 3}` : "");

// Dựng flow cho 3D từ d.flow, chỉ gồm phần có dữ liệu (role không có quyền thì backend đã bỏ key đó)
function flows() {
  const f = d.flow || {}, out = {};
  const wait = (x) => ({ ...x, tip: x.tip + ", chờ cửa" });
  // Xe nhập: mỗi PO tới hạn là 1 xe
  const ins = (f.inbound || []).map((p) => ({ key: "f:po:" + p.po_no, label: `${p.po_no} · ${p.sku}`, tip: `Xe nhập ${p.po_no}: ${p.sku}, ${num(p.qty)} thùng` }));
  // Xe xuất: gộp đơn đang giao theo biển số, mỗi biển số là 1 xe
  const ship = {};
  for (const s of f.shipping || []) (ship[s.plate || "?"] ??= []).push(s);
  const outs = Object.entries(ship).map(([p, l]) => ({ key: "f:truck:" + p, label: `${p} · ${sos(l)}`, tip: `Xe ${p}: ${sos(l)}` }));
  const a = docks(ins, "N"), b = docks(outs, "X");
  out.inDocks = a.docks.map((x) => ({ ...x, tip: `${x.tip}, cửa ${x.dock}` })); out.inWait = a.wait;
  out.outDocks = b.docks.map((x) => ({ ...x, tip: `${x.tip}, cửa ${x.dock}` })); out.outWait = b.wait;
  // Bãi 9: xe nhập chờ cửa, xe xuất chờ cửa, rồi xe rảnh (wh3d.js dựa vào thứ tự này để chọn chỗ đỗ và màu)
  const idle = (f.fleet || []).filter((v) => !v.busy && !ship[v.plate])
    .map((v) => ({ key: "f:truck:" + v.plate, label: v.plate, tip: `Xe ${v.plate} rảnh, ${v.driver}` }));
  out.yard = [...ins.slice(DOCKS).map(wait), ...outs.slice(DOCKS).map(wait), ...idle];
  if (f.topick?.length) out.topick = { key: "f:topick", n: f.topick.length, tip: `${num(f.topick.length)} đơn chờ soạn` };
  if (f.staged?.length) out.staged = f.staged.map((s) => ({ key: "f:so:" + s.so_no, tip: `${s.so_no}, ${s.customer}: ${s.sku}, ${num(s.qty)} thùng (hàng vẫn tính ở ô kệ)` }));
  const q = f.quarantine || {}, exp = q.expired || [], dmg = q.dmg || [];
  const parts = [exp.length && `${num(exp.length)} lô hết hạn (đang ở kệ)`, dmg.length && `${num(dmg.reduce((t, x) => t + x.dmg, 0))} thùng hỏng khi nhận`].filter(Boolean);
  if (parts.length) out.qa = { key: "f:qa", label: parts.join(" · "), pallets: dmg.length };
  return out;
}

// Chỗ của xe trên sơ đồ (minh họa): "Cửa N1", "Chờ cửa, ở bãi 9" hoặc "Bãi 9"
function place(k) {
  const x = [...(fl.inDocks || []), ...(fl.outDocks || [])].find((x) => x.key === k);
  if (x) return "Cửa " + x.dock;
  const i = (fl.yard || []).findIndex((x) => x.key === k);
  return i < 0 ? "Không rõ" : i < fl.inWait + fl.outWait ? "Chờ cửa, ở bãi 9" : "Bãi 9";
}

// Bảng đơn bán: SO, khách, SKU, số lượng, ngày giao (đơn đang giao không có ngày thì bỏ trống)
const soTable = (l) => table(["Số SO", "Khách", "SKU", "SL*", "Ngày giao"], l.map((s) =>
  `<tr><td>${esc(s.so_no)}</td><td>${esc(s.customer)}</td><td>${esc(s.sku)}</td><td class="r">${num(s.qty)}</td><td>${s.due ? dmy(s.due) : ""}</td></tr>`).join(""));
const NOTE = `<p class="note">Số cửa và chỗ đỗ là minh họa, xe xếp theo thứ tự</p>`;

// Khung chi tiết cho đối tượng luồng (key "f:…"); không tìm thấy thì trả ""
function flowInfo(k) {
  const f = d.flow || {};
  if (k.startsWith("f:po:")) {
    const p = (f.inbound || []).find((x) => "f:po:" + x.po_no === k);
    return p ? `<h2>Xe nhập ${esc(p.po_no)}</h2><dl class="kv"><dt>Số PO</dt><dd>${esc(p.po_no)}</dd><dt>Sản phẩm</dt><dd><b>${esc(p.sku)}</b></dd>
      <dt>Số lượng</dt><dd>${num(p.qty)} thùng</dd><dt>Ngày dự kiến</dt><dd>${dmy(p.eta)}</dd><dt>Chỗ đỗ</dt><dd>${esc(place(k))}</dd></dl>${NOTE}` : "";
  }
  if (k.startsWith("f:truck:")) {
    const p = k.slice(8), v = (f.fleet || []).find((x) => x.plate === p), l = (f.shipping || []).filter((s) => (s.plate || "?") === p);
    if (!v && !l.length) return "";
    return `<h2>Xe ${esc(p)}</h2><dl class="kv"><dt>Biển số</dt><dd>${esc(p)}</dd><dt>Tài xế</dt><dd>${esc(v?.driver ?? "Không rõ")}</dd>
      <dt>Loại xe</dt><dd>${esc(VK[v?.kind] ?? v?.kind ?? "Không rõ")}</dd><dt>Chỗ đỗ</dt><dd>${esc(place(k))}</dd></dl>
      <h3>Đơn đang giao (${l.length})</h3>${l.length ? soTable(l) : `<p class="note">Xe đang rảnh</p>`}${NOTE}`;
  }
  if (k === "f:topick" && f.topick?.length) return `<h2>Bàn soạn hàng</h2><p class="note">${num(f.topick.length)} đơn chờ soạn</p>${soTable(f.topick)}`;
  if (k.startsWith("f:so:")) {
    const s = (f.staged || []).find((x) => "f:so:" + x.so_no === k);
    return s ? `<h2>Pallet tập kết ${esc(s.so_no)}</h2><dl class="kv"><dt>Số SO</dt><dd>${esc(s.so_no)}</dd><dt>Khách</dt><dd>${esc(s.customer)}</dd>
      <dt>Sản phẩm</dt><dd><b>${esc(s.sku)}</b></dd><dt>Số lượng</dt><dd>${num(s.qty)} thùng</dd><dt>Ngày giao</dt><dd>${dmy(s.due)}</dd></dl>
      <p class="note">Hàng vẫn tính tồn ở ô kệ (đã giữ) cho tới khi xuất</p>` : "";
  }
  if (k === "f:qa" && fl.qa) {
    const q = f.quarantine || {}, exp = q.expired || [], dmg = q.dmg;
    return `<h2>Hàng lỗi & trả về</h2><p class="note">${esc(fl.qa.label)}</p>
      <h3>Lô hết hạn (${exp.length})</h3>${table(["Vị trí", "Số lô", "SKU", "SL*", "Hạn dùng"], exp.map((b) =>
        `<tr><td>${loc(b.zone, b.bin)}</td><td>${esc(b.batch_no)}</td><td>${esc(b.sku)}</td><td class="r">${num(b.qty)}</td><td>${dmy(b.exp)}</td></tr>`).join(""))}
      ${dmg?.length ? `<h3>PO có hàng hỏng khi nhận (${dmg.length})</h3>${table(["Số PO", "SKU", "Hỏng*"], dmg.map((x) =>
        `<tr><td>${esc(x.po_no)}</td><td>${esc(x.sku)}</td><td class="r">${num(x.dmg)} thùng</td></tr>`).join(""))}` : ""}`;
  }
  return "";
}

// Danh sách khu bên trái
const zoneList = () => `<button type="button" aria-pressed="${!zone}" onclick="whZone('')"><span class="nm" style="margin:0">Toàn kho</span></button>`
  + d.zones.map((z) => `<button type="button" aria-pressed="${zone === z.code}" onclick="whZone('${z.code}')">
    <span class="nm"><span>${esc(z.name)}</span>${loc(z.code)}</span><div class="track"><div class="fill ${capCls(z.pct)}" style="width:${Math.min(z.pct, 100)}%"></div></div>
    <small>${num(z.used)} / ${num(z.cap)} thùng, ${num(z.pct)}%</small>
    <small class="${z.temp >= z.tmin && z.temp <= z.tmax ? "" : "bad"}">${num(z.temp)}°C, ẩm ${num(z.hum)}%${z.temp >= z.tmin && z.temp <= z.tmax ? "" : ", ngoài ngưỡng"}</small></button>`).join("");

// Khung chi tiết bên phải: ô đang chọn, hoặc kết quả tìm, hoặc hướng dẫn
function info() {
  const b = bins[sel], f = found(), x = sel?.startsWith("f:") && flowInfo(sel);
  if (x) return x;
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

// Sơ đồ 2D: mỗi khu 1 lưới ô, số ô theo kệ của khu (z.bins = dãy · ô · tầng)
function html2d() {
  const f = found();
  return `<div class="wh-2d">${d.zones.filter((z) => !zone || z.code === zone).map((z) => {
    let cells = "";
    for (let i = 1; i <= z.bins; i++) {
      const k = z.code + i, b = bins[k];
      cells += b ? `<button class="bin has ${f && !f.has(k) ? "dim" : ""}" aria-pressed="${sel === k}" style="--c:${colorOf(k)}" onclick="whPick('${k}')"
          title="${spot(i, z)}: ${esc(b.name)}, ${EXP[expOf(b)][1].toLowerCase()}"><span class="no">${no(i)}</span><span><span class="sk">${esc(b.sku)}</span><span class="q">${num(b.qty)}</span></span></button>`
        : `<button class="bin" disabled title="${spot(i, z)}: trống"><span class="no">${no(i)}</span></button>`;
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
    const { mount } = await import("../wh3d.js");
    if (my !== turn || !el.isConnected) return;   // đã chuyển trang hoặc đổi chế độ trong lúc tải
    el.innerHTML = "";
    view3d = mount(el, {
      zones: d.zones.map((z) => ({ code: z.code, name: z.name, sub: `${z.code}  ${num(z.pct)}%`, racks: z.racks, bays: z.bays, levels: z.levels })),
      loads: Object.entries(bins).map(([key, b]) => ({ key, zone: b.zone.code, bin: b.bin, tip: `${code(b)}, ${spot(b.bin, b.zone)}: ${b.sku}, ${num(b.qty)} thùng` })),
      flow: fl,   // xe ở cửa / bãi, đơn chờ soạn, pallet tập kết, hàng lỗi
    }, whPick);
    const out = view3d.outside ? `. ${view3d.outside} lô nằm ngoài sơ đồ` : "";
    el.insertAdjacentHTML("beforeend", `<div class="wh-note">Số cửa và chỗ đỗ là minh họa, xe xếp theo thứ tự. Kéo để xoay, cuộn để phóng to${out}</div>`);
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
  for (const z of d.zones) for (const b of z.items) bins[z.code + b.bin] = { ...b, zone: z };   // z.items: lô đang có hàng, z.bins: số ô
  fl = flows();
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

export const page = { perm: ["map.view"], id: "map", name: "Sơ đồ kho", desc: "Vị trí hàng 2D, 3D", icon: "map", wide: true, render, after: stage, leave: drop };
