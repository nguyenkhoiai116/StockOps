// Feature: Lưu trữ & Kiểm soát tồn kho (Nhóm 2: CV1–CV5) — Tồn/Điều chuyển 2 đầu, Slotting COI/FEFO, Dự báo/ROP, Kiểm kê RCA, SLOB.
import { api, can, icon, loc, table, form, kpi, hbar, capCls, expTag, dmy, dmyt, num, vnd, esc, STORE, toast } from "../core.js";

let tab = "lots";
let inv = null;
let intel = null;
let prods = [];
let slotRes = null;

const QC_TAG = { ok: ["Đạt QC", "ok"], hold: ["Chờ kiểm (Hold)", "warn"], quarantine: ["Cách ly QC", "bad"] };
const CNT_TAG = {
  open: ["Đang kiểm (Khóa vị trí)", "info"], recount: ["Yêu cầu đếm lại (Recount)", "warn"],
  pending_approve: ["Chờ phê duyệt", "bad"], approved: ["Đã duyệt", "ok"], rejected: ["Từ chối", ""],
};

function invTab(t) { tab = t; window.route(); }

function invAdj(id) {
  const b = inv.batches.find((x) => x.id === id);
  form(`Điều chỉnh lô ${b.batch_no} (đang có ${b.qty})`, [
    { k: "delta", label: "Số thay đổi (âm để giảm, vd -5)", type: "number", val: -1 },
    { k: "note", label: "Lý do điều chỉnh", val: "Kiểm kê lệch" },
  ], (v) => api(`/inventory/${id}/adjust`, "POST", v));
}

function invQc(id) {
  const b = inv.batches.find((x) => x.id === id);
  form(`Trạng thái chất lượng lô ${b.batch_no} (${b.sku})`, [
    { k: "q_status", label: "Trạng thái QC", opts: [["ok", "Đạt QC (cho phép soạn FEFO)"], ["hold", "Giữ lại chờ kiểm tra nhiệt độ/CL (Hold)"], ["quarantine", "Cách ly (Quarantine)"]] },
    { k: "note", label: "Ghi chú nguyên nhân", val: "Kiểm tra sau biến động nhiệt độ kho" },
  ], (v) => api(`/inventory/${id}/quality`, "POST", v));
}

function invTransferModal(bid, defZone, defBin) {
  const b = inv.batches.find((x) => x.id === bid);
  form(`Điều chuyển 2 đầu — Lô ${b.batch_no} (${b.zone}-${String(b.bin).padStart(2, "0")})`, [
    { k: "to_zone", label: "Khu đích (phải đúng vùng nhiệt độ)", val: defZone || b.zone },
    { k: "to_bin", label: "Số ô đích", type: "number", val: defBin || (b.bin + 1) },
    { k: "note", label: "Lý do điều chuyển", val: defBin ? "Re-slotting tối ưu ROI" : "Dồn hàng / tối ưu kệ" },
  ], (v) => api("/storage/transfers", "POST", { ...v, batch_id: bid }), "Xuất nguồn (In-Transit)");
}

async function runSlotSuggest(e) {
  e.preventDefault();
  const fd = Object.fromEntries(new FormData(e.target));
  try {
    slotRes = await api("/storage/slot-suggest", "POST", fd);
    window.route();
  } catch (x) { toast(x.message, false); }
}

function invCountSubmit(cid, qSys) {
  form(`Nhập kết quả đếm thực tế (Tồn hệ thống: ${qSys} thùng)`, [
    { k: "q_physical", label: "Số lượng đếm thực tế (thùng)", type: "number", val: qSys },
  ], (v) => api(`/storage/counts/${cid}/submit`, "POST", v), "Ghi nhận số đếm");
}

async function invCreatePo(pid, qty, sku) {
  try {
    await api("/pos", "POST", { product_id: pid, qty });
    toast(`Đã tạo PO bổ sung ${qty} thùng ${sku}`);
    window.route();
  } catch (x) { toast(x.message, false); }
}

