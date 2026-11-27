"""Engine nghiệp vụ & thuật toán cho Nhóm 4 (Shipping – Outbound: CV1–CV5).

Gồm:
- CV1: Bóc tách đơn hàng (CSV/Text), đối chiếu 3 chiều (SO ↔ Thực đóng ↔ Chứng từ + % HSD kênh), gợi ý hoán đổi lô.
- CV2 & CV3: Ghép đơn tối ưu (CVRP heuristic), sơ đồ xếp tải 2D LIFO (Khoang × 2 Tầng) + Safety Guard, xếp lịch cửa xuất (Dock X1–X4).
- CV5 & CV4: Giám sát Staging chống sốc nhiệt, đối chiếu quét mã QR, dự báo ETA động và phát hiện bất thường nhiệt độ thùng xe.
"""
import json
import math
import re
import unicodedata
from collections import defaultdict
from datetime import date, datetime, timedelta

from .core import shelf_pct, stock_by_sku
from .db import day, rows
from .xlsx import excel_date_to_iso

CHANNEL_INFO = {
    "sieuthi": {"name": "Siêu thị lớn", "min_shelf_pct": 65, "unload_min": 38},
    "daily":   {"name": "Đại lý / Nhà hàng", "min_shelf_pct": 50, "unload_min": 22},
    "taphoa":  {"name": "Tạp hóa nhỏ", "min_shelf_pct": 40, "unload_min": 10},
}

ROUTE_TRAFFIC_MIN = {"Q1": 35, "Q3": 30, "Q7": 45, "BinhThanh": 28, "ThuDuc": 50}


def _plain(s):
    s = unicodedata.normalize("NFD", str(s or ""))
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return s.replace("đ", "d").replace("Đ", "d").lower().strip()


# ---------- CV1A: Bóc tách & chuẩn hóa file/văn bản đơn đặt hàng ----------
def parse_order_text(con, raw_text):
    """Bóc tách nội dung CSV/text khách gửi thành danh sách dòng SO chuẩn hóa SKU + kiểm tra tồn 100%."""
    prods = stock_by_sku(con)
    custs = rows(con, "SELECT * FROM customers")
    lines = [ln.strip() for ln in str(raw_text or "").splitlines() if ln.strip()]
    parsed = []

    for idx, ln in enumerate(lines, 1):
        # Bỏ dòng tiêu đề nếu có
        low = _plain(ln)
        if idx == 1 and ("khach" in low or "sku" in low or "san pham" in low) and not re.search(r"\d+", ln):
            continue
        parts = [p.strip() for p in re.split(r"[,;\t|]+", ln) if p.strip()]
        if len(parts) < 3:
            parsed.append({
                "line": idx, "raw": ln, "ok": False, "confidence": "low",
                "warn": "Thiếu cột (cần: Khách hàng, Tên/Mã hàng, Số lượng[, Hạn giao])",
            })
            continue
        c_raw, p_raw, q_raw = parts[0], parts[1], parts[2]
        due_raw = excel_date_to_iso(parts[3] if len(parts) >= 4 else "", day(1))

        m_q = re.search(r"\d+", q_raw)
        qty = int(m_q.group()) if m_q else 0

        # Khớp khách hàng & tự nạp chuẩn % HSD kênh
        cp = _plain(c_raw)
        cust = next((c for c in custs if _plain(c["name"]) == cp or cp in _plain(c["name"]) or _plain(c["name"]) in cp), None)
        if cust:
            cust_name, ch, min_pct, r_zone = cust["name"], cust["channel"], cust["min_shelf_pct"], cust["route_zone"]
            c_conf = 1.0
        else:
            cust_name = c_raw
            ch = "sieuthi" if "sieu thi" in cp else ("daily" if "dai ly" in cp or "nha hang" in cp else "taphoa")
            min_pct = CHANNEL_INFO[ch]["min_shelf_pct"]
            r_zone = "Q1"
            c_conf = 0.6

        # Khớp SKU bằng mã chính xác hoặc chấm điểm trùng từ khóa
        pp = _plain(p_raw)
        best_p, best_sc = None, 0.0
        for p in prods:
            if _plain(p["sku"]) == pp or _plain(p["sku"]) in pp:
                best_p, best_sc = p, 1.0
                break
            toks = [t for t in re.split(r"\W+", pp) if len(t) >= 2]
            name_p = _plain(p["name"])
            if toks:
                hit = sum(1 for t in toks if t in name_p) / len(toks)
                if hit > best_sc:
                    best_p, best_sc = p, hit

        warns = []
        if not best_p or best_sc < 0.4:
            warns.append("Không khớp chính xác mã SKU trong danh mục")
        elif best_sc < 0.85:
            warns.append(f"Khớp gần đúng ({int(best_sc * 100)}%) — cần xác nhận lại SKU")
        if c_conf < 1.0:
            warns.append("Khách mới ngoài danh mục — tạm gán chuẩn kênh tự suy luận")
        if qty <= 0:
            warns.append("Số lượng không hợp lệ")

        stock_ok = False
        av = best_p["av"] if best_p else 0
        if best_p and qty > 0:
            stock_ok = av >= qty
            if not stock_ok:
                warns.append(f"Chặn từ cổng: thiếu hàng (cần {qty}, khả dụng {av})")

        conf = "high" if (best_p and best_sc >= 0.85 and c_conf >= 0.9 and qty > 0) else "low"
        parsed.append({
            "line": idx, "raw": ln,
            "customer": cust_name, "channel": ch, "min_shelf_pct": min_pct, "route_zone": r_zone,
            "product_id": best_p["id"] if best_p else None,
            "sku": best_p["sku"] if best_p else "?",
            "product_name": best_p["name"] if best_p else p_raw,
            "qty": qty, "due": due_raw, "av": av, "stock_ok": stock_ok,
            "confidence": conf, "ok": bool(best_p and qty > 0 and stock_ok),
            "warn": "; ".join(warns),
        })
    return parsed


