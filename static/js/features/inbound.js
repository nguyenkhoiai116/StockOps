// Feature: Nhập hàng (Nhóm 1 Inbound: CV1–CV4) — PO/ASN, Time-slot & Dock N1–N4, Mặt bằng/QC, Tem nhãn FEFO & Nhận kho.
import { api, can, table, form, kpi, hbar, capCls, openModal, closeModal, dmy, dmyt, num, esc, STORE, toast } from "../core.js";

let pos = [];
let rejs = [];
let prods = [];
let parsedPos = [];
let tab = "cv1";

const STEP_ORDER = ["draft", "validated", "scheduled", "ready_area", "arrived", "received"];
const STEP_LABEL = {
  draft: "1. Chờ duyệt ASN", validated: "2. Sẵn sàng xếp lịch", scheduled: "3. Đã chốt Dock",
  ready_area: "4. Sẵn sàng mặt bằng", arrived: "5. Xe đã cập bến", received: "Đã nhập kho", rejected: "Từ chối tại Dock",
};
const INB_SLOTS = ["07:30-08:30", "08:30-09:30", "09:30-10:30", "10:30-11:30", "13:30-14:30", "14:30-15:30", "15:30-16:30"];

function stepPills(cur) {
  const idx = STEP_ORDER.indexOf(cur || "draft");
  return `<div class="step-pills">${STEP_ORDER.slice(0, 5).map((k, i) =>
    `<span class="step-pill ${i < idx ? "done" : (i === idx ? "cur" : "")}">${STEP_LABEL[k]}</span>`).join("")}</div>`;
}

function prioTag(o) {
  return o.priority === "urgent"
    ? `<span class="tag bad">Cờ Đỏ · Khẩn</span>`
    : `<span class="tag ok">Cờ Xanh · Chuẩn</span>`;
}

// In Phiếu kiểm đếm (Tally Sheet) & Tem nhãn tạm chuẩn FEFO
function poPrint(id) {
  const o = pos.find((x) => x.id === id);
  if (!o) return;
  const pl = o.pre_label;
  const w = window.open("", "_blank", "width=820,height=700");
  if (!w) return toast("Trình duyệt đang chặn cửa sổ in — hãy cho phép popup", false);
  w.document.write(`<!DOCTYPE html><html lang="vi"><head><meta charset="utf-8"><title>Phiếu kiểm đếm & Tem ${esc(o.po_no)}</title>
    <style>body{font-family:"Segoe UI",sans-serif;padding:24px;color:#171717;line-height:1.5}
    h1{margin:0 0 4px;font-size:20px}table{width:100%;border-collapse:collapse;margin:14px 0}
    th,td{border:1px solid #bbb;padding:8px;text-align:left;font-size:13px}
    .lbl{border:2px dashed #333;padding:14px;border-radius:8px;margin-top:18px;background:#fafafa}
    .bdg{display:inline-block;padding:2px 8px;border:1px solid #333;border-radius:4px;margin-right:6px;font-size:12px;font-weight:600}
    @media print{.noprint{display:none}}</style></head><body>
    <div style="display:flex;justify-content:space-between;align-items:center">
      <div><h1>PHIẾU KIỂM ĐẾM NHẬP KHO (TALLY SHEET)</h1><div>Mã PO: <b>${esc(o.po_no)}</b> · ASN: <b>${esc(o.asn_no || "-")}</b> · Thẻ cổng: <b>${esc(o.gate_pass || "Chưa cấp")}</b></div></div>
      <button class="noprint" onclick="window.print()" style="padding:8px 16px;cursor:pointer">In biểu mẫu</button>
    </div>
    <table><tr><th>SKU</th><th>Sản phẩm</th><th>NCC</th><th>SL đặt</th><th>Dock / Khung giờ</th><th>Biển số xe</th></tr>
      <tr><td><b>${esc(o.sku)}</b></td><td>${esc(o.name)}</td><td>${esc(o.supplier)}</td><td>${num(o.qty)} ${esc(o.unit)}</td>
      <td>${esc(o.dock || "-")} · ${esc(o.slot_time || "-")}</td><td>${esc(o.plate || "-")}</td></tr></table>
    <h3>Checklist kiểm tra tại Dock</h3><ul>${pl.checklist.map((c) => `<li>☐ ${esc(c)}</li>`).join("")}</ul>
    <div class="lbl"><div style="font-size:12px;color:#555">TEM NHÃN TẠM ĐỊNH DANH FEFO (DÁN LÊN PALLET / THÙNG)</div>
      <div style="font-size:22px;font-weight:700;margin:6px 0;font-family:monospace">${esc(pl.batch_id)}</div>
      <div><b>${esc(o.sku)}</b> — ${esc(o.name)} | SL: <b>${num(o.qty)} ${esc(o.unit)}</b> | HSD dự kiến: <b>${o.asn_exp ? dmy(o.asn_exp) : "Điền thực tế"}</b></div>
      <div style="margin-top:8px">${pl.badges.map((b) => `<span class="bdg">${esc(b)}</span>`).join("") || `<span class="bdg">Hàng tiêu chuẩn</span>`}</div>
    </div></body></html>`);
  w.document.close();
}

