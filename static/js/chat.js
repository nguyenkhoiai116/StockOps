// ===== CHAT: khung chat nổi ở góc phải dưới trang =====
// Hiện tại chỉ có giao diện. Để nối Claude API sau này, chỉ cần sửa hàm `botReply` bên dưới.
import { esc } from "./core.js";

const WELCOME = "Xin chào! Tôi là trợ lý Kvis. Bạn cần hỏi gì?";

// Điểm nối API: nhận câu hỏi của người dùng, trả về câu trả lời.
// TODO: thay phần giả lập bằng lời gọi backend, ví dụ:
//   const d = await api("/chat", "POST", { message: text });  return d.reply;
// Lưu ý: không đặt API key Claude ở frontend; gọi qua backend Python.
async function botReply(text) {
  await new Promise((r) => setTimeout(r, 400));   // giả lập độ trễ mạng
  return "(Chưa kết nối Claude API) Bạn vừa hỏi: " + text;
}

export function mountChat() {
  const root = document.createElement("div");
  root.id = "chat";
  root.innerHTML = `
    <button class="chat-fab" id="chatFab" title="Trợ lý chat" aria-label="Mở chat"><img src="/icons/Chatbot.png" alt=""></button>
    <section class="chat-box" id="chatBox" hidden>
      <header class="chat-head">
        <b>Trợ lý Kvis</b>
        <button class="chat-close" id="chatClose" aria-label="Đóng">✕</button>
      </header>
      <div class="chat-log" id="chatLog"></div>
      <form class="chat-form" id="chatForm">
        <input id="chatInput" placeholder="Nhập câu hỏi..." autocomplete="off" maxlength="1000">
        <button class="btn" type="submit">Gửi</button>
      </form>
    </section>`;
  document.body.appendChild(root);

  const fab = root.querySelector("#chatFab");
  const box = root.querySelector("#chatBox");
  const log = root.querySelector("#chatLog");
  const form = root.querySelector("#chatForm");
  const input = root.querySelector("#chatInput");

  const addMsg = (who, text) => {
    const div = document.createElement("div");
    div.className = "chat-msg " + who;
    div.innerHTML = esc(text);
    log.appendChild(div);
    log.scrollTop = log.scrollHeight;
    return div;
  };

  const setOpen = (open, focus = true) => {
    box.hidden = !open;
    fab.hidden = open;
    if (open && focus) input.focus();
  };

  // Bong bóng lời thoại kiểu truyện tranh: hiện cạnh nút 5 giây khi mở web, rồi tự ẩn.
  // Bấm vào bong bóng hoặc nút thì mở khung chat ngay.
  const bubble = document.createElement("div");
  bubble.className = "chat-bubble";
  bubble.textContent = WELCOME;
  root.appendChild(bubble);

  const hideBubble = () => { bubble.hidden = true; };
  bubble.onclick = () => { hideBubble(); setOpen(true); };

  fab.onclick = () => { hideBubble(); setOpen(true); };
  root.querySelector("#chatClose").onclick = () => setOpen(false);

  setTimeout(hideBubble, 5000);

  form.onsubmit = async (e) => {
    e.preventDefault();
    const text = input.value.trim();
    if (!text) return;
    input.value = "";
    addMsg("user", text);
    const pending = addMsg("bot", "…");
    try {
      pending.innerHTML = "";
      pending.textContent = await botReply(text);
    } catch (x) {
      pending.textContent = "Lỗi: " + x.message;
    }
    log.scrollTop = log.scrollHeight;
  };

  addMsg("bot", WELCOME);
}
