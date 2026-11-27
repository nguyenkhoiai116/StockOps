// Feature: Xuất kho & Giao vận (Nhóm 4 Outbound: CV1–CV5)
// Mục 1: Tạo SO (nhập tay / bóc tách tự động) + Đối chiếu 3 chiều + In chứng từ QR
// Mục 2: KPI Chi phí + Ghép chuyến CVRP + Sơ đồ xếp tải 2D LIFO & Safety Guard + Lịch Dock X1–X4
// Mục 3: KPI Thực thi + Giám sát Staging chống sốc nhiệt + Quét QR lên xe + ETA & Biểu đồ nhiệt độ thùng xe
import { api, can, table, kpi, hbar, soTag, openModal, closeModal, loc, STORE, dmy, num, vnd, esc, toast } from "../core.js";

let tab = "m1";
let b = null;
let prods = [];
let selTripId = null;
let parsedRows = [];

const CH_NAME = { sieuthi: "Siêu thị (≥65%)", daily: "Đại lý (≥50%)", taphoa: "Tạp hóa (≥40%)" };
const VK = { dry: "Xe thường", cold: "Xe lạnh" };

// Sinh mã QR SVG xác định từ chuỗi mã đơn (dùng in lên Packing List / Phiếu xuất không cần thư viện ngoài)
function qrSvg(text, size = 84) {
  let h = 2166136261;
  for (let i = 0; i < text.length; i++) h = Math.imul(h ^ text.charCodeAt(i), 16777619);
  const n = 15, cells = [];
  const finder = (r, c) => (r < 5 && c < 5) || (r < 5 && c >= n - 5) || (r >= n - 5 && c < 5);
  for (let r = 0; r < n; r++) {
    for (let c = 0; c < n; c++) {
      let on = false;
      if (finder(r, c)) {
        const lr = r >= n - 5 ? r - (n - 5) : r, lc = c >= n - 5 ? c - (n - 5) : c;
        on = lr === 0 || lr === 4 || lc === 0 || lc === 4 || (lr === 2 && lc === 2);
      } else {
        h = Math.imul(h ^ (r * 31 + c * 17 + 7), 16777619);
        on = (h & 3) === 0 || (h & 5) === 5;
      }
      if (on) cells.push(`<rect x="${c}" y="${r}" width="1" height="1"/>`);
    }
  }
  return `<svg width="${size}" height="${size}" viewBox="0 0 ${n} ${n}" fill="#171717">${cells.join("")}</svg>`;
}

// Vẽ biểu đồ đường nhiệt độ thùng xe kèm vùng nhiệt độ chuẩn và điểm bất thường
function tempChartSvg(tinfo) {
  const pts = tinfo.points || [];
  if (!pts.length) return `<div class="empty">Chưa có dữ liệu cảm biến nhiệt độ</div>`;
  const W = 560, H = 210, pL = 44, pR = 20, pT = 20, pB = 34;
  const vals = pts.map((p) => p.temp).concat([tinfo.tmin, tinfo.tmax]);
  const minY = Math.floor(Math.min(...vals) - 2), maxY = Math.ceil(Math.max(...vals) + 2);
  const sx = (i) => pL + (pts.length > 1 ? (i / (pts.length - 1)) * (W - pL - pR) : (W - pL - pR) / 2);
  const sy = (v) => pT + ((maxY - v) / (maxY - minY || 1)) * (H - pT - pB);
  const bandY = sy(tinfo.tmax), bandH = Math.max(4, sy(tinfo.tmin) - sy(tinfo.tmax));
  const poly = pts.map((p, i) => `${sx(i).toFixed(1)},${sy(p.temp).toFixed(1)}`).join(" ");
  const dots = pts.map((p, i) => {
    const x = sx(i), y = sy(p.temp), col = p.anomaly ? "#b92b2b" : (p.event.includes("Mở cửa") ? "#855300" : "#2f62d6");
    return `<circle cx="${x}" cy="${y}" r="${p.anomaly ? 5.5 : 4}" fill="${col}" stroke="#fff" stroke-width="1.5"/>
      <text x="${x}" y="${H - 12}" text-anchor="middle" font-size="11" fill="#666">${esc(p.t)}</text>
      <text x="${x}" y="${y - 9}" text-anchor="middle" font-size="11" font-weight="600" fill="${col}">${p.temp}°C</text>`;
  }).join("");
  return `<svg class="temp-svg" viewBox="0 0 ${W} ${H}">
    <rect x="${pL}" y="${bandY}" width="${W - pL - pR}" height="${bandH}" fill="#e3f2ea" opacity="0.85"/>
    <line x1="${pL}" y1="${bandY}" x2="${W - pR}" y2="${bandY}" stroke="#14704a" stroke-dasharray="4 3"/>
    <text x="${pL + 6}" y="${bandY + 13}" font-size="11" fill="#14704a">Dải chuẩn: ${tinfo.tmin}°C .. ${tinfo.tmax}°C</text>
    <polyline fill="none" stroke="#2f62d6" stroke-width="2.5" points="${poly}"/>
    ${dots}</svg>`;
}

