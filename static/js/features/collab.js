// Feature: Phối hợp liên phòng ban — Chat nội bộ giữa các user/role và Nhật ký thao tác (Audit Trail).
import { api, me, table, dmyt, esc, toast } from "../core.js";

let tab = "chat";
let ch = "all";
let timer = null;
let roleF = "", qF = "";

const CHANNELS = [
  ["all", "Toàn kho"], ["inbound", "Nhập kho"], ["storage", "Lưu kho"],
  ["picking", "Soạn hàng"], ["shipping", "Xuất kho"], ["admin", "Quản lý"],
];
const ROLE_TAG = {
  admin: ["Quản trị", "info"], inbound: ["Nhập kho", "ok"], storage: ["Lưu kho", "warn"],
  picking: ["Soạn hàng", "info"], shipping: ["Xuất kho", "bad"],
};

function roleBadge(r) {
  const [lb, cls] = ROLE_TAG[r] || [r, ""];
  return `<span class="tag ${cls}">${lb}</span>`;
}

async function loadChat() {
  const box = document.getElementById("teamFeed");
  if (!box) return;
  const d = await api("/collab/messages?channel=" + encodeURIComponent(ch));
  box.innerHTML = d.messages.length ? d.messages.map((m) => {
    const mine = me && m.sender_user === me.username;
    const chName = d.channels[m.channel] || m.channel;
    return `<div class="msg-item ${mine ? "mine" : ""}">
      <div class="msg-meta"><b>${esc(m.sender_name)}</b> ${roleBadge(m.sender_role)}
        <span class="tag">→ ${esc(chName)}</span>${m.ref_no ? `<span class="loc">${esc(m.ref_no)}</span>` : ""}
        <span style="margin-left:auto">${dmyt(m.ts)}</span></div>
      <div class="msg-body">${esc(m.body)}</div></div>`;
  }).join("") : `<div class="empty">Chưa có tin nhắn nào trong kênh này</div>`;
  box.scrollTop = box.scrollHeight;
}

async function loadAudit() {
  const box = document.getElementById("auditBox");
  if (!box) return;
  const p = new URLSearchParams();
  if (roleF) p.set("role", roleF);
  if (qF) p.set("q", qF);
  const d = await api("/collab/audit?" + p.toString());
  const rows = d.items.map((a) => `<tr><td>${dmyt(a.ts)}</td><td><b>${esc(a.user_name)}</b><small>${esc(a.username)}</small></td>
    <td>${roleBadge(a.role)}</td><td><b>${esc(a.action)}</b></td><td>${a.ref_no ? `<span class="loc">${esc(a.ref_no)}</span>` : "-"}</td>
    <td>${esc(a.detail)}</td></tr>`).join("");
  box.innerHTML = table(["Thời gian", "Người thực hiện", "Vai trò", "Thao tác", "Chứng từ", "Chi tiết"], rows);
}

async function colSend(e) {
  e.preventDefault();
  const f = e.target;
  const body = f.body.value.trim();
  if (!body) return;
  try {
    await api("/collab/messages", "POST", { channel: f.channel.value, ref_no: f.ref_no.value.trim(), body });
    f.body.value = "";
    f.ref_no.value = "";
    await loadChat();
  } catch (x) { toast(x.message, false); }
}

function colTab(t) { tab = t; window.route(); }
function colChan(c) { ch = c; window.route(); }
function colFilter() {
  roleF = document.getElementById("audRole")?.value || "";
  qF = document.getElementById("audQ")?.value || "";
  loadAudit();
}
Object.assign(window, { colTab, colChan, colSend, colFilter });

async function render() {
  const tabs = `<div class="tabs">
    <button class="${tab === "chat" ? "on" : ""}" onclick="colTab('chat')">Chat nội bộ liên phòng ban</button>
    <button class="${tab === "audit" ? "on" : ""}" onclick="colTab('audit')">Nhật ký thao tác các Role (Audit Trail)</button></div>`;
  if (tab === "chat") {
    return `<h1>Phối hợp liên phòng ban</h1>
      <p class="sub">Trao đổi trực tiếp giữa các bộ phận Nhập – Lưu trữ – Soạn – Xuất – Quản lý và theo dõi lịch sử bàn giao</p>
      ${tabs}
      <div class="card">
        <div class="tools" style="margin-bottom:12px">${CHANNELS.map(([k, lb]) =>
          `<button class="btn sm ${ch === k ? "" : "ghost"}" onclick="colChan('${k}')">${lb}</button>`).join("")}</div>
        <div id="teamFeed" class="chat-feed"><div class="empty">Đang tải tin nhắn...</div></div>
        <form onsubmit="colSend(event)" class="tools" style="align-items:stretch">
          <select name="channel" aria-label="Gửi tới kênh">${CHANNELS.map(([k, lb]) => `<option value="${k}" ${k === ch ? "selected" : ""}>Gửi tới: ${lb}</option>`).join("")}</select>
          <input name="ref_no" placeholder="Mã đơn/lô (vd SO-004)" style="width:165px">
          <input name="body" placeholder="Nhập tin nhắn phối hợp cho bộ phận khác..." style="flex:1 1 260px" required maxlength="600">
          <button class="btn">Gửi tin</button>
        </form>
      </div>`;
  }
  return `<h1>Phối hợp liên phòng ban</h1>
    <p class="sub">Lịch sử thao tác của tất cả các vai trò trước đó: ai làm gì, lúc nào, trên chứng từ nào</p>
    ${tabs}
    <div class="card">
      <div class="filters">
        <input id="audQ" type="search" value="${esc(qF)}" placeholder="Tìm mã đơn (PO/SO/TR), số lô, người thao tác..." oninput="colFilter()">
        <select id="audRole" onchange="colFilter()">
          <option value="">Mọi vai trò</option>
          ${Object.entries(ROLE_TAG).map(([k, [lb]]) => `<option value="${k}" ${roleF === k ? "selected" : ""}>${lb}</option>`).join("")}
        </select>
      </div>
      <div id="auditBox"><div class="empty">Đang tải nhật ký...</div></div>
    </div>`;
}

function after() {
  if (timer) clearInterval(timer);
  if (tab === "chat") {
    loadChat();
    timer = setInterval(loadChat, 4000);   // polling 4 giây theo kiến trúc StockOps
  } else {
    loadAudit();
  }
}
function leave() { if (timer) { clearInterval(timer); timer = null; } }

export const page = { perm: ["collab.use"], id: "collab", name: "Phối hợp", desc: "Chat nội bộ & nhật ký", icon: "collab", render, after, leave };
