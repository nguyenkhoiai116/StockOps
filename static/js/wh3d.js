// ===== WH3D: kho 3D cơ bản bằng Three.js =====
// File này chỉ lo phần hình. Dữ liệu và thao tác nằm ở features/layout.js.
// Sau này có mô hình 3D cụ thể: thay makeRack() (kệ) và makeLoad() (hàng) bằng mô hình GLB, sửa slot() theo sơ đồ thật.
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";

const BAY = 2.7, LEVEL = 1.8, DEEP = 1.3, AISLE = 3;       // kích thước 1 ô kệ và lối đi (mét)
const RACKS = 2, LEVELS = 2, BAYS = 3;                      // mỗi khu: 2 kệ x 2 tầng x 3 ô = 12 ô
const ZW = BAYS * BAY + 2.4, ZD = RACKS * DEEP + AISLE + 2.4, GAP = 2.5;   // bề rộng, bề sâu khu và khoảng cách giữa các khu

const PAD = "#e1e6ee";   // màu sàn khu

// slot: số ô (1..12) -> kệ, tầng, vị trí trên kệ. QUY ƯỚC TẠM để bày hình, chưa phải sơ đồ kho thật.
export function slot(bin) {
  const i = bin - 1;
  return { rack: Math.floor(i / (LEVELS * BAYS)) + 1, level: Math.floor((i % (LEVELS * BAYS)) / BAYS) + 1, bay: (i % BAYS) + 1 };
}
// Tọa độ đáy ô trong khu
function slotPos(bin) {
  const s = slot(bin);
  return new THREE.Vector3((s.bay - (BAYS + 1) / 2) * BAY, (s.level - 1) * LEVEL + 0.15, (s.rack - (RACKS + 1) / 2) * (AISLE + DEEP));
}

const G = {};   // hình khối dùng chung, tạo 1 lần
function box(w, h, d) { return (G[[w, h, d]] ??= new THREE.BoxGeometry(w, h, d)); }

// Kệ: trụ đứng và thanh ngang
function makeRack(mat) {
  const g = new THREE.Group(), add = (w, h, d, x, y, z) => {
    const m = new THREE.Mesh(box(w, h, d), mat);
    m.position.set(x, y, z); m.castShadow = true; g.add(m);
  };
  const L = BAYS * BAY, T = LEVELS * LEVEL;
  for (let i = 0; i <= BAYS; i++) for (const z of [-DEEP / 2, DEEP / 2]) add(0.1, T, 0.1, i * BAY - L / 2, T / 2, z);
  for (let l = 0; l < LEVELS; l++) for (const z of [-DEEP / 2, DEEP / 2]) add(L, 0.12, 0.08, 0, l * LEVEL + 0.08, z);
  return g;
}

// Hàng trên 1 ô: pallet + khối thùng (vật liệu riêng để đổi màu)
function makeLoad(wood) {
  const g = new THREE.Group();
  const p = new THREE.Mesh(box(2.1, 0.14, 1.15), wood);
  p.position.y = 0.07;
  const b = new THREE.Mesh(box(1.95, 1.2, 1.05), new THREE.MeshLambertMaterial({ transparent: true }));
  b.position.y = 0.74; b.castShadow = b.receiveShadow = true;
  g.add(p, b);
  return { group: g, body: b, pallet: p };
}

// Nhãn chữ luôn quay về phía người xem
function label(text, sub) {
  const c = document.createElement("canvas"), x = c.getContext("2d");
  c.width = 512; c.height = 144;
  x.fillStyle = "#ffffff"; x.strokeStyle = "#c9cfd8"; x.lineWidth = 4;
  x.beginPath(); x.roundRect(2, 2, 508, 140, 16); x.fill(); x.stroke();
  x.textAlign = "center"; x.fillStyle = "#171717";
  x.font = '600 56px "IBM Plex Sans", "Segoe UI", sans-serif'; x.fillText(text, 256, 64, 480);
  x.fillStyle = "#4d4d52"; x.font = '400 44px "IBM Plex Mono", Consolas, monospace'; x.fillText(sub, 256, 120, 480);
  const t = new THREE.CanvasTexture(c);
  t.colorSpace = THREE.SRGBColorSpace;
  const s = new THREE.Sprite(new THREE.SpriteMaterial({ map: t, depthTest: false }));
  s.scale.set(3.9, 1.1, 1); s.renderOrder = 5;
  return s;
}