// In bộ chứng từ Xuất kho + Packing List + Mã QR + Biên bản nhiệt độ
function obPrintDocs(soId) {
  const q = b.ready_queue.find((x) => x.so.id === soId);
  if (!q) return;
  const s = q.so;
  const w = window.open("", "_blank", "width=840,height=740");
  if (!w) return toast("Trình duyệt đang chặn cửa sổ in — hãy cho phép popup", false);
  w.document.write(`<!DOCTYPE html><html lang="vi"><head><meta charset="utf-8"><title>Bộ chứng từ xuất ${esc(s.so_no)}</title>
    <style>body{font-family:"Segoe UI",sans-serif;padding:24px;color:#171717;line-height:1.5}
    .hdr{display:flex;justify-content:space-between;align-items:center;border-bottom:2px solid #222;padding-bottom:12px}
    table{width:100%;border-collapse:collapse;margin:14px 0}th,td{border:1px solid #bbb;padding:8px;font-size:13px;text-align:left}
    @media print{.noprint{display:none}}</style></head><body>
    <div class="hdr">
      <div><h1 style="margin:0;font-size:20px">PHIẾU XUẤT KHO & PACKING LIST</h1>
        <div>Mã đơn: <b>${esc(s.so_no)}</b> · Khách hàng: <b>${esc(s.customer)}</b> (${esc(q.channel_name)} · chuẩn ≥${q.min_shelf_pct}% HSD)</div>
        <div>Tuyến giao: <b>${esc(s.route_zone)}</b> · Hạn SLA: <b>${dmy(s.due)}</b></div></div>
      <div style="text-align:center">${qrSvg(s.so_no, 88)}<div style="font-family:monospace;font-size:12px;font-weight:700">${esc(s.so_no)}</div></div>
    </div>
    <button class="noprint" onclick="window.print()" style="margin-top:12px;padding:8px 16px;cursor:pointer">In / Lưu PDF</button>
    <h3>Chi tiết lô hàng đối chiếu 3 chiều (Đã đóng gói bởi Nhóm 3)</h3>
    <table><tr><th>SKU</th><th>Sản phẩm</th><th>Số lô FEFO</th><th>Vị trí</th><th>Hạn dùng</th><th>% HSD còn lại</th><th>SL (thùng)</th></tr>
      ${q.lots.map((l) => `<tr><td>${esc(s.sku)}</td><td>${esc(s.pname)}</td><td><b>${esc(l.batch_no)}</b></td><td>${esc(l.zone)}-${String(l.bin).padStart(2, "0")}</td>
        <td>${dmy(l.exp)}</td><td>${l.shelf_pct}%</td><td><b>${num(l.qty)}</b></td></tr>`).join("")}</table>
    <h3>Danh mục chứng từ đính kèm</h3>
    <ul>${q.docs.map((d) => `<li>☑ ${esc(d.name)} ${d.warn ? `— <b>${esc(d.warn)}</b>` : ""}</li>`).join("")}</ul>
    ${s.storage === "chilled" || s.storage === "frozen" ? `<div style="border:1px solid #222;padding:12px;margin-top:12px"><b>BIÊN BẢN XÁC NHẬN NHIỆT ĐỘ XUẤT KHO (CHUỖI LẠNH)</b>
      <div>☐ Đã làm lạnh trước thùng xe đạt chuẩn (${s.storage === "frozen" ? "≤ -18°C" : "2–8°C"}) · ☐ Thời gian lưu tại Staging nằm trong giới hạn an toàn · Chữ ký thủ kho / tài xế: __________________</div></div>` : ""}
    </body></html>`);
  w.document.close();
}

// Popup Đối chiếu 3 chiều (Split-View Audit)
function obAuditModal(soId) {
  const q = b.ready_queue.find((x) => x.so.id === soId);
  if (!q) return;
  const s = q.so;
  const c = q.checks;
  openModal(`<div style="display:flex;justify-content:space-between;align-items:center">
    <h2>Đối chiếu 3 chiều — ${esc(s.so_no)} (${esc(s.customer)})</h2>
    <span class="tag ${q.can_approve ? "ok" : "bad"}">${q.can_approve ? "Đạt cả 3 điều kiện cứng" : "Bị chặn — có sai lệch"}</span></div>
    <div class="split">
      <div class="pane"><h3>Bên trái · Yêu cầu SO gốc</h3>
        <dl class="kv">
          <dt>Khách / Kênh</dt><dd><b>${esc(s.customer)}</b> (${esc(q.channel_name)})</dd>
          <dt>Chuẩn HSD kênh</dt><dd><b>≥ ${q.min_shelf_pct}%</b> vòng đời (${s.shelf_days} ngày)</dd>
          <dt>Sản phẩm</dt><dd>${esc(s.sku)} · ${esc(s.pname)}</dd>
          <dt>Yêu cầu SL</dt><dd><b>${num(s.qty)} thùng</b> (${STORE[s.storage]})</dd>
          <dt>Hạn SLA</dt><dd>${dmy(s.due)} · Tuyến ${esc(s.route_zone)}</dd>
        </dl></div>
      <div class="pane"><h3>Bên phải · Thực đóng Nhóm 3</h3>
        <ul class="list">${q.lots.map((l) => `<li><b>Lô ${esc(l.batch_no)}</b> · ${loc(l.zone, l.bin)} · <b>${num(l.qty)} thùng</b>
          <small>HSD ${dmy(l.exp)} (còn ${l.left_days} ngày = <b>${l.shelf_pct}%</b>) — ${l.ok_channel ? `<span class="tag ok">Đạt kênh</span>` : `<span class="tag bad">Dưới chuẩn ${q.min_shelf_pct}%</span>`}</small></li>`).join("") || "<li>Chưa có lô đóng gói</li>"}</ul>
        <h3 style="margin-top:12px">Bộ chứng từ</h3>
        <ul class="list">${q.docs.map((d) => `<li style="padding:4px 0">${d.ready ? "✓" : "✗"} ${esc(d.name)}${d.warn ? `<small style="color:var(--bad)">${esc(d.warn)}</small>` : ""}</li>`).join("")}</ul>
      </div>
    </div>
    <div class="tools" style="margin:8px 0">
      <span class="tag ${c.qty_ok ? "ok" : "bad"}">1. Đủ 100% SL (${q.packed_qty}/${s.qty})</span>
      <span class="tag ${c.hsd_ok ? "ok" : "bad"}">2. Đạt % HSD kênh (≥${q.min_shelf_pct}%)</span>
      <span class="tag ${c.docs_ok ? "ok" : "bad"}">3. Đủ bộ chứng từ</span>
    </div>
    ${q.swap_hint ? `<div class="callout warn"><b>Gợi ý Hoán đổi lô (Batch Swap) & Phòng rủi ro:</b> ${esc(q.swap_hint)}<br><small>Chi phí phạt/hoàn đơn tránh được ước tính: <b>${vnd(q.avoided_penalty_vnd)}</b></small></div>` : ""}
    <div class="acts">
      <button class="btn ghost" onclick="closeModal()">Đóng</button>
      <button class="btn ghost" onclick="obPrintDocs(${s.id})">Xem / In chứng từ QR</button>
      ${can("so.ship") ? `<button class="btn red" onclick="obAuditAct(${s.id}, 'return')">Trả về Nhóm 3</button>
        <button class="btn ok" ${q.can_approve ? "" : "disabled title='Khóa duyệt khi chưa đạt 3 điều kiện cứng'"} onclick="obAuditAct(${s.id}, 'approve')">Duyệt & Mở khóa xuất</button>` : ""}
    </div>`);
  document.querySelector("#modal .box").classList.add("wide");
}