function inbTab(t) { tab = t; window.route(); }

function poFillSample() {
  const d1 = new Date(Date.now() + 864e5).toISOString().slice(0, 10);
  const expCold = new Date(Date.now() + 28 * 864e5).toISOString().slice(0, 10);
  const expFrz = new Date(Date.now() + 110 * 864e5).toISOString().slice(0, 10);
  const el = document.getElementById("rawPo");
  if (el) {
    el.value = [
      "Sản phẩm, Số lượng, Ngày đến, Mã ASN, Đơn vị tính, HSD dự kiến, Cần QC",
      `Sữa tươi tiệt trùng 1L, 120, ${d1}, ASN-2501, thùng, ${expCold}, Có`,
      `Mì gói tôm chua cay, 250, ${d1}, , lốc, , Không`,
      `SKU-005, 80, ${d1}, ASN-2503, thùng, ${expFrz}, Có`,
    ].join("\n");
  }
}

function poDownloadTemplate() {
  const d1 = new Date(Date.now() + 864e5).toISOString().slice(0, 10);
  const exp1 = new Date(Date.now() + 28 * 864e5).toISOString().slice(0, 10);
  const exp2 = new Date(Date.now() + 180 * 864e5).toISOString().slice(0, 10);
  const csv = "\ufeff" + [
    "Sản phẩm / Mã SKU,Số lượng,Ngày đến (YYYY-MM-DD),Mã ASN,Đơn vị tính,HSD dự kiến,Cần kiểm QC (Có/Không)",
    `Sữa tươi tiệt trùng 1L,120,${d1},ASN-2501,thùng,${exp1},Có`,
    `SKU-001,200,${d1},ASN-2502,thùng,${exp2},Không`,
  ].join("\r\n");
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }));
  a.download = "mau-nhap-PO-StockOps.csv";
  a.click();
}

function poRenderParsed(items) {
  parsedPos = items || [];
  const okCount = parsedPos.filter((r) => r.ok).length;
  const out = document.getElementById("poParseOut");
  if (!out) return;
  out.innerHTML = table(
    ["SKU chuẩn hóa", "SL / UOM*", "ETA & Ưu tiên", "ASN / HSD / QC", "Cảnh báo kiểm tra"],
    parsedPos.map((r) => `<tr style="${r.confidence === "low" || !r.ok ? "background:#fffbeb" : ""}">
      <td><b>${esc(r.sku)}</b><small>${esc(r.product_name || r.raw)}</small></td>
      <td class="r"><b>${num(r.qty)}</b><small>${esc(r.asn_uom || "thùng")}</small></td>
      <td>${r.eta ? dmy(r.eta) : "-"}<br>${r.priority === "urgent" ? `<span class="tag bad">Cờ Đỏ</span>` : `<span class="tag ok">Cờ Xanh</span>`}</td>
      <td>${esc(r.asn_no || "Thiếu ASN")}<small>HSD: ${r.asn_exp ? dmy(r.asn_exp) : "Chưa có"}${r.need_qc ? " · ⚠ QC" : ""}</small></td>
      <td>${r.ok ? `<span class="tag ok">Sẵn sàng tạo PO</span>` : `<span class="tag bad">Bị chặn</span>`}
        ${r.confidence === "low" && r.ok ? ` <span class="tag warn">Cần rà soát</span>` : ""}
        ${r.warn ? `<small>${esc(r.warn)}</small>` : ""}</td></tr>`).join(""),
  );
  const btn = document.getElementById("btnSavePoParsed");
  if (btn) {
    btn.style.display = okCount ? "inline-flex" : "none";
    btn.textContent = `Xác nhận tạo ${okCount} đơn PO`;
  }
}

async function poRunParse(fileObj = null) {
  try {
    let res;
    if (fileObj) {
      const fd = new FormData();
      fd.append("file", fileObj);
      res = await api("/pos/parse", "POST", fd);
    } else {
      const txt = document.getElementById("rawPo").value;
      res = await api("/pos/parse", "POST", { text: txt });
    }
    poRenderParsed(res.items);
  } catch (x) { toast(x.message, false); }
}

async function poSaveParsed() {
  const valid = parsedPos.filter((r) => r.ok);
  let ok = 0;
  for (const r of valid) {
    try {
      await api("/pos", "POST", {
        product_id: r.product_id, qty: r.qty, eta: r.eta,
        asn_no: r.asn_no, asn_uom: r.asn_uom, asn_exp: r.asn_exp, need_qc: r.need_qc,
      });
      ok++;
    } catch (x) { toast(x.message, false); }
  }
  closeModal();
  toast(`Đã tạo thành công ${ok}/${valid.length} đơn PO từ file`);
  window.route();
}

