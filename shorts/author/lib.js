// Shared helpers, inlined into every scene where it says /*LIB*/ (see AUTHOR.md).
const NS = "http://www.w3.org/2000/svg";
const $ = (s) => document.querySelector(s);
const INK = "#1F1235", DOT = "#FFD23F", CREAM = "#FFF4DC";
function mk(p, tag, a) { const e = document.createElementNS(NS, tag); for (const k in a) e.setAttribute(k, a[k]); p.appendChild(e); return e; }
function rng(s) { return () => ((s = (s * 1664525 + 1013904223) >>> 0) / 4294967296); }
// finite yoyo loop standing in for an endless one (no repeat:-1 allowed)
function amb(tl, t, vars, half, at, total) { tl.to(t, Object.assign({ duration: half, ease: "sine.inOut", repeat: Math.max(1, Math.round(total / half) - 1), yoyo: true }, vars), at); }
// camera: world point (px,py) lands on screen point (sx,sy) at scale s
const _camInit = new Set();
function cam(tl, sel, s, px, py, sx, sy, dur, at, ease) {
  // svgOrigin is read through the element's current matrix, so set it once at identity and never again
  [].concat(sel).forEach((q) => { if (!_camInit.has(q)) { gsap.set(q, { svgOrigin: "0 0" }); _camInit.add(q); } });
  const v = { scale: s, x: sx - px * s, y: sy - py * s };
  if (!dur) (at ? tl.set(sel, v, at) : gsap.set(sel, v)); else tl.to(sel, Object.assign(v, { duration: dur, ease: ease || "power2.inOut" }), at);
}
// two-bone arm drawn along +x from shoulder S; p = [x, y, elbowSide, toolAngleDeg]
function ik(S, L1, L2, tx, ty, side, tool) { const dx = tx - S.x, dy = ty - S.y; let d = Math.hypot(dx, dy); d = Math.min(L1 + L2 - 1, Math.max(Math.abs(L1 - L2) + 1, d)); const base = Math.atan2(dy, dx), A = Math.acos((L1 * L1 + d * d - L2 * L2) / (2 * L1 * d)); const sa = base + side * A; const ex = S.x + L1 * Math.cos(sa), ey = S.y + L1 * Math.sin(sa); const fa = Math.atan2(S.y + d * Math.sin(base) - ey, S.x + d * Math.cos(base) - ex); const D = 180 / Math.PI; return { sa: sa * D, rel: (fa - sa) * D, wr: tool - fa * D }; }
function reach(tl, a, p, dur, at, ease) { const k = ik(a.S, a.L1, a.L2, p[0], p[1], p[2], p[3]); const o = [a.S.x + " " + a.S.y, (a.S.x + a.L1) + " " + a.S.y, (a.S.x + a.L1 + a.L2) + " " + a.S.y]; const r = [k.sa, k.rel, k.wr], t = [a.u, a.f, a.h]; for (let i = 0; i < 3; i++) { if (!t[i]) continue; if (!dur) (at ? tl.set(t[i], { rotation: r[i], svgOrigin: o[i] }, at) : gsap.set(t[i], { rotation: r[i], svgOrigin: o[i] })); else tl.to(t[i], { rotation: r[i] + "_short", svgOrigin: o[i], duration: dur, ease: ease || "power2.inOut" }, at); } }
function gearD(cx, cy, r, n, t) { let d = ""; const ri = r - t, w = Math.PI / n; const p = (rad, a) => (cx + rad * Math.cos(a)).toFixed(1) + " " + (cy + rad * Math.sin(a)).toFixed(1); for (let i = 0; i < n; i++) { const a0 = (i / n) * 2 * Math.PI; d += (i ? "L" : "M") + p(ri, a0 - w * 0.55) + "L" + p(r, a0 - w * 0.32) + "L" + p(r, a0 + w * 0.32) + "L" + p(ri, a0 + w * 0.55); } return d + "Z"; }
function gears(root) { document.querySelectorAll(root + " path[data-gear]").forEach((e) => { const v = e.getAttribute("data-gear").split(",").map(Number); e.setAttribute("d", gearD(v[0], v[1], v[2], v[3], v[4])); }); }
function hexPack(cx, cy, R, sp) { const out = []; const h = sp * 0.866; for (let j = -20; j <= 20; j++) for (let i = -20; i <= 20; i++) { const x = i * sp + (j & 1 ? sp / 2 : 0), y = j * h; if (x * x + y * y <= R * R) out.push({ x: cx + x, y: cy + y }); } out.sort((a, b) => b.y - a.y || a.x - b.x); return out; }
