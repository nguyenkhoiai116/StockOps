"""Đọc / ghi database bằng file CSV (mở, sửa được bằng Excel), cho người chưa quen SQL.

Mỗi file CSV = 1 bảng, dòng đầu là tên cột (giữ nguyên tên cột trong database), mỗi dòng sau = 1 bản ghi.
  load(con, thư mục)   nạp các file vào những bảng đang trống (dùng khi reset database)
  dump(con, thư mục)   xuất mọi bảng ra file CSV

Ba chỗ khác bảng thật, để sửa tay cho dễ:
- Bảng có product_id thì CSV dùng cột sku (gõ SKU-001 thay vì nhớ số id của sản phẩm).
- Chỉ batches và sos giữ cột id (vì picks, txs trỏ vào); bảng khác tự đánh số theo thứ tự dòng.
- Ngày được dời theo file ngay_goc.txt: khi nạp, ngày gốc thành hôm nay và mọi ngày trong CSV dời theo
  cùng số ngày. Nhờ vậy nạp lại tuần sau thì lô "còn 5 ngày hết hạn" vẫn còn 5 ngày, demo luôn mới.
"""
import csv
import io
import re
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

from .core import ledger_gaps
from .db import ROOT, day, log, rows, today

DATA = ROOT / "data"        # bộ dữ liệu mẫu, nạp khi reset
BASE = "ngay_goc.txt"       # file ghi ngày gốc của bộ CSV
# Thứ tự nạp: bảng được trỏ tới nạp trước (khu, sản phẩm trước lô; lô, đơn trước picks, txs)
TABLES = ["zones", "products", "vehicles", "users", "batches", "pos", "sos", "picks", "txs"]
HIDE = {"products": {"id"}, "users": {"id", "pw_hash"}, "pos": {"id"}, "picks": {"id"}, "txs": {"id"}}   # không có trong CSV
DATES = {"batches": {"exp"}, "pos": {"eta"}, "sos": {"due"}, "txs": {"ts"}, "users": {"created_at"}}   # cột ngày, được dời
STORAGE = ("dry", "chilled", "frozen", "cosmetics")
# Các kiểu ngày nhận được. Excel tiếng Việt hay tự đổi 2026-11-27 thành 27/11/2026 khi lưu, nên nhận cả 2 kiểu.
FMTS = ("%Y-%m-%d", "%d/%m/%Y", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M",
        "%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M")


# ---------- Nạp CSV vào database ----------
def load(con, folder=None):
    """Nạp folder/<bảng>.csv (mặc định data/) vào các bảng đang trống; bảng đã có dữ liệu hoặc không có file thì bỏ qua.
    Không tự gọi lock(): nơi gọi mở transaction có khóa (seed.init_db). Lỗi trong file -> ValueError
    ghi rõ file, dòng, cột; nơi gọi hoàn tác cả lần nạp nên không bao giờ nạp dở dang."""
    folder = Path(folder or DATA)
    n = (today() - base(folder)).days   # số ngày phải dời
    for t in TABLES:
        f = folder / f"{t}.csv"
        if f.exists() and not con.execute(f"SELECT 1 FROM {t} LIMIT 1").fetchone():
            put(con, t, f, n)
    check(con)


def base(folder):
    """Ngày gốc trong ngay_goc.txt; không có file thì coi như hôm nay (không dời ngày)."""
    f = folder / BASE
    if not f.exists():
        return today()
    s = next((x.strip() for x in f.read_text(encoding="utf-8-sig").splitlines() if x.strip()), "")
    for fm in FMTS[:2]:
        try:
            return datetime.strptime(s, fm).date()
        except ValueError:
            pass
    raise ValueError(f"{BASE}: '{s}' không phải ngày (cần dạng YYYY-MM-DD)")


def read(f):
    """Đọc file CSV thành danh sách dòng. Nhận cả file Excel lưu bằng dấu ; (máy cài tiếng Việt) và có/không BOM."""
    try:
        s = f.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError:
        raise ValueError(f"{f.name}: không đọc được tiếng Việt. Trong Excel chọn Save As > "
                         "'CSV UTF-8 (Comma delimited)' rồi lưu lại") from None
    head = s.split("\n", 1)[0]
    sep = ";" if head.count(";") > head.count(",") else ","
    return list(csv.reader(io.StringIO(s, newline=""), delimiter=sep))