// Modal Tạo PO 2 chế độ: Nhập tay & Upload file Excel (.xlsx) / CSV (bóc tách tự động)
async function poAdd(mode = "manual") {
  if (!prods.length) prods = await api("/products");
  const pOpts = prods.map((p) => `<option value="${p.id}">${esc(p.sku)} · ${esc(p.name)} (${STORE[p.storage]})</option>`).join("");
  const d1 = new Date(Date.now() + 864e5).toISOString().slice(0, 10);

  openModal(`<h2>Tạo đơn mua hàng (PO) — Nhập tay hoặc Upload Excel</h2>
    <div class="tabs" style="margin-top:8px">
      <button class="${mode === "manual" ? "on" : ""}" onclick="poAdd('manual')">Nhập tay từng đơn</button>
      <button class="${mode === "upload" ? "on" : ""}" onclick="poAdd('upload')">Upload file Excel / CSV (Bóc tách tự động)</button>
    </div>
    ${mode === "manual" ? `<form id="poManF">
      <label>Sản phẩm<select name="product_id">${pOpts}</select></label>
      <label>Số lượng đặt (thùng)<input name="qty" type="number" min="1" value="100" required></label>
      <label>Ngày dự kiến đến (ETA)<input name="eta" type="date" value="${d1}"></label>
      <label>Mã ASN từ NCC (để trống nếu chưa có để hệ thống nhắc ở CV1)<input name="asn_no" placeholder="vd ASN-2501"></label>
      <label>Đơn vị tính trên ASN<input name="asn_uom" value="thùng"></label>
      <label>Hạn sử dụng dự kiến (ASN)<input name="asn_exp" type="date"></label>
      <label>Cần giữ tạm kiểm tra chất lượng (QC) trước khi bán?
        <select name="need_qc"><option value="0">Không — đạt là nhập kệ bán ngay</option><option value="1">Có — giữ chỗ khu cách ly QC (Khu 8)</option></select></label>
      <div class="acts"><button type="button" class="btn ghost" onclick="closeModal()">Hủy</button><button class="btn">Tạo PO</button></div>
    </form>` : `<div>
      <div class="tools" style="margin-bottom:8px">
        <input type="file" id="poFile" accept=".xlsx,.csv,.txt" style="flex:1">
        <button type="button" class="btn sm ghost" onclick="poDownloadTemplate()">Tải mẫu Excel (.csv)</button>
        <button type="button" class="btn sm ghost" onclick="poFillSample()">Nạp đơn mẫu demo</button>
      </div>
      <label>Hoặc dán trực tiếp nội dung từ Excel/CSV (Sản phẩm/SKU, Số lượng, Ngày đến, Mã ASN, ĐVT, HSD, Cần QC)
        <textarea id="rawPo" rows="4" placeholder="Sữa tươi tiệt trùng 1L, 120, ${d1}, ASN-2501, thùng, 2026-12-25, Có"></textarea></label>
      <div class="tools"><button type="button" class="btn sm" onclick="poRunParse()">Bóc tách & Kiểm tra sức chứa</button></div>
      <div id="poParseOut" style="margin-top:12px"></div>
      <div class="acts"><button type="button" class="btn ghost" onclick="closeModal()">Đóng</button>
        <button type="button" class="btn ok" id="btnSavePoParsed" style="display:none" onclick="poSaveParsed()">Xác nhận tạo PO</button></div>
    </div>`}`);
  document.querySelector("#modal .box").classList.add("wide");

  if (mode === "manual") {
    document.getElementById("poManF").onsubmit = async (e) => {
      e.preventDefault();
      try {
        const v = Object.fromEntries(new FormData(e.target));
        await api("/pos", "POST", { ...v, need_qc: v.need_qc === "1" });
        closeModal(); toast("Đã tạo PO mới"); window.route();
      } catch (x) { toast(x.message, false); }
    };
  } else {
    document.getElementById("poFile").onchange = async (e) => {
      const f = e.target.files[0];
      if (!f) return;
      if (f.name.toLowerCase().endsWith(".xlsx")) {
        toast(`Đang đọc file Excel ${f.name}...`);
        await poRunParse(f);
      } else {
        document.getElementById("rawPo").value = await f.text();
        await poRunParse();
      }
    };
  }
}

function poAsnEdit(id) {
  const o = pos.find((x) => x.id === id);
  form("Bổ sung / Chuẩn hóa chứng từ ASN — " + o.po_no, [
    { k: "asn_no", label: "Mã ASN từ nhà cung cấp", val: o.asn_no || ("ASN-" + Date.now().toString().slice(-4)) },
    { k: "asn_uom", label: "Đơn vị tính chuẩn hóa (PO yêu cầu: " + o.unit + ")", val: o.unit },
    { k: "asn_batch", label: "Mã lô sản xuất (NCC)", val: o.asn_batch || o.pre_label.batch_id, opt: 1 },
    { k: "asn_exp", label: "Hạn sử dụng dự kiến", type: "date", val: o.asn_exp || "" },
    { k: "need_qc", label: "Yêu cầu kiểm định QC (Khu cách ly)", opts: [["0", "Không"], ["1", "Có — giữ chỗ Khu 8 (Quarantine)"]] },
  ], (v) => api(`/pos/${id}/asn`, "POST", v), "Lưu ASN");
}