async function obAuditAct(soId, action) {
  try {
    await api(`/outbound/orders/${soId}/audit`, "POST", { action });
    closeModal();
    toast(action === "approve" ? "Đã duyệt 3 chiều & mở khóa ghép chuyến" : "Đã trả đơn về Nhóm 3 và nhắn tin phối hợp");
    window.route();
  } catch (x) { toast(x.message, false); }
}

function obDownloadTemplate() {
  const d1 = new Date(Date.now() + 864e5).toISOString().slice(0, 10);
  const csv = "\ufeff" + [
    "Khách hàng,Tên hoặc Mã sản phẩm,Số lượng,Hạn giao (YYYY-MM-DD)",
    `Siêu thị An Phú,Nước ngọt có ga 330ml,40,${d1}`,
    `Tạp hóa Minh Tâm,SKU-001,50,${d1}`,
  ].join("\r\n");
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }));
  a.download = "mau-don-SO-StockOps.csv";
  a.click();
}

function obFillSample() {
  const tomorrow = new Date(Date.now() + 864e5).toISOString().slice(0, 10);
  const el = document.getElementById("rawOrd");
  if (el) {
    el.value = [
      `Siêu thị An Phú, Nước ngọt có ga 330ml, 40, ${tomorrow}`,
      `Tạp hóa Minh Tâm, Mì gói tôm chua cay, 50, ${tomorrow}`,
      `Nhà hàng Biển Xanh, Há cảo đông lạnh, 200, ${tomorrow}`,
    ].join("\n");
  }
}

// Modal Tạo SO 2 chế độ: Tab Nhập tay & Tab Upload/Bóc tách tự động
function obCreateSoModal(mode = "manual") {
  const cOpts = (b.customers || []).map((c) => `<option value="${esc(c.name)}" data-ch="${c.channel}" data-pct="${c.min_shelf_pct}" data-rt="${c.route_zone}">${esc(c.name)} — ${CH_NAME[c.channel]} · ${c.route_zone}</option>`).join("");
  const pOpts = prods.map((p) => `<option value="${p.id}">${esc(p.sku)} · ${esc(p.name)} (Tồn ${num(p.stock)})</option>`).join("");

  openModal(`<h2>Chặng 1A · Tạo đơn xuất (SO) — Chặn tồn 100% từ cổng</h2>
    <div class="tabs" style="margin-top:8px">
      <button class="${mode === "manual" ? "on" : ""}" onclick="obCreateSoModal('manual')">Nhập tay theo kênh khách</button>
      <button class="${mode === "upload" ? "on" : ""}" onclick="obCreateSoModal('upload')">Upload / Bóc tách đơn tự động</button>
    </div>
    ${mode === "manual" ? `<form id="soManF">
      <label>Khách hàng (tự động nạp chuẩn % HSD & tuyến giao)<select name="customer">${cOpts}</select></label>
      <label>Sản phẩm<select name="product_id">${pOpts}</select></label>
      <label>Số lượng đặt (thùng)<input name="qty" type="number" min="1" value="40" required></label>
      <label>Hạn giao cam kết (SLA)<input name="due" type="date" value="${new Date(Date.now() + 864e5).toISOString().slice(0, 10)}"></label>
      <div class="acts"><button type="button" class="btn ghost" onclick="closeModal()">Hủy</button><button class="btn">Kiểm tra tồn 100% & Tạo SO</button></div>
    </form>` : `<div>
      <div class="tools" style="margin-bottom:8px">
        <input type="file" id="csvFile" accept=".xlsx,.csv,.txt" style="flex:1">
        <button type="button" class="btn sm ghost" onclick="obDownloadTemplate()">Tải mẫu Excel (.csv)</button>
        <button type="button" class="btn sm ghost" onclick="obFillSample()">Nạp đơn mẫu demo</button>
      </div>
      <label>Nội dung đơn khách hàng (mỗi dòng: Khách hàng, Tên/Mã hàng, Số lượng, Hạn giao)
        <textarea id="rawOrd" rows="4" placeholder="Siêu thị An Phú, Sữa tươi 1L, 50, 2026-11-30"></textarea></label>
      <div class="tools"><button type="button" class="btn sm" onclick="obRunParse()">Bóc tách & Check tồn 100%</button></div>
      <div id="parseOut" style="margin-top:12px"></div>
      <div class="acts"><button type="button" class="btn ghost" onclick="closeModal()">Đóng</button>
        <button type="button" class="btn ok" id="btnSaveParsed" style="display:none" onclick="obSaveParsed()">Xác nhận tạo các dòng đạt chuẩn</button></div>
    </div>`}`);
  document.querySelector("#modal .box").classList.add("wide");

  if (mode === "manual") {
    document.getElementById("soManF").onsubmit = async (e) => {
      e.preventDefault();
      try {
        await api("/orders", "POST", { ...Object.fromEntries(new FormData(e.target)), strict_stock: true });
        closeModal(); toast("Đã tạo SO (đạt Rule 100% tồn khả dụng)"); window.route();
      } catch (x) { toast(x.message, false); }
    };
  } else {
    document.getElementById("csvFile").onchange = async (e) => {
      const f = e.target.files[0];
      if (!f) return;
      if (f.name.toLowerCase().endsWith(".xlsx")) {
        toast(`Đang đọc file Excel ${f.name}...`);
        await obRunParse(f);
      } else {
        document.getElementById("rawOrd").value = await f.text();
        await obRunParse();
      }
    };
  }
}

