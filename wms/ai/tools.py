"""Tool CHỈ ĐỌC cho Kvis: LLM chọn tool + tham số, backend tự chạy truy vấn có sẵn (LLM không viết SQL).

Mỗi tool gồm: quyền cần có (trong wms/roles.py), nhãn tiếng Việt (hiện ở dòng "Đã tra"), mô tả cho LLM,
schema tham số (kiểu JSON Schema, dùng luôn để kiểm tham số) và hàm chạy.
- specs(role): chỉ đưa cho LLM các tool role đó được dùng -> LLM không biết tới tool bị cấm.
- call(...): kiểm lại quyền lần nữa (LLM có thể bịa tên tool), kiểm tham số, chạy, cắt kết quả cho gọn.
  Lỗi trả về {"error": "..."} để LLM đọc rồi tự sửa, không bao giờ làm sập vòng lặp agent.
"""
import json
import sqlite3
import unicodedata
from datetime import date

from ..core import get_alerts, get_kpis, reorder, stock_by_sku, stock_status, zone_status
from ..db import day, rows, today
from ..roles import PERMS, can

MAX_ROWS = 50      # mỗi kết quả tối đa 50 dòng
MAX_CHARS = 4000   # và tối đa khoảng 4.000 ký tự JSON -> đỡ tốn token, mỗi bước agent gửi lại toàn bộ


def plain(s):
    """Chữ không dấu, chữ thường: "Sữa chua Đà Lạt" -> "sua chua da lat" (để tìm kiểu gõ không dấu)."""
    s = unicodedata.normalize("NFD", str(s or "").replace("đ", "d").replace("Đ", "D"))
    return "".join(ch for ch in s if unicodedata.category(ch) != "Mn").lower()


# ---------- Kiểu tham số (JSON Schema rút gọn) ----------
def S(desc):
    return {"type": "string", "description": desc, "maxLength": 64}


def E(desc, *vals):
    return {"type": "string", "description": desc, "enum": list(vals)}


def I(desc, lo, hi):
    return {"type": "integer", "description": desc, "minimum": lo, "maximum": hi}


def clean(params, a):
    """Kiểm tham số LLM gửi theo schema; trả dict đã chuẩn hóa. Khóa lạ bỏ qua, None/"" coi như không có."""
    out = {}
    for k, p in params.items():
        v = a.get(k)
        if v is None or v == "":
            continue
        if p["type"] == "integer":
            ok = isinstance(v, int) and not isinstance(v, bool)
            if isinstance(v, float) and v.is_integer():
                v, ok = int(v), True
            if isinstance(v, str) and v.strip().lstrip("-").isdigit():
                v, ok = int(v.strip()), True
            if not ok or not p["minimum"] <= v <= p["maximum"]:
                raise ValueError(f"Tham số {k} phải là số nguyên từ {p['minimum']} đến {p['maximum']}")
        else:
            if not isinstance(v, str):
                raise ValueError(f"Tham số {k} phải là chữ")
            v = v.strip()
            if "enum" in p:
                v = v.lower()
                if v not in p["enum"]:
                    raise ValueError(f"Tham số {k} chỉ nhận: {', '.join(p['enum'])}")
            elif len(v) > p["maxLength"]:
                raise ValueError(f"Tham số {k} dài quá {p['maxLength']} ký tự")
        out[k] = v
    return out


def listing(rs):
    """Kết quả dạng danh sách; count = tổng số dòng tìm thấy (trước khi cắt)."""
    return {"rows": rs, "count": len(rs)}


def fit(r):
    """Cắt danh sách còn MAX_ROWS dòng và JSON còn khoảng MAX_CHARS ký tự, đánh dấu truncated."""
    if "rows" not in r:
        return r
    if len(r["rows"]) > MAX_ROWS:
        r["rows"], r["truncated"] = r["rows"][:MAX_ROWS], True
    while r["rows"] and len(json.dumps(r, ensure_ascii=False)) > MAX_CHARS:
        r["truncated"] = True
        r["rows"].pop()
    return r


# ---------- Các tool ----------
def t_kpis(con):
    return get_kpis(con)


def t_alerts(con, kind=None):
    return listing([{k: a[k] for k in ("kind", "level", "msg")} for a in get_alerts(con) if not kind or a["kind"] == kind])


