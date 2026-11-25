// ===== CHAT: khung chat nổi ở góc phải dưới trang =====
import { esc, api, icon } from "./core.js";

const WELCOME = "Tôi là Kvis, trợ lý kho. Bạn cần hỏi gì?";
const MAX_HIST = 6;   // số tin nhắn gần nhất gửi kèm để Kvis nhớ ngữ cảnh

// Lịch sử hội thoại trong phiên (mất khi tải lại trang - cố ý, cho đơn giản)
const hist = [];

// Gửi câu hỏi lên backend (/api/chat). API key nằm ở backend, frontend không bao giờ thấy.
// Backend tự ghép số liệu kho hiện tại vào để Kvis trả lời theo dữ liệu thật.
async function botReply(text) {
  const d = await api("/chat", "POST", { text, history: hist.slice(-MAX_HIST) });
  // Chỉ lưu vào lịch sử khi hỏi-đáp thành công
  hist.push({ role: "user", content: text }, { role: "assistant", content: d.reply });
  return d.reply;
}

// Tạo nút chat, bong bóng lời chào và khung chat, gắn vào cuối <body>
export function mountChat() {
  const root = document.createElement("div");
  root.id = "chat";
  root.innerHTML = `
    <button class="chat-fab" id="chatFab" title="Trợ lý chat" aria-label="Mở chat"><img src="/icons/Chatbot.png" alt=""></button>
    <section class="chat-box" id="chatBox" hidden>
      <header class="chat-head">
        <b>Trợ lý Kvis</b>
        <button class="chat-close" id="chatClose" aria-label="Đóng">${icon("close")}</button>
      </header>
      <div class="chat-log" id="chatLog"></div>
      <form class="chat-form" id="chatForm">
        <input id="chatInput" placeholder="Nhập câu hỏi" autocomplete="off" maxlength="1000">
        <button class="btn" type="submit">Gửi</button>
      </form>
    </section>`;
  document.body.appendChild(root);

  const fab = root.querySelector("#chatFab");
  const box = root.querySelector("#chatBox");
  const log = root.querySelector("#chatLog");
  const form = root.querySelector("#chatForm");
  const input = root.querySelector("#chatInput");

  // Thêm 1 tin nhắn vào khung chat (who: "user" | "bot") và cuộn xuống cuối
  const addMsg = (who, text) => {
    const div = document.createElement("div");
    div.className = "chat-msg " + who;
    div.style.whiteSpace = "pre-wrap";   // giữ xuống dòng trong câu trả lời của Kvis
    div.innerHTML = esc(text);
    log.appendChild(div);
    log.scrollTop = log.scrollHeight;
    return div;
  };

  // Mở / đóng khung chat; khi mở thì ẩn nút tròn và đặt con trỏ vào ô nhập
  const setOpen = (open, focus = true) => {
    box.hidden = !open;
    fab.hidden = open;
    if (open && focus) input.focus();
  };

  // Bong bóng lời chào: hiện cạnh nút 5 giây khi mở web rồi tự ẩn.
  // Bấm vào bong bóng hoặc nút thì mở khung chat.
  const bubble = document.createElement("div");
  bubble.className = "chat-bubble";
  bubble.textContent = WELCOME;
  root.appendChild(bubble);

  const hideBubble = () => { bubble.hidden = true; };
  bubble.onclick = () => { hideBubble(); setOpen(true); };

  fab.onclick = () => { hideBubble(); setOpen(true); };
  root.querySelector("#chatClose").onclick = () => setOpen(false);

  setTimeout(hideBubble, 5000);

  // Gửi câu hỏi: hiện tin của người dùng, hiện "…" trong lúc chờ rồi thay bằng câu trả lời
  form.onsubmit = async (e) => {
    e.preventDefault();
    const text = input.value.trim();
    if (!text) return;
    input.value = "";
    addMsg("user", text);
    const pending = addMsg("bot", "Kvis đang suy nghĩ…");
    input.disabled = true;   // khóa ô nhập trong lúc chờ (model có thể mất vài giây)
    try {
      pending.textContent = await botReply(text);
    } catch (x) {
      pending.textContent = "Lỗi: " + x.message;   // lời giải thích lỗi do backend gửi về
    }
    input.disabled = false;
    input.focus();
    log.scrollTop = log.scrollHeight;
  };

  addMsg("bot", WELCOME);

  // Hỏi backend xem đã cấu hình API key chưa; chưa thì nhắc ngay trong khung chat
  api("/chat/status")
    .then((s) => { if (!s.ready) addMsg("bot", "Chưa có API key. Tạo file .env (xem .env.example) rồi chạy lại server."); })
    .catch(() => {});
}