async function obRunParse(fileObj = null) {
  try {
    let res;
    if (fileObj) {
      const fd = new FormData();
      fd.append("file", fileObj);
      res = await api("/outbound/parse", "POST", fd);
    } else {
      const txt = document.getElementById("rawOrd").value;
      res = await api("/outbound/parse", "POST", { text: txt });
    }
    parsedRows = res.items || [];
    const okCount = parsedRows.filter((r) => r.ok).length;
    document.getElementById("parseOut").innerHTML = table(
      ["Khách / Kênh", "SKU chuẩn hóa", "SL*", "Khả dụng*", "Độ tin cậy & Cảnh báo"],
      parsedRows.map((r) => `<tr style="${r.confidence === "low" || !r.ok ? "background:#fffbeb" : ""}">
        <td><b>${esc(r.customer || "-")}</b><small>${esc(r.channel || "")} ≥${r.min_shelf_pct || 40}% · ${esc(r.route_zone || "")}</small></td>
        <td><b>${esc(r.sku)}</b><small>${esc(r.product_name || r.raw)}</small></td>
        <td class="r">${num(r.qty)}</td><td class="r">${num(r.av)}</td>
        <td>${r.ok ? `<span class="tag ok">Đạt 100% tồn</span>` : `<span class="tag bad">Bị chặn</span>`}
          ${r.confidence === "low" ? ` <span class="tag warn">Cần kiểm tra</span>` : ""}
          ${r.warn ? `<small>${esc(r.warn)}</small>` : ""}</td></tr>`).join(""),
    );
    const btn = document.getElementById("btnSaveParsed");
    btn.style.display = okCount ? "inline-flex" : "none";
    btn.textContent = `Xác nhận tạo ${okCount} đơn đạt chuẩn`;
  } catch (x) { toast(x.message, false); }
}

async function obSaveParsed() {
  const valid = parsedRows.filter((r) => r.ok);
  let ok = 0;
  for (const r of valid) {
    try {
      await api("/orders", "POST", {
        customer: r.customer, product_id: r.product_id, qty: r.qty, due: r.due,
        channel: r.channel, min_shelf_pct: r.min_shelf_pct, route_zone: r.route_zone, strict_stock: true,
      });
      ok++;
    } catch (x) { toast(x.message, false); }
  }
  closeModal();
  toast(`Đã tạo thành công ${ok}/${valid.length} đơn xuất từ file bóc tách`);
  window.route();
}

// Kiểm thử Safety Guard trên chuyến xe (đổi xe hoặc mô phỏng xếp chung hóa mỹ phẩm)
async function obSafetyTest(tid, plate, simCos = false) {
  try {
    const res = await api(`/outbound/trips/${tid}/safety-check`, "POST", { plate, simulate_cosmetics: simCos });
    const p = res.plan;
    if (p.blocked || p.warnings.length) {
      openModal(`<h2>Safety Guard — Cảnh báo rủi ro xếp tải</h2>
        ${p.warnings.map((w) => `<div class="callout ${w.level}">${esc(w.msg)}</div>`).join("")}
        ${p.protected_vnd ? `<p>Giá trị lô hàng đã được hệ thống bảo toàn: <b>${vnd(p.protected_vnd)}</b></p>` : ""}
        <div class="acts"><button class="btn" onclick="closeModal()">Đã hiểu</button></div>`);
    } else {
      toast(`Đã chuyển sang xe ${plate} — Đạt chuẩn an toàn xếp tải`);
      window.route();
    }
  } catch (x) { toast(x.message, false); }
}

async function obScan(tid, code) {
  try {
    const res = await api(`/outbound/trips/${tid}/scan`, "POST", { code });
    toast(`Quét QR khớp: ${res.so_no} (${res.scanned}/${res.qty} thùng)`);
    window.route();
  } catch (x) { toast(x.message, false); }
}

function obDeliverModal(soId, soNo) {
  openModal(`<h2>Hoàn tất giao hàng & Lưu e-POD (${esc(soNo)})</h2>
    <form id="epF">
      <label>Ghi chú biên bản giao nhận điện tử (e-POD)
        <input name="epod_note" value="Khách đã kiểm đủ thùng, đúng nhiệt độ và ký nhận" required></label>
      <div class="acts"><button type="button" class="btn ghost" onclick="closeModal()">Hủy</button><button class="btn ok">Xác nhận Đã giao</button></div>
    </form>`);
  document.getElementById("epF").onsubmit = async (e) => {
    e.preventDefault();
    try {
      await api(`/orders/${soId}/deliver`, "POST", Object.fromEntries(new FormData(e.target)));
      closeModal(); toast("Đã lưu e-POD & cập nhật OTIF"); window.route();
    } catch (x) { toast(x.message, false); }
  };
}