def t_stock(con, sku=None, q=None):
    out = []
    for p in stock_by_sku(con):
        if sku and p["sku"].upper() != sku.upper():
            continue
        if q and plain(q) not in plain(p["name"]) and plain(q) not in plain(p["sku"]):
            continue
        out.append({"sku": p["sku"], "name": p["name"], "av": p["av"], "safety": p["safety"],
                    "status": stock_status(p["av"], p["safety"])})
    return listing(out)


def t_lots(con, sku=None, zone=None, near_days=None):
    sql, args = """SELECT b.batch_no, p.sku, p.name, b.exp, b.qty, b.reserved, b.zone, b.bin
                   FROM batches b JOIN products p ON p.id=b.product_id WHERE b.qty>0""", []
    if sku:
        sql, args = sql + " AND UPPER(p.sku)=?", [*args, sku.upper()]
    if zone:
        sql, args = sql + " AND UPPER(b.zone)=?", [*args, zone.upper()]
    if near_days is not None:
        sql, args = sql + " AND b.exp<=?", [*args, day(near_days)]   # gồm cả lô đã hết hạn
    out = []
    for b in rows(con, sql + " ORDER BY b.exp, b.id", args):
        left = (date.fromisoformat(b["exp"]) - today()).days
        out.append({"batch_no": b["batch_no"], "sku": b["sku"], "name": b["name"], "exp": b["exp"],
                    "days_left": left, "expired": left < 0, "qty": b["qty"], "reserved": b["reserved"],
                    "av": b["qty"] - b["reserved"], "zone": b["zone"], "bin": f"{b['zone']}-{b['bin']:02d}"})
    return listing(out)


def t_zones(con, zone=None):
    keep = ("code", "name", "storage", "cap", "used", "pct", "bins", "temp", "tmin", "tmax")
    return listing([{k: z[k] for k in keep} for z in zone_status(con) if not zone or z["code"].upper() == zone.upper()])


def t_orders(con, status=None, sku=None, customer=None):
    sql, args = """SELECT s.so_no, s.customer, p.sku, p.name, s.qty, s.due, s.status, s.plate, s.on_time
                   FROM sos s JOIN products p ON p.id=s.product_id WHERE 1=1""", []
    if status:
        sql, args = sql + " AND s.status=?", [*args, status]
    if sku:
        sql, args = sql + " AND UPPER(p.sku)=?", [*args, sku.upper()]
    rs = rows(con, sql + " ORDER BY s.due, s.id", args)   # sắp tới hạn giao nằm đầu: danh sách dài bị cắt vẫn giữ đơn gấp
    return listing([r for r in rs if not customer or plain(customer) in plain(r["customer"])])


def t_pos(con, status=None, sku=None):
    sql, args = """SELECT o.po_no, p.sku, p.name, o.qty, o.eta, o.status, o.recv, o.dmg
                   FROM pos o JOIN products p ON p.id=o.product_id WHERE 1=1""", []
    if status:
        sql, args = sql + " AND o.status=?", [*args, status]
    if sku:
        sql, args = sql + " AND UPPER(p.sku)=?", [*args, sku.upper()]
    return listing(rows(con, sql + " ORDER BY o.eta, o.id", args))   # sắp về nằm đầu


def t_reorder(con):
    return listing(reorder(con))