// Dựng cảnh vào el. zones: [{code, name, sub}], loads: [{key, zone, bin, tip}], bins: số ô mỗi khu.
// onPick(key | null) khi bấm vào hàng / chỗ trống. Trả về các hàm điều khiển.
export function mount(el, { zones, loads, bins }, onPick) {
  const gl = new THREE.WebGLRenderer({ antialias: true });   // không có WebGL thì ném lỗi, layout.js sẽ về 2D
  gl.setPixelRatio(Math.min(devicePixelRatio, 2));
  gl.shadowMap.enabled = true;
  gl.shadowMap.type = THREE.PCFSoftShadowMap;
  const cv = gl.domElement;
  cv.tabIndex = 0;
  cv.setAttribute("role", "img");
  cv.setAttribute("aria-label", "Mô hình 3D các khu kho. Kéo để xoay, cuộn để phóng to. Chế độ 2D có cùng thông tin và dùng được bằng bàn phím");
  el.append(cv);
  const tip = document.createElement("div");
  tip.className = "wh-tip"; tip.hidden = true;
  el.append(tip);

  const scene = new THREE.Scene(), cam = new THREE.PerspectiveCamera(38, 1, 0.5, 300);
  scene.background = new THREE.Color("#eef1f6");
  scene.add(new THREE.HemisphereLight("#ffffff", "#d5dbe5", 1.9));
  const sun = new THREE.DirectionalLight("#ffffff", 1.1);
  sun.position.set(-14, 26, 16); sun.castShadow = true;
  sun.shadow.mapSize.set(2048, 2048);
  Object.assign(sun.shadow.camera, { left: -26, right: 26, top: 26, bottom: -26, far: 80 });
  sun.shadow.bias = -0.0005;
  scene.add(sun);

  // Nền kho và các khu, xếp 2 cột
  const steel = new THREE.MeshLambertMaterial({ color: "#8f9bad" }), wood = new THREE.MeshLambertMaterial({ color: "#b8b4ac" });
  const rowsN = Math.ceil(zones.length / 2), W = 2 * ZW + GAP, D = rowsN * ZD + (rowsN - 1) * GAP;
  const floor = new THREE.Mesh(box(W + 4, 0.2, D + 4), new THREE.MeshLambertMaterial({ color: "#f3f5f8" }));
  floor.position.y = -0.13; floor.receiveShadow = true;
  scene.add(floor);
  const at = {}, pads = {}, items = {};   // vị trí khu, sàn khu, hàng theo key
  const emptyGeo = new THREE.EdgesGeometry(new THREE.BoxGeometry(1.95, 1.3, 1.05)), emptyMat = new THREE.LineBasicMaterial({ color: "#c3cbd7" });
  zones.forEach((z, i) => {
    const g = new THREE.Group();
    g.position.set((i % 2 - 0.5) * (ZW + GAP), 0, (Math.floor(i / 2) - (rowsN - 1) / 2) * (ZD + GAP));
    at[z.code] = g.position;
    const pad = new THREE.Mesh(box(ZW, 0.06, ZD), new THREE.MeshLambertMaterial({ color: PAD }));
    pad.receiveShadow = true;
    pads[z.code] = pad;
    g.add(pad);
    for (let r = 0; r < RACKS; r++) {
      const k = makeRack(steel);
      k.position.z = (r - (RACKS - 1) / 2) * (AISLE + DEEP);
      g.add(k);
    }
    for (let b = 1; b <= bins; b++) {
      const l = loads.find((x) => x.zone === z.code && x.bin === b);
      if (l) {
        const o = makeLoad(wood);
        o.group.position.copy(slotPos(b));
        o.body.userData = l;
        items[l.key] = o;
        g.add(o.group);
      } else {
        const e = new THREE.LineSegments(emptyGeo, emptyMat);
        e.position.copy(slotPos(b)); e.position.y += 0.7;
        g.add(e);
      }
    }
    const t = label(z.name, z.sub);
    t.position.set(0, 0.5, ZD / 2 + 0.4);   // đặt sát mép trước khu để không che hàng
    g.add(t);
    scene.add(g);
  });

  // Viền đánh dấu ô đang chọn
  const ring = new THREE.LineSegments(new THREE.EdgesGeometry(new THREE.BoxGeometry(2.1, 1.35, 1.2)), new THREE.LineBasicMaterial({ color: "#171717" }));
  ring.visible = false;
  scene.add(ring);

  // Chỉ vẽ lại khi có thay đổi, đỡ tốn pin
  let raf = 0, dead = false, anim = 0;
  const draw = () => { raf = 0; if (!dead) gl.render(scene, cam); };
  const req = () => { if (!raf && !dead) raf = requestAnimationFrame(draw); };
  const ctl = new OrbitControls(cam, cv);
  ctl.maxPolarAngle = Math.PI * 0.47; ctl.minDistance = 6; ctl.maxDistance = 90;
  ctl.addEventListener("change", req);
  ctl.addEventListener("start", () => { cancelAnimationFrame(anim); });   // người dùng kéo thì dừng camera tự chạy

  // Khoảng cách camera để thấy trọn vùng rộng w, sâu d
  const fit = (w, d) => {
    const v = Math.tan((cam.fov * Math.PI) / 360);
    return Math.max((w * 0.56) / (v * cam.aspect), (d * 0.5) / v) + d * 0.27;
  };
  // Đưa camera tới 1 khu (hoặc toàn kho khi code rỗng)
  const focus = (code, jump) => {
    cancelAnimationFrame(anim);
    const p = at[code] || new THREE.Vector3(), r = code ? fit(ZW + 1, ZD) : fit(W + 3, D);
    const to = new THREE.Vector3(p.x, 1.2, p.z), pos = new THREE.Vector3(0.32, 0.72, 0.9).normalize().multiplyScalar(r).add(to);
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

  // Tìm khối hàng dưới con trỏ
  const ray = new THREE.Raycaster(), ptr = new THREE.Vector2(), bodies = Object.values(items).map((o) => o.body);
  const hit = (e) => {
    const r = cv.getBoundingClientRect();
    ptr.set(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1);
    ray.setFromCamera(ptr, cam);
    return ray.intersectObjects(bodies.filter((b) => b.material.opacity > 0.5), false)[0]?.object.userData;
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
    tip.textContent = l.tip;
    tip.style.left = Math.min(e.clientX - r.left + 12, r.width - tip.offsetWidth - 8) + "px";
    tip.style.top = Math.max(8, e.clientY - r.top - 32) + "px";
  });
  cv.addEventListener("pointerleave", () => { tip.hidden = true; });

  return {
    // Tô màu: hàm nhận key trả về mã màu
    paint(fn) { for (const k in items) items[k].body.material.color.set(fn(k)); req(); },
    // Làm mờ hàng không nằm trong danh sách; null = hiện rõ tất cả
    dim(keys) {
      for (const k in items) {
        const on = !keys || keys.has(k);
        items[k].body.material.opacity = on ? 1 : 0.12;
        items[k].body.castShadow = items[k].pallet.visible = on;
      }
      req();
    },
    select(key) {
      const o = items[key];
      ring.visible = !!o;
      if (o) o.body.getWorldPosition(ring.position);
      req();
    },
    focus(code) {
      zoneNow = code || "";
      for (const c in pads) pads[c].material.color.set(c === zoneNow ? "#c3d6fa" : PAD);
      if (!first) focus(zoneNow);
      req();
    },
    dispose() {
      dead = true;
      cancelAnimationFrame(raf); cancelAnimationFrame(anim);
      ro.disconnect(); ctl.dispose();
      scene.traverse((o) => {
        if (o.geometry) o.geometry.dispose();
        if (o.material) { o.material.map?.dispose(); o.material.dispose(); }
      });
      for (const k in G) delete G[k];
      gl.dispose(); gl.forceContextLoss();
      cv.remove(); tip.remove();
    },
  };
}
