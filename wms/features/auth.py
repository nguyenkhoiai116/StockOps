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

from ..db import bad, db
from ..roles import ANY, PERMS, PUBLIC, ROLES, perm_of
from ..users import MIN, set_password

bp = Blueprint("auth", __name__)

WAIT = 300                # khóa tạm 5 phút khi sai nhiều lần
MAX_USER, MAX_IP = 5, 20  # số lần sai tối đa: của 1 tài khoản từ 1 máy / của 1 máy
fails = {}                # (ip, tài khoản hoặc None) -> thời điểm các lần sai gần đây
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


def body():
    d = request.get_json(silent=True)
    return d if isinstance(d, dict) else {}


def recent(k, now):
    """Số lần sai còn trong thời gian khóa."""
    fails[k] = [t for t in fails.get(k, []) if now - t < WAIT]
    if not fails[k]:
        del fails[k]
        return 0
    return len(fails[k])


@bp.get("/api/me")
def api_me():
    """Người đang đăng nhập; chưa đăng nhập thì user = null."""
    return jsonify(user=info(g.user))


@bp.post("/api/login")
def api_login():
    """Đăng nhập. Báo lỗi chung chung để không lộ tài khoản nào có thật."""
    d = body()
    name, pw = str(d.get("user") or "").strip().lower()[:64], str(d.get("pass") or "")[:256]
    now, ip = time.time(), request.remote_addr
    if len(fails) > 1000:   # dọn bộ nhớ
        for k in list(fails):
            recent(k, now)
    if recent((ip, name), now) >= MAX_USER or recent((ip, None), now) >= MAX_IP:
        return bad("Sai quá nhiều lần, thử lại sau 5 phút", 429)
    con = db()
    u = con.execute("SELECT * FROM users WHERE username=? AND active=1", (name,)).fetchone()
    con.close()
    ok = check_password_hash(u["pw_hash"] if u and u["pw_hash"] else DUMMY, pw)
    if not (ok and u and u["pw_hash"]):
        for k in ((ip, name), (ip, None)):
            fails.setdefault(k, []).append(now)
        return bad("Sai tài khoản hoặc mật khẩu", 401)
    fails.pop((ip, name), None)
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
        set_password(con, g.user["username"], new)
    u = con.execute("SELECT * FROM users WHERE id=?", (g.user["id"],)).fetchone()
    con.close()
    start(u)
    return jsonify(ok=True)
