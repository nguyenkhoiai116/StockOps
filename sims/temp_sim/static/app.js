const $ = (s) => document.querySelector(s);

let apiConfigLoaded = false;

async function post(url, body) {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body || {}),
  });
  return res.json();
}

function drawSpark(z) {
  const pts = z.history || [];
  const w = 320, h = 68, pad = 6;
  if (pts.length < 2) return `<svg class="spark" viewBox="0 0 ${w} ${h}"></svg>`;

  const temps = pts.map((p) => p.temp);
  const lo = Math.min(z.tmin - 2, ...temps);
  const hi = Math.max(z.tmax + 2, ...temps);
  const span = Math.max(1, hi - lo);
  const yOf = (v) => pad + ((hi - v) / span) * (h - pad * 2);
  const xOf = (i) => pad + (i / (pts.length - 1)) * (w - pad * 2);

  const yMax = yOf(z.tmax);
  const yMin = yOf(z.tmin);
  const poly = pts.map((p, i) => `${xOf(i).toFixed(1)},${yOf(p.temp).toFixed(1)}`).join(" ");
  const color = z.status === "critical" ? "#ef4444" : z.status === "warn" ? "#f59e0b" : "#38bdf8";

  return `
    <svg class="spark" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none">
      <rect x="0" y="${Math.min(yMax, yMin)}" width="${w}" height="${Math.abs(yMin - yMax)}" fill="rgba(34,197,94,0.08)" />
      <line x1="0" y1="${yMax}" x2="${w}" y2="${yMax}" stroke="rgba(239,68,68,0.45)" stroke-dasharray="3,3" />
      <line x1="0" y1="${yMin}" x2="${w}" y2="${yMin}" stroke="rgba(56,189,248,0.45)" stroke-dasharray="3,3" />
      <polyline fill="none" stroke="${color}" stroke-width="2" points="${poly}" />
    </svg>`;
}

function statusText(st) {
  if (st === "critical") return "Vượt ngưỡng";
  if (st === "warn") return "Cảnh báo sớm";
  return "Ổn định";
}

function renderZone(z) {
  const rateStr = `${z.rate_c_per_min >= 0 ? "+" : ""}${z.rate_c_per_min.toFixed(3)} °C/phút`;
  let etaStr = "Xu hướng ổn định";
  if (z.status === "critical") {
    etaStr = `Đã vượt ngưỡng (${z.breach_dir === "high" ? "quá nóng" : "quá lạnh"})`;
  } else if (z.eta_breach_min !== null) {
    etaStr = `Dự báo vượt ngưỡng sau ~<strong>${z.eta_breach_min} phút</strong>`;
  }

  const doorTxt = z.door_open_sec > 0 ? `Đóng cửa (${Math.ceil(z.door_open_sec)}s)` : "Mở cửa kho";
  const compTxt = z.compressor_fault ? "Sửa máy nén" : "Hỏng máy nén";
  const defTxt = z.defrost_sec > 0 ? `Tắt xả đá (${Math.ceil(z.defrost_sec)}s)` : "Xả đá";

  return `
    <article class="zone-card ${z.status}">
      <div class="zone-head">
        <div>
          <div class="zone-title">${z.code} · ${z.name}</div>
          <div class="sensor-id">${z.sensor_id}</div>
        </div>
        <span class="badge ${z.status}">${statusText(z.status)}</span>
      </div>
      <div class="metrics">
        <div class="temp-val">${z.temp.toFixed(2)}°C</div>
        <div class="hum-val">${z.hum.toFixed(1)}% RH</div>
      </div>
      <div class="range-info">
        <span>Ngưỡng: ${z.tmin}°C .. ${z.tmax}°C</span>
        <span>Mục tiêu: ${z.setpoint}°C</span>
      </div>
      ${drawSpark(z)}
      <div class="edge-box">
        <div>Edge AIoT: <strong>${rateStr}</strong> · ${etaStr}</div>
      </div>
      <div class="zone-actions">
        <button class="btn ${z.door_open_sec > 0 ? "warn active" : ""}" data-act="door_open" data-zone="${z.code}" data-active="${z.door_open_sec <= 0}">${doorTxt}</button>
        <button class="btn ${z.compressor_fault ? "warn active" : ""}" data-act="compressor_fault" data-zone="${z.code}" data-active="${!z.compressor_fault}">${compTxt}</button>
        ${(z.code === "CHL" || z.code === "FRZ") ? `<button class="btn ${z.defrost_sec > 0 ? "warn active" : ""}" data-act="defrost" data-zone="${z.code}" data-active="${z.defrost_sec <= 0}">${defTxt}</button>` : ""}
      </div>
    </article>`;
}

