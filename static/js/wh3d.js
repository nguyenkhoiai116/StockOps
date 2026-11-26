// ===== WH3D: kho 3D theo mặt bằng chữ U (90 × 50 m) bằng Three.js =====
// File này chỉ lo phần hình. Dữ liệu và thao tác nằm ở features/layout.js.
// Toạ độ tính bằng mét: gốc ở tâm nhà kho, x tăng sang phải, z âm là phía sau, z dương là mặt trước có cửa.
// Kệ, hàng, đồ trang trí dùng InstancedMesh (mỗi loại 1 mesh) để giữ dưới 150 lượt vẽ mỗi khung hình.
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { slot, num } from "./core.js";

// ---------- Hằng số và mặt bằng ----------
const BAY = 2.7, LEVEL = 1.5, DEEP = 1.1, AISLE = 3;   // ô kệ rộng, mỗi tầng cao, kệ sâu, lối đi giữa các dãy (mét)
const WALL = 1.2, WT = 0.3;                             // tường cắt thấp để nhìn vào trong, bề dày tường
const BG = "#eef1f6", PAD = "#e1e6ee", PICK = "#c3d6fa";   // nền cảnh, sàn khu chứa, sàn khu đang chọn
const FADE = "#e3e7ed", STEEL = "#8f9bad", WOOD = "#b8b4ac";   // khối đã mờ (gần màu nền), kệ, pallet
const LINE = "#f8f9fb", ASPH = "#d9dee6";                       // vạch sơn, mặt đường / bãi
// Biển chữ (nhãn khu, số cửa, cổng) đo bằng mét. Cao 1 dòng = min(khoảng cách camera × LK, LH):
// lại gần thì chữ giữ cỡ gần như cố định trên màn hình, ra xa thì dừng ở LH để biển không tràn khỏi khu.
// Gần hơn NEAR mét thì biển hiện thêm dòng chi tiết (tên đầy đủ, số liệu).
const LH = 3.4, LK = 0.025, NEAR = 60;
const DOORY = 2.5;   // chân biển số cửa: cao hơn nóc xe đỗ ở cửa (3,3 m) để xe không che số cửa
const SANS = '"IBM Plex Sans", "Segoe UI", sans-serif', MONO = '"IBM Plex Mono", Consolas, monospace';

// SITE: toạ độ các khu (ước lượng từ ảnh). r: [x0, x1, z0, z1]. code: khu chứa hàng gắn dữ liệu.
// t: tên ngắn hiện khi nhìn xa; long / sub: dòng chi tiết khi lại gần (khu chứa ghi thêm số liệu).
// at: chân biển [x, z, y]; đặt trên phần sàn trống, không đè lên kệ. w: bề rộng biển tối đa (m), giữ biển các khu không chồng nhau.
export const SITE = {
  land: [-70, 70, -32, 54],    // khuôn viên (nền ngoài cùng)
  fence: [-68, 68, -30, 50],   // hàng rào
  hall: [-45, 45, -25, 25],    // nhà kho
  view: [-68, 68, -27, 53],    // vùng camera canh khi xem toàn kho
  zones: [
    { no: "2", t: "Mát", long: "Kho mát", code: "CHL", r: [-45, -32.5, -25, -5], at: [-38.75, -4.3], w: 11, pad: "#dde6f1" },
    { no: "2", t: "Đông", long: "Kho đông", code: "FRZ", r: [-32.5, -20, -25, -5], at: [-26.25, -4.3], w: 11, pad: "#dde6f1" },
    { no: "3", t: "TP & đồ uống", long: "Hàng khô", code: "DRY", r: [-18, 12, -25, -5], at: [-6, -1.2], w: 22 },
    { no: "4", t: "Hoá mỹ phẩm", long: "Hàng khô", code: "COS", r: [14, 45, -25, -8], at: [24, -5.2], w: 19 },
    { no: "7", t: "Xe nâng", sub: "Đậu & sạc xe nâng", r: [34, 45, -8, 2], at: [38, 1.5], w: 15, pad: "#ebe7da" },
    { no: "8", t: "Hàng lỗi", sub: "Trả về (Quarantine) & văn phòng", r: [-45, -30, -5, 25], at: [-37.5, 13.5], w: 13, pad: "#f0e4e4" },
    { no: "1B", t: "Tập kết", sub: "Chờ lên kệ, đỗ xe nâng nhập hàng", r: [-30, -18, -5, 25], at: [-24, 15.5], w: 12, pad: "#e6e9ef" },
    { no: "5", t: "Soạn hàng", sub: "Soạn hàng lẻ & đóng gói", r: [-16, 12, -3, 25], at: [2, 23.5], w: 18, pad: "#e6e9ef" },
    { no: "6", t: "Xuất hàng", sub: "Xuất hàng & tập kết đơn", r: [14, 45, 2, 25], at: [29.5, 7.6], w: 18, pad: "#e6e9ef" },
    { no: "1A", t: "Kiểm đếm", sub: "Kiểm đếm & đối chiếu số lượng", r: [-30, -8, 25, 33], at: [-19, 36.4], w: 18, pad: "#e4e9f1" },
    { no: "9", t: "Bãi xe tải", sub: "Bãi chờ & đậu xe tải / container", r: [-5, 45, 27, 45], at: [5, 32], w: 20, pad: ASPH },
    { no: "10", t: "Xe nhân viên", sub: "Bãi đỗ xe máy & ô tô nhân viên", r: [-62, -32, 27, 45], at: [-47, 37.5], w: 26, pad: ASPH },
  ],
  // Cửa trên tường trước (z = 25): N1–N4 nhập, X1–X4 xuất
  doors: [["N1", -27.25], ["N2", -21.75], ["N3", -16.25], ["N4", -10.75], ["X1", 21], ["X2", 27], ["X3", 33], ["X4", 39]],
  gates: [["Xe vào nhập hàng", -20], ["Xe vào xuất hàng", 30]],   // cổng vào trên hàng rào trước (z = 50)
  exits: [["Xe nhập hàng đi ra", -68], ["Xe xuất hàng đi ra", 68]], // lối ra ở 2 bên hàng rào, ngang đường trước
  road: [46, 49.6],                                                 // đường chạy ngang trước bãi (z0, z1)
  tables: [-12, -5, 2, 9].flatMap((x) => [[x, 3], [x, 10]]),        // bàn soạn ở khu 5
  lanes: { x0: 16, x1: 44, z0: 8, z1: 22, n: 8 },                   // làn tập kết ở khu 6
  yard: [-1.75, 2.75, 7.25, 11.75, 16.25],                          // tâm các ô đỗ xe tải bãi 9 (trái -> phải), không chắn cửa X
  qa: { board: [-34.5, 2], xs: [-43, -41, -39, -37], zs: [7.5, 5.5, 3.5, 1.5, -0.5] },   // khu 8: bảng số liệu, lưới pallet đỏ
};