function poPickOpt(id, idx) {
  const o = pos.find((x) => x.id === id);
  const p = o?.dock_opts?.[idx];
  if (!p) return;
  document.getElementById("sDock").value = p.dock;
  document.getElementById("sSlot").value = p.slot;
  document.getElementById("sWrk").value = p.workers;
  document.getElementById("sMin").value = p.est_min;
  document.getElementById("sFk").value = p.forklift;
}

function poScheduleModal(id) {
  const o = pos.find((x) => x.id === id);
  const opt0 = o.dock_opts[0] || { dock: "N1", slot: INB_SLOTS[0], est_min: 45, workers: 2, forklift: "Xe nâng tiêu chuẩn" };
  const optsHtml = o.dock_opts.map((p, i) => `<li><b>Phương án ${i + 1}:</b> Cửa <span class="loc">${p.dock}</span> · Khung <b>${p.slot}</b> · ~${p.est_min} phút · ${p.workers} người · ${esc(p.forklift)}
    <small>${esc(p.reason)}</small>
    <button type="button" class="btn sm ghost" style="margin-top:6px" onclick="poPickOpt(${id}, ${i})">Chọn phương án này</button></li>`).join("");
  openModal(`<h2>CV2: Điều phối Time-slot & Nguồn lực (${esc(o.po_no)})</h2>
    <div class="callout info"><b>Gợi ý sắp xếp tối ưu theo luồng chữ U:</b><ul class="list" style="margin-top:8px">${optsHtml || "<li>Chọn khung giờ trống bên dưới</li>"}</ul></div>
    <form id="schF">
      <label>Cửa nhập (N1–N2 gần kho lạnh, N3–N4 kho khô/mỹ phẩm)<select id="sDock" name="dock">${["N1", "N2", "N3", "N4"].map((d) => `<option value="${d}" ${d === (o.dock || opt0.dock) ? "selected" : ""}>Cửa ${d}</option>`).join("")}</select></label>
      <label>Khung giờ tiếp nhận (Time-slot)<select id="sSlot" name="slot_time">${INB_SLOTS.map((s) => `<option value="${s}" ${s === (o.slot_time || opt0.slot) ? "selected" : ""}>${s}</option>`).join("")}</select></label>
      <label>Thời lượng dỡ dự kiến (phút)<input id="sMin" name="est_min" type="number" value="${o.est_min || opt0.est_min}" required></label>
      <label>Số nhân sự bốc xếp<input id="sWrk" name="workers" type="number" value="${o.workers || opt0.workers}" required></label>
      <label>Thiết bị xe nâng<input id="sFk" name="forklift" value="${esc(o.forklift || opt0.forklift)}" required></label>
      <div class="acts"><button type="button" class="btn ghost" onclick="closeModal()">Hủy</button><button class="btn">Xác nhận Time-slot</button></div>
    </form>`);
  document.getElementById("schF").onsubmit = async (e) => {
    e.preventDefault();
    try {
      await api(`/pos/${id}/schedule`, "POST", Object.fromEntries(new FormData(e.target)));
      closeModal(); toast("Đã chốt lịch Dock & thông báo tổ Lưu kho"); window.route();
    } catch (x) { toast(x.message, false); }
  };
}

function poArrive(id) {
  const o = pos.find((x) => x.id === id);
  form("Cấp thẻ an toàn cổng & Xe cập bến (" + o.po_no + ")", [
    { k: "plate", label: "Biển số xe giao hàng", val: o.plate || "51D-778.90" },
    { k: "driver", label: "Tên tài xế", val: o.driver || "Nguyễn Văn Minh" },
    { k: "pre_batch", label: "Mã lô chuẩn FEFO (dán tem tạm)", val: o.pre_label.batch_id },
  ], (v) => api(`/pos/${id}/arrive`, "POST", v), "Cấp thẻ & Cập bến");
}