SKU = S("Mã SKU, vd SKU-001")
TOOLS = {
    "get_kpis": dict(perm="dash.view", label="Chỉ số KPI", fn=t_kpis, params={},
                     desc="Chỉ số chung của kho: giá trị tồn (VND), tổng thùng, sức chứa, % lấp đầy, % cận date, "
                          "giá trị hàng hết hạn, OTIF %, tỉ lệ đáp ứng đơn %, số PO chờ nhận, số đơn bán chưa giao xong."),
    "get_alerts": dict(perm="dash.view", label="Cảnh báo", fn=t_alerts,
                       params={"kind": E("Lọc loại cảnh báo: temp (nhiệt độ), cap (sức chứa), expiry (hạn dùng), stock (tồn thấp)",
                                         "temp", "cap", "expiry", "stock")},
                       desc="Danh sách cảnh báo hiện tại, mức high/med, xếp mức nặng trước."),
    "get_stock": dict(perm="sku.view", label="Tồn theo SKU", fn=t_stock,
                      params={"sku": SKU, "q": S("Tìm theo tên sản phẩm, gõ có dấu hay không dấu đều được")},
                      desc="Tồn khả dụng theo sản phẩm (chỉ tính lô còn hạn, đã trừ phần giữ cho đơn), tồn an toàn và "
                           "trạng thái ok / low (dưới tồn an toàn) / crit (hết hoặc dưới nửa tồn an toàn)."),
    "get_lots": dict(perm="inv.view", label="Tồn theo lô", fn=t_lots,
                     params={"sku": SKU, "zone": S("Mã khu: DRY, CHL, FRZ, COS..."),
                             "near_days": I("Chỉ lấy lô hết hạn trong vòng n ngày tới (gồm cả lô đã hết hạn)", 0, 365)},
                     desc="Các lô đang còn hàng: số lô, hạn dùng, số ngày còn lại, đã hết hạn chưa, số lượng, phần đã giữ, "
                          "phần khả dụng, khu và ô kệ. Xếp theo hạn dùng sớm nhất trước (FEFO)."),
    "get_zone_status": dict(perm="map.view", label="Khu kho", fn=t_zones, params={"zone": S("Mã khu, vd CHL")},
                            desc="Từng khu kho: loại hàng chứa, sức chứa, số thùng đang chứa, % lấp đầy, số ô kệ, "
                                 "nhiệt độ hiện tại và ngưỡng nhiệt độ cho phép."),
    "get_orders": dict(perm="so.view", label="Đơn bán", fn=t_orders,
                       params={"status": E("Lọc trạng thái: new (mới), picked (đã soạn), shipping (đang giao), "
                                           "delivered (đã giao), cancelled (đã hủy)",
                                           "new", "picked", "shipping", "delivered", "cancelled"),
                               "sku": SKU, "customer": S("Tìm theo tên khách hàng, không dấu cũng được")},
                       desc="Đơn bán, xếp theo hạn giao sớm nhất trước: số đơn, khách, SKU, số thùng, hạn giao, trạng thái, "
                            "biển số xe, giao đúng hạn (1/0)."),
    "get_pos": dict(perm="po.view", label="Đơn mua (PO)", fn=t_pos,
                    params={"status": E("Lọc trạng thái: pending (chờ nhận), received (đã nhận)", "pending", "received"),
                            "sku": SKU},
                    desc="Đơn mua hàng (PO), xếp theo ngày dự kiến đến sớm nhất trước: số PO, SKU, số thùng đặt, "
                         "ngày dự kiến đến, trạng thái, số đạt, số hỏng khi nhận."),
    "get_reorder": dict(perm="dash.view", label="Gợi ý đặt hàng", fn=t_reorder, params={},
                        desc="SKU dưới tồn an toàn kèm số thùng đang chờ trong PO và số thùng nên đặt thêm "
                             "(qty = 0 nghĩa là PO đang chờ đã đủ bù). Dùng khi được hỏi nên nhập gì."),
}


def specs(role):
    """Schema các tool role này được dùng, đúng định dạng "tools" của API chuẩn OpenAI."""
    return [{"type": "function", "function": {"name": n, "description": t["desc"],
                                              "parameters": {"type": "object", "properties": t["params"]}}}
            for n, t in TOOLS.items() if can(role, t["perm"])]


def call(con, user, name, args):
    """Chạy 1 tool cho người hỏi `user` (cần user["role"]). args: chuỗi JSON từ LLM ("" / None = không tham số)."""
    t = TOOLS.get(name)
    if not t:
        return {"error": f"Không có tool {name}"}
    if not can(user["role"], t["perm"]):
        return {"error": f"Không có quyền: {PERMS[t['perm']][0]}"}
    try:
        a = json.loads(args) if isinstance(args, str) and args.strip() else args
    except ValueError:
        return {"error": "Tham số không phải JSON hợp lệ"}
    if a is None or a == "":
        a = {}
    if not isinstance(a, dict):
        return {"error": 'Tham số phải là 1 object JSON, vd {"sku": "SKU-001"}'}
    try:
        return fit(t["fn"](con, **clean(t["params"], a)))
    except (ValueError, TypeError, sqlite3.Error) as e:
        return {"error": str(e)}