// ---------- Hình khối và nhãn ----------
// Bộ gom khối: mỗi loại (kind) cuối cùng thành 1 InstancedMesh. Khối nào cũng là hình đơn vị được co giãn.
function kit() {
  const L = {}, Q = new THREE.Quaternion();
  let o = new THREE.Matrix4();
  return {
    // Đặt gốc cho các khối tiếp theo: vị trí (x, z) và góc xoay quanh trục đứng
    at(x = 0, z = 0, ry = 0) { o = new THREE.Matrix4().makeRotationY(ry).setPosition(x, 0, z); },
    // Số khối đã thêm của 1 loại (để biết khối nào thuộc đối tượng nào)
    n(kind) { return L[kind]?.length ?? 0; },
    // Thêm 1 khối: tâm (x, y, z) tính theo gốc, cỡ w × h × d, màu c. Trả về số thứ tự trong loại
    box(kind, x, y, z, w, h, d, c) {
      const m = new THREE.Matrix4().compose(new THREE.Vector3(x, y, z), Q, new THREE.Vector3(w, h, d)).premultiply(o);
      return (L[kind] ??= []).push([m, new THREE.Color(c)]) - 1;
    },
    // Gộp mỗi loại thành 1 InstancedMesh (màu từng khối qua setColorAt)
    build(geo, mat) {
      return Object.fromEntries(Object.entries(L).map(([k, a]) => {
        const im = new THREE.InstancedMesh(geo[k], mat, a.length);
        a.forEach(([m, c], i) => { im.setMatrixAt(i, m); im.setColorAt(i, c); });
        im.computeBoundingSphere();
        im.receiveShadow = true;
        return [k, im];
      }));
    },
  };
}

// Vạch / sàn phẳng từ x0..x1, z0..z1, mặt trên ở độ cao y
const flat = (K, kind, [x0, x1, z0, z1], y, c) => K.box(kind, (x0 + x1) / 2, y - 0.01, (z0 + z1) / 2, x1 - x0, 0.02, z1 - z0, c);
// Tường thẳng dọc trục x (tại z) hoặc dọc trục z (tại x)
const wallX = (K, x0, x1, z, c, h = WALL) => K.box("wall", (x0 + x1) / 2, h / 2, z, x1 - x0, h, WT, c);
const wallZ = (K, z0, z1, x, c, h = WALL) => K.box("wall", x, h / 2, (z0 + z1) / 2, WT, h, z1 - z0, c);

// Chữ vẽ lên canvas -> texture
function tex(c) { const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; return t; }

// Vẽ các dòng chữ lên canvas: dòng 1 đậm, dòng 2 nhỏ (mono: số liệu). dark: nền xám đậm chữ trắng (số cửa).
// Trả về {map, a: rộng / cao, k: cao gấp mấy lần biển 1 dòng}
function card(lines, { mono, dark } = {}) {
  const c = document.createElement("canvas"), x = c.getContext("2d");
  const F = ["600 52px " + SANS, "400 40px " + (mono ? MONO : SANS)];
  const w = Math.ceil(Math.max(...lines.map((t, i) => { x.font = F[i]; return x.measureText(t).width; }))) + 40, h = 18 + lines.length * 52;
  c.width = w; c.height = h;   // đổi cỡ canvas thì mất font, đặt lại bên dưới
  x.fillStyle = x.strokeStyle = dark ? "#5b6676" : "#ffffff"; x.lineWidth = 4;
  if (!dark) x.strokeStyle = "#c9cfd8";
  x.beginPath(); x.roundRect(2, 2, w - 4, h - 4, 14); x.fill(); x.stroke();
  x.textAlign = "center"; x.textBaseline = "middle";
  lines.forEach((t, i) => { x.font = F[i]; x.fillStyle = dark ? "#ffffff" : i ? "#4d4d52" : "#171717"; x.fillText(t, w / 2, 37 + i * 52); });
  return { map: tex(c), a: w / h, k: h / 70 };
}

// Biển đứng quay về người xem, chân đặt tại at = [x, z, y]. far: chữ khi nhìn xa; near: chữ khi lại gần (có thể không có).
// far = null: biển chỉ hiện khi lại gần (biển số xe), nhìn xa thì ẩn cho đỡ rối.
// Cỡ biển chỉnh mỗi lần vẽ (xem LH, LK), không bao giờ rộng quá w mét. Có kiểm độ sâu nên không đè lên kệ đứng trước nó.
function sign(far, near, [x, z, y = 0.2], w) {
  const s = new THREE.Sprite(new THREE.SpriteMaterial({ map: (far || near).map }));
  s.center.set(0.5, 0); s.position.set(x, y, z);
  return { s, far, near, w };
}

// Chữ dãy kệ (A, B, C…) trong vòng tròn, cỡ theo mét
function tag(ch) {
  const c = document.createElement("canvas"), x = c.getContext("2d");
  c.width = c.height = 128;
  x.fillStyle = "#ffffff"; x.strokeStyle = STEEL; x.lineWidth = 8;
  x.beginPath(); x.arc(64, 64, 56, 0, Math.PI * 2); x.fill(); x.stroke();
  x.fillStyle = "#171717"; x.font = '600 72px "IBM Plex Sans", "Segoe UI", sans-serif';
  x.textAlign = "center"; x.textBaseline = "middle"; x.fillText(ch, 64, 68);
  const s = new THREE.Sprite(new THREE.SpriteMaterial({ map: tex(c) }));
  s.scale.set(1.3, 1.3, 1);
  return s;
}

// Cửa kho có số ghi trên mặt tường trước
function door(no) {
  const c = document.createElement("canvas"), x = c.getContext("2d");
  c.width = 256; c.height = 80;
  x.fillStyle = "#5b6676"; x.fillRect(0, 0, 256, 80);
  x.fillStyle = "#ffffff"; x.font = '600 52px "IBM Plex Sans", "Segoe UI", sans-serif';
  x.textAlign = "center"; x.textBaseline = "middle"; x.fillText(no, 128, 43);
  return new THREE.Mesh(new THREE.PlaneGeometry(3.4, 1.06), new THREE.MeshBasicMaterial({ map: tex(c) }));
}

