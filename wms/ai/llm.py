"""Gọi LLM qua API chuẩn OpenAI (mặc định: OpenRouter).

Cấu hình nằm trong file .env (KHÔNG commit lên GitHub):
    LLM_BASE_URL = https://openrouter.ai/api/v1
    LLM_API_KEY  = sk-or-...
    LLM_MODEL    = nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free

Đổi nhà cung cấp (LM Studio chạy local, Gemini...) chỉ cần đổi 3 dòng trên,
không phải sửa code, vì các bên đều nói chung "ngôn ngữ" /chat/completions.
"""
import os

import requests

TIMEOUT = 60   # chờ tối đa 60 giây; model miễn phí đôi khi trả lời chậm


class LLMError(Exception):
    """Lỗi khi gọi LLM, kèm câu giải thích tiếng Việt để hiện cho người dùng."""


class NoTools(LLMError):
    """Model đang cấu hình không hỗ trợ gọi tool -> agent lui về cách dán ảnh chụp số liệu."""


def cfg():
    """Đọc cấu hình từ biến môi trường (do .env nạp vào lúc khởi động)."""
    return {
        "url": os.getenv("LLM_BASE_URL", "https://openrouter.ai/api/v1").rstrip("/"),
        "key": os.getenv("LLM_API_KEY", "").strip(),
        "model": os.getenv("LLM_MODEL", "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free").strip(),
        "site": os.getenv("APP_URL", "http://localhost:5000"),
        "name": os.getenv("APP_NAME", "StockOps"),
    }


def ready():
    """Đã có API key chưa? (không trả key ra ngoài, chỉ trả đúng/sai)"""
    return bool(cfg()["key"])


# Lỗi HTTP thường gặp -> câu giải thích dễ hiểu
ERRS = {
    400: "Yêu cầu không hợp lệ (thường do tên model trong LLM_MODEL bị sai).",
    401: "API key sai hoặc đã bị thu hồi. Kiểm tra LLM_API_KEY trong file .env.",
    402: "Tài khoản OpenRouter hết credit. Nạp thêm hoặc đổi sang model có đuôi :free.",
    403: "Nội dung bị bộ lọc của nhà cung cấp chặn.",
    404: "Không tìm thấy model. Kiểm tra lại LLM_MODEL trên openrouter.ai/models.",
    408: "Model trả lời quá lâu, thử lại sau.",
    429: "Gửi quá nhiều yêu cầu (model miễn phí bị giới hạn lượt). Đợi một lúc rồi thử lại.",
    502: "Nhà cung cấp model đang lỗi, thử lại hoặc đổi model khác.",
    503: "Không có nhà cung cấp nào phục vụ model này lúc này, thử model khác.",
}


def chat(msgs, tools=None, temp=0.3, max_out=800):
    """Gửi danh sách tin nhắn cho LLM. Trả về dict:
        text  : câu trả lời (được phép rỗng khi model gọi tool)
        calls : nguyên mảng tool_calls của API [{"id", "type", "function": {"name", "arguments"}}], không có = []
        model : tên model đã dùng
        usage : số token {"prompt_tokens", "completion_tokens"} (nếu nhà cung cấp trả về)

    msgs: [{"role": "system"|"user"|"assistant"|"tool", "content": "..."}]
    tools: danh sách schema tool kiểu OpenAI; None = không cho model gọi tool.
    temp: độ "sáng tạo" (0 = chắc chắn, 1 = bay bổng). Trợ lý kho nên để thấp.
    max_out: số token tối đa của câu trả lời (chặn tốn chi phí).
    """
    c = cfg()
    if not c["key"]:
        raise LLMError("Chưa cấu hình LLM_API_KEY trong file .env.")

    req = {"model": c["model"], "messages": msgs, "temperature": temp, "max_tokens": max_out}
    if tools:
        req["tools"] = tools
    try:
        r = requests.post(
            f"{c['url']}/chat/completions",
            headers={
                "Authorization": f"Bearer {c['key']}",   # key chỉ nằm ở backend
                "Content-Type": "application/json",
                "HTTP-Referer": c["site"],               # tùy chọn: tên app hiện trên OpenRouter
                "X-OpenRouter-Title": c["name"],         # tùy chọn
            },
            json=req,
            timeout=TIMEOUT,
        )
    except requests.Timeout:
        raise LLMError("Hết thời gian chờ model trả lời. Thử lại sau.")
    except requests.ConnectionError:
        raise LLMError("Không kết nối được tới máy chủ LLM. Kiểm tra mạng hoặc LLM_BASE_URL.")

    # Lỗi HTTP: ưu tiên câu giải thích của mình, kèm thông báo gốc để dễ debug
    if r.status_code != 200:
        try:
            raw = r.json().get("error", {}).get("message", "")
        except ValueError:
            raw = r.text[:200]
        # OpenRouter báo model không gọi được tool bằng 404/400, vd "No endpoints found that support tool use".
        # Phải có cả "tool" lẫn "support"/"endpoint": lỗi do chính request (vd "tool_call_id" sai) không được coi là thiếu tool.
        low = str(raw).lower()
        if tools and r.status_code in (400, 404) and "tool" in low and ("support" in low or "endpoint" in low):
            raise NoTools(f"Model hiện tại không hỗ trợ gọi tool. ({raw})")
        msg = ERRS.get(r.status_code, f"Lỗi {r.status_code} từ máy chủ LLM.")
        raise LLMError(f"{msg} ({raw})" if raw else msg)

    d = r.json()
    # Có khi HTTP 200 nhưng bên trong vẫn báo lỗi (nhà cung cấp phía sau gặp sự cố)
    if d.get("error"):
        raise LLMError("Model báo lỗi: " + str(d["error"].get("message", d["error"])))
    try:
        m = d["choices"][0]["message"]
    except (KeyError, IndexError, TypeError):
        raise LLMError("Phản hồi của model không đúng định dạng.")
    text, calls = (m.get("content") or "").strip(), m.get("tool_calls") or []
    if not text and not calls:   # có tool call thì được phép không có chữ
        raise LLMError("Model trả về câu trả lời rỗng, thử hỏi lại.")
    return {"text": text, "calls": calls, "model": d.get("model", c["model"]), "usage": d.get("usage") or {}}