# ---------- CV1B: Đối chiếu 3 chiều & Gợi ý Hoán đổi lô (Batch Swap) ----------
def audit_so_3way(con, so_id):
    """Kiểm tra 3 điều kiện cứng trước khi phát hành bộ chứng từ: Đủ 100% SL, Đạt % HSD kênh, Đủ chứng từ."""
    so = con.execute(
        """SELECT s.*, p.sku, p.name AS pname, p.storage, p.shelf_days, p.price, p.weight_kg, p.vol_m3, p.fragile
           FROM sos s JOIN products p ON p.id=s.product_id WHERE s.id=?""",
        (so_id,),
    ).fetchone()
    if not so:
        raise ValueError("Không tìm thấy đơn bán")
    pks = rows(
        con,
        """SELECT k.qty, b.id AS batch_id, b.batch_no, b.exp, b.zone, b.bin, b.q_status
           FROM picks k JOIN batches b ON b.id=k.batch_id WHERE k.so_id=?""",
        (so_id,),
    )
    packed_qty = sum(k["qty"] for k in pks)
    qty_ok = packed_qty == so["qty"] and packed_qty > 0

    lots = []
    hsd_ok = bool(pks)
    min_pct = so["min_shelf_pct"] or CHANNEL_INFO.get(so["channel"], CHANNEL_INFO["taphoa"])["min_shelf_pct"]
    for k in pks:
        pct = shelf_pct(k["exp"], so["shelf_days"])
        left = (date.fromisoformat(k["exp"]) - date.today()).days
        ok_lot = pct >= min_pct and left >= 0 and k["q_status"] == "ok"
        if not ok_lot:
            hsd_ok = False
        lots.append({**k, "shelf_pct": pct, "left_days": left, "ok_channel": ok_lot})

    # Kiểm tra bộ chứng từ bắt buộc (hàng lạnh cần thêm biên bản nhiệt độ kho đạt chuẩn)
    need_temp_cert = so["storage"] in ("chilled", "frozen")
    z = con.execute("SELECT * FROM zones WHERE storage=?", (so["storage"],)).fetchone()
    zone_temp_ok = (z["tmin"] <= z["temp"] <= z["tmax"]) if z else True
    docs = [
        {"name": "Phiếu xuất kho (Delivery Note)", "ready": qty_ok},
        {"name": "Phiếu đóng gói + Mã QR (Packing List)", "ready": qty_ok},
    ]
    if need_temp_cert:
        docs.append({
            "name": f"Biên bản nhiệt độ xuất kho ({z['name']}: {z['temp']}°C)",
            "ready": True, "warn": "" if zone_temp_ok else f"Cảnh báo: nhiệt độ kho đang {z['temp']}°C ngoài ngưỡng!",
        })
    docs_ok = all(d["ready"] for d in docs)

    # Nếu vi phạm % HSD kênh -> tìm đơn kênh thấp hơn hoặc lô khác còn hạn dài hơn để gợi ý Hoán đổi lô
    swap_hint = None
    if not hsd_ok:
        alt_lot = con.execute(
            """SELECT batch_no, exp, qty - reserved AS av FROM batches
               WHERE product_id=? AND qty-reserved>=? AND q_status='ok' ORDER BY exp DESC LIMIT 1""",
            (so["product_id"], so["qty"]),
        ).fetchone()
        lower_so = con.execute(
            """SELECT so_no, customer, channel, min_shelf_pct FROM sos
               WHERE status IN ('new','picked') AND id!=? AND min_shelf_pct < ? ORDER BY min_shelf_pct LIMIT 1""",
            (so_id, min_pct),
        ).fetchone()
        parts = []
        if alt_lot and shelf_pct(alt_lot["exp"], so["shelf_days"]) >= min_pct:
            parts.append(f"Có lô {alt_lot['batch_no']} (HSD {alt_lot['exp']}, còn {shelf_pct(alt_lot['exp'], so['shelf_days'])}%) đủ chuẩn kênh {CHANNEL_INFO.get(so['channel'], {}).get('name', so['channel'])}.")
        if lower_so:
            parts.append(f"Gợi ý hoán đổi lô cận date sang đơn {lower_so['so_no']} ({lower_so['customer']} — chuẩn {lower_so['min_shelf_pct']}% HSD) để tránh phí phạt hoàn đơn siêu thị.")
        if not parts:
            parts.append("Không có lô đạt chuẩn % HSD kênh trong kho — đề xuất trả về Nhóm 3 và liên hệ khách hàng/chuyển kênh tạp hóa.")
        swap_hint = " ".join(parts)

    risk_vnd = int(so["qty"] * so["price"] * 0.15 + 1500000) if not (qty_ok and hsd_ok) else 0
    return {
        "so": dict(so),
        "channel_name": CHANNEL_INFO.get(so["channel"], CHANNEL_INFO["taphoa"])["name"],
        "min_shelf_pct": min_pct,
        "packed_qty": packed_qty,
        "lots": lots,
        "checks": {"qty_ok": qty_ok, "hsd_ok": hsd_ok, "docs_ok": docs_ok},
        "can_approve": qty_ok and hsd_ok and docs_ok,
        "docs": docs,
        "swap_hint": swap_hint,
        "avoided_penalty_vnd": risk_vnd,
    }


