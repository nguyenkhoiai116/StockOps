"""Feature: Chat với trợ lý Kvis (nối LLM qua OpenRouter).

Luồng: giao diện gửi câu hỏi -> backend ghép [lời dặn + số liệu kho + lịch sử + câu hỏi]
-> gọi LLM -> trả câu trả lời. API key chỉ nằm ở backend, trình duyệt không bao giờ thấy.
"""
from flask import Blueprint, g, jsonify

from ..ai.llm import LLMError, cfg, chat, ready
from ..ai.prompts import SYSTEM, snapshot
from ..db import bad, body, db, text

bp = Blueprint("chat", __name__)

MAX_LEN = 1000    # độ dài tối đa 1 câu hỏi (ký tự)
MAX_HIST = 6      # chỉ gửi kèm 6 tin nhắn gần nhất -> đỡ tốn token


@bp.get("/api/chat/status")
def api_status():
    """Cho giao diện biết chat đã sẵn sàng chưa và đang dùng model nào (không lộ key)."""
    return jsonify(ready=ready(), model=cfg()["model"])


@bp.post("/api/chat")
def api_chat():
    """Nhận {text, history} và trả {reply, model}."""
    d = body()   # body hỏng -> {} -> "Câu hỏi đang trống", không gọi LLM
    q = text(d.get("text"))
    if not q:
        return bad("Câu hỏi đang trống")
    if len(q) > MAX_LEN:
        return bad(f"Câu hỏi dài quá {MAX_LEN} ký tự")

    # Lịch sử từ giao diện: chỉ nhận đúng 2 vai user/assistant, cắt ngắn từng tin
    hist = []
    his = d.get("history") if isinstance(d.get("history"), list) else []
    for m in his[-MAX_HIST:]:
        if isinstance(m, dict) and m.get("role") in ("user", "assistant"):
            hist.append({"role": m["role"], "content": str(m.get("content", ""))[:MAX_LEN * 2]})

    con = db()
    try:
        ctx = snapshot(con, g.user["role"])   # số liệu kho ngay lúc hỏi, chỉ phần role này được xem
    finally:
        con.close()

    msgs = [{"role": "system", "content": SYSTEM + "\n\n" + ctx}, *hist,
            {"role": "user", "content": q}]
    try:
        reply, model = chat(msgs)
    except LLMError as e:
        return bad(str(e), 502)   # 502 = lỗi từ dịch vụ bên ngoài
    return jsonify(reply=reply, model=model)
