"""Feature: Nhập hàng (Inbound CV1–CV4) — PO/ASN, Time-slot & Dock, Chuẩn bị mặt bằng, Tem nhãn & Nhận kho."""
import re
import unicodedata
from datetime import date

from flask import Blueprint, jsonify, request

from ..core import actor, audit, free_bin, notify_team, now_iso, zone_bins, zone_used
from ..db import NEAR, bad, day, db, log, rows
from ..xlsx import excel_date_to_iso, extract_text_from_upload

bp = Blueprint("inbound", __name__)

SLOTS = ["07:30-08:30", "08:30-09:30", "09:30-10:30", "10:30-11:30", "13:30-14:30", "14:30-15:30", "15:30-16:30"]


def _plain(s):
    s = unicodedata.normalize("NFD", str(s or ""))
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return s.replace("đ", "d").replace("Đ", "d").lower().strip()


def parse_po_text(con, raw_text):
    """Bóc tách nội dung Excel (.xlsx)/CSV/Text thành danh sách dòng PO chuẩn hóa SKU, kiểm tra ASN và sức chứa kho."""
    prods = rows(con, "SELECT * FROM products ORDER BY sku")
    zs = {z["storage"]: z for z in rows(con, "SELECT * FROM zones")}
    used_map = {st: zone_used(con, z["code"]) for st, z in zs.items()}
    lines = [ln.strip() for ln in str(raw_text or "").splitlines() if ln.strip()]
    out = []

    for idx, ln in enumerate(lines, 1):
        low = _plain(ln)
        if idx == 1 and ("sku" in low or "san pham" in low or "so luong" in low) and not re.search(r"\d+", ln):
            continue
        parts = [p.strip() for p in re.split(r"[,;\t|]+", ln)]
        while parts and not parts[-1]:
            parts.pop()
        if len(parts) < 2:
            out.append({
                "line": idx, "raw": ln, "ok": False, "confidence": "low",
                "warn": "Thiếu cột bắt buộc (cần ít nhất: Mã/Tên sản phẩm, Số lượng)",
            })
            continue

        p_raw, q_raw = parts[0], parts[1]
        eta_raw = parts[2] if len(parts) >= 3 else ""
        asn_no = parts[3] if len(parts) >= 4 else ""
        asn_uom = parts[4] if len(parts) >= 5 and parts[4] else "thùng"
        exp_raw = parts[5] if len(parts) >= 6 else ""
        qc_raw = _plain(parts[6]) if len(parts) >= 7 else ""

        m_q = re.search(r"\d+", q_raw)
        qty = int(m_q.group()) if m_q else 0
        eta = excel_date_to_iso(eta_raw, day(1))
        asn_exp = excel_date_to_iso(exp_raw, "") if exp_raw else ""
        need_qc = qc_raw in ("1", "co", "yes", "true", "qc", "x")

        pp = _plain(p_raw)
        best_p, best_sc = None, 0.0
        for p in prods:
            if _plain(p["sku"]) == pp or _plain(p["sku"]) in pp:
                best_p, best_sc = p, 1.0
                break
            toks = [t for t in re.split(r"\W+", pp) if len(t) >= 2]
            np_txt = _plain(p["name"])
            if toks:
                hit = sum(1 for t in toks if t in np_txt) / len(toks)
                if hit > best_sc:
                    best_p, best_sc = p, hit

        warns = []
        cap_ok = True
        prio = "standard"
        zone_code, free_cap = "", 0

        if not best_p or best_sc < 0.4:
            warns.append("Không khớp mã SKU trong danh mục kho")
        else:
            if best_sc < 0.85:
                warns.append(f"Khớp gần đúng ({int(best_sc * 100)}%) — cần kiểm tra lại SKU")
            prio = "urgent" if (best_p["storage"] in ("chilled", "frozen") or best_p["shelf_days"] <= 45) else "standard"
            z = zs.get(best_p["storage"])
            if z:
                zone_code = z["code"]
                free_cap = max(0, z["cap"] - used_map[best_p["storage"]])
                if qty > free_cap:
                    cap_ok = False
                    warns.append(f"Vượt sức chứa trống {z['name']} (chỉ còn {free_cap} thùng)")
                elif z["cap"] and (used_map[best_p["storage"]] + qty) / z["cap"] >= 0.85:
                    warns.append(f"{z['name']} sẽ đạt ≥85% sức chứa sau khi nhập")
            if asn_uom.strip().lower() != (best_p["unit"] or "thùng").strip().lower():
                warns.append(f"Sai UOM: PO dùng '{best_p['unit']}' nhưng file ghi '{asn_uom}'")
        if qty <= 0:
            warns.append("Số lượng phải > 0")
        if not asn_no:
            warns.append("Thiếu mã ASN (vẫn tạo được PO để bổ sung ở CV1)")
        if not asn_exp:
            warns.append("Chưa có HSD dự kiến trên ASN")

        ok = bool(best_p and best_sc >= 0.4 and qty > 0 and cap_ok)
        conf = "high" if (ok and best_sc >= 0.85 and asn_no and asn_exp and not any("Sai UOM" in w for w in warns)) else "low"
        out.append({
            "line": idx, "raw": ln,
            "product_id": best_p["id"] if best_p else None,
            "sku": best_p["sku"] if best_p else "?",
            "product_name": best_p["name"] if best_p else p_raw,
            "storage": best_p["storage"] if best_p else "",
            "zone_code": zone_code, "free_cap": free_cap,
            "qty": qty, "eta": eta, "asn_no": asn_no, "asn_uom": asn_uom, "asn_exp": asn_exp,
            "need_qc": need_qc, "priority": prio,
            "confidence": conf, "ok": ok, "warn": "; ".join(warns),
        })
    return out