// In Biên bản Từ chối & Hoàn trả hàng cho NCC ngay tại cửa nhập (Dock Rejection / RTV)
function poPrintReject(rid) {
  const r = rejs.find((x) => x.id === rid);
  if (!r) return;
  const w = window.open("", "_blank", "width=820,height=720");
  if (!w) return toast("Trình duyệt đang chặn cửa sổ in — hãy cho phép popup", false);
  const kindTxt = r.kind === "full" ? "TỪ CHỐI TOÀN BỘ CHUYẾN XE TẠI DOCK" : "HOÀN TRẢ 1 PHẦN HÀNG LỖI NGAY TẠI DOCK";
  w.document.write(`<!DOCTYPE html><html lang="vi"><head><meta charset="utf-8"><title>Biên bản trả hàng NCC ${esc(r.rej_no)}</title>
    <style>body{font-family:"Segoe UI",sans-serif;padding:28px;color:#171717;line-height:1.55}
    h1{margin:0 0 4px;font-size:19px}table{width:100%;border-collapse:collapse;margin:14px 0}
    th,td{border:1px solid #bbb;padding:8px;text-align:left;font-size:13px}
    .sign{display:grid;grid-template-columns:1fr 1fr;gap:32px;margin-top:36px;text-align:center}
    .sig-box{height:76px;border-bottom:1px dashed #888;margin:12px 24px 6px}
    @media print{.noprint{display:none}}</style></head><body>
    <div style="display:flex;justify-content:space-between;align-items:flex-start;border-bottom:2px solid #222;padding-bottom:12px">
      <div><h1>BIÊN BẢN TỪ CHỐI & HOÀN TRẢ HÀNG TẠI DOCK (RTV)</h1>
        <div>Số biên bản: <b>${esc(r.rej_no)}</b> · Loại: <b>${kindTxt}</b></div>
        <div>Thời điểm lập: <b>${dmyt(r.created_at)}</b> · Cửa nhập: <b>${esc(r.dock || "Dock")}</b></div></div>
      <button class="noprint" onclick="window.print()" style="padding:8px 16px;cursor:pointer">In / Lưu PDF</button>
    </div>
    <table>
      <tr><th>Mã PO</th><th>Nhà cung cấp</th><th>Biển số xe</th><th>Tài xế giao hàng</th></tr>
      <tr><td><b>${esc(r.po_no)}</b></td><td>${esc(r.supplier || "-")}</td><td>${esc(r.plate || "-")}</td><td>${esc(r.driver || "-")}</td></tr>
    </table>
    <table>
      <tr><th>SKU</th><th>Sản phẩm</th><th>SL từ chối trả về</th><th>SL đạt nhập kho</th><th>Nhiệt độ đo tại thùng xe</th></tr>
      <tr><td><b>${esc(r.sku)}</b></td><td>${esc(r.product_name)}</td><td><b style="color:#b92b2b">${num(r.qty_rejected)} thùng</b></td>
        <td>${num(r.qty_accepted)} thùng</td><td>${r.measured_temp != null ? `<b>${r.measured_temp}°C</b>` : "Không áp dụng"}</td></tr>
    </table>
    <div style="border:1px solid #b92b2b;background:#fbe5e4;padding:12px;border-radius:6px">
      <b>Lý do từ chối tại hiện trường (trước khi nhập kho):</b> ${esc(r.reason)}
    </div>
    <p style="font-size:13px;margin-top:12px">Hai bên xác nhận số lượng hàng bị từ chối nêu trên chưa ký nhập tồn kho và đã được bàn giao lại cho tài xế/nhà cung cấp chở về ngay tại cửa nhập.</p>
    <div class="sign">
      <div><b>ĐẠI DIỆN KHO (INBOUND)</b><div class="sig-box"></div><small>Người lập: ${esc(r.created_by)}</small></div>
      <div><b>TÀI XẾ / ĐẠI DIỆN NCC</b><div class="sig-box"></div><small>Xác nhận nhận lại đủ ${num(r.qty_rejected)} thùng chở về</small></div>
    </div></body></html>`);
  w.document.close();
}

function poRejectModal(id) {
  const o = pos.find((x) => x.id === id);
  const cold = o.storage === "chilled" || o.storage === "frozen";
  const tempHint = o.storage === "frozen" ? "Chuẩn đông lạnh ≤ -18°C" : (o.storage === "chilled" ? "Chuẩn hàng mát 2–8°C" : "Không bắt buộc với hàng khô");
  form(`Từ chối toàn bộ tại Dock — ${o.po_no} (${num(o.qty)} thùng)`, [
    { k: "reason", label: "Lý do từ chối ngay tại cửa nhập", opts: [
      ["Nhiệt độ thùng xe vượt ngưỡng bảo quản", "Nhiệt độ thùng xe vượt ngưỡng bảo quản"],
      ["Hàng hết hạn hoặc dưới chuẩn % HSD nhập kho", "Hàng hết hạn hoặc dưới chuẩn % HSD nhập kho"],
      ["Bao bì móp méo, rách vỡ hoặc ẩm ướt diện rộng", "Bao bì móp méo, rách vỡ hoặc ẩm ướt diện rộng"],
      ["Sai mã SKU / sai quy cách so với PO", "Sai mã SKU / sai quy cách so với PO"],
      ["Không có chứng từ an toàn / nhiễm mùi lạ", "Không có chứng từ an toàn / nhiễm mùi lạ"],
    ] },
    { k: "measured_temp", label: `Nhiệt độ đo thực tế tại thùng xe °C (${tempHint})`, val: cold ? (o.storage === "frozen" ? "-5" : "12") : "", opt: 1 },
    { k: "plate", label: "Biển số xe giao hàng", val: o.plate || "51D-778.90", opt: 1 },
    { k: "driver", label: "Tên tài xế ký nhận chở về", val: o.driver || "Nguyễn Văn Minh", opt: 1 },
    { k: "note", label: "Ghi chú chi tiết hiện trường", opt: 1 },
  ], (v) => api(`/pos/${id}/reject`, "POST", v), "Lập biên bản Từ chối tại Dock");
}

