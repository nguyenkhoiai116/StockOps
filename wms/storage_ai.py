"""Engine nghiệp vụ & thuật toán cho Nhóm 2 (Storage & Inventory: CV1–CV5).

Toàn bộ thuật toán đều xác định (deterministic), đọc dữ liệu thật từ SQLite và
chỉ trả về đề xuất/phân tích để con người xác nhận trước khi ghi kho.
"""
import math
from collections import defaultdict
from datetime import date, timedelta

from .core import shelf_pct, stock_by_sku, zone_bins, zone_used
from .db import NEAR, day, rows


def bin_coords(bin_no, z):
    """Đổi số ô -> (dãy chữ, ô, tầng) khớp công thức layout 3D."""
    i = bin_no - 1
    rack = i // (z["bays"] * z["levels"]) + 1
    bay = (i // z["levels"]) % z["bays"] + 1
    level = (i % z["levels"]) + 1
    return chr(64 + rack), bay, level


# ---------- CV1: Slotting (ràng buộc cứng + ABC + COI + Golden Zone + FEFO) ----------
def pick_freq_by_sku(con):
    """Tần suất dòng lấy hàng (pick lines / xuất kho) của từng SKU."""
    freq = defaultdict(int)
    for r in rows(con, "SELECT product_id, COUNT(*) AS n FROM txs WHERE kind='OUT' GROUP BY product_id"):
        freq[r["product_id"]] += r["n"]
    for r in rows(con, "SELECT b.product_id, COUNT(*) AS n FROM picks k JOIN batches b ON b.id=k.batch_id GROUP BY b.product_id"):
        freq[r["product_id"]] += r["n"]
    return freq


def abc_class_map(con):
    """Phân loại ABC theo tần suất lấy hàng (pick lines), không theo doanh thu."""
    freq = pick_freq_by_sku(con)
    ps = rows(con, "SELECT id, sku FROM products")
    ranked = sorted(ps, key=lambda p: freq.get(p["id"], 0), reverse=True)
    tot = sum(max(1, freq.get(p["id"], 0)) for p in ranked) or 1
    acc, out = 0, {}
    for p in ranked:
        f = max(1, freq.get(p["id"], 0))
        acc += f
        pct = acc / tot
        cls = "A" if pct <= 0.60 else ("B" if pct <= 0.85 else "C")
        out[p["id"]] = {"abc": cls, "freq": freq.get(p["id"], 0)}
    return out


def slotting_recommend(con, product_id, qty, exp_str=""):
    """Lọc ràng buộc cứng (nhiệt độ, tương thích, sức chứa) rồi chấm điểm COI + Golden Zone + FEFO."""
    p = con.execute("SELECT * FROM products WHERE id=?", (product_id,)).fetchone()
    if not p:
        raise ValueError("Không tìm thấy sản phẩm")
    z = con.execute("SELECT * FROM zones WHERE storage=?", (p["storage"],)).fetchone()
    if not z:
        raise ValueError("Không có khu phù hợp điều kiện bảo quản")
    used_qty = zone_used(con, z["code"])
    free_cap = z["cap"] - used_qty
    if qty > free_cap:
        return {
            "product": dict(p), "zone": dict(z), "ok": False,
            "error": f"{z['name']} chỉ còn trống {free_cap} thùng, không đủ chứa {qty} thùng",
            "suggestions": [],
        }

    abc_info = abc_class_map(con).get(p["id"], {"abc": "C", "freq": 1})
    freq = max(1, abc_info["freq"])
    coi = round((p["vol_m3"] * max(1, qty)) / freq, 4)
    left_days = (date.fromisoformat(exp_str) - date.today()).days if exp_str else p["shelf_days"]
    near_exp = left_days <= 45

    occupied = {r["bin"] for r in rows(con, "SELECT bin FROM batches WHERE zone=? AND (qty>0 OR locked=1)", (z["code"],))}
    total_bins = zone_bins(z)
    cands = []
    for b in range(1, total_bins + 1):
        if b in occupied:
            continue
        rack_ch, bay, level = bin_coords(b, z)
        # Golden Zone: tầng 1-2 và ô gần cửa xuất (bay nhỏ, dãy đầu)
        dist = (ord(rack_ch) - 65) * 3 + bay + (level - 1) * 2
        score = 100.0
        reasons = [f"Đạt chuẩn nhiệt độ {z['tmin']:g}..{z['tmax']:g}°C"]
        if abc_info["abc"] == "A":
            score += max(0, 25 - dist * 2)
            if level <= 2:
                score += 12
                reasons.append("Nhóm A (tần suất xuất cao) → ưu tiên Golden Zone tầng thấp")
        elif abc_info["abc"] == "B":
            score += max(0, 15 - abs(level - 2) * 5 - bay)
            reasons.append("Nhóm B → vị trí cân bằng quãng đường")
        else:
            score += level * 3   # nhóm C nhường vị trí đẹp cho nhóm A
            reasons.append("Nhóm C → tầng cao để nhường Golden Zone cho hàng quay nhanh")
        if p["weight_kg"] >= 9.0 and level == 1:
            score += 15
            reasons.append(f"Hàng nặng ({p['weight_kg']}kg/thùng) → ưu tiên tầng 1 an toàn")
        if p["fragile"] and level <= 2:
            score += 8
            reasons.append("Hàng dễ vỡ/móp → hạn chế nâng lên tầng cao")
        if near_exp:
            if level == 1 and bay <= 2:
                score += 22
                reasons.append(f"FEFO cận hạn ({left_days} ngày) → mặt trước dễ lấy xuất trước")
            else:
                score -= (level - 1) * 8
        # Phạt nhẹ hàng cồng kềnh (COI cao) không chiếm ô đẹp nhất của hàng nhỏ bán chạy
        if coi > 1.5 and bay == 1 and level == 1 and not near_exp:
            score -= 6
            reasons.append(f"COI cao ({coi}) → cân đối tránh chiếm ô đẹp của hàng gọn bán chạy")
        cands.append({
            "zone": z["code"], "bin": b, "loc": f"{z['code']}-{b:02d}",
            "spot": f"Dãy {rack_ch} · Ô {bay} · Tầng {level}",
            "level": level, "score": round(score, 1), "reasons": reasons[:3],
        })

    cands.sort(key=lambda x: (-x["score"], x["bin"]))
    return {
        "product": dict(p), "zone": dict(z), "ok": True,
        "abc": abc_info["abc"], "freq": abc_info["freq"], "coi": coi,
        "left_days": left_days, "free_cap": free_cap,
        "suggestions": cands[:3],
    }


def capacity_and_reslot(con):
    """Phân tích sức chứa, honeycombing và đề xuất Re-slotting chỉ khi ROI >= 1.5."""
    zs = rows(con, "SELECT * FROM zones ORDER BY code")
    abc_map = abc_class_map(con)
    zone_stats, reslots = [], []

    for z in zs:
        used_qty = zone_used(con, z["code"])
        tbins = zone_bins(z)
        bs = rows(con, """SELECT b.*, p.sku, p.name, p.vol_m3, p.shelf_days, p.weight_kg
                          FROM batches b JOIN products p ON p.id=b.product_id
                          WHERE b.zone=? AND b.qty>0 ORDER BY b.bin""", (z["code"],))
        used_bins = {b["bin"] for b in bs}
        max_bin = max(used_bins) if used_bins else 0
        honeycomb = sum(1 for i in range(1, max_bin) if i not in used_bins)
        vol_used = round(sum(b["qty"] * b["vol_m3"] for b in bs), 2)
        vol_cap = round(z["cap"] * 0.035, 1)
        pct = round(used_qty / z["cap"] * 100, 1) if z["cap"] else 0
        bin_pct = round(len(used_bins) / tbins * 100, 1) if tbins else 0
        # Kho lạnh cần chừa khoảng lưu thông khí nên ngưỡng cảnh báo chặt hơn (80%)
        warn_at = 80 if z["storage"] in ("chilled", "frozen") else 85
        zone_stats.append({
            "code": z["code"], "name": z["name"], "storage": z["storage"],
            "used_qty": used_qty, "cap_qty": z["cap"], "pct": pct,
            "used_bins": len(used_bins), "total_bins": tbins, "bin_pct": bin_pct,
            "vol_used": vol_used, "vol_cap": vol_cap, "honeycomb": honeycomb,
            "temp": z["temp"], "hum": z["hum"], "tmin": z["tmin"], "tmax": z["tmax"],
            "temp_ok": z["tmin"] <= z["temp"] <= z["tmax"],
            "overload_warn": pct >= warn_at,
        })
        # Tìm ứng viên Re-slotting (lô cận hạn ở tầng cao hoặc nhóm A ở xa)
        free_front = [i for i in range(1, tbins + 1) if i not in used_bins and bin_coords(i, z)[2] == 1]
        for b in bs:
            if not free_front:
                break
            _, bay, level = bin_coords(b["bin"], z)
            left = (date.fromisoformat(b["exp"]) - date.today()).days
            info = abc_map.get(b["product_id"], {"abc": "C", "freq": 1})
            if (left <= 30 and left >= 0 and level >= 2) or (info["abc"] == "A" and level >= 3):
                target = free_front[0]
                t_rack, t_bay, t_lvl = bin_coords(target, z)
                d_old = bay * 2.7 + level * 4.0
                d_new = t_bay * 2.7 + t_lvl * 4.0
                freq = max(3, info["freq"])
                saving = max(12.0, round((d_old - d_new) * freq * 14, 1))
                cost = 18.0
                roi = round(saving / cost, 2)
                if roi >= 1.5:
                    free_front.pop(0)
                    reslots.append({
                        "batch_id": b["id"], "sku": b["sku"], "name": b["name"], "batch_no": b["batch_no"],
                        "qty": b["qty"], "from_zone": z["code"], "from_bin": b["bin"],
                        "from_loc": f"{z['code']}-{b['bin']:02d}",
                        "to_zone": z["code"], "to_bin": target,
                        "to_loc": f"{z['code']}-{target:02d}",
                        "to_spot": f"Dãy {t_rack} · Ô {t_bay} · Tầng {t_lvl}",
                        "roi": roi,
                        "reason": f"Lô cận hạn ({left} ngày) đang ở tầng {level}" if left <= 30 else f"Nhóm A ở tầng {level}, dời về Golden Zone",
                    })
    return {"zones": zone_stats, "reslots": reslots}


# ---------- CV2: Dự báo nhu cầu (Syntetos-Boylan ADI/CV², so Naive), ROP, SS, EOQ ----------
def _mean(xs):
    return sum(xs) / len(xs) if xs else 0.0


def _std(xs):
    if len(xs) < 2:
        return 0.0
    m = _mean(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / len(xs))


def demand_and_replenishment(con):
    """Dự báo nhu cầu theo SKU, so với baseline Naive, tính Inventory Position, ROP, SS, DOC và đề xuất đặt hàng."""
    horizon = 14
    days = [day(i - horizon + 1) for i in range(horizon)]
    out_map = defaultdict(lambda: defaultdict(int))
    for r in rows(con, "SELECT product_id, substr(ts,1,10) AS d, SUM(ABS(qty)) AS q FROM txs WHERE kind='OUT' AND substr(ts,1,10)>=? GROUP BY product_id, d", (days[0],)):
        out_map[r["product_id"]][r["d"]] += r["q"]

    in_po = {r["product_id"]: r["q"] for r in rows(con, "SELECT product_id, COALESCE(SUM(qty),0) AS q FROM pos WHERE status='pending' GROUP BY product_id")}
    res_map = {r["product_id"]: r["q"] for r in rows(con, "SELECT product_id, COALESCE(SUM(reserved),0) AS q FROM batches GROUP BY product_id")}
    z_free = {}
    for z in rows(con, "SELECT * FROM zones"):
        z_free[z["storage"]] = max(0, z["cap"] - zone_used(con, z["code"]))

    abc_map = abc_class_map(con)
    z_val = {"A": 2.05, "B": 1.65, "C": 1.28}   # Z-score mức phục vụ 98% / 95% / 90%
    items = []

    for p in stock_by_sku(con):
        series = [out_map[p["id"]].get(d, 0) for d in days]
        nz = [x for x in series if x > 0]
        # Syntetos-Boylan: ADI & CV²
        if nz:
            adi = round(len(series) / len(nz), 2)
            m_nz = _mean(nz)
            cv2 = round((_std(nz) / m_nz) ** 2, 2) if m_nz > 0 else 0.0
        else:
            adi, cv2 = 14.0, 0.0

        if adi < 1.32 and cv2 < 0.49:
            sb_cls, model_pref = "Smooth (Ổn định)", "WMA"
        elif adi < 1.32:
            sb_cls, model_pref = "Erratic (Thất thường)", "Holt-damped"
        elif cv2 < 0.49:
            sb_cls, model_pref = "Intermittent (Gián đoạn)", "Croston"
        else:
            sb_cls, model_pref = "Lumpy (Rời rạc)", "Croston"

        # Rolling backtest trên 4 ngày cuối: so mô hình ứng viên với Naive baseline
        eval_n = 4
        naive_err, cand_err = [], []
        for t in range(len(series) - eval_n, len(series)):
            hist = series[:t]
            actual = series[t]
            naive_pred = hist[-1] if hist else 0
            if model_pref == "WMA":
                w = list(range(1, len(hist[-5:]) + 1))
                cand_pred = sum(a * b for a, b in zip(hist[-5:], w)) / sum(w) if w else 0
            elif model_pref == "Holt-damped":
                alpha, beta, phi = 0.4, 0.2, 0.8
                lvl, tr = float(hist[0]), 0.0
                for v in hist[1:]:
                    prev = lvl
                    lvl = alpha * v + (1 - alpha) * (lvl + phi * tr)
                    tr = beta * (lvl - prev) + (1 - beta) * phi * tr
                cand_pred = max(0.0, lvl + phi * tr)
            else:
                # Croston đơn giản: cỡ đơn trung bình / khoảng cách giữa các kỳ có nhu cầu
                h_nz = [x for x in hist if x > 0]
                cand_pred = (_mean(h_nz) / (len(hist) / len(h_nz))) if h_nz else 0.0
            naive_err.append(abs(actual - naive_pred))
            cand_err.append(abs(actual - cand_pred))

        mae_naive = round(_mean(naive_err), 1)
        mae_cand = round(_mean(cand_err), 1)
        # Bắt buộc: không thắng Naive thì dùng Naive
        if mae_cand <= mae_naive and sum(series) > 0:
            chosen = model_pref
            if model_pref == "WMA":
                w = list(range(1, 6))
                d_day = sum(a * b for a, b in zip(series[-5:], w)) / sum(w)
            elif model_pref == "Holt-damped":
                d_day = max(0.0, _mean(series[-5:]) * 0.7 + _mean(series) * 0.3)
            else:
                d_day = (_mean(nz) / adi) if nz else 0.0
        else:
            chosen = "Naive (Baseline)"
            d_day = float(series[-1] if series[-1] > 0 else _mean(series))
        # Nếu chưa đủ lịch sử xuất (SKU mới / chưa xuất), ước lượng nền tối thiểu từ safety/10
        if d_day <= 0:
            d_day = max(2.0, round(p["safety"] / 10.0, 1))
            chosen = "Ước lượng nền (ít lịch sử)"
        d_day = round(d_day, 1)

        sigma_d = _std(series) or (d_day * 0.25)
        lead = p["lead_days"] or 2
        abc = abc_map.get(p["id"], {"abc": "B"})["abc"]
        ss_calc = int(math.ceil(z_val[abc] * sigma_d * math.sqrt(lead)))
        ss = max(p["safety"], ss_calc)
        rop = int(math.ceil(d_day * lead + ss))
        # EOQ tham chiếu (chi phí đặt 350k/lần, lưu kho 18%/năm)
        annual_d = d_day * 365
        h_cost = max(1000, p["price"] * 0.18)
        eoq = int(round(math.sqrt(2 * annual_d * 350000 / h_cost))) if annual_d > 0 else p["safety"]

        incoming = in_po.get(p["id"], 0)
        reserved = res_map.get(p["id"], 0)
        inv_pos = p["av"] + incoming
        doc = round(p["av"] / d_day, 1) if d_day > 0 else 999.0

        # Phân mức cảnh báo 4 cấp theo File 3 trang 8
        if p["av"] < ss:
            alert = "crit"
            alert_lbl = "Khẩn (dưới SS)"
        elif inv_pos < rop and doc < lead:
            alert = "high"
            alert_lbl = "Đỏ (DOC < Lead time)"
        elif inv_pos <= rop:
            alert = "warn"
            alert_lbl = "Vàng (Chạm ROP)"
        else:
            alert = "ok"
            alert_lbl = "Xanh (An toàn)"

        # Lượng đặt Q = max(0, Target - InvPos), làm tròn bội 10, chặn bởi sức chứa khu & hạn dùng
        target = max(rop + eoq // 2, int(round(d_day * (lead + 7) + ss)))
        raw_q = max(0, target - inv_pos)
        cap_free = z_free.get(p["storage"], 0)
        shelf_cap = int(d_day * max(3, p["shelf_days"] - 7))
        rec_q = min(raw_q, cap_free, shelf_cap)
        rec_q = int(math.ceil(rec_q / 10.0) * 10) if rec_q > 0 else 0
        if rec_q > cap_free:
            rec_q = cap_free
        cap_note = ""
        if raw_q > cap_free:
            cap_note = f"Chặn bởi sức chứa trống ({cap_free} thùng)"
        elif raw_q > shelf_cap:
            cap_note = f"Chặn bởi HSD ({p['shelf_days']} ngày)"

        items.append({
            "product_id": p["id"], "sku": p["sku"], "name": p["name"], "storage": p["storage"],
            "abc": abc, "adi": adi, "cv2": cv2, "sb_class": sb_cls,
            "model": chosen, "mae_model": mae_cand, "mae_naive": mae_naive,
            "forecast_day": d_day, "forecast_7d": int(round(d_day * 7)),
            "av": p["av"], "incoming": incoming, "reserved": reserved, "inv_pos": inv_pos,
            "lead_days": lead, "safety": ss, "rop": rop, "eoq": eoq, "doc": doc,
            "alert": alert, "alert_lbl": alert_lbl, "rec_qty": rec_q, "cap_note": cap_note,
        })

    rank = {"crit": 0, "high": 1, "warn": 2, "ok": 3}
    items.sort(key=lambda x: (rank[x["alert"]], x["doc"]))
    return items


# ---------- CV3: Kiểm kê ABC Risk-based & Luật RCA ----------
def cycle_count_risk(con):
    """Chấm điểm rủi ro kiểm kê theo 6 yếu tố (Giá trị, Tần suất, Lịch sử lệch, Cận hạn, Dễ vỡ, Thao tác)."""
    bs = rows(con, """SELECT b.*, p.sku, p.name, p.price, p.fragile, p.shelf_days
                      FROM batches b JOIN products p ON p.id=b.product_id WHERE b.qty>0""")
    if not bs:
        return []
    freq_map = pick_freq_by_sku(con)
    adj_map = {r["batch_no"]: r["n"] for r in rows(con, "SELECT batch_no, COUNT(*) AS n FROM txs WHERE kind='ADJ' GROUP BY batch_no")}
    ops_map = {r["batch_no"]: r["n"] for r in rows(con, "SELECT batch_no, COUNT(*) AS n FROM txs GROUP BY batch_no")}

    max_val = max((b["qty"] * b["price"] for b in bs), default=1) or 1
    max_freq = max((freq_map.get(b["product_id"], 0) for b in bs), default=1) or 1
    max_err = max((adj_map.get(b["batch_no"], 0) for b in bs), default=1) or 1
    max_ops = max((ops_map.get(b["batch_no"], 0) for b in bs), default=1) or 1
    abc_map = abc_class_map(con)

    out = []
    for b in bs:
        val = b["qty"] * b["price"]
        left = (date.fromisoformat(b["exp"]) - date.today()).days
        val_n = val / max_val
        freq_n = freq_map.get(b["product_id"], 0) / max_freq
        err_n = adj_map.get(b["batch_no"], 0) / max_err
        exp_n = 1.0 if left <= 7 else (0.7 if left <= 30 else (0.2 if left <= 60 else 0.0))
        frag_n = 1.0 if b["fragile"] else 0.0
        ops_n = ops_map.get(b["batch_no"], 0) / max_ops
        score = round((0.25 * val_n + 0.20 * freq_n + 0.15 * err_n + 0.15 * exp_n + 0.10 * frag_n + 0.15 * ops_n) * 100, 1)
        reasons = []
        if b["q_status"] != "ok":
            score = min(100.0, score + 20)
            reasons.append(f"Trạng thái {b['q_status']}")
        if left <= 30:
            reasons.append(f"Hết/cận hạn ({left} ngày)")
        if adj_map.get(b["batch_no"], 0):
            reasons.append(f"Từng điều chỉnh {adj_map[b['batch_no']]} lần")
        if val_n >= 0.6:
            reasons.append("Giá trị tồn cao")
        if b["fragile"]:
            reasons.append("Hàng dễ vỡ/móp")
        if not reasons:
            reasons.append("Kiểm kê định kỳ ABC")
        out.append({
            "batch_id": b["id"], "sku": b["sku"], "name": b["name"], "batch_no": b["batch_no"],
            "zone": b["zone"], "bin": b["bin"], "loc": f"{b['zone']}-{b['bin']:02d}",
            "qty": b["qty"], "value": val, "left_days": left, "q_status": b["q_status"],
            "locked": bool(b["locked"]), "abc": abc_map.get(b["product_id"], {"abc": "C"})["abc"],
            "risk_score": score, "reasons": "; ".join(reasons),
        })
    out.sort(key=lambda x: -x["risk_score"])
    return out


def rca_analyze(con, batch_row, variance, val_diff):
    """Chạy luật RCA cho FMCG và xác định cấp phê duyệt theo giá trị chênh lệch."""
    hints = []
    if variance == 0:
        return "Khớp tồn kho hệ thống", "Tự động ghi nhận"
    # Kiểm tra trùng giao dịch cùng ngày / số lượng
    dups = con.execute(
        """SELECT COUNT(*) FROM txs WHERE batch_no=? AND ABS(qty)=?""",
        (batch_row["batch_no"], abs(variance)),
    ).fetchone()[0]
    if dups:
        hints.append("Nghi nhập/xuất trùng giao dịch khớp đúng số lượng chênh lệch")
    if abs(variance) % 12 == 0 or abs(variance) % 24 == 0:
        hints.append("Nghi nhầm đơn vị quy đổi (thùng / lốc / hộp)")
    adjs = con.execute("SELECT COUNT(*) FROM txs WHERE batch_no=? AND kind='ADJ'", (batch_row["batch_no"],)).fetchone()[0]
    if adjs:
        hints.append("Lô từng có điều chỉnh tồn trước đó — cần kiểm tra lại chứng từ")
    left = (date.fromisoformat(batch_row["exp"]) - date.today()).days
    if left < 0 or batch_row["q_status"] != "ok":
        hints.append("Hàng hết hạn/cách ly chưa ghi nhận hủy hoặc xuất tách")
    if variance < 0 and batch_row["fragile"]:
        hints.append("Hàng dễ vỡ/móp — nghi hư hỏng trong thao tác chưa lập biên bản")
    in_tr = con.execute("SELECT COUNT(*) FROM transfers WHERE batch_id=? AND status='in_transit'", (batch_row["id"],)).fetchone()[0]
    if in_tr:
        hints.append("Có lệnh điều chuyển đang vận chuyển chưa xác nhận nhập đích")
    if not hints:
        hints.append("Nghi nhặt nhầm lô cùng SKU hoặc đếm nhầm — cần đối chiếu phiếu soạn gần nhất")

    # Phân quyền duyệt điều chỉnh theo File 3 trang 10
    abs_val = abs(val_diff)
    if batch_row["q_status"] != "ok" or left < 0:
        lvl = "Bộ phận chất lượng (QC)"
    elif abs(variance) <= 1 and abs_val < 500000:
        lvl = "Tự động ghi nhận (trong dung sai)"
    elif abs_val < 5000000:
        lvl = "Trưởng ca / Thủ kho"
    else:
        lvl = "Quản lý kho + Kế toán"
    return "; ".join(hints), lvl


# ---------- CV4: Gợi ý lộ trình lấy hàng (S-shape, nặng trước dễ vỡ sau, lạnh lấy cuối) ----------
def picking_route_suggest(con):
    """Đề xuất lộ trình lấy hàng cho các đơn mới/đã soạn: tách chặng theo khu, hàng lạnh lấy cuối."""
    zone_order = {"DRY": 1, "COS": 2, "CHL": 3, "FRZ": 4}
    zs = {z["code"]: z for z in rows(con, "SELECT * FROM zones")}
    stops = []
    # Lấy các lô đã chọn của đơn picked và lô FEFO dự kiến của đơn new
    for r in rows(con, """SELECT s.so_no, s.customer, s.status, p.sku, p.name, p.weight_kg, p.fragile,
                                 k.qty, b.batch_no, b.zone, b.bin, b.exp
                          FROM sos s JOIN picks k ON k.so_id=s.id
                          JOIN batches b ON b.id=k.batch_id JOIN products p ON p.id=s.product_id
                          WHERE s.status='picked'"""):
        rack_ch, bay, lvl = bin_coords(r["bin"], zs[r["zone"]])
        stops.append({
            "so_no": r["so_no"], "customer": r["customer"], "sku": r["sku"], "name": r["name"],
            "batch_no": r["batch_no"], "qty": r["qty"], "zone": r["zone"], "bin": r["bin"],
            "loc": f"{r['zone']}-{r['bin']:02d}", "spot": f"Dãy {rack_ch} · Ô {bay} · Tầng {lvl}",
            "phase": "Chặng lạnh (lấy cuối)" if r["zone"] in ("CHL", "FRZ") else "Chặng khô (lấy trước)",
            "_ord": (zone_order.get(r["zone"], 9), 1 if r["fragile"] else 0, -r["weight_kg"], ord(rack_ch), bay if (ord(rack_ch) % 2 == 1) else -bay),
        })
    stops.sort(key=lambda x: x["_ord"])
    for idx, s in enumerate(stops, 1):
        s["step"] = idx
        del s["_ord"]
    return stops


# ---------- CV5: Hàng chậm luân chuyển (SLOB), FSN, ABC-XYZ, Expiry Risk & Tồn dư thừa ----------
def slob_analysis(con):
    """Phân tích FSN, ABC-XYZ, DIO, nguy cơ hết hạn trước khi bán hết và đề xuất xử lý theo giá trị thu hồi ròng."""
    rep = {x["product_id"]: x for x in demand_and_replenishment(con)}
    bs = rows(con, """SELECT b.*, p.sku, p.name, p.price, p.storage, p.shelf_days
                      FROM batches b JOIN products p ON p.id=b.product_id
                      WHERE b.qty>0 AND b.q_status='ok' ORDER BY b.product_id, b.exp""")
    by_sku = defaultdict(list)
    for b in bs:
        by_sku[b["product_id"]].append(b)

    sku_rows, expiry_risks = [], []
    for pid, r in rep.items():
        d_day = max(0.5, r["forecast_day"])
        av = r["av"]
        dio = round(av / d_day, 1) if d_day > 0 else 999.0
        turnover = round(365.0 / dio, 1) if dio > 0 else 0.0
        # FSN (ngưỡng ngắn cho FMCG)
        fsn = "Fast (Nhanh)" if dio <= 14 else ("Slow (Chậm)" if dio <= 45 else "Non-moving (Đứng)")
        xyz = "X" if r["cv2"] < 0.25 else ("Y" if r["cv2"] < 0.65 else "Z")
        abc_xyz = f"{r['abc']}{xyz}"

        # Tồn mục tiêu = nhu cầu * cover mục tiêu (21 ngày khô / 10 ngày lạnh) + SS
        cov_days = 10 if r["storage"] in ("chilled", "frozen") else 21
        target = int(round(d_day * cov_days + r["safety"]))
        excess = max(0, av - target)
        p_row = con.execute("SELECT price, shelf_days FROM products WHERE id=?", (pid,)).fetchone()
        price = p_row["price"] if p_row else 0
        excess_val = excess * price

        # Phân tích Expiry Risk theo thứ tự FEFO từng lô
        cum = 0
        high_exp_risk = False
        for b in by_sku.get(pid, []):
            left = (date.fromisoformat(b["exp"]) - date.today()).days
            cum += b["qty"]
            sellout_days = round(cum / d_day, 1)
            at_risk = left < 0 or sellout_days > max(0, left - 3)
            if at_risk:
                high_exp_risk = True
                lot_val = b["qty"] * price
                # Giá trị thu hồi ròng ước tính cho phương án khuyến mãi ưu tiên xuất (thu 75% - chi phí xử lý 5%)
                net_promo = int(lot_val * 0.70) if left >= 0 else 0
                expiry_risks.append({
                    "batch_id": b["id"], "sku": b["sku"], "name": b["name"], "batch_no": b["batch_no"],
                    "loc": f"{b['zone']}-{b['bin']:02d}", "qty": b["qty"], "exp": b["exp"],
                    "left_days": left, "sellout_days": sellout_days,
                    "shelf_pct": shelf_pct(b["exp"], b["shelf_days"]),
                    "lot_val": lot_val, "net_promo": net_promo,
                    "action": "Hủy lô & lập biên bản QC" if left < 0 else "Ưu tiên đẩy kênh tạp hóa / khuyến mãi 20–30%",
                })

        is_slob = fsn != "Fast (Nhanh)" or excess > 0 or high_exp_risk
        if excess > 0:
            opt = f"Dừng nhập bổ sung & đẩy khuyến mãi xả {excess} thùng (thu hồi ròng ~{int(excess_val * 0.75):,} đ)"
        elif high_exp_risk:
            opt = "Ưu tiên xuất FEFO cho kênh tạp hóa (chuẩn HSD 40%)"
        elif fsn != "Fast (Nhanh)":
            opt = "Rà soát danh mục / giảm tồn định mức"
        else:
            opt = "Luân chuyển tốt — giữ định mức hiện tại"

        sku_rows.append({
            "product_id": pid, "sku": r["sku"], "name": r["name"], "storage": r["storage"],
            "av": av, "forecast_day": d_day, "dio": dio, "turnover": turnover,
            "fsn": fsn, "abc_xyz": abc_xyz, "target": target,
            "excess": excess, "excess_val": excess_val,
            "is_slob": is_slob, "recommendation": opt,
        })

    sku_rows.sort(key=lambda x: (-x["excess_val"], -x["dio"]))
    expiry_risks.sort(key=lambda x: x["left_days"])
    return {"skus": sku_rows, "expiry_risks": expiry_risks}
