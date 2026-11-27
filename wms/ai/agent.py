"""Kvis agent: 1 LLM, tự gọi tool đọc dữ liệu, vòng lặp viết tay (không dùng framework agent).

Luồng 1 câu hỏi:
1. Ghi trước 1 dòng chat_logs (transaction ngắn) -> có id để sau này gắn đề xuất (agent_actions).
2. Lặp tối đa MAX_STEPS lần: gửi tin nhắn + danh sách tool role này được dùng cho LLM.
   LLM gọi tool -> backend chạy tool (chỉ đọc) -> gửi kết quả lại. LLM trả chữ -> xong.
3. Hết bước mà chưa xong -> hỏi thêm 1 lần, không kèm tool, bắt trả lời bằng những gì đã tra.
4. Model không gọi được tool (NoTools) hoặc LLM_TOOLS=0 -> lui về cách cũ: dán ảnh chụp số liệu.
5. Cập nhật dòng chat_logs ở cuối (kể cả khi lỗi).

QUAN TRỌNG: không giữ khóa ghi database trong lúc chờ LLM (1 câu có thể mất vài chục giây).
Chỉ 2 transaction ngắn ở bước 1 và 5; giữa hai bước chỉ có câu SELECT (sqlite3 không mở transaction cho SELECT).
"""
import json
import os
import time

from . import llm
from .prompts import SYSTEM, agent_system, snapshot
from .tools import TOOLS, call, specs
from ..db import db, lock, now

MAX_STEPS = 5
NOTE = "\n\n(Chế độ ảnh chụp số liệu: Kvis trả lời từ bản tóm tắt số liệu, chưa tự tra thêm được.)"
LAST = "Đã hết số bước tra cứu. Trả lời ngay bằng những gì đã tra được, không gọi thêm tool."


def ask(user, text, hist):
    """Trả lời 1 câu hỏi của user (cần user["id"], ["name"], ["role"]). hist: các tin user/assistant gần nhất.
    Trả về {reply, model, mode, tools, steps, actions, sources}; lỗi LLM thì ghi log rồi raise LLMError."""
    con = db()
    t0 = time.monotonic()
    st = {"reply": None, "model": None, "mode": "agent", "steps": 0, "tools": [], "tok_in": 0, "tok_out": 0, "error": None}
    with con:
        lock(con)
        cid = con.execute("INSERT INTO chat_logs (ts, user_id, question, mode) VALUES (?,?,?,?)",
                          (now().isoformat(timespec="seconds"), user["id"], text, "agent")).lastrowid
    try:
        if os.getenv("LLM_TOOLS", "1").strip() == "0":
            snap(con, user, text, hist, st)
        else:
            try:
                loop(con, user, text, hist, st)
            except llm.NoTools as e:
                st["error"] = f"Lui về snapshot: {e}"   # giữ lý do để biết model thật sự thiếu tool hay request của mình sai
                snap(con, user, text, hist, st)
    except Exception as e:
        st["error"] = str(e) or type(e).__name__
        raise
    finally:
        save(con, cid, st, t0)
        con.close()
    used = []
    for c in st["tools"]:
        if c["ok"] and TOOLS[c["name"]]["label"] not in used:
            used.append(TOOLS[c["name"]]["label"])
    return {"reply": st["reply"], "model": st["model"], "mode": st["mode"], "tools": used,
            "steps": st["steps"], "actions": [], "sources": []}


def step(st, msgs, tools=None):
    """1 lần gọi LLM, cộng dồn số bước và token."""
    st["steps"] += 1
    r = llm.chat(msgs, tools=tools)
    u = r.get("usage") or {}
    st["model"] = r["model"]
    st["tok_in"] += u.get("prompt_tokens") or 0
    st["tok_out"] += u.get("completion_tokens") or 0
    return r


def args_of(a):
    """Tham số tool để ghi log: đọc được JSON thì lưu object, không thì lưu nguyên chuỗi."""
    try:
        return json.loads(a) if isinstance(a, str) and a.strip() else (a or {})
    except ValueError:
        return a


def loop(con, user, text, hist, st):
    """Cách chính: LLM tự gọi tool, tối đa MAX_STEPS bước."""
    msgs = [{"role": "system", "content": agent_system(user)}, *hist, {"role": "user", "content": text}]
    sp = specs(user["role"])
    for _ in range(MAX_STEPS):
        r = step(st, msgs, sp)
        if not r["calls"]:
            st["reply"] = r["text"]
            return
        for i, c in enumerate(r["calls"]):   # API bắt mỗi tool call có id để ghép với kết quả
            c["id"] = c.get("id") or f"call_{st['steps']}_{i}"
        msgs.append({"role": "assistant", "content": r["text"] or None, "tool_calls": r["calls"]})
        for c in r["calls"]:   # model gọi nhiều tool 1 lúc -> trả đủ từng kết quả, đúng id
            f = c.get("function") or {}
            res = call(con, user, f.get("name") or "", f.get("arguments"))
            st["tools"].append({"name": f.get("name") or "", "args": args_of(f.get("arguments")), "ok": "error" not in res})
            msgs.append({"role": "tool", "tool_call_id": c["id"], "content": json.dumps(res, ensure_ascii=False)})
    r = step(st, [*msgs, {"role": "user", "content": LAST}])
    if not r["text"]:
        raise llm.LLMError("Kvis tra cứu quá nhiều bước mà chưa trả lời được, hãy hỏi cụ thể hơn.")
    st["reply"] = r["text"]


def snap(con, user, text, hist, st):
    """Đường lui: dán ảnh chụp số liệu (chỉ phần role được xem) vào prompt, gọi LLM không kèm tool."""
    st["mode"] = "snapshot"
    msgs = [{"role": "system", "content": SYSTEM + "\n\n" + snapshot(con, user["role"])}, *hist,
            {"role": "user", "content": text}]
    st["reply"] = step(st, msgs)["text"] + NOTE


def save(con, cid, st, t0):
    """Cập nhật dòng chat_logs của câu hỏi (transaction ngắn)."""
    with con:
        lock(con)
        con.execute("""UPDATE chat_logs SET reply=?, model=?, mode=?, steps=?, tools=?, tok_in=?, tok_out=?, ms=?, error=?
                       WHERE id=?""",
                    (st["reply"], st["model"], st["mode"], st["steps"], json.dumps(st["tools"], ensure_ascii=False),
                     st["tok_in"], st["tok_out"], int((time.monotonic() - t0) * 1000), st["error"], cid))