# ---------- CV2 & CV3: Ghép đơn (CVRP Heuristic), Xếp tải 2D LIFO & An toàn, Lịch Dock ----------
def build_lifo_plan(order_rows, vehicle):
    """Tạo sơ đồ xếp tải 2D (Khoang dọc LIFO × 2 Tầng chịu lực) và chạy Safety Guard."""
    # Thứ tự giao ưu tiên hạn SLA sớm trước -> xếp ngược LIFO: giao sau nằm Khoang 1 (sát đầu xe), giao trước sát cửa sau
    deliver_order = sorted(order_rows, key=lambda o: (o["due"], o["so_no"]))
    load_order = list(reversed(deliver_order))   # Khoang 1..N từ trong ra ngoài

    bays = []
    warnings = []
    blocked = False
    protected_vnd = 0
    has_cos = any(o["storage"] == "cosmetics" for o in order_rows)
    has_food = any(o["storage"] in ("dry", "chilled", "frozen") for o in order_rows)
    has_cold = any(o["storage"] in ("chilled", "frozen") for o in order_rows)

    if has_cold and vehicle["kind"] != "cold":
        blocked = True
        cold_val = sum(o["qty"] * o["price"] for o in order_rows if o["storage"] in ("chilled", "frozen"))
        protected_vnd += cold_val
        warnings.append({
            "level": "bad",
            "msg": f"CHẶN CỨNG: Hàng mát/đông lạnh không được xếp lên xe thường {vehicle['plate']} (nguy cơ hỏng lô {cold_val:,} đ).",
        })
    if has_cos and has_food:
        warnings.append({
            "level": "warn",
            "msg": "CẢNH BÁO NHIỄM CHÉO: Có hóa mỹ phẩm chung chuyến với thực phẩm — bắt buộc đặt vách ngăn khoang hoặc tách chuyến!",
        })

    tot_qty = sum(o["qty"] for o in order_rows)
    tot_kg = round(sum(o["qty"] * o["weight_kg"] for o in order_rows), 1)
    tot_m3 = round(sum(o["qty"] * o["vol_m3"] for o in order_rows), 2)
    if tot_kg > vehicle["cap_kg"] or tot_m3 > vehicle["cap_m3"] or tot_qty > vehicle["cap_qty"]:
        warnings.append({
            "level": "bad",
            "msg": f"Vượt tải trọng/thể tích xe ({tot_kg}/{vehicle['cap_kg']} kg, {tot_m3}/{vehicle['cap_m3']} m³) — cần đổi xe lớn hơn hoặc tách chuyến.",
        })

    n_stops = len(load_order)
    for idx, o in enumerate(load_order, 1):
        stop_num = n_stops - idx + 1   # Điểm giao 1 nằm sát cửa sau (idx == n_stops)
        is_top = bool(o["fragile"] or o["weight_kg"] < 7.0)
        layer = "top" if is_top else "bottom"
        bays.append({
            "bay": idx,
            "stop_no": stop_num,
            "position": "Sát cửa sau (dỡ trước)" if stop_num == 1 else ("Sát đầu xe (dỡ sau)" if idx == 1 else f"Khoang giữa (điểm {stop_num})"),
            "so_id": o["id"], "so_no": o["so_no"], "customer": o["customer"],
            "sku": o["sku"], "name": o["pname"], "qty": o["qty"], "storage": o["storage"],
            "weight_kg": round(o["qty"] * o["weight_kg"], 1),
            "vol_m3": round(o["qty"] * o["vol_m3"], 2),
            "layer": layer,
            "layer_label": "Tầng trên (nhẹ / dễ móp)" if is_top else "Tầng dưới (nặng / chịu lực)",
            "fragile": bool(o["fragile"]),
        })

    fill_pct = round(min(100.0, max(tot_qty / vehicle["cap_qty"], tot_m3 / vehicle["cap_m3"], tot_kg / vehicle["cap_kg"]) * 100), 1)
    return {
        "bays": bays,
        "tot_qty": tot_qty, "tot_kg": tot_kg, "tot_m3": tot_m3,
        "fill_pct": fill_pct, "blocked": blocked, "warnings": warnings,
        "protected_vnd": protected_vnd,
        "vehicle": dict(vehicle),
    }