def _enrich_po(con, o, busy_slots):
    """Bổ sung kiểm tra tự động cho từng PO: rà soát ASN, cờ ưu tiên, gợi ý Dock/Time-slot, kiểm tra mặt bằng, tem FEFO."""
    issues = []
    if not o["asn_no"]:
        issues.append("Thiếu thông báo giao hàng trước (ASN)")
    if not o["asn_exp"]:
        issues.append("Thiếu hạn sử dụng (HSD) dự kiến từ NCC")
    if (o["asn_uom"] or "thùng").strip().lower() != (o["unit"] or "thùng").strip().lower():
        issues.append(f"Sai lệch đơn vị tính: PO đặt '{o['unit']}' nhưng ASN khai báo '{o['asn_uom']}'")

    urgent = o["storage"] in ("chilled", "frozen") or (o["shelf_days"] or 180) <= 45
    priority = "urgent" if urgent else "standard"

    # CV2: Gợi ý 3 phương án Dock (luồng chữ U) + Time-slot + nhân sự/xe nâng
    docks = ("N1", "N2") if o["storage"] in ("chilled", "frozen") else ("N3", "N4")
    est_min = max(25, min(90, int(15 + (o["qty"] * (o["weight_kg"] or 8)) / 70)))
    workers = 3 if o["qty"] >= 200 else 2
    forklift = "Xe nâng điện kho lạnh" if o["storage"] in ("chilled", "frozen") else "Xe nâng tay / điện tiêu chuẩn"
    dock_opts = []
    for sl in SLOTS:
        for dk in docks:
            if (o["eta"], dk, sl) not in busy_slots:
                dock_opts.append({
                    "dock": dk, "slot": sl, "est_min": est_min, "workers": workers, "forklift": forklift,
                    "reason": f"Cửa {dk} sát khu {'lạnh' if dk in ('N1', 'N2') else 'khô/mỹ phẩm'} (luồng chữ U), trống lịch",
                })
                if len(dock_opts) >= 3:
                    break
        if len(dock_opts) >= 3:
            break

    # CV3: Kiểm tra mặt bằng 3 vùng (Staging, Quarantine, Storage Zone đích)
    z = con.execute("SELECT * FROM zones WHERE storage=?", (o["storage"],)).fetchone()
    z_used = zone_used(con, z["code"]) if z else 0
    z_pct = round(z_used / z["cap"] * 100, 1) if z and z["cap"] else 0
    z_after = round((z_used + o["qty"]) / z["cap"] * 100, 1) if z and z["cap"] else 0
    used_bins = con.execute("SELECT COUNT(DISTINCT bin) FROM batches WHERE zone=? AND qty>0", (z["code"],)).fetchone()[0] if z else 0
    tot_bins = zone_bins(z) if z else 0
    area_warns = []
    if z_after >= 85:
        area_warns.append(f"{z['name']} sẽ đạt {z_after}% sức chứa — nhắc Storage giải phóng kệ/dồn lô")
    if z and not (z["tmin"] <= z["temp"] <= z["tmax"]):
        area_warns.append(f"Nhiệt độ {z['name']} đang {z['temp']}°C ngoài ngưỡng {z['tmin']:g}..{z['tmax']:g}°C")
    if o["need_qc"]:
        area_warns.append("Đã giữ chỗ tại Khu 8 (Quarantine/QC) để lấy mẫu kiểm định trước khi lên kệ")

    # CV4: Sinh sẵn mã lô chuẩn FEFO + ký hiệu tem tạm + checklist hành động
    exp_tag = (o["asn_exp"] or day(o["shelf_days"] or 90)).replace("-", "")
    pre_batch = o["pre_batch"] or o["asn_batch"] or f"{o['sku'].replace('SKU-', 'L')}-{day().replace('-', '')[4:]}-{exp_tag[4:]}"
    badges = []
    if o["storage"] == "frozen":
        badges.append("❄ Đông lạnh ≤ -18°C")
    elif o["storage"] == "chilled":
        badges.append("❄ Hàng mát 2–8°C")
    if o["need_qc"]:
        badges.append("⚠ QC Cách ly")
    if o["fragile"]:
        badges.append("🍷 Dễ vỡ/móp")
    checklist = [
        f"Đối chiếu mã lịch hẹn {o['dock'] or 'Dock'} ({o['slot_time'] or 'chưa chốt'}) và cấp thẻ an toàn cổng",
        f"Kiểm đếm thực tế đủ {o['qty']} {o['unit']} ({o['sku']}), dán tem tạm {pre_batch}",
    ]
    if o["storage"] == "frozen":
        checklist.insert(0, "Đo nhiệt độ thùng xe lạnh trước khi mở cửa — yêu cầu ≤ -18°C")
    elif o["storage"] == "chilled":
        checklist.insert(0, "Đo nhiệt độ hàng mát khi hạ — yêu cầu 2–8°C và kiểm tra HSD còn đủ chuẩn")
    if o["need_qc"]:
        checklist.append("Lấy mẫu kiểm định chất lượng tại Khu 8 trước khi đẩy lên kệ chính")

    return {
        **o,
        "priority": priority,
        "ai_issues": issues,
        "dock_opts": dock_opts,
        "area_check": {
            "zone_code": z["code"] if z else "", "zone_name": z["name"] if z else "",
            "zone_pct": z_pct, "zone_after_pct": z_after,
            "free_bins": max(0, tot_bins - used_bins), "total_bins": tot_bins,
            "qc_reserved": bool(o["need_qc"]), "warnings": area_warns,
        },
        "pre_label": {"batch_id": pre_batch, "badges": badges, "checklist": checklist},
    }