// ---------- Đồ trang trí (gộp vào các loại prop / wheel) ----------
const GREY = "#6b7380", TIRE = "#3d434c";
// Xe nâng: đầu càng hướng về -z khi ry = 0
function lift(K, x, z, ry = 0) {
  K.at(x, z, ry);
  K.box("prop", 0, 0.65, 0.35, 1.1, 0.9, 1.7, "#e3bc66");            // thân
  K.box("prop", 0, 1.2, 0.9, 0.9, 0.35, 0.5, "#d4ab52");             // đối trọng
  for (const dx of [-0.48, 0.48]) for (const dz of [-0.2, 0.95]) K.box("prop", dx, 1.5, dz, 0.06, 0.9, 0.06, GREY);   // khung mái
  K.box("prop", 0, 1.95, 0.38, 1.0, 0.05, 1.25, GREY);               // mái che
  K.box("prop", 0, 1.15, -0.6, 0.9, 2.1, 0.1, GREY);                 // cột nâng
  for (const dx of [-0.3, 0.3]) K.box("prop", dx, 0.08, -1.2, 0.12, 0.06, 1.1, GREY);   // càng
  for (const dx of [-0.5, 0.5]) for (const dz of [-0.25, 0.8]) K.box("wheel", dx, 0.25, dz, 0.22, 0.5, 0.5, TIRE);
}
// Ô tô con: đầu xe hướng về -z khi ry = 0
function car(K, x, z, ry, c) {
  K.at(x, z, ry);
  K.box("prop", 0, 0.55, 0, 1.8, 0.6, 4.2, c);
  K.box("prop", 0, 1.1, 0.25, 1.6, 0.5, 2.2, "#dfe4ec");             // cabin
  for (const dx of [-0.85, 0.85]) for (const dz of [-1.35, 1.35]) K.box("wheel", dx, 0.33, dz, 0.24, 0.66, 0.66, TIRE);
}
// Xe máy
function bike(K, x, z, ry, c) {
  K.at(x, z, ry);
  K.box("prop", 0, 0.55, 0, 0.3, 0.35, 1.3, c);
  K.box("prop", 0, 0.78, 0.15, 0.32, 0.1, 0.6, "#4d545e");           // yên
  K.box("prop", 0, 0.95, -0.55, 0.62, 0.06, 0.06, "#4d545e");        // tay lái
  for (const dz of [-0.62, 0.62]) K.box("wheel", 0, 0.3, dz, 0.1, 0.6, 0.6, TIRE);
}
// Bàn: mặt w × d, cao 0.9 m
function desk(K, x, z, w, d, c = "#d9d2c3") {
  K.at(x, z);
  K.box("prop", 0, 0.88, 0, w, 0.06, d, c);
  for (const sx of [-1, 1]) for (const sz of [-1, 1]) K.box("prop", sx * (w / 2 - 0.08), 0.43, sz * (d / 2 - 0.08), 0.06, 0.86, 0.06, GREY);
}
// Pallet có thùng hàng đặt dưới sàn (hàng chờ lên kệ)
function stack(K, x, z, h) {
  K.at(x, z);
  K.box("prop", 0, 0.07, 0, 1.2, 0.14, 1.0, "#c8bfae");
  K.box("prop", 0, 0.14 + h / 2, 0, 1.1, h, 0.9, "#d8c9a8");
}

// ---------- Luồng hàng (gộp vào các loại box / wheel của bộ gom riêng, dò chuột được) ----------
// Màu thùng xe, đầu kéo: xe nhập (xanh, cùng tông chuỗi Nhập), xe xuất (xanh ngọc, chuỗi Xuất), xe rảnh (xám)
const TRUCK = { in: ["#d6e0f5", "#8ea9e0"], out: ["#cfe9e5", "#7cc2b9"], idle: ["#e2e5ea", "#b3bac5"] };
// Xe tải đầu kéo + thùng: đuôi thùng tại (x, z), thân dài 8,3 m kéo về -z khi ry = 0 (ry = π: lùi vào cửa, đầu quay ra sân)
function truck(P, x, z, ry, [c1, c2]) {
  P.at(x, z, ry);
  P.box("box", 0, 2.05, -3, 2.4, 2.5, 6, c1);              // thùng
  P.box("box", 0, 0.6, -4.15, 1, 0.3, 8.1, GREY);          // khung gầm
  P.box("box", 0, 1.55, -7.25, 2.2, 2.3, 2.1, c2);         // đầu kéo
  P.box("box", 0, 2.15, -8.32, 1.9, 0.75, 0.04, "#5b6676");   // kính lái
  for (const dz of [-0.9, -2.1, -7.6]) for (const dx of [-1.05, 1.05]) P.box("wheel", dx, 0.45, dz, 0.35, 0.9, 0.9, TIRE);
}
// Pallet có hàng (tập kết xuất hoặc hàng lỗi), tâm tại (x, z)
function load(P, x, z, c) {
  P.at(x, z);
  P.box("box", 0, 0.07, 0, 1.2, 0.14, 1.0, "#c8bfae");
  P.box("box", 0, 0.62, 0, 1.1, 0.96, 0.9, c);
}

