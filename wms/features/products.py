"""Feature: SKU Master - danh mục sản phẩm."""
import sqlite3

from flask import Blueprint, jsonify, request

from ..db import bad, db, rows

bp = Blueprint("products", __name__)


@bp.get("/api/products")
def api_products():
    """Danh sách sản phẩm kèm tổng tồn thực có, sắp theo mã SKU."""
    con = db()
    out = rows(con, """SELECT p.*, COALESCE(SUM(b.qty),0) AS stock FROM products p
                       LEFT JOIN batches b ON b.product_id=p.id GROUP BY p.id ORDER BY p.sku""")
    con.close()
    return jsonify(out)


@bp.post("/api/products")
def api_product_add():
    """Thêm sản phẩm mới; kiểm tra mã SKU, tên, loại kho và chặn trùng SKU."""
    d = request.get_json()
    if not d.get("sku") or not d.get("name"):
        return bad("Cần nhập mã SKU và tên sản phẩm")
    if d.get("storage") not in ("dry", "chilled", "frozen", "cosmetics"):
        return bad("Loại kho không hợp lệ")
    con = db()
    try:
        with con:
            con.execute("INSERT INTO products (sku,name,cat,unit,storage,price,safety,supplier) VALUES (?,?,?,?,?,?,?,?)",
                        (d["sku"].strip(), d["name"].strip(), d.get("cat", ""), "thùng", d["storage"],
                         int(d.get("price") or 0), int(d.get("safety") or 0), d.get("supplier", "")))
    except sqlite3.IntegrityError:
        return bad("Mã SKU đã tồn tại")
    finally:
        con.close()
    return jsonify(ok=True)


@bp.delete("/api/products/<int:pid>")
def api_product_del(pid):
    """Xóa sản phẩm; từ chối nếu sản phẩm còn lô hàng, PO hoặc đơn bán."""
    con = db()
    used = sum(con.execute(f"SELECT COUNT(*) FROM {t} WHERE product_id=?", (pid,)).fetchone()[0]
               for t in ("batches", "pos", "sos"))
    if used:
        con.close()
        return bad("Không xóa được: sản phẩm đang có tồn kho hoặc đơn hàng")
    with con:
        con.execute("DELETE FROM products WHERE id=?", (pid,))
    con.close()
    return jsonify(ok=True)
