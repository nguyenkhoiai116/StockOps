"""Feature: Tồn kho - theo lô, điều chỉnh, lịch sử, xuất CSV."""
import csv
import io

from flask import Blueprint, Response, jsonify, request

from ..core import do_adjust, run
from ..db import bad, db, day, rows

bp = Blueprint("inventory", __name__)


@bp.get("/api/inventory")
def api_inv():
    """Danh sách lô còn hàng (sắp theo hạn dùng) và 15 giao dịch kho gần nhất."""
    con = db()
    out = rows(con, """SELECT b.*, p.sku, p.name FROM batches b JOIN products p ON p.id=b.product_id
                       WHERE b.qty>0 ORDER BY b.exp""")
    txs = rows(con, """SELECT t.*, p.sku FROM txs t JOIN products p ON p.id=t.product_id
                       ORDER BY t.id DESC LIMIT 15""")
    con.close()
    return jsonify(batches=out, txs=txs, today=day(), near=day(30))


@bp.post("/api/inventory/<int:bid>/adjust")
def api_adjust(bid):
    """Điều chỉnh tồn (kiểm kê lệch, hàng vỡ, hủy lô). delta âm = giảm."""
    d = request.get_json(silent=True)
    d = d if isinstance(d, dict) else {}   # body hỏng hoặc không phải {...} -> báo lỗi rõ thay vì lỗi 500
    try:
        delta = int(d.get("delta"))
    except (TypeError, ValueError):
        return bad("Số điều chỉnh không hợp lệ")
    return run(do_adjust, bid, delta, d.get("note") or "Điều chỉnh tồn")   # luật nằm ở core.do_adjust


@bp.get("/api/export/inventory.csv")
def api_export():
    """Xuất tồn kho ra file CSV (mở được bằng Excel)."""
    con = db()
    f = io.StringIO()
    w = csv.writer(f)
    w.writerow(["SKU", "Tên", "Số lô", "Hạn dùng", "Vị trí", "Thực có", "Đã giữ", "Khả dụng"])
    for b in rows(con, "SELECT b.*, p.sku, p.name FROM batches b JOIN products p ON p.id=b.product_id WHERE b.qty>0 ORDER BY p.sku, b.exp"):
        w.writerow([b["sku"], b["name"], b["batch_no"], b["exp"], f"{b['zone']}-{b['bin']:02d}",
                    b["qty"], b["reserved"], b["qty"] - b["reserved"]])
    con.close()
    # "﻿" (BOM) giúp Excel hiển thị đúng tiếng Việt
    return Response("﻿" + f.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=ton-kho.csv"})