// Vẽ flow (xem mount) vào bộ gom P. mark(mục, vẽ): mọi khối vẽ trong lúc gọi vẽ() thuộc về mục đó (để dò chuột).
// Trả về các biển chữ cần thêm (biển số xe, "+n chờ cửa", "+n", bảng khu 8)
function flows(P, flow, mark) {
  const out = [], door = Object.fromEntries(SITE.doors), dz = SITE.hall[3] + 1.5;   // đuôi xe sát ụ cửa
  const more = (n, at, w) => out.push(sign(card(["+" + num(n)]), null, at, w));
  // Biển số trên nóc thùng, chỉ hiện khi lại gần. c: tâm nóc thùng [x, z]
  const plate = (x, c) => { if (x.label) out.push(sign(null, card([x.label]), [c[0], c[1], 3.4], 5.2)); };
  // Xe ở cửa N1–N4 (nhập) và X1–X4 (xuất): lùi vào cửa, đầu quay ra sân
  for (const [list, col] of [[flow.inDocks, TRUCK.in], [flow.outDocks, TRUCK.out]]) for (const x of list || []) {
    const dx = door[x.dock];
    if (dx === undefined) continue;
    mark(x, () => truck(P, dx, dz, Math.PI, col));
    plate(x, [dx, dz + 3]);
  }
  // Bãi 9: xe chờ cửa nhập đỗ từ trái; xe xuất chờ cửa rồi xe rảnh đỗ từ phải. yard xếp đúng thứ tự đó
  const Y = SITE.yard, yz = 44.3, yard = flow.yard || [], inW = flow.inWait | 0, outW = flow.outWait | 0, first = {};
  let l = 0, r = Y.length - 1, miss = 0;
  yard.forEach((x, i) => {
    const t = i < inW ? "in" : i < inW + outW ? "out" : "idle";
    if (l > r) { miss++; return; }
    const s = t === "in" ? l++ : r--;
    first[t] ??= Y[s];
    mark(x, () => truck(P, Y[s], yz, 0, TRUCK[t]));
    plate(x, [Y[s], yz - 3]);
  });
  if (inW) out.push(sign(card([`+${num(inW)} chờ cửa`]), null, [first.in ?? Y[0], yz - 3, 5], 6));
  if (outW) out.push(sign(card([`+${num(outW)} chờ cửa`]), null, [first.out ?? Y[Y.length - 1], yz - 3, 5], 6));
  if (miss) more(miss, [(Y[0] + Y[Y.length - 1]) / 2, yz + 1.2], 4);   // bãi hết ô đỗ: ghi số xe không vẽ được
  // Khu 5: mỗi đơn chờ soạn là 1 thùng trên bàn, 3 thùng mỗi bàn, tối đa 12 (bàn hàng trước trước)
  const tp = flow.topick;
  if (tp && tp.n > 0) {
    const T = [...SITE.tables].sort((a, b) => b[1] - a[1] || a[0] - b[0]), k = Math.min(tp.n, 12);
    mark(tp, () => { for (let i = 0; i < k; i++) { const [x, z] = T[Math.floor(i / 3)]; P.at(x, z); P.box("box", (i % 3 - 1) * 0.9, 1.16, 0, 0.6, 0.5, 0.5, "#d9bf8f"); } });
    if (tp.n > 12) more(tp.n - 12, [T[3][0], T[3][1], 1.5], 2.4);
  }
  // Khu 6: mỗi đơn đã soạn là 1 pallet; rải lần lượt qua các làn, từ đầu làn gần cửa X
  const st = flow.staged || [], { x0, x1, z1, n: ln } = SITE.lanes, lw = (x1 - x0) / ln, cap = ln * 8;
  st.slice(0, cap).forEach((x, i) => mark(x, () => load(P, x0 + lw * ((i % ln) + 0.5), z1 - 1 - Math.floor(i / ln) * 1.6, "#cfe3d3")));
  if (st.length > cap) more(st.length - cap, [x1 - lw / 2, z1 + 1.2], 3);
  // Khu 8: bảng số liệu và mỗi PO có hàng hỏng là 1 pallet đỏ
  const qa = flow.qa;
  if (qa) {
    const { board: [bx, bz], xs, zs } = SITE.qa, k = Math.min(qa.pallets | 0, xs.length * zs.length);
    mark(qa, () => {
      P.at(bx, bz);
      P.box("box", 0, 1.8, 0, 3, 1.5, 0.08, "#f6eeee");
      for (const dx of [-1.3, 1.3]) P.box("box", dx, 0.55, 0, 0.08, 1.1, 0.08, GREY);
      for (let i = 0; i < k; i++) load(P, xs[i % xs.length], zs[Math.floor(i / xs.length)], "#e8a5a5");
    });
    out.push(sign(card(qa.label.split(" · ").slice(0, 2)), null, [bx, bz, 2.6], 9));
    if (qa.pallets > k) more(qa.pallets - k, [xs[1], zs[0] + 1.6], 3);
  }
  return out;
}