function obTab(t) { tab = t; window.route(); }
function obSelTrip(id) { selTripId = id; window.route(); }
Object.assign(window, { obTab, obSelTrip, obAuditModal, obAuditAct, obPrintDocs, obDownloadTemplate, obFillSample, obCreateSoModal, obRunParse, obSaveParsed, obSafetyTest, obScan, obDeliverModal });

function renderLifo2d(t) {
  if (!t || !t.plan) return `<div class="empty">Chọn một chuyến xe để xem sơ đồ xếp tải 2D LIFO</div>`;
  const p = t.plan;
  const bays = p.bays || [];
  const vehOpts = (b.vehicles || []).map((v) => `<option value="${v.plate}" ${v.plate === t.plate ? "selected" : ""}>${v.plate} (${VK[v.kind]} · ${v.cap_qty} th)</option>`).join("");
  return `<div class="truck-wrap">
    <div class="truck-head">
      <div><b>Sơ đồ thùng xe 2D LIFO · ${esc(t.trip_no)} (${esc(t.plate)})</b> · Tải: ${num(p.tot_qty)} th / ${p.tot_kg} kg / ${p.tot_m3} m³ · <b>Fill Rate ${p.fill_pct}%</b></div>
      ${can("so.ship") ? `<div class="tools">
        <select id="chgVeh" style="min-height:32px;padding:4px 8px">${vehOpts}</select>
        <button class="btn sm ghost" onclick="obSafetyTest(${t.id}, document.getElementById('chgVeh').value, false)">Kiểm tra / Đổi xe</button>
        <button class="btn sm ghost" onclick="obSafetyTest(${t.id}, '${esc(t.plate)}', true)">Thử xếp kèm Mỹ phẩm</button>
      </div>` : ""}
    </div>
    ${p.warnings.length ? p.warnings.map((w) => `<div class="callout ${w.level}">${esc(w.msg)}</div>`).join("") : `<div class="callout ok">✓ Safety Guard: Đạt chuẩn nhiệt độ xe, tải trọng và không nhiễm chéo hóa mỹ phẩm.</div>`}
    <div class="truck-grid">
      <div style="display:grid;place-items:center;padding:8px;background:var(--raised);border-radius:var(--r-sm);font-size:.75rem;color:var(--text-2);font-weight:600">ĐẦU XE<br>(Giao sau<br>xếp sâu)</div>
      ${bays.map((bay) => {
        const cold = bay.storage === "chilled" || bay.storage === "frozen";
        const card = `<div class="truck-slot ${cold ? "cold" : (bay.layer === "top" ? "top" : "bot")}">
          <b>${esc(bay.so_no)}</b> · ${esc(bay.sku)} (${num(bay.qty)} th)<br><small>${esc(bay.customer)} · ${bay.weight_kg} kg</small><br><span class="tag">${esc(bay.layer_label)}</span></div>`;
        const empty = `<div class="truck-slot empty">Trống</div>`;
        return `<div class="truck-bay"><div class="bh"><span>Khoang ${bay.bay}</span><span class="tag info">Điểm giao #${bay.stop_no}</span></div>
          ${bay.layer === "top" ? card + empty : empty + card}</div>`;
      }).join("")}
      <div style="display:grid;place-items:center;padding:8px;background:var(--primary-bg);border-radius:var(--r-sm);font-size:.75rem;color:var(--primary);font-weight:600">CỬA SAU<br>(Điểm 1<br>dỡ trước)</div>
    </div>
  </div>`;
}

function renderDockGantt(trips) {
  const docks = [["X1", "Dock X1 (Lạnh)"], ["X2", "Dock X2 (Lạnh)"], ["X3", "Dock X3 (Khô)"], ["X4", "Dock X4 (Khô)"]];
  const toMin = (hm) => { const [h, m] = String(hm || "08:00").split(":").map(Number); return (h || 8) * 60 + (m || 0); };
  const startDay = 6 * 60, span = 12 * 60;
  return `<div class="gantt">${docks.map(([dk, lb]) => {
    const ts = trips.filter((t) => t.dock === dk && t.slot_start);
    const blks = ts.map((t) => {
      const l = Math.max(0, Math.min(92, ((toMin(t.slot_start) - startDay) / span) * 100));
      const w = Math.max(10, ((Math.max(30, t.est_load_min)) / span) * 100);
      const cold = t.storage === "chilled" || t.storage === "frozen";
      return `<div class="gantt-blk ${cold ? "cold" : ""} ${t.sla_risk_pct >= 30 ? "sla" : ""}" style="left:${l}%;width:${w}%" title="${esc(t.trip_no)} · ${esc(t.slot_start)}–${esc(t.slot_end)}">
        <b>${esc(t.trip_no)}</b> ${esc(t.slot_start)}–${esc(t.slot_end)}<br>${esc(t.plate)} (~${t.est_load_min}p)</div>`;
    }).join("");
    return `<div class="gantt-row"><b>${lb}</b><div class="gantt-track">${blks || `<span style="padding:10px;display:inline-block;color:var(--muted);font-size:.75rem">06:00 — 18:00 trống</span>`}</div></div>`;
  }).join("")}</div>`;
}