def consolidate_orders(con):
    """Tự động ghép các đơn đã duyệt (ready_dispatch, chưa có trip) theo cùng tuyến & cùng nhiệt độ."""
    ready = rows(
        con,
        """SELECT s.*, p.sku, p.name AS pname, p.storage, p.price, p.weight_kg, p.vol_m3, p.fragile
           FROM sos s JOIN products p ON p.id=s.product_id
           WHERE s.status='picked' AND s.audit_status='approved' AND s.trip_id IS NULL
           ORDER BY s.due, s.id""",
    )
    if not ready:
        return []
    vehicles = rows(con, "SELECT * FROM vehicles ORDER BY cap_qty DESC")
    busy = {r["plate"] for r in rows(con, "SELECT DISTINCT plate FROM trips WHERE status IN ('scheduled','loading','in_transit') AND plate IS NOT NULL")}

    # Gom theo (tuyến, nhóm nhiệt độ: cold vs dry)
    groups = defaultdict(list)
    for o in ready:
        tgrp = "cold" if o["storage"] in ("chilled", "frozen") else "dry"
        groups[(o["route_zone"], tgrp)].append(o)

    created = []
    seq = con.execute("SELECT COUNT(*) FROM trips").fetchone()[0]
    for (rzone, tgrp), grp_orders in groups.items():
        # Chọn xe đúng loại (ưu tiên xe rảnh)
        v_cands = [v for v in vehicles if v["kind"] == tgrp]
        v_free = [v for v in v_cands if v["plate"] not in busy]
        veh = (v_free or v_cands)[0]
        busy.add(veh["plate"])

        # Tách chuyến nếu tổng tải vượt sức chứa xe
        bucket, cur_q = [], 0
        chunks = []
        for o in grp_orders:
            if bucket and cur_q + o["qty"] > veh["cap_qty"]:
                chunks.append(bucket)
                bucket, cur_q = [], 0
            bucket.append(o)
            cur_q += o["qty"]
        if bucket:
            chunks.append(bucket)

        for chunk in chunks:
            seq += 1
            tno = f"TR-{seq:03d}"
            plan = build_lifo_plan(chunk, veh)
            solo_cost = len(chunk) * veh["cost_trip"]
            saved = max(0, solo_cost - veh["cost_trip"])
            est_min = max(20, min(90, 15 + int(plan["tot_qty"] * 0.25)))
            st_kind = "frozen" if any(o["storage"] == "frozen" for o in chunk) else ("chilled" if tgrp == "cold" else "dry")
            con.execute(
                """INSERT INTO trips
                   (trip_no,plate,route_zone,storage,est_load_min,status,load_plan_json,fill_pct,saved_vnd,created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (tno, veh["plate"], rzone, st_kind, est_min, "planned",
                 json.dumps(plan, ensure_ascii=False), plan["fill_pct"], saved, datetime.now().isoformat(timespec="seconds")),
            )
            tid = con.execute("SELECT id FROM trips WHERE trip_no=?", (tno,)).fetchone()[0]
            for o in chunk:
                con.execute("UPDATE sos SET trip_id=? WHERE id=?", (tid, o["id"]))
            created.append(tno)
    return created


def auto_schedule_docks(con):
    """Phân bổ Cửa xuất (X1-X4) và Khung giờ (06:00-18:00) theo EDF + Cold-Chain Priority + Slot Smoothing."""
    trips = rows(con, "SELECT * FROM trips WHERE status IN ('planned','scheduled') ORDER BY id")
    if not trips:
        return 0
    # Đọc hạn giao sớm nhất của mỗi chuyến để xếp EDF
    def sort_key(t):
        due = con.execute("SELECT MIN(due) FROM sos WHERE trip_id=?", (t["id"],)).fetchone()[0] or "9999-12-31"
        cold = 0 if t["storage"] in ("chilled", "frozen") else 1
        return (cold, due, t["id"])

    trips.sort(key=sort_key)
    # Con trỏ thời gian rảnh (phút từ 00:00) cho 4 cửa xuất: X1/X2 gần kho lạnh, X3/X4 hàng khô
    dock_clock = {"X1": 8 * 60, "X2": 8 * 60, "X3": 8 * 60, "X4": 8 * 60}
    fmt = lambda m: f"{m // 60:02d}:{m % 60:02d}"
    count = 0
    for t in trips:
        pool = ("X1", "X2") if t["storage"] in ("chilled", "frozen") else ("X3", "X4")
        dock = min(pool, key=lambda d: dock_clock[d])
        start = dock_clock[dock]
        dur = max(25, t["est_load_min"])
        end = start + dur
        dock_clock[dock] = end + 10   # đệm 10 phút đổi xe
        # Tính ETA dự báo và % nguy cơ trễ SLA
        traffic = ROUTE_TRAFFIC_MIN.get(t["route_zone"], 35)
        n_stops = con.execute("SELECT COUNT(*) FROM sos WHERE trip_id=?", (t["id"],)).fetchone()[0] or 1
        eta_min = end + traffic + n_stops * 20
        risk = 45 if eta_min > 15 * 60 else (20 if n_stops >= 2 else 8)
        con.execute(
            """UPDATE trips SET dock=?, slot_start=?, slot_end=?, status='scheduled', eta_text=?, sla_risk_pct=?
               WHERE id=?""",
            (dock, fmt(start), fmt(end), f"{day(0)} {fmt(min(eta_min, 23 * 60))}", risk, t["id"]),
        )
        count += 1
    return count


# ---------- CV5 & CV4: Giám sát Staging & Nhiệt độ thùng xe ----------
def staging_monitor(con):
    """Tính thời gian hàng đang chờ tại Khu 6 (Staging) so với ngưỡng an toàn nhiệt độ."""
    now = datetime.now()
    staged = rows(
        con,
        """SELECT s.id, s.so_no, s.customer, s.qty, s.due, s.staged_at, s.trip_id, s.audit_status,
                  p.sku, p.name AS pname, p.storage, p.price
           FROM sos s JOIN products p ON p.id=s.product_id
           WHERE s.status='picked' ORDER BY s.staged_at""",
    )
    out = []
    for s in staged:
        limit = 20 if s["storage"] == "frozen" else (35 if s["storage"] == "chilled" else 180)
        try:
            wait = max(1, int((now - datetime.fromisoformat(s["staged_at"])).total_seconds() // 60)) if s["staged_at"] else 5
        except ValueError:
            wait = 5
        pct = round(min(100.0, wait / limit * 100), 1)
        level = "bad" if wait >= limit * 0.8 else ("warn" if wait >= limit * 0.55 else "ok")
        out.append({
            **s, "wait_min": wait, "limit_min": limit, "pct": pct, "level": level,
            "cargo_val": s["qty"] * s["price"],
            "is_cold": s["storage"] in ("chilled", "frozen"),
        })
    out.sort(key=lambda x: (-int(x["is_cold"]), -x["pct"]))
    return out


def analyze_truck_temp(trip_row):
    """Phân tích chuỗi nhiệt độ thùng xe: phân biệt mở cửa dỡ hàng vs bất thường kỹ thuật & ngoại suy phút hỏng."""
    try:
        pts = json.loads(trip_row["temp_log_json"] or "[]")
    except ValueError:
        pts = []
    storage = trip_row["storage"]
    if storage == "frozen":
        lo, hi = -25.0, -18.0
    elif storage == "chilled":
        lo, hi = 2.0, 8.0
    else:
        lo, hi = 15.0, 30.0
    if not pts:
        base = -19.0 if storage == "frozen" else (4.5 if storage == "chilled" else 25.0)
        pts = [
            {"t": "08:00", "temp": base, "event": "Xuất cổng", "anomaly": False},
            {"t": "08:20", "temp": round(base + 0.4, 1), "event": "", "anomaly": False},
            {"t": "08:40", "temp": round(base + 2.1, 1), "event": "Mở cửa dỡ hàng (An toàn)", "anomaly": False},
            {"t": "09:00", "temp": round(base + 0.3, 1), "event": "Ổn định", "anomaly": False},
        ]
    # Kiểm tra xu hướng 3 điểm cuối (ngoại suy tuyến tính)
    anomalies = [p for p in pts if p.get("anomaly")]
    mins_to_spoil = None
    if len(pts) >= 3:
        slope = (pts[-1]["temp"] - pts[-3]["temp"]) / 40.0   # °C mỗi phút (mỗi điểm cách nhau ~20p)
        if slope > 0.03:
            remain = max(0.0, (hi + 2.0) - pts[-1]["temp"])
            mins_to_spoil = max(5, int(round(remain / slope)))
    return {
        "points": pts, "tmin": lo, "tmax": hi,
        "has_anomaly": bool(anomalies) or pts[-1]["temp"] > hi,
        "mins_to_spoil": mins_to_spoil,
        "latest_temp": pts[-1]["temp"],
    }
