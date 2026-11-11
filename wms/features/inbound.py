"""Feature: Nhập hàng - PO và nhận hàng theo lô."""
from flask import Blueprint, jsonify, request

from ..core import free_bin, zone_used
from ..db import BINS, bad, day, db, log, rows

bp = Blueprint("inbound", __name__)


@bp.get("/api/pos")
def api_pos():
    con = db()
    out = rows(con, """SELECT o.*, p.sku, p.name, p.supplier, p.storage FROM pos o
                       JOIN products p ON p.id=o.product_id ORDER BY o.status DESC, o.id DESC""")
    con.close()
    return jsonify(out)


@bp.post("/api/pos")
def api_po_add():
    d = request.get_json()
    qty = int(d.get("qty") or 0)
    if qty <= 0:
        return bad("Số lượng phải lớn hơn 0")
    con = db()
    with con:
        n = con.execute("SELECT COUNT(*) FROM pos").fetchone()[0] + 1
        con.execute("INSERT INTO pos (po_no,product_id,qty,eta) VALUES (?,?,?,?)",
                    (f"PO-{n:03d}", int(d["product_id"]), qty, d.get("eta") or day(1)))
    con.close()
    return jsonify(ok=True)


@bp.post("/api/pos/<int:po_id>/receive")
def api_po_receive(po_id):
    """Nhận hàng: tạo lô mới, cất vào đúng khu nhiệt độ, kiểm tra sức chứa, cộng tồn."""
    d = request.get_json()
    ok, dmg = int(d.get("qty") or 0), int(d.get("dmg") or 0)
    exp, no = d.get("exp", ""), (d.get("batch_no") or "").strip()
    if ok <= 0 or dmg < 0 or not no:
        return bad("Cần số lô và số lượng đạt > 0")
    if exp <= day():
        return bad("Hạn dùng phải sau hôm nay (không nhận hàng hết hạn)")
    con = db()
    try:
        with con:
            po = con.execute("SELECT o.*, p.storage FROM pos o JOIN products p ON p.id=o.product_id WHERE o.id=?",
                             (po_id,)).fetchone()
            if not po or po["status"] != "pending":
                raise ValueError("PO không tồn tại hoặc đã nhận")
            z = con.execute("SELECT * FROM zones WHERE storage=?", (po["storage"],)).fetchone()  # đúng vùng nhiệt
            if zone_used(con, z["code"]) + ok > z["cap"]:
                raise ValueError(f"{z['name']} không đủ sức chứa cho {ok} thùng")
            b = free_bin(con, z["code"], BINS)
            if b is None:
                raise ValueError(f"{z['name']} đã hết ô trống")
            con.execute("INSERT INTO batches (product_id,batch_no,exp,qty,zone,bin) VALUES (?,?,?,?,?,?)",
                        (po["product_id"], no, exp, ok, z["code"], b))
            con.execute("UPDATE pos SET status='received', recv=?, dmg=? WHERE id=?", (ok, dmg, po_id))
            log(con, "IN", po["product_id"], no, ok, f"Nhận {po['po_no']} vào {z['code']}-{b:02d}")
    except ValueError as e:
        return bad(str(e))
    finally:
        con.close()
    return jsonify(ok=True)
