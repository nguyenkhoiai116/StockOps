"""Mật khẩu tài khoản: chỉ lưu dạng băm, không lưu chữ gốc."""
from werkzeug.security import generate_password_hash

MIN = 8   # độ dài mật khẩu tối thiểu


def set_password(con, username, pw):
    """Đặt mật khẩu cho 1 tài khoản. Trả về số tài khoản đã đổi."""
    return con.execute("UPDATE users SET pw_hash=? WHERE username=?", (generate_password_hash(pw), username)).rowcount