Object.assign(window, { invTab, invAdj, invQc, invTransferModal, runSlotSuggest, invCountSubmit, invCreatePo });

async function render() {
  [inv, intel, prods] = await Promise.all([api("/inventory"), api("/storage/intel"), api("/products")]);
  const KIND = { IN: ["Nhập", "ok"], OUT: ["Xuất", "info"], ADJ: ["Điều chỉnh", "warn"] };
  const tabs = `<div class="tabs">
    <button class="${tab === "lots" ? "on" : ""}" onclick="invTab('lots')">CV4 · Tồn theo lô & Điều chuyển 2 đầu</button>
    <button class="${tab === "slot" ? "on" : ""}" onclick="invTab('slot')">CV1 · Slotting COI/FEFO & Sức chứa</button>
    <button class="${tab === "rop" ? "on" : ""}" onclick="invTab('rop')">CV2 · Dự báo nhu cầu & ROP</button>
    <button class="${tab === "cnt" ? "on" : ""}" onclick="invTab('cnt')">CV3 · Kiểm kê ABC & RCA</button>
    <button class="${tab === "slob" ? "on" : ""}" onclick="invTab('slob')">CV5 · SLOB & Tồn dư thừa</button>
  </div>`;

  let bodyHtml = "";
  if (tab === "lots") {
    const lotsRows = inv.batches.map((b) => {
      const [qlb, qcls] = QC_TAG[b.q_status] || [b.q_status, ""];
      const acts = can("inv.adjust") ? `<div class="tools" style="justify-content:flex-end">
        <button class="btn sm ghost" onclick="invTransferModal(${b.id})" ${b.locked ? "disabled" : ""}>Chuyển vị trí</button>
        <button class="btn sm ghost" onclick="invQc(${b.id})">QC</button>
        <button class="btn sm ghost" onclick="invAdj(${b.id})" ${b.locked ? "disabled" : ""}>Điều chỉnh</button></div>` : "";
      return `<tr><td><b>${esc(b.sku)}</b><small>${esc(b.name)}</small></td>
        <td><b>${esc(b.batch_no)}</b>${b.locked ? ` <span class="tag info">Đang khóa</span>` : ""}</td>
        <td>${dmy(b.exp)} ${expTag(b.exp, inv.today, inv.near)}<small>Còn ${b.shelf_pct}% vòng đời</small></td>
        <td><span class="tag ${qcls}">${qlb}</span></td>
        <td>${loc(b.zone, b.bin)}</td>
        <td class="r">${num(b.qty)}</td><td class="r">${num(b.reserved)}</td><td class="r"><b>${num(b.qty - b.reserved)}</b></td>
        <td class="r">${acts}</td></tr>`;
    }).join("");

    const trRows = (inv.transfers || []).map((t) => `<tr><td>${dmyt(t.created_at)}</td>
      <td><b>${esc(t.sku)}</b> · ${esc(t.batch_no)} (${num(t.qty)} thùng)</td>
      <td>${loc(t.from_zone, t.from_bin)} → ${loc(t.to_zone, t.to_bin)}</td>
      <td><span class="tag ${t.status === "in_transit" ? "warn" : (t.status === "completed" ? "ok" : "")}">${t.status === "in_transit" ? "Đang vận chuyển" : (t.status === "completed" ? "Đã nhập đích" : "Đã hủy")}</span><small>${esc(t.note)}</small></td>
      <td class="r">${t.status === "in_transit" && can("inv.adjust") ? `<div class="tools" style="justify-content:flex-end">
        <button class="btn sm ok" onclick="run(() => api('/storage/transfers/${t.id}/confirm', 'POST', {action:'complete'}), 'Đã xác nhận nhập đích')">Xác nhận nhập đích</button>
        <button class="btn sm ghost" onclick="run(() => api('/storage/transfers/${t.id}/confirm', 'POST', {action:'cancel'}), 'Đã hủy lệnh chuyển')">Hủy</button></div>` : esc(t.confirmed_by || "-")}</td></tr>`).join("");

    const envWarns = (intel.capacity.zones || []).filter((z) => !z.temp_ok);
    const hist = inv.txs.map((t) => `<tr><td>${dmyt(t.ts)}</td><td><span class="tag ${KIND[t.kind][1]}">${KIND[t.kind][0]}</span></td>
      <td>${esc(t.sku)}</td><td>${esc(t.batch_no)}</td><td class="r">${t.qty > 0 ? "+" : ""}${num(t.qty)}</td><td>${esc(t.note)}</td></tr>`).join("");

    bodyHtml = `${envWarns.length ? `<div class="callout bad"><b>Cảnh báo môi trường bảo quản:</b> ${envWarns.map((z) => `${esc(z.name)} đang ${z.temp}°C (chuẩn ${z.tmin}..${z.tmax}°C)`).join(" · ")}. Hãy kiểm tra và dùng nút <b>QC</b> chuyển các lô bị ảnh hưởng sang trạng thái Chờ kiểm (Hold).</div>` : ""}
      <div class="card"><h2>Tồn kho theo lô & Trạng thái chất lượng</h2>${table(["Sản phẩm", "Lô", "Hạn dùng", "Chất lượng", "Vị trí", "Thực có*", "Đã giữ*", "Khả dụng*", ""], lotsRows)}</div>
      <div class="card"><h2>Lệnh điều chuyển giữa vị trí / khu (Xác nhận 2 đầu)</h2>${table(["Thời gian", "Lô hàng", "Nguồn → Đích", "Trạng thái", ""], trRows)}</div>
      <div class="card"><h2>Lịch sử giao dịch kho</h2>${table(["Thời gian", "Loại", "SKU", "Lô", "SL*", "Ghi chú"], hist)}</div>`;
  } else if (tab === "slot") {
    const zCards = intel.capacity.zones.map((z) => `<tr><td><b>${esc(z.name)}</b> (${z.code})<small>${z.temp}°C · ẩm ${z.hum}%</small></td>
      <td>${hbar("Thùng", z.pct, `${num(z.used_qty)}/${num(z.cap_qty)} (${z.pct}%)`, capCls(z.pct))}</td>
      <td>${z.used_bins}/${z.total_bins} ô (${z.bin_pct}%)<small>Thể tích ~${z.vol_used}/${z.vol_cap} m³</small></td>
      <td>${z.honeycomb ? `<span class="tag warn">${z.honeycomb} ô trống rải rác</span>` : `<span class="tag ok">Gọn</span>`}
        ${z.overload_warn ? ` <span class="tag bad">Sắp quá tải</span>` : ""}</td></tr>`).join("");
    const resRows = intel.capacity.reslots.map((r) => `<tr><td><b>${esc(r.sku)}</b> · ${esc(r.batch_no)} (${num(r.qty)} thùng)</td>
      <td>${loc(r.from_zone, r.from_bin)} → ${loc(r.to_zone, r.to_bin)}<small>${esc(r.to_spot)}</small></td>
      <td><span class="tag ok">ROI ${r.roi}×</span></td><td>${esc(r.reason)}</td>
      <td class="r">${can("inv.adjust") ? `<button class="btn sm" onclick="invTransferModal(${r.batch_id}, '${r.to_zone}', ${r.to_bin})">Tạo lệnh dời</button>` : ""}</td></tr>`).join("");
    const sugHtml = slotRes ? (slotRes.ok
      ? `<div class="callout ok"><b>Kết quả Slotting cho ${esc(slotRes.product.sku)}:</b> Nhóm <b>${slotRes.abc}</b> (${slotRes.freq} lượt xuất) · COI = <b>${slotRes.coi}</b> · Khu <b>${esc(slotRes.zone.name)}</b> (còn trống ${num(slotRes.free_cap)} thùng)</div>
         ${table(["Hạng", "Mã vị trí", "Tọa độ kệ", "Điểm*", "Lý do đề xuất"], slotRes.suggestions.map((s, i) =>
           `<tr><td><b>#${i + 1}</b></td><td>${loc(s.zone, s.bin)}</td><td>${esc(s.spot)}</td><td class="r"><b>${s.score}</b></td><td>${s.reasons.map(esc).join(" · ")}</td></tr>`).join(""))}`
      : `<div class="callout bad">${esc(slotRes.error)}</div>`) : `<p class="note">Chọn SKU, số lượng và hạn dùng để hệ thống lọc ràng buộc cứng (nhiệt độ, tương thích, tải trọng) và chấm điểm Top 3 vị trí kệ tốt nhất.</p>`;

    bodyHtml = `<div class="card"><h2>CV1 · Đề xuất vị trí lưu trữ (Ràng buộc cứng + ABC + COI + Golden Zone + FEFO)</h2>
      <form onsubmit="runSlotSuggest(event)" class="tools" style="margin-bottom:14px">
        <select name="product_id" style="min-width:260px">${prods.map((p) => `<option value="${p.id}">${esc(p.sku)} — ${esc(p.name)} (${STORE[p.storage]})</option>`).join("")}</select>
        <input name="qty" type="number" value="80" min="1" placeholder="Số thùng" style="width:120px" required>
        <input name="exp" type="date" title="Hạn sử dụng lô">
        <button class="btn">Tính Top 3 vị trí</button>
      </form>${sugHtml}</div>
      <div class="card"><h2>Phân tích sức chứa & Ô trống rải rác (Honeycombing)</h2>${table(["Khu kho", "Mức lấp đầy", "Ô kệ / Thể tích", "Cảnh báo"], zCards)}</div>
      <div class="card"><h2>Đề xuất sắp xếp lại kệ (Re-slotting chỉ đề xuất khi ROI ≥ 1.5)</h2>
        ${table(["Lô hàng", "Chuyển vị trí", "ROI", "Lý do", ""], resRows)}</div>`;
  } else if (tab === "rop") {
    const aCls = { crit: "bad", high: "bad", warn: "warn", ok: "ok" };
    const rowsHtml = intel.demand.map((d) => `<tr><td><b>${esc(d.sku)}</b><small>${esc(d.name)}</small><span class="tag">${d.abc} · ${esc(d.sb_class)}</span></td>
      <td><b>${d.forecast_day}/ngày</b><small>7 ngày: ${num(d.forecast_7d)} · ${esc(d.model)}</small><small>MAE ${d.mae_model} vs Naive ${d.mae_naive}</small></td>
      <td class="r"><b>${num(d.av)}</b><small>Đang về +${num(d.incoming)} · IP=${num(d.inv_pos)}</small></td>
      <td class="r">ROP ${num(d.rop)}<small>SS ${num(d.safety)} · EOQ ${num(d.eoq)}</small></td>
      <td class="r"><b>${d.doc} ngày</b><small>Lead ${d.lead_days} ngày</small></td>
      <td><span class="tag ${aCls[d.alert]}">${esc(d.alert_lbl)}</span>${d.cap_note ? `<small>${esc(d.cap_note)}</small>` : ""}</td>
      <td class="r">${d.rec_qty > 0 && can("po.create") ? `<button class="btn sm" onclick="invCreatePo(${d.product_id}, ${d.rec_qty}, '${esc(d.sku)}')">Đặt +${num(d.rec_qty)}</button>` : (d.rec_qty > 0 ? `<b>+${num(d.rec_qty)}</b>` : "-")}</td></tr>`).join("");
    bodyHtml = `<div class="callout info"><b>Phương pháp:</b> Phân loại Syntetos-Boylan (ADI / CV²), so sánh mô hình ứng viên với Baseline Naive (không thắng Naive thì dùng Naive), tính ROP = d×L + SS, chặn lượng đặt Q bởi sức chứa trống và hạn sử dụng.</div>
      <div class="card"><h2>Dự báo nhu cầu, Nguy cơ thiếu hàng & Đề xuất bổ sung (PO)</h2>
        ${table(["SKU / Phân loại", "Dự báo & Mô hình", "Tồn / IP*", "ROP / SS*", "DOC*", "Cảnh báo", "Đề xuất đặt"], rowsHtml)}</div>`;
  } else if (tab === "cnt") {
    const riskRows = intel.risks.map((r) => `<tr><td><b>${esc(r.sku)}</b> · ${esc(r.batch_no)}<small>${esc(r.name)}</small></td>
      <td>${loc(r.zone, r.bin)} <span class="tag">ABC: ${r.abc}</span></td>
      <td class="r">${num(r.qty)}<small>${vnd(r.value)}</small></td>
      <td><span class="tag ${r.risk_score >= 60 ? "bad" : (r.risk_score >= 35 ? "warn" : "ok")}">${r.risk_score} điểm</span></td>
      <td>${esc(r.reasons)}</td>
      <td class="r">${can("inv.adjust") ? `<button class="btn sm" ${r.locked ? "disabled" : ""} onclick="run(() => api('/storage/counts', 'POST', {batch_id:${r.batch_id}}), 'Đã mở đợt kiểm kê & khóa vị trí')">${r.locked ? "Đang khóa" : "Mở kiểm kê"}</button>` : ""}</td></tr>`).join("");

    const cntRows = (inv.counts || []).map((c) => {
      const [lb, cls] = CNT_TAG[c.status] || [c.status, ""];
      let act = "";
      if (can("inv.adjust")) {
        if (c.status === "open" || c.status === "recount") {
          act += `<button class="btn sm" onclick="invCountSubmit(${c.id}, ${c.q_system})">${c.status === "recount" ? "Đếm lại (Recount)" : "Nhập số thực tế"}</button>`;
        }
        if (c.status === "pending_approve" || c.status === "recount") {
          act += ` <button class="btn sm ok" onclick="run(() => api('/storage/counts/${c.id}/approve', 'POST', {action:'approve'}), 'Đã duyệt điều chỉnh & mở khóa vị trí')">Duyệt</button>`;
        }
        if (c.status !== "approved" && c.status !== "rejected") {
          act += ` <button class="btn sm ghost" onclick="run(() => api('/storage/counts/${c.id}/approve', 'POST', {action:'reject'}), 'Đã hủy đợt kiểm kê')">Hủy</button>`;
        }
      }
      return `<tr><td><b>#${c.id}</b> · ${esc(c.sku)} (${esc(c.batch_no)})<small>${loc(c.zone, c.bin)} · ${dmyt(c.created_at)}</small></td>
        <td class="r">HT: ${num(c.q_system)}<small>TT: ${c.q_physical ?? "-"}</small></td>
        <td class="r"><b>${c.q_physical == null ? "-" : (c.variance > 0 ? "+" : "") + num(c.variance)}</b><small>${c.val_diff ? vnd(Math.abs(c.val_diff)) : ""}</small></td>
        <td><span class="tag ${cls}">${lb}</span><small>${esc(c.approval_level || "")}</small></td>
        <td>${esc(c.rca_hint || "Chờ nhập số thực tế")}</td>
        <td class="r"><div class="tools" style="justify-content:flex-end">${act}</div></td></tr>`;
    }).join("");

    bodyHtml = `<div class="card"><h2>Đợt kiểm kê đang mở / Lịch sử đối chiếu (Cut-off · Recount · RCA)</h2>
        ${table(["Đợt / Lô", "HT vs TT*", "Chênh lệch*", "Trạng thái / Cấp duyệt", "Phân tích nguyên nhân (RCA)", ""], cntRows)}</div>
      <div class="card"><h2>Danh sách ưu tiên kiểm kê theo Điểm rủi ro (ABC Risk-based Cycle Counting)</h2>
        ${table(["SKU / Lô", "Vị trí", "Tồn / Giá trị*", "Điểm rủi ro", "Yếu tố rủi ro", ""], riskRows)}</div>`;
  } else {
    const expRows = intel.slob.expiry_risks.map((e) => `<tr><td><b>${esc(e.sku)}</b> · ${esc(e.batch_no)}<small>${esc(e.name)} · ${e.loc}</small></td>
      <td class="r">${num(e.qty)}<small>${vnd(e.lot_val)}</small></td>
      <td>${dmy(e.exp)}<small>Còn ${e.left_days} ngày (${e.shelf_pct}%)</small></td>
      <td class="r"><span class="tag bad">Cần ${e.sellout_days} ngày bán</span></td>
      <td><b>${esc(e.action)}</b><small>Thu hồi ròng dự kiến: ${vnd(e.net_promo)}</small></td></tr>`).join("");

    const slobRows = intel.slob.skus.map((s) => `<tr><td><b>${esc(s.sku)}</b><small>${esc(s.name)}</small></td>
      <td><span class="tag ${s.fsn.startsWith("Fast") ? "ok" : (s.fsn.startsWith("Slow") ? "warn" : "bad")}">${esc(s.fsn)}</span> <span class="tag">${esc(s.abc_xyz)}</span></td>
      <td class="r">DIO ${s.dio} ngày<small>Vòng quay ${s.turnover}×/năm</small></td>
      <td class="r">Khả dụng ${num(s.av)}<small>Mục tiêu ${num(s.target)}</small></td>
      <td class="r">${s.excess > 0 ? `<span class="tag warn">+${num(s.excess)} thùng</span><small>${vnd(s.excess_val)}</small>` : `<span class="tag ok">Không dư</span>`}</td>
      <td>${esc(s.recommendation)}</td></tr>`).join("");

    const totExcess = intel.slob.skus.reduce((s, x) => s + x.excess_val, 0);
    bodyHtml = `<div class="kpis">
        ${kpi("Lô nguy cơ không bán kịp", intel.slob.expiry_risks.length, "Ngày bán hết FEFO > Hạn còn lại")}
        ${kpi("Giá trị tồn dư thừa", vnd(totExcess), "Available − Target (SS + cover)")}
        ${kpi("SKU chậm / đứng (S/N)", intel.slob.skus.filter((x) => !x.fsn.startsWith("Fast")).length, "Theo phân loại FSN FMCG")}
        ${kpi("Tổng SKU theo dõi", intel.slob.skus.length, "Kết hợp ma trận ABC-XYZ")}
      </div>
      <div class="card"><h2>Phân tích nguy cơ hết hạn theo chuỗi FEFO (Expiry Risk Analysis)</h2>
        ${table(["Lô hàng", "SL / Giá trị*", "Hạn dùng", "Dự báo bán hết*", "Phương án thu hồi ròng"], expRows)}</div>
      <div class="card"><h2>Phân loại luân chuyển FSN, ABC-XYZ, DIO & Tồn dư thừa (SLOB)</h2>
        ${table(["SKU", "FSN / ABC-XYZ", "DIO / Vòng quay*", "Tồn vs Mục tiêu*", "Tồn dư thừa*", "Đề xuất xử lý"], slobRows)}</div>`;
  }

  return `<div class="head"><div><h1>Lưu trữ & Kiểm soát tồn kho (Storage & Inventory)</h1>
    <p class="sub">Slotting COI/FEFO · Dự báo nhu cầu & ROP · Kiểm kê Risk-based RCA · Điều chuyển 2 đầu · Phân tích SLOB</p></div>
    ${can("inv.export") ? `<a class="btn ghost" href="/api/export/inventory.csv">${icon("download")} Xuất CSV</a>` : ""}</div>
    ${tabs}${bodyHtml}`;
}

export const page = { perm: ["inv.view"], id: "inv", name: "Tồn kho", desc: "Lô, Slotting, ROP & SLOB", icon: "inv", render };
