"""Feature: Tồn kho - theo lô, điều chỉnh, lịch sử, xuất CSV."""
import csv
import io

from flask import Blueprint, Response, jsonify, request

from ..core import run, zone_used
from ..db import db, day, log, rows

bp = Blueprint("inventory", __name__)


@bp.get("/api/inventory")
def api_inv():
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
    d = request.get_json()
    try:
        delta = int(d.get("delta"))
    except (TypeError, ValueError):
        from ..db import bad
        return bad("Số điều chỉnh không hợp lệ")

    def work(con):
        b = con.execute("SELECT b.*, z.cap, z.name AS zname FROM batches b JOIN zones z ON z.code=b.zone WHERE b.id=?",
                        (bid,)).fetchone()
        if not b or delta == 0:
            raise ValueError("Không có gì để điều chỉnh")
        new = b["qty"] + delta
        if new < 0:
            raise ValueError("Không cho phép tồn kho âm")
        if new < b["reserved"]:
            raise ValueError(f"Lô đang giữ {b['reserved']} thùng cho đơn hàng, không giảm thấp hơn được")
        if delta > 0 and zone_used(con, b["zone"]) + delta > b["cap"]:
            raise ValueError(f"{b['zname']} không đủ sức chứa")
        con.execute("UPDATE batches SET qty=? WHERE id=?", (new, bid))
        log(con, "ADJ", b["product_id"], b["batch_no"], delta, d.get("note") or "Điều chỉnh tồn")

    return run(work)


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