def put(con, t, f, n):
    """Nạp 1 file vào bảng t; n = số ngày dời các cột ngày."""
    kind = {r["name"]: (r["type"] or "TEXT").upper() for r in con.execute(f"PRAGMA table_info({t})")}
    ok = set(kind) - HIDE.get(t, set())
    by_sku = "product_id" in kind   # bảng trỏ tới sản phẩm: CSV dùng cột sku
    if by_sku:
        ok = ok - {"product_id"} | {"sku"}
    rs = read(f)
    head = [h.strip() for h in rs[0]] if rs else []
    wrong = [h for h in head if h not in ok]
    if wrong or not head or len(set(head)) != len(head):
        raise ValueError(f"{f.name}: dòng tiêu đề có cột lạ hoặc trùng ({', '.join(wrong) or 'trùng tên'}). "
                         f"Các cột dùng được: {', '.join(sorted(ok))}")
    skus = dict(con.execute("SELECT sku, id FROM products").fetchall()) if by_sku else {}
    for i, r in enumerate(rs[1:], start=2):   # i = số dòng như Excel hiện (dòng 1 là tiêu đề)
        r = [c.strip() for c in r]
        if not any(r):
            continue   # dòng trống (Excel hay để lại ở cuối)
        where = f"{f.name} dòng {i}"
        if len(r) > len(head) and any(r[len(head):]):
            raise ValueError(f"{where}: nhiều ô hơn số cột tiêu đề")
        got = {}   # cột -> giá trị; ô trống không đưa vào câu INSERT nên database tự điền giá trị mặc định
        for h, v in zip(head, r):
            if by_sku and h == "sku":
                if not v or v not in skus:
                    raise ValueError(f"{where}: " + (f"SKU '{v}' chưa có trong products.csv" if v else "thiếu SKU"))
                got["product_id"] = skus[v]
            elif v:
                if h == "barcode" and not v.isdigit():
                    raise ValueError(f"{where}: mã vạch '{v}' phải toàn chữ số. Nếu thấy dạng 8.93E+12 là Excel đã đổi số; "
                                     "định dạng cột thành Text, gõ lại mã rồi lưu")
                if h in DATES.get(t, ()):
                    v = shift(v, n, f"{where}, cột {h}")
                got[h] = cast(v, kind[h], f"{where}, cột {h}")
        # tên cột lấy từ PRAGMA table_info (đã lọc ở trên) nên ghép vào SQL được, không sợ chữ lạ trong file
        sql = f"INSERT INTO {t} ({', '.join(got)}) VALUES ({', '.join('?' * len(got))})"
        try:
            con.execute(sql, list(got.values()))
        except sqlite3.IntegrityError as e:
            raise ValueError(f"{where}: {why(e)}") from None


def cast(v, kind, where):
    """Đổi chữ trong ô (không trống) sang đúng kiểu của cột."""
    if kind == "INTEGER":
        if re.fullmatch(r"-?\d+", v):
            return int(v)
        raise ValueError(f"{where}: phải là số nguyên, đang là '{v}'")
    if kind == "REAL":
        try:
            return float(v.replace(",", "."))   # Excel tiếng Việt ghi số thập phân bằng dấu phẩy: 27,5
        except ValueError:
            raise ValueError(f"{where}: phải là số, đang là '{v}'") from None
    return v


def shift(v, n, where):
    """Dời ngày v đi n ngày, trả về dạng chuẩn YYYY-MM-DD (kèm giờ THH:MM:SS nếu ô có giờ)."""
    for fm in FMTS:
        try:
            t = datetime.strptime(v, fm) + timedelta(days=n)
        except ValueError:
            continue
        return t.isoformat(timespec="seconds") if "%H" in fm else t.date().isoformat()
    raise ValueError(f"{where}: '{v}' không phải ngày (cần dạng YYYY-MM-DD hoặc DD/MM/YYYY)")


