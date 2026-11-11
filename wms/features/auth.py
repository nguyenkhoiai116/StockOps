"""Feature: Đăng nhập (giữ chỗ cho sau này).

Hiện chưa kiểm tra tài khoản. Khi làm thật, xử lý tại đây:
kiểm tra user/mật khẩu, tạo phiên đăng nhập, trả token.
"""
from flask import Blueprint

from ..db import bad

bp = Blueprint("auth", __name__)


@bp.post("/api/login")
def api_login():
    return bad("Chức năng đăng nhập sẽ được bổ sung sau", 501)
