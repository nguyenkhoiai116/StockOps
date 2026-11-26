"""Quản lý mật khẩu tài khoản bằng dòng lệnh (chạy trong thư mục dự án):

  python users.py                  xem danh sách tài khoản
  python users.py passwd admin     đặt mật khẩu cho 1 tài khoản
  python users.py passwd --moi     đặt chung 1 mật khẩu cho mọi tài khoản chưa có (chỉ dùng khi chạy thử)

Mật khẩu được hỏi khi chạy, không hiện trên màn hình và không nằm trong lịch sử lệnh.
"""
import sys
from getpass import getpass

from wms import create_app
from wms.db import db, rows
from wms.roles import ROLES
from wms.users import MIN, set_password


def main(args):
    create_app()   # tạo bảng và tài khoản mẫu nếu chưa có
    con = db()
    us = rows(con, "SELECT username, name, role, active, pw_hash IS NOT NULL AS has FROM users ORDER BY id")
    if not args:
        for u in us:
            print(f"{u['username']:<10} {ROLES[u['role']]:<10} {u['name']:<18} "
                  f"{'đã có mật khẩu' if u['has'] else 'CHƯA có mật khẩu'}{'' if u['active'] else ', đang khóa'}")
        return 0
    if len(args) != 2 or args[0] != "passwd":
        print(__doc__)
        return 2
    who = [u["username"] for u in us if (not u["has"] if args[1] == "--moi" else u["username"] == args[1])]
    if not who:
        print("Không có tài khoản nào phù hợp")
        return 1
    pw = getpass(f"Mật khẩu mới cho {', '.join(who)}: ")
    if not MIN <= len(pw) <= 256:
        print(f"Mật khẩu cần từ {MIN} ký tự")
        return 1
    if getpass("Nhập lại: ") != pw:
        print("Hai lần nhập không giống nhau")
        return 1
    with con:
        for u in who:
            set_password(con, u, pw)
    print("Đã đặt mật khẩu cho", ", ".join(who))
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    sys.exit(main(sys.argv[1:]))