function poRecv(id) {
  const o = pos.find((x) => x.id === id);
  const cold = o.storage === "chilled" || o.storage === "frozen";
  form("Nhận hàng vào kho — " + o.po_no, [
    { k: "batch_no", label: "Số lô (Batch FEFO)", val: o.pre_batch || o.pre_label.batch_id },
    { k: "exp", label: "Hạn sử dụng thực tế", type: "date", val: o.asn_exp || "" },
    ...(cold ? [{ k: "measured_temp", label: `Nhiệt độ đo tại thùng xe °C (${o.storage === "frozen" ? "yêu cầu ≤ -18°C" : "yêu cầu 2–8°C"})`, val: o.storage === "frozen" ? "-19" : "5", opt: 1 }] : []),
    { k: "qty", label: "Số lượng đạt (thùng — cộng tồn kho)", type: "number", val: o.qty },
    { k: "dmg", label: "Số lượng hỏng/móp trả NCC ngay tại Dock (tự lập biên bản RTV)", type: "number", val: 0 },
    { k: "dmg_reason", label: "Lý do trả phần hàng hỏng (nếu SL hỏng > 0)", val: "Thùng móp vỡ lúc dỡ hàng — trả tài xế chở về tại Dock", opt: 1 },
    ...(o.need_qc ? [{ k: "to_qc", label: "Đưa lô vào trạng thái Cách ly QC?", opts: [["0", "Đạt QC — nhập kệ ngay"], ["1", "Chuyển Cách ly QC (chưa cho soạn)"]] }] : []),
  ], (v) => api(`/pos/${id}/receive`, "POST", { ...v, to_qc: v.to_qc === "1" }), "Xác nhận nhập kho");
}

function dockGantt(pend) {
  const docks = [["N1", "Cửa N1 (Lạnh)"], ["N2", "Cửa N2 (Lạnh)"], ["N3", "Cửa N3 (Khô)"], ["N4", "Cửa N4 (Khô)"]];
  return `<div class="gantt">${docks.map(([dk, lb]) => {
    const items = pend.filter((o) => o.dock === dk && o.slot_time);
    const blks = items.map((o) => {
      const i = Math.max(0, INB_SLOTS.indexOf(o.slot_time));
      const left = (i / INB_SLOTS.length) * 100;
      const w = (1 / INB_SLOTS.length) * 96;
      const cold = o.storage === "chilled" || o.storage === "frozen";
      return `<div class="gantt-blk ${cold ? "cold" : ""} ${o.priority === "urgent" ? "sla" : ""}" style="left:${left}%;width:${w}%" title="${esc(o.po_no)} · ${esc(o.slot_time)}">
        <b>${esc(o.po_no)}</b> ${esc(o.slot_time)}<br>${esc(o.sku)} (${num(o.qty)})</div>`;
    }).join("");
    return `<div class="gantt-row"><b>${lb}</b><div class="gantt-track">${blks || `<span style="padding:10px;display:inline-block;color:var(--muted);font-size:.75rem">Trống lịch</span>`}</div></div>`;
  }).join("")}</div>`;
}

