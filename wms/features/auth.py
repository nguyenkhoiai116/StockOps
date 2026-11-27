"""Feature: Đăng nhập và chặn quyền.

Mọi request tới /api/ đều đi qua guard(): chưa đăng nhập -> 401, sai quyền -> 403,
API chưa khai báo trong wms/roles.py -> 403 (mặc định là chặn).
Phiên đăng nhập nằm trong cookie có chữ ký của Flask (trình duyệt không sửa được, JS không đọc được).
"""
import hashlib
import time
from urllib.parse import urlsplit

from flask import Blueprint, g, jsonify, request, session
from werkzeug.security import check_password_hash, generate_password_hash

from ..db import bad, body, db, lock
from ..roles import ANY, PERMS, PUBLIC, ROLES, perm_of
from ..users import MIN, set_password

bp = Blueprint("auth", __name__)

WAIT = 300                # khóa tạm 5 phút khi sai nhiều lần
MAX_USER, MAX_IP = 5, 20  # số lần sai tối đa: của 1 tài khoản từ 1 máy / của 1 máy (bảng login_fails)
DUMMY = generate_password_hash("x")   # để tài khoản không tồn tại cũng tốn thời gian kiểm tra như thật


def stamp(u):
    """Dấu của mật khẩu hiện tại. Đổi mật khẩu thì các phiên cũ tự hết hiệu lực."""
    return hashlib.sha256(u["pw_hash"].encode()).hexdigest()[:16]


def current():
    """Người đang đăng nhập (đọc lại DB mỗi lần, nên khóa tài khoản / đổi role có hiệu lực ngay)."""
    uid = session.get("uid")
    if not uid:
        return None
    con = db()
    u = con.execute("SELECT * FROM users WHERE id=? AND active=1", (uid,)).fetchone()
    con.close()
    return u if u and u["pw_hash"] and session.get("pw") == stamp(u) else None


@bp.before_app_request
def guard():
    """Chốt chặn chung của mọi API."""
    g.user = None
    if not request.path.startswith("/api/") or request.method == "OPTIONS" or request.url_rule is None:
        return None
    # Chặn trang web khác gửi lệnh ghi bằng phiên của người dùng (CSRF)
    origin = request.headers.get("Origin")
    if request.method not in ("GET", "HEAD") and origin and urlsplit(origin).netloc != request.host:
        return bad("Yêu cầu đến từ trang khác, đã bị chặn", 403)
    g.user = current()
    key = f"{'GET' if request.method == 'HEAD' else request.method} {request.url_rule.rule}"
    if key in PUBLIC:
        return None
    if not g.user:
        return bad("Bạn cần đăng nhập", 401)
    if key in ANY:
        return None
    p = perm_of(key)
    if not p or g.user["role"] not in PERMS[p][1]:
        return bad("Tài khoản của bạn không có quyền này", 403)
    return None


def info(u):
    """Thông tin gửi cho giao diện: tên, role và danh sách quyền (để ẩn nút)."""
    return u and {"username": u["username"], "name": u["name"], "role": u["role"], "role_name": ROLES[u["role"]],
                  "perms": [p for p, x in PERMS.items() if u["role"] in x[1]]}


def recent(con, ip, now, name=None):
    """Số lần sai còn trong thời gian khóa: của tài khoản name từ máy ip, hoặc của cả máy ip (name=None)."""
    sql = "SELECT COUNT(*) FROM login_fails WHERE ip=? AND ts>?" + (" AND username=?" if name is not None else "")
    return con.execute(sql, (ip, now - WAIT) + ((name,) if name is not None else ())).fetchone()[0]


@bp.get("/api/me")
def api_me():
    """Người đang đăng nhập; chưa đăng nhập thì user = null."""
    return jsonify(user=info(g.user))


@bp.post("/api/login")
def api_login():
    """Đăng nhập. Báo lỗi chung chung để không lộ tài khoản nào có thật."""
    d = body()
    name, pw = str(d.get("user") or "").strip().lower()[:64], str(d.get("pass") or "")[:256]
    now, ip = time.time(), request.remote_addr or "?"
    con = db()
    try:
        with con:   # dọn các lần sai đã quá thời gian khóa
            lock(con)
            con.execute("DELETE FROM login_fails WHERE ts<=?", (now - WAIT,))
        if recent(con, ip, now, name) >= MAX_USER or recent(con, ip, now) >= MAX_IP:
            return bad("Sai quá nhiều lần, thử lại sau 5 phút", 429)
        u = con.execute("SELECT * FROM users WHERE username=? AND active=1", (name,)).fetchone()
        # Kiểm mật khẩu ngoài transaction: băm mật khẩu mất ~0,1 giây, không giữ khóa ghi DB trong lúc đó
        ok = check_password_hash(u["pw_hash"] if u and u["pw_hash"] else DUMMY, pw)
        if not (ok and u and u["pw_hash"]):
            with con:
                lock(con)
                con.execute("INSERT INTO login_fails (ip, username, ts) VALUES (?,?,?)", (ip, name, now))
            return bad("Sai tài khoản hoặc mật khẩu", 401)
        with con:   # đăng nhập đúng: xóa các lần sai của tài khoản này từ máy này
            lock(con)
            con.execute("DELETE FROM login_fails WHERE ip=? AND username=?", (ip, name))
    finally:
        con.close()
    start(u)
    return jsonify(user=info(u))


def start(u):
    """Mở phiên mới cho người dùng u."""
    session.clear()
    session.permanent = True
    session["uid"], session["pw"] = u["id"], stamp(u)


@bp.post("/api/logout")
def api_logout():
    session.clear()
    return jsonify(ok=True)


@bp.post("/api/password")
def api_password():
    """Tự đổi mật khẩu; các phiên khác của tài khoản này bị đăng xuất."""
    d = body()
    old, new = str(d.get("old") or "")[:256], str(d.get("new") or "")
    if not check_password_hash(g.user["pw_hash"], old):
        return bad("Mật khẩu hiện tại không đúng")
    if not MIN <= len(new) <= 256:
        return bad(f"Mật khẩu mới cần từ {MIN} ký tự")
    con = db()
    with con:
        lock(con)
        set_password(con, g.user["username"], new)
    u = con.execute("SELECT * FROM users WHERE id=?", (g.user["id"],)).fetchone()
    con.close()
    start(u)
    return jsonify(ok=True)