@bp.get("/api/pos")
def api_pos():
    """Danh sách PO kèm phân tích kiểm tra (CV1–CV4) và biên bản từ chối tại Dock; PO chờ nhận xếp lên trước."""
    con = db()
    raw = rows(
        con,
        """SELECT o.*, p.sku, p.name, p.unit, p.supplier, p.storage, p.shelf_days, p.weight_kg, p.fragile
           FROM pos o JOIN products p ON p.id=o.product_id
           ORDER BY CASE o.status WHEN 'pending' THEN 0 WHEN 'rejected' THEN 1 ELSE 2 END, o.id DESC""",
    )
    rejs_by_po = {}
    for r in rows(con, "SELECT * FROM dock_rejections ORDER BY id DESC"):
        rejs_by_po.setdefault(r["po_id"], []).append(r)
    busy = {(r["eta"], r["dock"], r["slot_time"]) for r in raw if r["status"] == "pending" and r["dock"] and r["slot_time"]}
    out = [{**_enrich_po(con, o, busy), "rejections": rejs_by_po.get(o["id"], [])} for o in raw]
    con.close()
    return jsonify(out)


@bp.get("/api/pos/rejections")
def api_po_rejections():
    """Danh sách biên bản từ chối & trả hàng NCC ngay tại cửa nhập (Dock Rejection / RTV)."""
    con = db()
    items = rows(con, "SELECT * FROM dock_rejections ORDER BY id DESC LIMIT 100")
    con.close()
    return jsonify(items)


