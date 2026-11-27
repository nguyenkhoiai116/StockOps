"""Feature: Phối hợp liên phòng ban — Hệ thống Chat nội bộ giữa các user/role và Lịch sử thao tác (Audit Trail)."""
from flask import Blueprint, g, jsonify, request

from ..core import now_iso
from ..db import bad, db, rows
from ..roles import ROLES

bp = Blueprint("collab", __name__)

CHANNELS = {
    "all": "Toàn kho",
    "inbound": "Nhập kho",
    "storage": "Lưu kho",
    "picking": "Soạn hàng",
    "shipping": "Xuất kho",
    "admin": "Quản lý",
}


@bp.get("/api/collab/audit")
def api_audit():
    """Lịch sử thao tác của tất cả các role trước đó; hỗ trợ lọc theo role, module và từ khóa."""
    role = (request.args.get("role") or "").strip()
    mod = (request.args.get("module") or "").strip()
    q = (request.args.get("q") or "").strip().lower()
    sql, args = "SELECT * FROM audit_logs WHERE 1=1", []
    if role:
        sql += " AND role=?"
        args.append(role)
    if mod:
        sql += " AND module=?"
        args.append(mod)
    sql += " ORDER BY id DESC LIMIT 120"
    con = db()
    items = rows(con, sql, args)
    con.close()
    if q:
        items = [x for x in items if q in f"{x['ref_no']} {x['action']} {x['detail']} {x['user_name']}".lower()]
    return jsonify(items=items, roles=ROLES)


@bp.get("/api/collab/messages")
def api_team_messages():
    """Tin nhắn trao đổi nội bộ giữa các user/role theo kênh (polling 3–5 giây)."""
    ch = (request.args.get("channel") or "all").strip()
    con = db()
    if ch == "all":
        msgs = rows(con, "SELECT * FROM team_messages ORDER BY id DESC LIMIT 80")
    else:
        msgs = rows(con, "SELECT * FROM team_messages WHERE channel IN ('all', ?) ORDER BY id DESC LIMIT 80", (ch,))
    con.close()
    msgs.reverse()
    return jsonify(messages=msgs, channels=CHANNELS, roles=ROLES)


@bp.post("/api/collab/messages")
def api_team_send():
    """Gửi 1 tin nhắn trao đổi nội bộ cho phòng ban khác hoặc toàn kho."""
    d = request.get_json(silent=True) or {}
    body = str(d.get("body") or "").strip()
    ch = (d.get("channel") or "all").strip()
    ref_no = str(d.get("ref_no") or "").strip()[:32]
    if not body:
        return bad("Nội dung tin nhắn đang trống")
    if len(body) > 600:
        return bad("Tin nhắn quá dài (tối đa 600 ký tự)")
    if ch not in CHANNELS:
        ch = "all"
    u = g.user
    con = db()
    with con:
        con.execute(
            """INSERT INTO team_messages (ts, sender_user, sender_name, sender_role, channel, ref_no, body)
               VALUES (?,?,?,?,?,?,?)""",
            (now_iso(), u["username"], u["name"], u["role"], ch, ref_no, body),
        )
    con.close()
    return jsonify(ok=True)