// Dựng nền, tường, cửa, sân bãi, đường và đồ trang trí. Trả về {chỗ sàn của khu chứa: [số thứ tự, màu]}
function site(K) {
  const pads = {}, [hx0, hx1, hz0, hz1] = SITE.hall, [fx0, fx1, fz0, fz1] = SITE.fence, [r0, r1] = SITE.road;
  K.at();
  // Nền khuôn viên, sân trước, nền nhà kho
  K.box("ground", 0, -0.1, (SITE.land[2] + SITE.land[3]) / 2, SITE.land[1] - SITE.land[0], 0.2, SITE.land[3] - SITE.land[2], "#e9ecf0");
  flat(K, "ground", [fx0, fx1, hz1, r1], 0.01, "#e0e4ea");
  flat(K, "ground", SITE.hall, 0.02, "#f3f5f8");
  // Sàn từng khu
  for (const s of SITE.zones) {
    const [x0, x1, z0, z1] = s.r, c = s.pad || PAD;
    const i = flat(K, "ground", [x0 + 0.3, x1 - 0.3, z0 + 0.3, z1 - 0.3], 0.04, c);
    if (s.code) pads[s.code] = [i, c];
  }
  // Đường trước và làn từ cổng nhập vào sân 1A
  flat(K, "ground", [fx0, fx1, r0, r1], 0.03, "#d3d9e1");
  flat(K, "ground", [-23, -17, 33, r0], 0.03, "#d3d9e1");
  for (let x = fx0 + 2; x < fx1 - 2; x += 6) flat(K, "ground", [x, x + 3, (r0 + r1) / 2 - 0.08, (r0 + r1) / 2 + 0.08], 0.05, LINE);   // vạch giữa đường
  // Vạch sân 1A, đỗ xe bãi 9 và bãi 10
  for (const z of [25.4, 32.6]) flat(K, "ground", [-29.6, -8.4, z - 0.06, z + 0.06], 0.05, LINE);
  for (let x = -4; x <= 44; x += 4.5) if (x < 27 || x > 33) flat(K, "ground", [x - 0.06, x + 0.06, 33, 44.5], 0.05, LINE);
  for (let x = -60.75; x <= -38; x += 3.5) flat(K, "ground", [x - 0.06, x + 0.06, 28.3, 33.8], 0.05, LINE);
  // Ụ cửa ngoài tường trước, cột biển số cửa trên đỉnh tường
  for (const [, x] of SITE.doors) {
    flat(K, "ground", [x - 1.7, x + 1.7, hz1 + WT / 2, hz1 + 1.4], 0.05, "#a3acb9");
    K.box("prop", x, (WALL + DOORY) / 2, hz1 + 0.4, 0.1, DOORY - WALL, 0.1, GREY);
  }

  // Tường bao nhà kho (cắt thấp)
  const W1 = "#c9d0da", W2 = "#d3deeb";
  wallX(K, hx0, hx1, hz0, W1); wallX(K, hx0, hx1, hz1, W1);
  wallZ(K, hz0, hz1, hx0, W1); wallZ(K, hz0, hz1, hx1, W1);
  // Phòng lạnh: tường trước có cửa mỗi phòng, tường phải, vách ngăn giữa mát và đông
  const [cx0, , cz0, cz1] = SITE.zones[0].r, cmid = SITE.zones[0].r[1], cx1 = SITE.zones[1].r[1];
  for (const [a, b] of [[cx0, -40.25], [-37.25, -27.75], [-24.75, cx1]]) wallX(K, a, b, cz1, W2);
  wallZ(K, cz0, cz1, cx1, W2);
  wallZ(K, cz0, cz1, cmid, W2, WALL + 0.3);   // vách ngăn cao hơn chút cho dễ thấy
  // Văn phòng ở khu 8: tường trong và bàn làm việc
  wallX(K, hx0, -36.2, 12, W1); wallX(K, -34.2, -31, 12, W1); wallZ(K, 12, hz1, -31, W1);
  for (const x of [-41, -35.5]) for (const z of [16, 21]) {
    desk(K, x, z, 2.6, 1.2, "#e2ddd2");
    K.at(x, z); K.box("prop", 0, 1.13, -0.3, 0.6, 0.4, 0.05, "#4d545e"); K.box("prop", 0, 0.45, 1.0, 0.5, 0.9, 0.5, "#9aa4b2");   // màn hình, ghế
  }
  K.at();
  // Vạch khu cách ly hàng lỗi (khu 8)
  for (const z of [-4, 10]) flat(K, "ground", [-44, -31, z - 0.08, z + 0.08], 0.06, "#e0a8a8");
  for (const x of [-44, -31]) flat(K, "ground", [x - 0.08, x + 0.08, -4, 10], 0.06, "#e0a8a8");

  // Hàng rào, cổng vào (trước) và lối ra (2 bên)
  const FN = "#b9c1cc", P = "#8f9bad";
  const fx = (a, b, z) => K.box("prop", (a + b) / 2, 0.45, z, b - a, 0.9, 0.12, FN);
  const fz = (a, b, x) => K.box("prop", x, 0.45, (a + b) / 2, 0.12, 0.9, b - a, FN);
  fx(fx0, -24, fz1); fx(-16, 26, fz1); fx(34, fx1, fz1); fx(fx0, fx1, fz0);
  for (const x of [fx0, fx1]) { fz(fz0, r0 - 0.2, x); fz(r1 + 0.2, fz1, x); }
  for (const [, x] of SITE.gates) {
    for (const d of [-4, 4]) K.box("prop", x + d, 0.9, fz1, 0.5, 1.8, 0.5, P);
    K.box("prop", x - 1.8, 1.1, fz1, 3.6, 0.12, 0.12, "#e39b9b");   // thanh chắn mở một nửa
  }
  for (const [, x] of SITE.exits) for (const z of [r0 - 0.2, r1 + 0.2]) K.box("prop", x, 0.9, z, 0.5, 1.8, 0.5, P);

  // Mũi tên luồng xe: vào cổng (đi về -z), ra lối hai bên
  const mid = (r0 + r1) / 2, arrow = (x, z, ry) => { K.at(x, z, ry); K.box("arrow", 0, 0.07, 0, 2.2, 1, 3.6, "#9fb6e8"); };
  arrow(-20, 43, 0); arrow(-20, 37, 0); arrow(30, 42, 0); arrow(30, 35, 0);
  arrow(-36, mid, Math.PI / 2); arrow(-56, mid, Math.PI / 2); arrow(48, mid, -Math.PI / 2); arrow(60, mid, -Math.PI / 2);

  // Khu 1B: pallet chờ lên kệ và chỗ đỗ xe nâng nhập hàng
  [-27.5, -24, -20.5].forEach((x, a) => [-1, 2, 5, 8].forEach((z, b) => stack(K, x, z, 0.6 + ((a + b) % 3) * 0.25)));
  K.at();
  for (const x of [-29, -25.6, -22.2, -18.8]) flat(K, "ground", [x - 0.06, x + 0.06, 16.5, 23], 0.06, "#e6cf8f");
  for (const x of [-27.3, -23.9, -20.5]) lift(K, x, 19.5, Math.PI);
  // Khu 5: bàn soạn và băng chuyền đóng gói
  for (const [x, z] of SITE.tables) desk(K, x, z, 3, 1.4);
  K.at();
  K.box("prop", -2, 0.75, 16, 24, 0.12, 1.0, "#aab3bf");
  for (let x = -13.5; x <= 9.5; x += 4.6) for (const dz of [-0.4, 0.4]) K.box("prop", x, 0.35, 16 + dz, 0.08, 0.7, 0.08, GREY);
  // Khu 6: làn tập kết đơn
  const { x0: lx0, x1: lx1, z0: lz0, z1: lz1, n: ln } = SITE.lanes;
  for (let i = 0; i <= ln; i++) { const x = lx0 + ((lx1 - lx0) * i) / ln; flat(K, "ground", [x - 0.06, x + 0.06, lz0, lz1], 0.06, "#e6cf8f"); }
  for (const z of [lz0, lz1]) flat(K, "ground", [lx0, lx1, z - 0.06, z + 0.06], 0.06, "#e6cf8f");
  lift(K, 42.5, 4.5, -Math.PI / 2);
  // Khu 7: xe nâng đậu sạc, trụ sạc phía sau
  for (const x of [36.2, 39.6, 43]) {
    lift(K, x, -3.4, Math.PI);
    K.at(x, -7.2); K.box("prop", 0, 0.65, 0, 0.7, 1.3, 0.4, "#9aa7b8"); K.box("prop", 0, 1.1, 0.21, 0.3, 0.1, 0.02, "#7fbf9a");
  }
  // Khu 10: ô tô và xe máy nhân viên
  const CAR = ["#c9d3e3", "#e6e8eb", "#b7c4d6", "#d9cfc2", "#c4ccd6", "#dde2e8"];
  CAR.forEach((c, i) => car(K, -59 + i * 3.5, 31, 0, c));
  for (const z of [40, 43]) for (let i = 0; i < 14; i++) bike(K, -60 + i * 1.5, z, 0, CAR[(i + z) % CAR.length]);
  K.at();
  return pads;
}

