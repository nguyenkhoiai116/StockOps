// ===== CHART: biểu đồ nhập / xuất theo ngày (đường, cột, bảng) =====
import { num, table } from "./core.js";

const NS = "http://www.w3.org/2000/svg";
const SER = [["inb", "s1", "Nhập"], ["out", "s2", "Xuất"]];   // [khóa số liệu, lớp màu, tên]
const H = 300, TOP = 16, BOT = 32, RIGHT = 12;

// Chọn bước chia trục dọc cho tròn số (1, 2, 5 x 10^n), khoảng 4 vạch
function tick(max) {
  const raw = Math.max(max, 1) / 4, p = 10 ** Math.floor(Math.log10(raw));
  return Math.max(1, [1, 2, 5, 10].find((k) => k * p >= raw) * p);
}

// Tạo phần tử SVG kèm thuộc tính
function el(tag, at, text) {
  const n = document.createElementNS(NS, tag);
  for (const k in at) n.setAttribute(k, at[k]);
  if (text != null) n.textContent = text;
  return n;
}

// Vẽ biểu đồ vào box, tự vẽ lại khi đổi bề rộng. Trả về hàm dọn dẹp.
export function flowChart(box, flow, mode) {
  if (mode === "table") {
    box.innerHTML = table(["Ngày", "Nhập*", "Xuất*"], flow.map((f) =>
      `<tr><td>${f.day}</td><td class="r">${num(f.inb)}</td><td class="r">${num(f.out)}</td></tr>`).join(""));
    return () => {};
  }
  let W = 0;
  const draw = () => {
    W = Math.round(box.clientWidth);
    if (W) paint(box, flow, mode, W);
  };
  const ro = new ResizeObserver(() => { if (Math.round(box.clientWidth) !== W) draw(); });
  draw();
  ro.observe(box);
  return () => ro.disconnect();
}

function paint(box, flow, mode, W) {
  const n = flow.length, max = Math.max(...flow.map((f) => Math.max(f.inb, f.out)));
  const st = tick(max), top = Math.max(st, Math.ceil(max / st) * st);
  const left = num(top).length * 7.5 + 16, step = (W - left - RIGHT) / n, base = H - BOT;
  const x = (i) => left + step * (i + 0.5), y = (v) => base - (base - TOP) * (v / top);

  const svg = el("svg", { viewBox: `0 0 ${W} ${H}`, role: "img", tabindex: 0,
    "aria-label": `Nhập và xuất ${n} ngày. Dùng phím mũi tên trái, phải để xem từng ngày` });
  const mark = svg.appendChild(el("rect", { class: "band", y: TOP, height: base - TOP, width: step, visibility: "hidden" }));

  // Lưới ngang, trục, nhãn (bớt nhãn ngày khi quá dày)
  for (let v = 0; v <= top; v += st) {
    svg.append(el("line", { class: v ? "gl" : "ax", x1: left, x2: W - RIGHT, y1: y(v), y2: y(v) }),
      el("text", { x: left - 8, y: y(v) + 4, "text-anchor": "end" }, num(v)));
  }
  const skip = Math.ceil(52 / step);
  flow.forEach((f, i) => { if ((n - 1 - i) % skip === 0) svg.append(el("text", { x: x(i), y: H - 8, "text-anchor": "middle" }, f.day)); });

  const guide = el("line", { class: "guide", y1: TOP, y2: base, visibility: "hidden" });
  if (mode === "line") {
    svg.append(guide);
    for (const [k, c] of SER) svg.append(el("polyline", { class: "ln " + c, points: flow.map((f, i) => `${x(i)},${y(f[k])}`).join(" ") }));
    if (n <= 14) for (const [k, c] of SER) flow.forEach((f, i) => svg.append(el("circle", { class: "dot " + c, cx: x(i), cy: y(f[k]), r: 4 })));
  } else {
    const w = Math.min(24, (step - 6) / 2);   // 2 cột cách nhau 2px
    SER.forEach(([k, c], s) => flow.forEach((f, i) => {
      const h = base - y(f[k]), r = Math.min(4, w / 2, h), bx = x(i) + (s ? 1 : -w - 1);
      if (h > 0) svg.append(el("path", { class: "bar " + c, d: `M${bx},${base}v${r - h}q0,${-r} ${r},${-r}h${w - 2 * r}q${r},0 ${r},${r}v${h - r}z` }));
    }));
  }

  // Ô số liệu khi rê chuột / dùng phím mũi tên
  const tip = document.createElement("div");
  tip.className = "tip"; tip.hidden = true;
  let at = -1;
  const show = (i) => {
    at = i;
    const off = i < 0;
    tip.hidden = off;
    guide.setAttribute("visibility", off ? "hidden" : "visible");
    mark.setAttribute("visibility", off || mode === "line" ? "hidden" : "visible");
    if (off) return;
    guide.setAttribute("x1", x(i)); guide.setAttribute("x2", x(i));
    mark.setAttribute("x", x(i) - step / 2);
    tip.innerHTML = `${flow[i].day}${SER.map(([k, c, t]) => `<div><i class="${k}"></i>${t}<b>${num(flow[i][k])}</b></div>`).join("")}`;
    const tw = tip.offsetWidth;
    tip.style.left = (x(i) + 12 + tw > W ? x(i) - 12 - tw : x(i) + 12) + "px";
  };
  svg.addEventListener("pointermove", (e) => {
    const i = Math.floor((e.clientX - svg.getBoundingClientRect().left - left) / step);
    show(i >= 0 && i < n ? i : -1);
  });
  svg.addEventListener("pointerleave", () => show(-1));
  svg.addEventListener("blur", () => show(-1));
  svg.addEventListener("keydown", (e) => {
    const d = { ArrowLeft: -1, ArrowRight: 1 }[e.key];
    if (!d) return;
    e.preventDefault();
    show(at < 0 ? n - 1 : Math.min(n - 1, Math.max(0, at + d)));
  });
  box.replaceChildren(svg, tip);
}