@bp.post("/api/pos")
def api_po_add():
    """Tạo PO mới, tự đánh số PO-xxx và tự gắn cờ ưu tiên FMCG."""
    d = request.get_json(silent=True) or {}
    try:
        qty = int(d.get("qty") or 0)
        pid = int(d.get("product_id") or 0)
    except (TypeError, ValueError):
        return bad("Sản phẩm hoặc số lượng không hợp lệ")
    if qty <= 0 or pid <= 0:
        return bad("Số lượng phải lớn hơn 0 và cần chọn sản phẩm")
    con = db()
    p = con.execute("SELECT * FROM products WHERE id=?", (pid,)).fetchone()
    if not p:
        con.close()
        return bad("Sản phẩm không tồn tại")
    prio = "urgent" if (p["storage"] in ("chilled", "frozen") or p["shelf_days"] <= 45) else "standard"
    with con:
        n = con.execute("SELECT COUNT(*) FROM pos").fetchone()[0] + 1
        po_no = f"PO-{n:03d}"
        con.execute(
            """INSERT INTO pos (po_no,product_id,qty,eta,plan_status,asn_no,asn_uom,asn_exp,asn_batch,priority,need_qc)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (po_no, pid, qty, d.get("eta") or day(1), "draft",
             (d.get("asn_no") or "").strip() or None,
             (d.get("asn_uom") or p["unit"]).strip(),
             (d.get("asn_exp") or "").strip() or None,
             (d.get("asn_batch") or "").strip() or None,
             prio, 1 if d.get("need_qc") else 0),
        )
        audit(con, "inbound", "Tạo đơn mua (PO)", po_no, f"Đặt {qty} thùng {p['sku']} ({'Cờ Đỏ' if prio == 'urgent' else 'Cờ Xanh'})")
    con.close()
    return jsonify(ok=True, po_no=po_no)


@bp.post("/api/pos/parse")
def api_po_parse():
    """CV1: Bóc tách file Excel (.xlsx) / CSV / văn bản đơn mua hàng (PO/ASN), chuẩn hóa SKU & kiểm tra sức chứa."""
    if "file" in request.files and request.files["file"].filename:
        try:
            raw = extract_text_from_upload(request.files["file"])
        except ValueError as e:
            return bad(str(e))
    else:
        d = request.get_json(silent=True) or {}
        raw = str(d.get("text") or "").strip()
    if not raw.strip():
        return bad("Nội dung file hoặc danh sách PO đang trống")
    con = db()
    items = parse_po_text(con, raw)
    con.close()
    return jsonify(items=items)


@bp.post("/api/pos/<int:po_id>/asn")
def api_po_asn(po_id):
    """CV1: Bổ sung/chỉnh sửa chứng từ ASN (mã ASN, đơn vị tính, lô & HSD dự kiến, yêu cầu QC)."""
    d = request.get_json(silent=True) or {}
    con = db()
    po = con.execute("SELECT * FROM pos WHERE id=?", (po_id,)).fetchone()
    if not po or po["status"] != "pending":
        con.close()
        return bad("PO không tồn tại hoặc đã nhập kho")
    with con:
        con.execute(
            """UPDATE pos SET asn_no=?, asn_uom=?, asn_exp=?, asn_batch=?, need_qc=? WHERE id=?""",
            ((d.get("asn_no") or "").strip() or None,
             (d.get("asn_uom") or "thùng").strip(),
             (d.get("asn_exp") or "").strip() or None,
             (d.get("asn_batch") or "").strip() or None,
             1 if d.get("need_qc") in (True, 1, "1", "true", "on") else 0,
             po_id),
        )
        audit(con, "inbound", "Cập nhật ASN", po["po_no"], f"ASN={d.get('asn_no') or '-'}, UOM={d.get('asn_uom') or 'thùng'}, HSD={d.get('asn_exp') or '-'}")
    con.close()
    return jsonify(ok=True)


@bp.post("/api/pos/<int:po_id>/validate")
def api_po_validate(po_id):
    """CV1: Xác nhận PO/ASN hợp lệ, khóa chứng từ và chuyển sang 'Sẵn sàng xếp lịch'."""
    con = db()
    po = con.execute("SELECT o.*, p.unit FROM pos o JOIN products p ON p.id=o.product_id WHERE o.id=?", (po_id,)).fetchone()
    if not po or po["status"] != "pending":
        con.close()
        return bad("PO không tồn tại hoặc đã nhập kho")
    if not po["asn_no"] or not po["asn_exp"]:
        con.close()
        return bad("Chưa thể xác nhận: cần bổ sung mã ASN và hạn sử dụng dự kiến trước")
    if (po["asn_uom"] or "").strip().lower() != (po["unit"] or "thùng").strip().lower():
        con.close()
        return bad(f"Sai lệch đơn vị tính ({po['asn_uom']} != {po['unit']}), hãy chuẩn hóa ASN trước")
    with con:
        con.execute("UPDATE pos SET plan_status='validated' WHERE id=?", (po_id,))
        audit(con, "inbound", "Xác nhận PO hợp lệ", po["po_no"], f"Đã khóa chứng từ {po['asn_no']}, chuyển sang Sẵn sàng xếp lịch")
    con.close()
    return jsonify(ok=True)


@bp.post("/api/pos/<int:po_id>/schedule")
def api_po_schedule(po_id):
    """CV2: Chốt khung giờ (Time-slot), cửa nhập (Dock N1-N4) & phân bổ nhân sự/xe nâng."""
    d = request.get_json(silent=True) or {}
    dock = (d.get("dock") or "").strip()
    slot_time = (d.get("slot_time") or "").strip()
    if dock not in ("N1", "N2", "N3", "N4") or not slot_time:
        return bad("Cần chọn cửa nhập (N1–N4) và khung giờ hợp lệ")
    con = db()
    po = con.execute("SELECT o.*, p.sku, p.storage FROM pos o JOIN products p ON p.id=o.product_id WHERE o.id=?", (po_id,)).fetchone()
    if not po or po["status"] != "pending":
        con.close()
        return bad("PO không tồn tại hoặc đã nhập kho")
    # Kiểm tra trùng slot cùng ngày & cửa nhập
    clash = con.execute(
        "SELECT po_no, priority FROM pos WHERE id!=? AND status='pending' AND eta=? AND dock=? AND slot_time=?",
        (po_id, po["eta"], dock, slot_time),
    ).fetchone()
    if clash:
        con.close()
        return bad(f"Trùng khung giờ {slot_time} tại cửa {dock} với {clash['po_no']} — hãy chọn khung trống khác")
    workers = int(d.get("workers") or 2)
    est_min = int(d.get("est_min") or 45)
    forklift = (d.get("forklift") or ("Xe nâng điện kho lạnh" if po["storage"] in ("chilled", "frozen") else "Xe nâng tiêu chuẩn")).strip()
    with con:
        con.execute(
            "UPDATE pos SET dock=?, slot_time=?, est_min=?, workers=?, forklift=?, plan_status='scheduled' WHERE id=?",
            (dock, slot_time, est_min, workers, forklift, po_id),
        )
        audit(con, "inbound", "Chốt lịch Time-slot", po["po_no"], f"Cửa {dock} ({slot_time}), {workers} nhân sự, {forklift}")
        notify_team(con, "storage", f"Đã chốt lịch {po['po_no']} ({po['sku']}, {po['qty']} thùng) vào cửa {dock} khung {slot_time}. Nhờ tổ Lưu trữ chuẩn bị kệ trống.", po["po_no"])
    con.close()
    return jsonify(ok=True)


@bp.post("/api/pos/<int:po_id>/area-ready")
def api_po_area_ready(po_id):
    """CV3: Xác nhận mặt bằng Staging, khu cách ly QC và vùng lưu trữ đã sẵn sàng đón hàng."""
    con = db()
    po = con.execute("SELECT * FROM pos WHERE id=?", (po_id,)).fetchone()
    if not po or po["status"] != "pending":
        con.close()
        return bad("PO không tồn tại hoặc đã nhập kho")
    with con:
        con.execute("UPDATE pos SET area_ready=1, plan_status='ready_area' WHERE id=?", (po_id,))
        audit(con, "inbound", "Xác nhận sẵn sàng mặt bằng", po["po_no"], "Khu hạ hàng, khu QC và kệ mục tiêu đã thông thoáng, đạt chuẩn")
    con.close()
    return jsonify(ok=True)


@bp.post("/api/pos/<int:po_id>/arrive")
def api_po_arrive(po_id):
    """CV4: Cấp thẻ an toàn cổng, ghi nhận biển số/tài xế và chuyển 'Xe đã cập bến – Sẵn sàng dỡ hàng'."""
    d = request.get_json(silent=True) or {}
    plate = (d.get("plate") or "").strip()
    driver = (d.get("driver") or "").strip()
    if not plate:
        return bad("Cần nhập biển số xe vận chuyển để cấp thẻ cổng")
    con = db()
    po = con.execute("SELECT o.*, p.sku, p.shelf_days FROM pos o JOIN products p ON p.id=o.product_id WHERE o.id=?", (po_id,)).fetchone()
    if not po or po["status"] != "pending":
        con.close()
        return bad("PO không tồn tại hoặc đã nhập kho")
    gp = f"GP-{po_id:04d}"
    exp_tag = (po["asn_exp"] or day(po["shelf_days"] or 90)).replace("-", "")
    pre_batch = (d.get("pre_batch") or po["asn_batch"] or f"{po['sku'].replace('SKU-', 'L')}-{day().replace('-', '')[4:]}-{exp_tag[4:]}").strip()
    with con:
        con.execute(
            "UPDATE pos SET gate_pass=?, plate=?, driver=?, pre_batch=?, plan_status='arrived' WHERE id=?",
            (gp, plate, driver, pre_batch, po_id),
        )
        audit(con, "inbound", "Cấp thẻ cổng & Xe cập bến", po["po_no"], f"Thẻ {gp}, xe {plate} ({driver or 'tài xế'}), tem lô {pre_batch}")
    con.close()
    return jsonify(ok=True, gate_pass=gp, pre_batch=pre_batch)


def _next_rej_no(con):
    n = con.execute("SELECT COUNT(*) FROM dock_rejections").fetchone()[0] + 1
    return f"RTV-{n:03d}"


def _parse_temp(val):
    if val is None or str(val).strip() == "":
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        raise ValueError("Nhiệt độ đo thực tế không hợp lệ")


@bp.post("/api/pos/<int:po_id>/reject")
def api_po_reject(po_id):
    """CV4: Từ chối toàn bộ chuyến hàng ngay tại Dock (không nhập vào tồn kho, lập biên bản RTV cho tài xế chở về)."""
    d = request.get_json(silent=True) or {}
    reason = str(d.get("reason") or "").strip()
    note = str(d.get("note") or "").strip()
    if not reason:
        return bad("Cần chọn hoặc nhập lý do từ chối hàng tại Dock")
    try:
        m_temp = _parse_temp(d.get("measured_temp"))
    except ValueError as e:
        return bad(str(e))
    full_reason = f"{reason} — {note}" if note else reason

    con = db()
    try:
        with con:
            po = con.execute(
                """SELECT o.*, p.sku, p.name AS pname, p.supplier, p.storage
                   FROM pos o JOIN products p ON p.id=o.product_id WHERE o.id=?""",
                (po_id,),
            ).fetchone()
            if not po or po["status"] != "pending":
                raise ValueError("PO không tồn tại hoặc đã nhận/đã từ chối")
            plate = (d.get("plate") or po["plate"] or "").strip()
            driver = (d.get("driver") or po["driver"] or "").strip()
            rej_no = _next_rej_no(con)
            un, _, _ = actor()
            con.execute(
                """UPDATE pos SET status='rejected', plan_status='rejected', recv=0, dmg=?, reject_reason=?,
                   plate=?, driver=? WHERE id=?""",
                (po["qty"], full_reason, plate or None, driver or None, po_id),
            )
            con.execute(
                """INSERT INTO dock_rejections
                   (rej_no,po_id,po_no,sku,product_name,supplier,kind,qty_rejected,qty_accepted,reason,measured_temp,plate,driver,dock,created_by,created_at)
                   VALUES (?,?,?,?,?,?,'full',?,0,?,?,?,?,?,?,?)""",
                (rej_no, po_id, po["po_no"], po["sku"], po["pname"], po["supplier"], po["qty"],
                 full_reason, m_temp, plate, driver, po["dock"] or "Dock", un, now_iso()),
            )
            t_txt = f", nhiệt đo {m_temp:g}°C" if m_temp is not None else ""
            detail = f"Biên bản {rej_no}: trả toàn bộ {po['qty']} thùng {po['sku']} cho {po['supplier']}{t_txt}. Lý do: {full_reason}"
            audit(con, "inbound", "Từ chối toàn bộ tại Dock", po["po_no"], detail)
            notify_team(con, "admin", f"[Từ chối tại Dock · {rej_no}] {po['po_no']} ({po['sku']} x{po['qty']}) bị từ chối nhận ngay tại cửa nhập: {full_reason}", rej_no)
            notify_team(con, "storage", f"[Giải phóng kệ · {rej_no}] {po['po_no']} đã bị từ chối tại Dock, không nhập vào kho.", rej_no)
    except ValueError as e:
        return bad(str(e))
    finally:
        con.close()
    return jsonify(ok=True, rej_no=rej_no)


@bp.post("/api/pos/<int:po_id>/receive")
def api_po_receive(po_id):
    """Nhận hàng vào kho: kiểm tra nhiệt độ (nếu nhập), tạo lô mới, cộng tồn; nếu có hàng hỏng (dmg>0) tự lập biên bản trả 1 phần tại Dock."""
    d = request.get_json(silent=True) or {}
    try:
        ok, dmg = int(d.get("qty") or 0), int(d.get("dmg") or 0)
        m_temp = _parse_temp(d.get("measured_temp"))
    except (TypeError, ValueError) as e:
        return bad(str(e) if isinstance(e, ValueError) else "Số lượng không hợp lệ")
    exp, no = str(d.get("exp") or ""), (d.get("batch_no") or "").strip()
    if ok <= 0 or dmg < 0 or not no:
        return bad("Cần số lô và số lượng đạt > 0 (nếu từ chối toàn bộ hãy dùng nút Từ chối tại Dock)")
    if exp <= day():
        return bad("Hạn dùng phải sau hôm nay (không nhận hàng hết hạn — hãy lập biên bản Từ chối tại Dock)")
    dmg_reason = str(d.get("dmg_reason") or "").strip()
    rej_no = None
    con = db()
    try:
        with con:
            po = con.execute("SELECT o.*, p.sku, p.name AS pname, p.supplier, p.storage FROM pos o JOIN products p ON p.id=o.product_id WHERE o.id=?",
                             (po_id,)).fetchone()
            if not po or po["status"] != "pending":
                raise ValueError("PO không tồn tại hoặc đã nhận")
            # Chặn nhận hàng lạnh/đông nếu nhiệt độ đo thực tế tại thùng xe vượt ngưỡng an toàn
            if m_temp is not None:
                if po["storage"] == "frozen" and m_temp > -15:
                    raise ValueError(f"Nhiệt độ thùng xe đông lạnh đo được {m_temp:g}°C (yêu cầu ≤ -18°C) — hãy dùng nút Từ chối tại Dock để trả NCC ngay!")
                if po["storage"] == "chilled" and not (0 <= m_temp <= 10):
                    raise ValueError(f"Nhiệt độ hàng mát đo được {m_temp:g}°C (chuẩn 2–8°C) — hãy dùng nút Từ chối tại Dock để trả NCC ngay!")
            z = con.execute("SELECT * FROM zones WHERE storage=?", (po["storage"],)).fetchone()
            if zone_used(con, z["code"]) + ok > z["cap"]:
                raise ValueError(f"{z['name']} không đủ sức chứa cho {ok} thùng")
            b = free_bin(con, z["code"])
            if b is None:
                raise ValueError(f"{z['name']} đã hết ô trống")
            q_st = "quarantine" if po["need_qc"] and d.get("to_qc") else "ok"
            con.execute(
                "INSERT INTO batches (product_id,batch_no,exp,qty,zone,bin,q_status,received_at) VALUES (?,?,?,?,?,?,?,?)",
                (po["product_id"], no, exp, ok, z["code"], b, q_st, now_iso()),
            )
            con.execute("UPDATE pos SET status='received', plan_status='received', recv=?, dmg=? WHERE id=?", (ok, dmg, po_id))
            log(con, "IN", po["product_id"], no, ok, f"Nhận {po['po_no']} vào {z['code']}-{b:02d}")
            # Nếu có hàng móp/hỏng -> tự lập biên bản trả 1 phần ngay tại Dock cho tài xế chở về
            if dmg > 0:
                rej_no = _next_rej_no(con)
                un, _, _ = actor()
                r_txt = dmg_reason or "Hàng móp méo / rách vỡ bao bì lúc dỡ xe — trả NCC ngay tại Dock"
                con.execute(
                    """INSERT INTO dock_rejections
                       (rej_no,po_id,po_no,sku,product_name,supplier,kind,qty_rejected,qty_accepted,reason,measured_temp,plate,driver,dock,created_by,created_at)
                       VALUES (?,?,?,?,?,?,'partial',?,?,?,?,?,?,?,?,?)""",
                    (rej_no, po_id, po["po_no"], po["sku"], po["pname"], po["supplier"], dmg, ok,
                     r_txt, m_temp, po["plate"] or "", po["driver"] or "", po["dock"] or "Dock", un, now_iso()),
                )
            audit(con, "inbound", "Nhận hàng vào kho", po["po_no"],
                  f"Nhập lô {no} ({ok} thùng đạt, {dmg} thùng trả tại Dock{(' · ' + rej_no) if rej_no else ''}) vào {z['code']}-{b:02d}, HSD {exp}")
            # Phối hợp liên phòng ban (Cross-Functional Synergy): lô cận date tự báo Storage & Picking
            left = (date.fromisoformat(exp) - date.today()).days
            if left <= NEAR:
                msg = f"[Cảnh báo cận date] {po['po_no']} vừa nhập lô {no} ({po['sku']} - {ok} thùng) tại {z['code']}-{b:02d} chỉ còn {left} ngày hạn! Storage ưu tiên kệ tầng 1, Picking đẩy lên đầu danh sách FEFO."
                notify_team(con, "storage", msg, no)
                notify_team(con, "picking", msg, no)
    except ValueError as e:
        return bad(str(e))
    finally:
        con.close()
    return jsonify(ok=True, rej_no=rej_no)