// ---------- Dựng cảnh ----------
// zones: [{code, name, sub, racks, bays, levels}], loads: [{key, zone, bin, tip}].
// flow (layout.js dựng, phần nào không có thì khu đó chỉ vẽ cảnh):
//   {inDocks: [{dock: "N1", key, label, tip}], inWait, outDocks: [{dock: "X1", key, label, tip}], outWait,
//    yard: [{key, label, tip}] (inWait xe nhập chờ cửa, rồi outWait xe xuất chờ cửa, rồi xe rảnh),
//    topick?: {key, n, tip}, staged?: [{key, tip}], qa?: {key, label, pallets}}
// onPick(key | null) khi bấm vào hàng, đối tượng luồng (key "f:…") hoặc chỗ trống.
// Trả về các hàm điều khiển và outside (số lô nằm ngoài sơ đồ).
export function mount(el, { zones, loads, flow = {} }, onPick) {
  const gl = new THREE.WebGLRenderer({ antialias: true });   // không có WebGL thì ném lỗi, layout.js sẽ về 2D
  gl.setPixelRatio(Math.min(devicePixelRatio, 2));
  gl.shadowMap.enabled = true;
  gl.shadowMap.type = THREE.PCFSoftShadowMap;
  const cv = gl.domElement;
  cv.tabIndex = 0;
  cv.setAttribute("role", "img");
  cv.setAttribute("aria-label", "Mô hình 3D mặt bằng kho chữ U: các khu chứa, cửa nhập xuất, sân và bãi xe. Kéo để xoay, cuộn để phóng to. Chế độ 2D có cùng thông tin về ô kệ và dùng được bằng bàn phím");
  el.append(cv);
  const tip = document.createElement("div");
  tip.className = "wh-tip"; tip.hidden = true;
  el.append(tip);

  const scene = new THREE.Scene(), cam = new THREE.PerspectiveCamera(38, 1, 1, 600);
  scene.background = new THREE.Color(BG);
  scene.add(new THREE.HemisphereLight("#ffffff", "#d5dbe5", 1.9));
  // Nắng chiếu vào dải kệ phía sau; chỉ kệ, hàng và khối luồng hàng đổ bóng
  const sun = new THREE.DirectionalLight("#ffffff", 1.1);
  sun.position.set(-25, 45, 15); sun.target.position.set(0, 0, -15); sun.castShadow = true;
  sun.shadow.mapSize.set(2048, 2048);
  Object.assign(sun.shadow.camera, { left: -52, right: 52, top: 34, bottom: -34, near: 1, far: 130 });
  sun.shadow.bias = -0.0005;
  scene.add(sun, sun.target);

  // Mặt bằng: nền, tường, sân bãi, đồ trang trí -> vài InstancedMesh
  const K = kit(), pads = site(K), unit = new THREE.BoxGeometry(1, 1, 1);
  const arrowShape = new THREE.Shape([[-0.12, -0.5], [0.12, -0.5], [0.12, 0], [0.5, 0], [0, 0.5], [-0.5, 0], [-0.12, 0]].map(([x, y]) => new THREE.Vector2(x, y)));
  const G = {
    ground: unit, wall: unit, prop: unit,
    wheel: new THREE.CylinderGeometry(0.5, 0.5, 1, 12).rotateZ(Math.PI / 2),   // trục bánh theo trục x
    arrow: new THREE.ShapeGeometry(arrowShape).rotateX(-Math.PI / 2),          // nằm trên sàn, mũi hướng -z
  };
  const deco = K.build(G, new THREE.MeshLambertMaterial());
  scene.add(...Object.values(deco));

  // Luồng hàng: bộ gom riêng; own[loại][số thứ tự khối] = mục flow, để dò chuột ra đúng xe / đơn
  const P = kit(), own = { box: [], wheel: [] };
  const mark = (item, draw) => {
    const a = { box: P.n("box"), wheel: P.n("wheel") };
    draw();
    for (const k in a) for (let i = a[k]; i < P.n(k); i++) own[k][i] = item;
  };
  const extra = flows(P, flow, mark), fm = P.build({ box: unit, wheel: G.wheel }, new THREE.MeshLambertMaterial());
  const mine = new Map(Object.entries(fm).map(([k, im]) => [im, own[k]]));   // mesh luồng -> danh sách mục
  if (fm.box) fm.box.castShadow = true;
  scene.add(...Object.values(fm));

  // Cửa đánh số trên mặt ngoài tường trước
  for (const [no, x] of SITE.doors) {
    const m = door(no);
    m.position.set(x, 0.6, SITE.hall[3] + WT / 2 + 0.02);
    scene.add(m);
  }

  // ---------- Kệ và hàng ----------
  const Z = Object.fromEntries(zones.map((z) => [z.code, z]));
  const posts = [], spots = {};   // khối trụ, thanh kệ [x, y, z, w, h, d]; tâm đáy ô theo "CODE:bin"
  for (const s of SITE.zones) {
    const z = s.code && Z[s.code];
    if (!z) continue;
    const [x0, x1, z0, z1] = s.r, cx = (x0 + x1) / 2, cz = (z0 + z1) / 2, L = z.bays * BAY, T = z.levels * LEVEL;
    const rowZ = (r) => cz + ((z.racks + 1) / 2 - r) * (DEEP + AISLE);   // dãy A ở trước (gần cửa), B, C… lùi về sau
    for (let r = 1; r <= z.racks; r++) {
      const rz = rowZ(r);
      for (const dz of [-DEEP / 2, DEEP / 2]) {
        for (let b = 0; b <= z.bays; b++) posts.push([cx - L / 2 + b * BAY, (T + 0.1) / 2, rz + dz, 0.1, T + 0.1, 0.1]);
        for (let l = 0; l <= z.levels; l++) posts.push([cx, l * LEVEL + 0.04, rz + dz, L, 0.08, 0.06]);
      }
      const t = tag(String.fromCharCode(64 + r));
      t.position.set(cx - L / 2 - 0.2, T + 0.9, rz);
      scene.add(t);
    }
    for (let bin = 1, n = z.racks * z.bays * z.levels; bin <= n; bin++) {
      const t = slot(bin, z);
      spots[s.code + ":" + bin] = new THREE.Vector3(cx + (t.bay - (z.bays + 1) / 2) * BAY, (t.level - 1) * LEVEL + 0.08, rowZ(t.rack));
    }
  }
  const steel = new THREE.MeshLambertMaterial({ color: STEEL });
  const rack = new THREE.InstancedMesh(unit, steel, posts.length), m = new THREE.Matrix4(), Q = new THREE.Quaternion(), v = new THREE.Vector3(), w = new THREE.Vector3();
  posts.forEach(([x, y, z, a, b, c], i) => rack.setMatrixAt(i, m.compose(v.set(x, y, z), Q, w.set(a, b, c))));
  rack.computeBoundingSphere();
  rack.castShadow = rack.receiveShadow = true;
  scene.add(rack);

  // Lô có ô nằm ngoài kệ của khu (database cũ, khu lạ): bỏ qua, báo lại cho layout.js
  const lots = [], out = [];
  for (const l of loads) { const p = spots[l.zone + ":" + l.bin]; if (p) lots.push([l, p]); else out.push(l); }
  if (out.length) console.warn("Lô nằm ngoài sơ đồ kệ:", out.map((l) => l.zone + "-" + l.bin).join(", "));
  const used = new Set(lots.map(([l]) => l.zone + ":" + l.bin)), ix = {};
  const n = lots.length, base = [], faded = [], wood = new THREE.Color(WOOD), fade = new THREE.Color(FADE);
  const pallet = new THREE.InstancedMesh(new THREE.BoxGeometry(2.2, 0.14, 1.0), new THREE.MeshLambertMaterial(), n);
  const cargo = new THREE.InstancedMesh(new THREE.BoxGeometry(2.0, 1.05, 0.95), new THREE.MeshLambertMaterial(), n);
  lots.forEach(([l, p], i) => {
    pallet.setMatrixAt(i, m.makeTranslation(p.x, p.y + 0.07, p.z));
    cargo.setMatrixAt(i, m.makeTranslation(p.x, p.y + 0.665, p.z));
    ix[l.key] = i; base.push(new THREE.Color("#c3cbd7")); faded.push(false);
  });
  pallet.castShadow = cargo.castShadow = cargo.receiveShadow = true;
  if (n) { pallet.computeBoundingSphere(); cargo.computeBoundingSphere(); scene.add(pallet, cargo); }

  // Khung ô trống: gộp cạnh của mọi ô trống vào 1 LineSegments
  const edge = new THREE.EdgesGeometry(new THREE.BoxGeometry(1.95, 1.05, 0.95)).attributes.position.array, pts = [];
  for (const k in spots) if (!used.has(k)) {
    const p = spots[k];
    for (let i = 0; i < edge.length; i += 3) pts.push(edge[i] + p.x, edge[i + 1] + p.y + 0.665, edge[i + 2] + p.z);
  }
  const eg = new THREE.BufferGeometry();
  eg.setAttribute("position", new THREE.Float32BufferAttribute(pts, 3));
  scene.add(new THREE.LineSegments(eg, new THREE.LineBasicMaterial({ color: "#c3cbd7" })));

  // Viền đánh dấu ô đang chọn
  const ring = new THREE.LineSegments(new THREE.EdgesGeometry(new THREE.BoxGeometry(2.15, 1.2, 1.1)), new THREE.LineBasicMaterial({ color: "#171717" }));
  ring.visible = false;
  scene.add(ring);

  // Biển đánh số các khu: xa chỉ "số · tên ngắn"; gần thêm dòng chi tiết (khu chứa: tên đầy đủ và số liệu)
  // Khu 5, 6 có số liệu luồng (role có quyền xem) thì dòng chi tiết ghi thêm số đơn
  const live = { 5: flow.topick && `${num(flow.topick.n)} đơn chờ soạn`, 6: flow.staged && `${num(flow.staged.length)} đơn chờ xe` };
  const signs = [];
  for (const s of SITE.zones) {
    const z = s.code && Z[s.code], head = `${s.no} · ${s.t}`, data = !s.code && live[s.no];
    const more = s.code ? (z ? `${s.long} · ${z.sub}` : s.long) : data ? `${s.sub} · ${data}` : s.sub;
    signs.push(sign(card([head]), more ? card([head, more], { mono: !!z || !!data }) : null, s.at, s.w));
  }
  signs.push(...extra);
  // Số cửa trên tường trước, cổng vào và lối ra
  for (const [no, x] of SITE.doors) signs.push(sign(card([no], { dark: true }), null, [x, SITE.hall[3] + 0.4, DOORY], 4.4));
  for (const [name, x] of SITE.gates) signs.push(sign(card([name]), null, [x, SITE.fence[3] + 2.5], 22));
  for (const [name, x] of SITE.exits) signs.push(sign(card([name]), null, [Math.sign(x) * 56, SITE.fence[3] + 2.5], 20));
  scene.add(...signs.map((g) => g.s));
  // Chỉnh cỡ và chữ của biển theo khoảng cách camera (gọi trước mỗi lần vẽ)
  const fitSigns = () => {
    for (const g of signs) {
      const d = cam.position.distanceTo(g.s.position), v = g.near && d < NEAR ? g.near : g.far;
      g.s.visible = !!v;
      if (!v) continue;
      g.s.material.map = v.map;
      const h = Math.min(Math.min(d * LK, LH) * v.k, g.w / v.a);
      g.s.scale.set(h * v.a, h, 1);
    }
  };

  // ---------- Vẽ lại và camera ----------
  // Chỉ vẽ lại khi có thay đổi, đỡ tốn pin
  let raf = 0, dead = false, anim = 0;
  const draw = () => { raf = 0; if (!dead) { fitSigns(); gl.render(scene, cam); } };
  const req = () => { if (!raf && !dead) raf = requestAnimationFrame(draw); };
  const ctl = new OrbitControls(cam, cv);
  ctl.maxPolarAngle = Math.PI * 0.47; ctl.minDistance = 4; ctl.maxDistance = 260;
  ctl.addEventListener("change", req);
  ctl.addEventListener("start", () => { cancelAnimationFrame(anim); });   // người dùng kéo thì dừng camera tự chạy

  // Khoảng cách camera để thấy trọn vùng rộng w, sâu d
  const fit = (w, d) => {
    const t = Math.tan((cam.fov * Math.PI) / 360);
    return Math.max((w * 0.56) / (t * cam.aspect), (d * 0.5) / t) + d * 0.27;
  };
  const DIR = new THREE.Vector3(0.1, 0.78, 0.62).normalize();   // nhìn từ phía trước, trên cao
  // Đưa camera tới 1 khu (hoặc toàn kho khi code rỗng); khung lấy theo kích thước khu trong SITE
  const focus = (code, jump) => {
    cancelAnimationFrame(anim);
    const r = (code && SITE.zones.find((s) => s.code === code)?.r) || SITE.view, [x0, x1, z0, z1] = r;
    const to = new THREE.Vector3((x0 + x1) / 2, r === SITE.view ? 0 : 1.5, (z0 + z1) / 2);
    const pos = DIR.clone().multiplyScalar(fit(x1 - x0 + (r === SITE.view ? 0 : 2), z1 - z0)).add(to);
    if (jump || matchMedia("(prefers-reduced-motion: reduce)").matches) {
      cam.position.copy(pos); ctl.target.copy(to); ctl.update(); req();
      return;
    }
    const p0 = cam.position.clone(), t0 = ctl.target.clone(), start = performance.now();
    const go = (now) => {
      if (dead) return;
      const k = Math.min(1, Math.max(0, now - start) / 450), e = 1 - (1 - k) ** 3;
      cam.position.lerpVectors(p0, pos, e); ctl.target.lerpVectors(t0, to, e); ctl.update(); req();
      if (k < 1) anim = requestAnimationFrame(go);
    };
    anim = requestAnimationFrame(go);
  };

  // Đổi cỡ theo khung chứa; lần đầu thì canh camera cho thấy trọn kho
  let zoneNow = "", first = true;
  const size = () => {
    const w = el.clientWidth, h = el.clientHeight;
    if (!w || !h) return;
    gl.setSize(w, h, false);
    cam.aspect = w / h; cam.updateProjectionMatrix();
    if (first) { first = false; focus(zoneNow, true); }
    draw();   // vẽ ngay, tránh nháy trắng khi đổi cỡ
  };
  const ro = new ResizeObserver(size);
  ro.observe(el);

  // ---------- Bấm và rê chuột ----------
  // Tìm khối hàng hoặc đối tượng luồng gần nhất dưới con trỏ (theo instanceId), bỏ qua khối hàng đã mờ.
  // Kết quả có dạng {key, tip}: lô trên kệ hoặc mục flow
  const ray = new THREE.Raycaster(), ptr = new THREE.Vector2(), pick = [...(n ? [cargo] : []), ...mine.keys()];
  const hit = (e) => {
    if (!pick.length) return null;
    const r = cv.getBoundingClientRect();
    ptr.set(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1);
    ray.setFromCamera(ptr, cam);
    for (const h of ray.intersectObjects(pick, false)) {
      const list = mine.get(h.object);
      if (list) { if (list[h.instanceId]) return list[h.instanceId]; }
      else if (!faded[h.instanceId]) return lots[h.instanceId][0];
    }
    return null;
  };
  let dx = 0, dy = 0;
  cv.addEventListener("pointerdown", (e) => { dx = e.clientX; dy = e.clientY; tip.hidden = true; });
  cv.addEventListener("click", (e) => {
    if (Math.hypot(e.clientX - dx, e.clientY - dy) < 5) onPick(hit(e)?.key ?? null);   // kéo xoay thì không tính là bấm
  });
  cv.addEventListener("pointermove", (e) => {
    if (e.buttons) return;
    const l = hit(e), r = el.getBoundingClientRect();
    cv.style.cursor = l ? "pointer" : "grab";
    tip.hidden = !l;
    if (!l) return;
    tip.textContent = l.tip ?? l.label;   // khu 8 (qa) không có tip riêng, dùng chữ trên bảng
    tip.style.left = Math.min(e.clientX - r.left + 12, r.width - tip.offsetWidth - 8) + "px";
    tip.style.top = Math.max(8, e.clientY - r.top - 32) + "px";
  });
  cv.addEventListener("pointerleave", () => { tip.hidden = true; });

  // Áp màu khối hàng: màu gốc, hoặc gần màu nền nếu đang mờ
  const tint = () => {
    if (!n) return;
    for (let i = 0; i < n; i++) { cargo.setColorAt(i, faded[i] ? fade : base[i]); pallet.setColorAt(i, faded[i] ? fade : wood); }
    cargo.instanceColor.needsUpdate = pallet.instanceColor.needsUpdate = true;
    req();
  };
  tint();

  return {
    outside: out.length,
    // Tô màu: hàm nhận key trả về mã màu
    paint(fn) { lots.forEach(([l], i) => base[i].set(fn(l.key))); tint(); },
    // Làm mờ hàng không nằm trong danh sách; null = hiện rõ tất cả
    dim(keys) { lots.forEach(([l], i) => { faded[i] = !!keys && !keys.has(l.key); }); tint(); },
    // Viền ô đang chọn, đặt theo ma trận của khối hàng
    select(key) {
      const i = ix[key];
      ring.visible = i !== undefined;
      if (ring.visible) { cargo.getMatrixAt(i, m); ring.position.setFromMatrixPosition(m); }
      req();
    },
    focus(code) {
      zoneNow = code || "";
      const g = deco.ground;
      for (const c in pads) g.setColorAt(pads[c][0], new THREE.Color(c === zoneNow ? PICK : pads[c][1]));
      g.instanceColor.needsUpdate = true;
      if (!first) focus(zoneNow);
      req();
    },
    dispose() {
      dead = true;
      cancelAnimationFrame(raf); cancelAnimationFrame(anim);
      ro.disconnect(); ctl.dispose();
      scene.traverse((o) => {
        if (o.isInstancedMesh) o.dispose();
        if (o.geometry) o.geometry.dispose();
        if (o.material) { o.material.map?.dispose(); o.material.dispose(); }
      });
      if (!n) { pallet.dispose(); cargo.dispose(); pallet.geometry.dispose(); cargo.geometry.dispose(); }
      for (const g of signs) { g.far?.map.dispose(); g.near?.map.dispose(); }   // biển có 2 texture, chỉ 1 cái đang gắn
      gl.dispose(); gl.forceContextLoss();
      cv.remove(); tip.remove();
    },
  };
}
