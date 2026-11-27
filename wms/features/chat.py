"""Feature: Chat với trợ lý Kvis (nối LLM qua OpenRouter).

Luồng: giao diện gửi câu hỏi -> agent Kvis (wms/ai/agent.py) tự gọi tool đọc số liệu theo quyền
của người hỏi -> trả câu trả lời kèm tên các tool đã tra. API key chỉ nằm ở backend, trình duyệt không bao giờ thấy.
"""
from flask import Blueprint, g, jsonify

from ..ai import agent
from ..ai.llm import LLMError, cfg, ready
from ..db import bad, body, text

bp = Blueprint("chat", __name__)

MAX_LEN = 1000    # độ dài tối đa 1 câu hỏi (ký tự)
MAX_HIST = 6      # chỉ gửi kèm 6 tin nhắn gần nhất -> đỡ tốn token


@bp.get("/api/chat/status")
def api_status():
    """Cho giao diện biết chat đã sẵn sàng chưa và đang dùng model nào (không lộ key)."""
    return jsonify(ready=ready(), model=cfg()["model"])


@bp.post("/api/chat")
def api_chat():
    """Nhận {text, history} và trả {reply, model, mode, tools, actions, sources} (xem agent.ask)."""
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

    try:
        r = agent.ask(g.user, q, hist)   # tool chỉ trả dữ liệu mà role của người hỏi được xem
    except LLMError as e:
        return bad(str(e), 502)   # 502 = lỗi từ dịch vụ bên ngoài
    return jsonify(reply=r["reply"], model=r["model"], mode=r["mode"], tools=r["tools"],
                   actions=r["actions"], sources=r["sources"])