async function render() {
  [b, prods] = await Promise.all([api("/outbound/board"), api("/products")]);
  const tabs = `<div class="tabs">
    <button class="${tab === "m1" ? "on" : ""}" onclick="obTab('m1')">Mục 1 · Đơn hàng & Chứng từ 3 chiều (${b.ready_queue.length})</button>
    <button class="${tab === "m2" ? "on" : ""}" onclick="obTab('m2')">Mục 2 · Ghép chuyến, LIFO 2D & Cửa xuất (${b.trips.length})</button>
    <button class="${tab === "m3" ? "on" : ""}" onclick="obTab('m3')">Mục 3 · Staging, Quét QR & Giám sát ETA/Nhiệt</button>
  </div>`;

  let content = "";
  if (tab === "m1") {
    const qRows = b.ready_queue.map((q) => {
      const s = q.so, c = q.checks;
      const aiNote = !q.can_approve
        ? `<span class="tag bad">Chặn xuất</span><small>${esc(q.swap_hint || "Kiểm tra đối chiếu")}</small>`
        : (s.audit_status === "approved" ? `<span class="tag ok">Đã duyệt · Sẵn sàng ghép</span>` : `<span class="tag info">Đạt chuẩn — chờ bấm duyệt</span>`);
      return `<tr><td><b>${esc(s.so_no)}</b><small>${esc(s.customer)} · ${esc(s.route_zone)}</small><span class="tag">${esc(q.channel_name)} ≥${q.min_shelf_pct}%</span></td>
        <td>${esc(s.sku)} ${esc(s.pname)}<small>${num(s.qty)} thùng · ${STORE[s.storage]}</small></td>
        <td><span class="tag ${c.qty_ok ? "ok" : "bad"}">${q.packed_qty}/${s.qty} (100%)</span></td>
        <td>${q.lots.map((l) => `<div><span class="loc">${esc(l.batch_no)}</span> <span class="tag ${l.ok_channel ? "ok" : "bad"}">${l.shelf_pct}% HSD</span></div>`).join("")}</td>
        <td>${dmy(s.due)}</td><td>${aiNote}</td>
        <td class="r"><div class="tools" style="justify-content:flex-end">
          <button class="btn sm" onclick="obAuditModal(${s.id})">Đối chiếu 3 chiều</button>
          <button class="btn sm ghost" onclick="obPrintDocs(${s.id})">In PDF/QR</button>
        </div></td></tr>`;
    }).join("");

    const histRows = b.orders.filter((o) => o.status !== "picked").map((o) => `<tr><td><b>${esc(o.so_no)}</b><small>${esc(o.customer)}</small></td>
      <td>${esc(o.sku)} ${esc(o.name)}<small>${num(o.qty)} thùng · ${STORE[o.storage]}</small></td>
      <td>${esc(o.plate || "-")}</td><td>${soTag(o.status)}</td>
      <td>${o.status === "delivered" ? (o.on_time ? `<span class="tag ok">Đúng hạn</span>` : `<span class="tag bad">Trễ hạn</span>`) : "-"}<small>${esc(o.epod_note || "")}</small></td></tr>`).join("");

    content = `<div class="card"><div class="head card-head"><h2>Bảng Hàng đợi kiểm duyệt (Ready-to-Ship Queue từ Nhóm 3)</h2>
        ${can("so.create") ? `<button class="btn sm" onclick="obCreateSoModal('manual')">+ Tạo đơn xuất (SO) / Upload file</button>` : ""}</div>
        ${table(["SO / Khách & Kênh", "Hàng hóa", "Đủ 100%", "Check HSD kênh", "Hạn SLA", "Trạng thái / Cảnh báo", ""], qRows)}</div>
      <div class="card"><h2>Đơn đang giao & Lịch sử đã giao (e-POD)</h2>${table(["Đơn", "Hàng hóa", "Xe", "Trạng thái", "Đúng hạn / e-POD"], histRows)}</div>`;
  } else if (tab === "m2") {
    const ck = b.cost_kpi;
    const readyNoTrip = b.ready_queue.filter((q) => q.so.audit_status === "approved" && !q.so.trip_id);
    const selTrip = b.trips.find((t) => t.id === selTripId) || b.trips[0];

    const readyRows = readyNoTrip.map((q) => `<tr><td><b>${esc(q.so.so_no)}</b><small>${esc(q.so.customer)}</small></td>
      <td><span class="loc">${esc(q.so.route_zone)}</span> · ${STORE[q.so.storage]}</td>
      <td class="r">${num(q.so.qty)} th</td><td>${dmy(q.so.due)}</td></tr>`).join("");

    const tripCards = b.trips.map((t) => {
      const n = t.orders.length;
      const solo = n * ((b.vehicles.find((v) => v.plate === t.plate)?.cost_trip) || 1800000);
      const actBtn = can("so.ship") && (t.status === "planned" || t.status === "scheduled")
        ? `<button class="btn sm ok" onclick="run(() => api('/outbound/trips/${t.id}/start-load', 'POST'), 'Đã chốt lệnh điều xe vào Dock bốc xếp')">Chốt lệnh & Bốc xếp</button>` : "";
      return `<div class="callout ${selTrip && selTrip.id === t.id ? "info" : ""}" style="cursor:pointer" onclick="obSelTrip(${t.id})">
        <div style="display:flex;justify-content:space-between;align-items:center;gap:8px;flex-wrap:wrap">
          <div><b>${esc(t.trip_no)}</b> · Xe <span class="loc">${esc(t.plate)}</span> · Tuyến <b>${esc(t.route_zone)}</b> · ${STORE[t.storage] || t.storage} · <b>${n} đơn</b> · Fill Rate <b>${t.fill_pct}%</b></div>
          <div class="tools"><span class="tag info">${esc(t.status)}</span>${t.dock ? `<span class="loc">${esc(t.dock)} ${esc(t.slot_start)}</span>` : ""}${actBtn}</div>
        </div>
        <small style="display:block;margin-top:4px">${n > 1 ? `So sánh kinh tế: Chạy lẻ ${n} xe (${vnd(solo)}) → Ghép 1 xe (${vnd(solo - t.saved_vnd)}) · <b>Tiết kiệm ${vnd(t.saved_vnd)}</b>` : "Chuyến đơn lẻ — ghép thêm đơn cùng tuyến để giảm chi phí"}</small>
      </div>`;
    }).join("") || `<div class="empty">Chưa có chuyến xe nào — bấm "Tự động ghép chuyến"</div>`;

    content = `<div class="kpis">
        ${kpi("Hệ số lấp đầy TB (Fill Rate)", ck.avg_fill_pct + "%", "Mục tiêu ghép đơn > 85%")}
        ${kpi("Chuyến xe tiết kiệm", ck.trips_saved, "Nhờ gom cùng tuyến & nhiệt độ")}
        ${kpi("Chi phí vận tải & neo xe giảm", vnd(ck.saved_vnd), "Ước tính từ ghép chuyến + san tải Dock")}
        ${kpi("Rủi ro xếp tải / HSD đã chặn", ck.risks_blocked, "Safety Guard & kiểm duyệt 3 chiều")}
      </div>
      <div class="cols2">
        <div class="card"><div class="head card-head"><h2>Đơn đã duyệt chờ ghép chuyến (${readyNoTrip.length})</h2>
          ${can("so.ship") ? `<button class="btn sm" onclick="run(() => api('/outbound/consolidate', 'POST'), 'Đã tự động ghép chuyến tối ưu')" ${readyNoTrip.length ? "" : "disabled"}>Tự động ghép chuyến</button>` : ""}</div>
          ${table(["Đơn", "Tuyến / Nhiệt độ", "SL*", "SLA"], readyRows)}</div>
        <div class="card"><h2>Danh sách Chuyến xe (Bấm để xem sơ đồ LIFO 2D)</h2>${tripCards}</div>
      </div>
      <div class="card"><h2>Trình xem Sơ đồ xếp tải 2D (LIFO Load Planner) & Safety Guard</h2>${renderLifo2d(selTrip)}</div>
      <div class="card"><div class="head card-head"><h2>Lịch biểu Cửa xuất (Dock Schedule Timeline · 06:00–18:00)</h2>
        ${can("so.ship") ? `<button class="btn sm" onclick="run(() => api('/outbound/schedule-docks', 'POST'), 'Đã tự động xếp lịch cửa xuất không chồng chéo')">Tự động xếp lịch Dock</button>` : ""}</div>
        ${renderDockGantt(b.trips)}</div>`;
  } else {
    const ek = b.exec_kpi;
    const stgRows = b.staging.map((s) => `<tr><td><b>${esc(s.so_no)}</b><small>${esc(s.customer)}</small></td>
      <td>${esc(s.sku)} ${esc(s.pname)}<small>${STORE[s.storage]} · ${num(s.qty)} th (${vnd(s.cargo_val)})</small></td>
      <td>${hbar(s.is_cold ? "Giới hạn an toàn lạnh" : "Thời gian chờ", s.pct, `${s.wait_min} / ${s.limit_min} phút`, s.level === "bad" ? "bad" : (s.level === "warn" ? "warn" : ""))}</td>
      <td class="r">${s.is_cold && can("so.ship") ? `<div class="tools" style="justify-content:flex-end">
        <button class="btn sm ghost" onclick="run(() => api('/outbound/staging/${s.id}/action', 'POST', {action:'return_cold'}), 'Đã đưa tạm vào Kho lạnh (Khu 2)')">Đưa tạm Kho lạnh</button>
        <button class="btn sm red" onclick="run(() => api('/outbound/staging/${s.id}/action', 'POST', {action:'prioritize'}), 'Đã đẩy ưu tiên bốc ngay tại cửa X1')">Ưu tiên bốc ngay</button></div>` : `<span class="tag ok">Ổn định</span>`}</td></tr>`).join("");

    const loadTrips = b.trips.filter((t) => t.status === "loading" || t.status === "scheduled");
    const scanHtml = loadTrips.length ? loadTrips.map((t) => {
      const pct = t.tot_qty ? Math.round(t.scanned_qty / t.tot_qty * 100) : 0;
      const full = t.tot_qty > 0 && t.scanned_qty >= t.tot_qty;
      return `<div class="pane" style="margin-bottom:12px">
        <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px;margin-bottom:8px">
          <div><b>${esc(t.trip_no)}</b> · Xe <span class="loc">${esc(t.plate)}</span> · Dock <span class="loc">${esc(t.dock || "X1")}</span></div>
          <b>Tiến độ QR: ${num(t.scanned_qty)} / ${num(t.tot_qty)} thùng (${pct}%)</b>
        </div>
        ${hbar("Quét đối chiếu lên xe (bắt buộc 100% mới mở khóa xuất cổng)", pct, pct + "%", full ? "top-v" : "warn")}
        <div class="tools" style="margin-top:10px">
          ${t.orders.map((o) => `<button class="btn sm ghost" onclick="obScan(${t.id}, '${esc(o.so_no)}')" ${o.scanned_qty >= o.qty ? "disabled" : ""}>Quét QR ${esc(o.so_no)} (${o.scanned_qty}/${o.qty})</button>`).join("")}
          <button class="btn sm red" onclick="obScan(${t.id}, 'SO-NHAM-999')">Thử quét nhầm kiện</button>
          ${can("so.ship") ? `<button class="btn sm ok" style="margin-left:auto" ${full ? "" : "disabled title='Khóa cứng khi chưa quét đủ 100% kiện'"} onclick="run(() => api('/outbound/trips/${t.id}/dispatch', 'POST', {}), 'Đã xác nhận xuất cổng & trừ tồn kho thật')">Xác nhận Xuất cổng</button>` : ""}
        </div></div>`;
    }).join("") : `<div class="empty">Chưa có chuyến nào đang tại Dock bốc xếp (vào Mục 2 → bấm "Chốt lệnh & Bốc xếp")</div>`;

    const transit = b.trips.filter((t) => t.status === "in_transit");
    const transitHtml = transit.length ? transit.map((t) => {
      const ti = t.temp;
      const stopHtml = t.orders.map((o, i) => `<li><b>Điểm ${i + 1}: ${esc(o.so_no)}</b> · ${esc(o.customer)} (${num(o.qty)} thùng) — ${soTag(o.status)}
        ${o.status === "shipping" && can("so.deliver") ? `<button class="btn sm ok" style="margin-left:8px" onclick="obDeliverModal(${o.id}, '${esc(o.so_no)}')">Hoàn tất & Lưu e-POD</button>` : ""}</li>`).join("");
      return `<div class="cols2" style="margin-bottom:16px">
        <div class="card"><h2>${esc(t.trip_no)} · Xe ${esc(t.plate)} (Đang chạy · Tuyến ${esc(t.route_zone)})</h2>
          <p class="sub" style="margin-bottom:10px">ETA dự báo: <b>${esc(t.eta_text || "Đang cập nhật")}</b> · Nguy cơ trễ SLA: <span class="tag ${t.sla_risk_pct >= 30 ? "bad" : "ok"}">${t.sla_risk_pct}%</span></p>
          <ul class="list">${stopHtml}</ul>
          ${t.sla_risk_pct >= 30 ? `<div class="callout warn" style="margin-top:12px"><b>Cảnh báo nguy cơ trễ SLA:</b> Nguy cơ trễ khung giờ nhận siêu thị (${t.sla_risk_pct}%). Chủ động báo khách nới khung giờ để tránh phí giao lại!
            <div class="tools" style="margin-top:8px"><button class="btn sm" onclick="run(() => api('/outbound/trips/${t.id}/alert', 'POST', {mode:'notify'}), 'Đã gửi cảnh báo SLA tới Quản lý & Tài xế')">Gửi cảnh báo SLA ngay</button></div></div>` : ""}
        </div>
        <div class="card"><div class="head card-head"><h2>Giám sát nhiệt độ thùng xe & Cảnh báo bất thường</h2>
          <div class="tools">
            ${can("so.deliver") ? `<button class="btn sm ghost" onclick="run(() => api('/outbound/trips/${t.id}/alert', 'POST', {mode:'sim_fault'}), 'Đã mô phỏng sự cố tăng nhiệt thùng xe')">Mô phỏng hỏng lốc lạnh</button>` : ""}
          </div></div>
          ${tempChartSvg(ti)}
          ${ti.has_anomaly ? `<div class="callout bad" style="margin-top:8px"><b>Cảnh báo bất thường nhiệt độ thùng xe:</b> Đang <b>${ti.latest_temp}°C</b> (ngoài dải ${ti.tmin}..${ti.tmax}°C)${ti.mins_to_spoil ? ` — <b>Còn ~${ti.mins_to_spoil} phút trước khi chạm ngưỡng hỏng</b>` : ""}. Bảo toàn giá trị lô hàng: <b>${vnd(t.cargo_val)}</b>.
            <div class="tools" style="margin-top:8px"><button class="btn sm red" onclick="run(() => api('/outbound/trips/${t.id}/alert', 'POST', {mode:'notify'}), 'Đã phát lệnh khẩn tới Tài xế & Quản lý kho')">Gửi lệnh khẩn tới Tài xế & Quản lý</button></div></div>`
            : `<div class="callout ok" style="margin-top:8px">✓ Nhiệt độ thùng xe ổn định (${ti.latest_temp}°C). Đợt tăng ngắn khi mở cửa dỡ hàng được hệ thống phân loại là an toàn (không báo động giả).</div>`}
        </div>
      </div>`;
    }).join("") : `<div class="card empty">Hiện chưa có chuyến xe nào đang chạy trên đường (In-Transit)</div>`;

    content = `<div class="kpis">
        ${kpi("Tỷ lệ xuất chuẩn xác", ek.loading_acc + "%", "Khóa cứng 100% quét mã QR")}
        ${kpi("Tỷ lệ giao đúng hạn (OTIF)", ek.otif + "%", "Cập nhật trực tiếp từ e-POD")}
        ${kpi("Cảnh báo nhiệt / SLA đang xử lý", ek.active_alerts, "Staging lạnh & thùng xe In-Transit")}
        ${kpi("Thiệt hại đã ngăn chặn", vnd(ek.prevented_vnd), "Lô lạnh cứu kịp + tránh phạt hoàn đơn")}
      </div>
      <div class="card"><h2>CV5 · Khu chờ xuất Staging Monitor (Chống sốc nhiệt hàng lạnh)</h2>${table(["Đơn", "Hàng hóa / Giá trị", "Thời gian lưu tại Khu 6", "Hành động nhanh"], stgRows)}</div>
      <div class="card"><h2>CV5 · Trạm Quét mã QR đối chiếu lên xe (Theo thứ tự LIFO)</h2>${scanHtml}</div>
      ${transitHtml}`;
  }

  return `<div class="head"><div><h1>Xuất kho & Giao vận (Outbound Control Tower)</h1>
    <p class="sub">Đối chiếu 3 chiều & chuẩn % HSD kênh · Ghép chuyến LIFO 2D · Chống sốc nhiệt Staging, Quét QR & Giám sát ETA</p></div>
    <div class="tools">${can("so.create") ? `<button class="btn" onclick="obCreateSoModal('manual')">+ Tạo đơn xuất (SO)</button>` : ""}</div></div>
    ${tabs}${content}`;
}

export const page = { perm: ["so.ship", "so.deliver"], id: "ship", name: "Xuất kho", desc: "Chứng từ, LIFO 2D & ETA", icon: "ship", render };