def why(e):
    """Dịch lỗi ràng buộc của SQLite sang câu dễ hiểu."""
    m = str(e)
    if "batches.zone, batches.bin" in m:
        return "ô kệ (zone, bin) này đã có lô khác còn hàng"
    if "UNIQUE" in m:
        return f"trùng với một dòng phía trên ở cột {m.split('.')[-1]}"
    if "FOREIGN KEY" in m:
        return "trỏ tới mã không có (khu, lô hoặc đơn chưa khai trong file tương ứng)"
    if "NOT NULL" in m:
        return f"thiếu ô bắt buộc ở cột {m.split('.')[-1]}"
    if "CHECK" in m:
        return "có giá trị không hợp lệ (vd số âm, giữ hàng nhiều hơn tồn, role hoặc trạng thái lạ)"
    return m


def check(con):
    """Kiểm tra sau khi nạp những gì database không tự chặn, và cân sổ giao dịch với tồn từng lô."""
    for t, key in (("products", "sku"), ("zones", "code")):
        for r in con.execute(f"SELECT {key}, storage FROM {t} WHERE storage NOT IN ({','.join('?' * len(STORAGE))})", STORAGE):
            raise ValueError(f"{t}.csv: {r[0]} có storage '{r[1]}', chỉ dùng {', '.join(STORAGE)}")
    for b in rows(con, """SELECT b.batch_no, b.zone, b.bin, z.racks*z.bays*z.levels AS n FROM batches b
                          JOIN zones z ON z.code=b.zone WHERE b.qty>0 AND (b.bin IS NULL OR b.bin<1 OR b.bin>z.racks*z.bays*z.levels)"""):
        raise ValueError(f"batches.csv: lô {b['batch_no']} nằm ở ô {b['bin']} nhưng khu {b['zone']} chỉ có ô 1..{b['n']}")
    # reserved của lô = tổng hàng đang giữ cho các đơn đã soạn chưa xuất (xem core.release)
    for b in rows(con, """SELECT b.id, b.batch_no, b.reserved, COALESCE((SELECT SUM(k.qty) FROM picks k JOIN sos s ON s.id=k.so_id
                          WHERE k.batch_id=b.id AND k.released=0 AND s.status='picked'), 0) AS held
                          FROM batches b"""):
        if b["reserved"] != b["held"]:
            raise ValueError(f"batches.csv: lô {b['batch_no']} (id {b['id']}) có reserved = {b['reserved']} "
                             f"nhưng picks.csv giữ {b['held']} thùng cho các đơn đã soạn")
    # Sổ txs phải cộng ra đúng tồn từng lô. Sửa qty trong batches.csv mà không sửa txs.csv
    # thì ghi thêm 1 dòng cho khớp (lô mới chưa có dòng nào = IN, lô đã có sổ = ADJ), để lịch sử vẫn thấy.
    for g in ledger_gaps(con):
        b = con.execute("SELECT product_id FROM batches WHERE id=?", (g["id"],)).fetchone()
        kind = "ADJ" if con.execute("SELECT 1 FROM txs WHERE batch_id=?", (g["id"],)).fetchone() else "IN"
        log(con, kind, b["product_id"], g["batch_no"], g["qty"] - g["ledger"], "Cân sổ khi nạp từ file CSV", bid=g["id"])


# ---------- Xuất database ra CSV ----------
def dump(con, folder):
    """Xuất mọi bảng ra folder/<bảng>.csv và ghi ngày gốc = hôm nay. Không bao giờ xuất mật khẩu (pw_hash).
    File có BOM (utf-8-sig) để Excel mở thấy đúng tiếng Việt."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    for t in TABLES:
        cols = [r["name"] for r in con.execute(f"PRAGMA table_info({t})") if r["name"] not in HIDE.get(t, ())]
        sel = ", ".join("(SELECT sku FROM products WHERE id=t.product_id) AS sku" if c == "product_id" else f"t.{c}"
                        for c in cols)
        cur = con.execute(f"SELECT {sel} FROM {t} t ORDER BY t.rowid")
        with (folder / f"{t}.csv").open("w", encoding="utf-8-sig", newline="") as f:
            w = csv.writer(f)
            w.writerow([d[0] for d in cur.description])
            w.writerows([cell(v) for v in r] for r in cur)
    (folder / BASE).write_text(day() + "\n", encoding="utf-8")


def cell(v):
    """Giá trị 1 ô khi xuất: NULL thành ô trống, -18.0 thành -18 cho gọn."""
    if v is None:
        return ""
    return int(v) if isinstance(v, float) and v.is_integer() else v