function render(data) {
  const { clock, warehouse, ingest } = data;
  $("#sim-time").textContent = clock.sim_time.replace("T", " ");
  $("#btn-pause").textContent = clock.paused ? "Tiếp tục" : "Tạm dừng";
  document.querySelectorAll("#speed-group .speed").forEach((b) => {
    b.classList.toggle("active", Number(b.dataset.speed) === clock.speed);
  });

  const btnPow = $("#btn-power");
  btnPow.classList.toggle("active", warehouse.power_outage);
  btnPow.textContent = warehouse.power_outage ? "Khôi phục điện" : "Mất điện toàn kho";

  $("#lbl-amb-t").textContent = `${warehouse.ambient.base_temp.toFixed(1)}°C`;
  $("#lbl-diu-t").textContent = warehouse.ambient.diurnal_temp.toFixed(1);
  $("#lbl-amb-h").textContent = `${warehouse.ambient.base_hum.toFixed(0)}%`;
  $("#lbl-diu-h").textContent = warehouse.ambient.diurnal_hum.toFixed(0);

  $("#zones-grid").innerHTML = warehouse.zones.map(renderZone).join("");

  if (!apiConfigLoaded) {
    $("#inp-url").value = ingest.target_url.replace(/\/api\/ingest\/sensor$/, "");
    $("#chk-push").checked = ingest.enabled;
    apiConfigLoaded = true;
  }

  const badge = $("#api-badge");
  if (!ingest.enabled) {
    badge.className = "badge";
    badge.textContent = "Đang tắt đẩy tự động";
  } else if (ingest.last_error) {
    badge.className = "badge warn";
    badge.textContent = `Lỗi kết nối (${ingest.last_status || "offline"})`;
  } else {
    badge.className = "badge ok";
    badge.textContent = "Đang đẩy dữ liệu";
  }

  $("#api-stats").textContent =
    `Đã gửi: ${ingest.sent_batches} lô (${ingest.sent_records} bản ghi) · Lỗi: ${ingest.failed_batches}` +
    (ingest.last_error ? ` · Lỗi gần nhất: ${ingest.last_error}` : "");
  $("#payload-preview").textContent = JSON.stringify(ingest.last_payload || {}, null, 2);
}

async function refresh() {
  try {
    const res = await fetch("/api/sim/state");
    if (res.ok) render(await res.json());
  } catch (_) {}
}

$("#btn-pause").onclick = async () => {
  const paused = $("#btn-pause").textContent === "Tạm dừng";
  await post("/api/sim/clock", { paused });
  refresh();
};

$("#speed-group").onclick = async (e) => {
  const btn = e.target.closest(".speed");
  if (!btn) return;
  await post("/api/sim/clock", { speed: Number(btn.dataset.speed) });
  refresh();
};

$("#btn-reset").onclick = async () => {
  await post("/api/sim/clock", { reset: true });
  refresh();
};

$("#btn-power").onclick = async () => {
  const active = !$("#btn-power").classList.contains("active");
  await post("/api/sim/event", { event: "power_outage", active });
  refresh();
};

$("#rng-amb-t").onchange = async (e) => {
  await post("/api/sim/ambient", { temp: Number(e.target.value) });
  refresh();
};

$("#rng-amb-h").onchange = async (e) => {
  await post("/api/sim/ambient", { hum: Number(e.target.value) });
  refresh();
};

$("#zones-grid").onclick = async (e) => {
  const btn = e.target.closest("[data-act]");
  if (!btn) return;
  await post("/api/sim/event", {
    event: btn.dataset.act,
    zone: btn.dataset.zone,
    active: btn.dataset.active === "true",
    duration_sec: 240,
  });
  refresh();
};

$("#btn-save-api").onclick = async () => {
  await post("/api/sim/target", {
    base_url: $("#inp-url").value,
    ingest_key: $("#inp-key").value || undefined,
    enabled: $("#chk-push").checked,
  });
  refresh();
};

$("#btn-push-now").onclick = async () => {
  await post("/api/sim/target", {
    base_url: $("#inp-url").value,
    ingest_key: $("#inp-key").value || undefined,
    push_now: true,
  });
  refresh();
};

refresh();
setInterval(refresh, 1000);