async function render() {
  [pos, rejs] = await Promise.all([api("/pos"), api("/pos/rejections")]);
  const pend = pos.filter((o) => o.status === "pending");
  const hasAsn = pend.filter((o) => o.asn_no).length;
  const pctAsn = pend.length ? Math.round(hasAsn / pend.length * 100) : 100;
  const urg = pend.filter((o) => o.priority === "urgent").length;
  const sched = pend.filter((o) => o.dock && o.slot_time).length;
  const arrived = pend.filter((o) => o.plan_status === "arrived").length;

  const tabs = `<div class="tabs">
    <button class="${tab === "cv1" ? "on" : ""}" onclick="inbTab('cv1')">CV1 · Rà soát PO / ASN (${pend.length})</button>
    <button class="${tab === "cv2" ? "on" : ""}" onclick="inbTab('cv2')">CV2 · Lịch xe & Dock N1–N4</button>
    <button class="${tab === "cv3" ? "on" : ""}" onclick="inbTab('cv3')">CV3 · Mặt bằng & Khu QC</button>
    <button class="${tab === "cv4" ? "on" : ""}" onclick="inbTab('cv4')">CV4 · Tem nhãn, Nhận kho & Trả tại Dock (${rejs.length})</button>
  </div>`;

  let content = "";
  if (tab === "cv1") {
    const body = pos.map((o) => {
      const warnHtml = o.status === "pending" && o.ai_issues.length
        ? `<div class="callout warn" style="margin:6px 0 0;padding:6px 10px;font-size:.8rem"><b>Phát hiện thiếu/lệch:</b> ${o.ai_issues.map(esc).join(" · ")}</div>`
        : (o.status === "pending" ? `<small style="color:var(--ok)">✓ Chứng từ PO/ASN hợp lệ, khớp UOM</small>`
          : (o.status === "rejected" ? `<small style="color:var(--bad)"><b>Từ chối tại Dock:</b> ${esc(o.reject_reason || "")}</small>` : ""));
      let acts = "";
      if (o.status === "pending" && can("po.receive")) {
        acts = `<button class="btn sm ghost" onclick="poAsnEdit(${o.id})">Sửa ASN</button>`;
        if (o.plan_status === "draft") {
          acts += ` <button class="btn sm" ${o.ai_issues.length ? "disabled title='Cần bổ sung ASN/UOM trước'" : ""} onclick="run(() => api('/pos/${o.id}/validate', 'POST'), 'Đã khóa chứng từ — Sẵn sàng xếp lịch')">Xác nhận PO hợp lệ</button>`;
        }
        acts += ` <button class="btn sm ok" onclick="poRecv(${o.id})">Nhận nhanh</button>`;
      } else if (o.rejections && o.rejections.length) {
        acts = `<button class="btn sm ghost" onclick="poPrintReject(${o.rejections[0].id})">In biên bản ${esc(o.rejections[0].rej_no)}</button>`;
      }
      const stBadge = o.status === "pending"
        ? `<span class="tag info">${STEP_LABEL[o.plan_status] || o.plan_status}</span>`
        : (o.status === "rejected"
          ? `<span class="tag bad">Từ chối tại Dock (${num(o.dmg)})</span>`
          : `<span class="tag ok">Đã nhận ${num(o.recv)}</span>${o.dmg ? ` <span class="tag bad">Trả tại Dock ${o.dmg}</span>` : ""}`);
      return `<tr><td><b>${o.po_no}</b><small>ASN: ${esc(o.asn_no || "Thiếu")}</small>${prioTag(o)}</td>
        <td>${esc(o.sku)} ${esc(o.name)}<small>${esc(o.supplier)} · ${STORE[o.storage]}</small>${warnHtml}${o.status === "pending" ? stepPills(o.plan_status) : ""}</td>
        <td class="r">${num(o.qty)} ${esc(o.unit)}<small>ASN: ${esc(o.asn_uom || "-")}</small></td>
        <td>${dmy(o.eta)}<small>HSD: ${o.asn_exp ? dmy(o.asn_exp) : "Chưa có"}</small></td>
        <td>${stBadge}</td>
        <td class="r"><div class="tools" style="justify-content:flex-end">${acts}</div></td></tr>`;
    }).join("");
    content = `<div class="card"><h2>Danh sách PO/ASN & Kiểm tra toàn vẹn tự động</h2>
      ${table(["PO / Ưu tiên", "Sản phẩm & Cảnh báo", "SL / UOM*", "ETA / HSD", "Trạng thái", ""], body)}</div>`;
  } else if (tab === "cv2") {
    const body = pend.map((o) => {
      const opt = o.dock_opts[0];
      const rec = opt ? `Gợi ý: <b>${opt.dock}</b> · ${opt.slot} (${opt.workers} người, ~${opt.est_min}p)` : "Hết slot trống";
      return `<tr><td><b>${o.po_no}</b> ${prioTag(o)}<small>${esc(o.sku)} · ${num(o.qty)} thùng (${STORE[o.storage]})</small></td>
        <td>${dmy(o.eta)}</td>
        <td>${o.dock ? `<span class="loc">${esc(o.dock)}</span> <b>${esc(o.slot_time)}</b><small>${o.workers} người · ${esc(o.forklift || "")}</small>` : `<span class="tag warn">Chưa xếp lịch</span><small>${rec}</small>`}</td>
        <td class="r">${can("po.receive") ? `<button class="btn sm" onclick="poScheduleModal(${o.id})">${o.dock ? "Đổi lịch / Xử lý trễ" : "Xếp Time-slot"}</button>` : ""}</td></tr>`;
    }).join("");
    content = `<div class="card"><h2>Biểu đồ công suất cửa nhập (Dock Capacity N1–N4 · 07:30–16:30)</h2>${dockGantt(pend)}</div>
      <div class="card"><h2>Điều phối lịch xe & Phân bổ nguồn lực</h2>${table(["Đơn PO / Ưu tiên", "Ngày đến", "Lịch cửa & Nguồn lực", ""], body)}</div>`;
  } else if (tab === "cv3") {
    const body = pend.map((o) => {
      const ac = o.area_check;
      const warns = ac.warnings.length
        ? ac.warnings.map((w) => `<div class="callout warn" style="margin:4px 0;padding:6px 10px;font-size:.8rem">${esc(w)}</div>`).join("")
        : `<span class="tag ok">Đủ sức chứa & đạt điều kiện bảo quản</span>`;
      return `<tr><td><b>${o.po_no}</b><small>${esc(o.sku)} · ${num(o.qty)} thùng</small></td>
        <td><b>${esc(ac.zone_name)}</b> (${ac.zone_code})
          ${hbar("Sau khi nhập", ac.zone_after_pct, `${ac.zone_pct}% → ${ac.zone_after_pct}%`, capCls(ac.zone_after_pct))}
          <small>Còn trống ${ac.free_bins}/${ac.total_bins} ô kệ · Khu QC: ${ac.qc_reserved ? "Đã giữ chỗ Khu 8" : "Không yêu cầu"}</small></td>
        <td>${warns}</td>
        <td class="r">${o.area_ready ? `<span class="tag ok">✓ Đã sẵn sàng</span>` : (can("po.receive") ? `<button class="btn sm" onclick="run(() => api('/pos/${o.id}/area-ready', 'POST'), 'Đã xác nhận sẵn sàng mặt bằng')">Xác nhận mặt bằng</button>` : "")}</td></tr>`;
    }).join("");
    content = `<div class="card"><h2>Kiểm tra quỹ mặt bằng (Staging · Khu QC · Storage Zone)</h2>
      ${table(["PO / Hàng", "Sức chứa vùng lưu trữ đích", "Cảnh báo điểm nghẽn", ""], body)}</div>`;
  } else {
    const body = pend.map((o) => {
      const pl = o.pre_label;
      return `<tr><td><b>${o.po_no}</b><small>Dock ${esc(o.dock || "-")} · ${esc(o.slot_time || "-")}</small>
          ${o.gate_pass ? `<span class="tag ok">Thẻ ${esc(o.gate_pass)} · ${esc(o.plate || "")}</span>` : `<span class="tag warn">Chưa cập bến</span>`}</td>
        <td><span class="loc">${esc(pl.batch_id)}</span><div class="tools" style="margin-top:4px">${pl.badges.map((b) => `<span class="tag info">${esc(b)}</span>`).join("")}</div></td>
        <td><ul class="list" style="font-size:.8rem">${pl.checklist.map((c) => `<li style="padding:3px 0">• ${esc(c)}</li>`).join("")}</ul></td>
        <td class="r"><div class="tools" style="justify-content:flex-end">
          <button class="btn sm ghost" onclick="poPrint(${o.id})">In phiếu & Tem</button>
          ${can("po.receive") && o.plan_status !== "arrived" ? `<button class="btn sm" onclick="poArrive(${o.id})">Cấp thẻ cổng</button>` : ""}
          ${can("po.receive") ? `<button class="btn sm ok" onclick="poRecv(${o.id})">Nhận vào kho</button>
            <button class="btn sm red" onclick="poRejectModal(${o.id})">Từ chối tại Dock</button>` : ""}
        </div></td></tr>`;
    }).join("");
    const rejRows = rejs.map((r) => `<tr><td><b>${esc(r.rej_no)}</b><small>${dmyt(r.created_at)}</small></td>
      <td><b>${esc(r.po_no)}</b> · ${esc(r.sku)}<small>${esc(r.supplier || "-")}</small></td>
      <td><span class="tag ${r.kind === "full" ? "bad" : "warn"}">${r.kind === "full" ? "Từ chối toàn bộ" : "Trả 1 phần hỏng"}</span>
        <small>Trả NCC: <b>${num(r.qty_rejected)}</b> · Nhập kho: ${num(r.qty_accepted)}</small></td>
      <td>${r.measured_temp != null ? `<b>${r.measured_temp}°C</b><br>` : ""}${esc(r.reason)}<small>Xe ${esc(r.plate || "-")} · ${esc(r.driver || "-")}</small></td>
      <td class="r"><button class="btn sm ghost" onclick="poPrintReject(${r.id})">In biên bản ký</button></td></tr>`).join("");
    content = `<div class="card"><h2>Pre-labeling FEFO, Checklist an toàn cổng, Tiếp nhận & Từ chối ngay tại Dock</h2>
        ${table(["PO / Thẻ cổng", "Mã lô & Tem tạm", "Checklist kiểm tra tại Dock", ""], body)}</div>
      <div class="card"><h2>Biên bản Từ chối & Hoàn trả NCC ngay tại Dock (RTV)</h2>
        ${table(["Số biên bản", "PO / NCC", "Loại & Số lượng", "Nhiệt độ đo & Lý do hiện trường", ""], rejRows)}</div>`;
  }

  return `<div class="head"><div><h1>Nhập hàng & Kế hoạch tiếp nhận (Inbound)</h1>
    <p class="sub">Quy trình 4 bước: Rà soát PO/ASN → Điều phối Dock N1–N4 → Chuẩn bị mặt bằng/QC → Tem nhãn FEFO, Nhận kho & Từ chối tại Dock</p></div>
    ${can("po.create") ? `<div class="tools"><button class="btn ghost" onclick="poAdd('upload')">Upload Excel PO</button><button class="btn" onclick="poAdd('manual')">+ Tạo PO</button></div>` : ""}</div>
    <div class="kpis">
      ${kpi("% PO có ASN", pctAsn + "%", `${hasAsn}/${pend.length} PO chờ đã có ASN`)}
      ${kpi("PO Cờ Đỏ (Lạnh/HSD ngắn)", urg, "Ưu tiên cửa N1–N2 & FEFO")}
      ${kpi("Đã xếp Time-slot", `${sched}/${pend.length}`, "Cửa nhập N1–N4 luồng chữ U")}
      ${kpi("Biên bản trả tại Dock", rejs.length, `${arrived} xe đang chờ dỡ hàng`)}
    </div>
    ${tabs}${content}`;
}

Object.assign(window, { inbTab, poAdd, poFillSample, poDownloadTemplate, poRunParse, poSaveParsed, poAsnEdit, poPickOpt, poScheduleModal, poArrive, poRecv, poRejectModal, poPrint, poPrintReject });

export const page = { perm: ["po.view"], id: "inb", name: "Nhập hàng", desc: "PO/ASN, Dock & nhận lô", icon: "inb", render };
