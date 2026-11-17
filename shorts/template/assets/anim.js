// Animated scenes for "anim" shots: drawn and moved entirely in code, every frame a function of
// timeline time (seeked, never played), so renders are identical. One builder per scene type.
// window.buildAnim(root, shot, tl, accent) fills `root` (a 1080x1920 box) and adds tweens to `tl`.
(function () {
  const NS = "http://www.w3.org/2000/svg";
  const W = 1080, H = 1920;
  const el = (tag, attrs, parent) => {
    const e = document.createElementNS(NS, tag);
    for (const k in attrs) e.setAttribute(k, attrs[k]);
    if (parent) parent.appendChild(e);
    return e;
  };
  const html = (tag, cls, text, parent) => {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    if (parent) parent.appendChild(e);
    return e;
  };
  const fmt = (n) => {
    const a = Math.abs(n);
    if (a >= 1e9) return (n / 1e9).toFixed(a >= 1e10 ? 0 : 1).replace(/\.0$/, "") + "B";
    if (a >= 1e6) return (n / 1e6).toFixed(a >= 1e7 ? 0 : 1).replace(/\.0$/, "") + "M";
    if (a >= 1e4) return Math.round(n).toLocaleString("en-US");
    return (Math.round(n * 10) / 10).toLocaleString("en-US");
  };
  const fmtLike = (n, target) => fmt(Number.isInteger(target) ? Math.round(n) : n);
  const reps = (span, cycle) => Math.max(0, Math.floor(span / cycle) - 1);
  const clip = (s, n) => (s || "").length > n ? s.slice(0, n - 1) + "…" : s || "";

  // ---------------------------------------------------------------- shared stage
  function stage(root, shot, tl, accent) {
    root.classList.add("anim-stage");
    const bg = html("div", "anim-bg", null, root);
    bg.style.background = `radial-gradient(120% 80% at 50% 38%, ${accent}33 0%, #0d1030 45%, #05060f 100%)`;
    // Slow-moving glow orbs give depth behind the drawing.
    const orbs = [[220, 520, 520], [860, 900, 640], [420, 1380, 560]];
    orbs.forEach(([x, y, r], i) => {
      const o = html("div", "anim-orb", null, root);
      Object.assign(o.style, { left: `${x - r / 2}px`, top: `${y - r / 2}px`, width: `${r}px`, height: `${r}px`,
        background: `radial-gradient(circle, ${i === 1 ? accent : "#5b7cff"}55 0%, transparent 70%)` });
      tl.fromTo(o, { x: -40, y: 20 }, { x: 40, y: -30, duration: shot.clipEnd - shot.clipStart, ease: "sine.inOut" }, shot.clipStart);
    });
    // A faint grid that drifts upward, like a technical drawing board.
    const svg = el("svg", { viewBox: `0 0 ${W} ${H}`, class: "anim-svg" }, root);
    const grid = el("g", { opacity: "0.09" }, svg);
    for (let x = 0; x <= W; x += 90) el("line", { x1: x, y1: -180, x2: x, y2: H + 180, stroke: "#fff", "stroke-width": 1.5 }, grid);
    for (let y = -180; y <= H + 180; y += 90) el("line", { x1: 0, y1: y, x2: W, y2: y, stroke: "#fff", "stroke-width": 1.5 }, grid);
    tl.fromTo(grid, { y: 0 }, { y: -90, duration: shot.clipEnd - shot.clipStart, ease: "none" }, shot.clipStart);
    const draw = el("g", { transform: "translate(0 70)" }, svg);
    // Title at the top of the drawing.
    const a = shot.anim;
    if (a.title) {
      const t = html("div", "anim-title", clip(a.title, 34), root);
      const bar = html("div", "anim-title-bar", null, t);
      bar.style.background = accent;
      const t0 = shot.start + 0.1;
      tl.fromTo(t, { opacity: 0, y: 30, filter: "blur(8px)" }, { opacity: 1, y: 0, filter: "blur(0px)", duration: 0.35, ease: "power3.out" }, t0);
      tl.fromTo(bar, { scaleX: 0 }, { scaleX: 1, duration: 0.5, ease: "power3.out" }, t0 + 0.15);
    }
    return { svg, draw, t0: shot.start + 0.35, t1: shot.end, span: shot.end - shot.start };
  }

  // ---------------------------------------------------------------- diagram: nodes joined by flowing arrows
  function diagram(root, shot, tl, accent) {
    const s = stage(root, shot, tl, accent);
    const items = shot.anim.items.slice(0, 5);
    const n = Math.max(2, items.length);
    const top = 540, bottom = 940;
    const pts = items.map((it, i) => ({ x: i % 2 ? 760 : 320, y: top + (bottom - top) * (n === 1 ? 0 : i / (n - 1)) }));
    const step = Math.min(0.55, (s.span - 1.2) / (n * 1.6));
    // Connectors first, so the nodes sit on top of them.
    pts.slice(1).forEach((p, i) => {
      const q = pts[i];
      const d = `M ${q.x} ${q.y} C ${q.x} ${(q.y + p.y) / 2}, ${p.x} ${(q.y + p.y) / 2}, ${p.x} ${p.y}`;
      const path = el("path", { d, fill: "none", stroke: accent, "stroke-width": 8, "stroke-linecap": "round", opacity: "0.85" }, s.draw);
      const len = path.getTotalLength();
      path.style.strokeDasharray = `${len}`;
      const at = s.t0 + (i + 0.6) * step * 1.6;
      tl.fromTo(path, { strokeDashoffset: len }, { strokeDashoffset: 0, duration: step * 1.2, ease: "power2.inOut" }, at);
      // Particles keep flowing along the connector once it is drawn.
      for (let k = 0; k < 3; k++) {
        const dot = el("circle", { r: 11, fill: "#fff", opacity: 0 }, s.draw);
        const proxy = { u: 0 };
        const cyc = 1.4;
        const start = at + step * 1.2 + k * (cyc / 3);
        tl.set(dot, { opacity: 0.95 }, start);
        tl.fromTo(proxy, { u: 0 }, { u: 1, duration: cyc, ease: "none", repeat: reps(s.t1 - start, cyc),
          onUpdate: () => { const pt = path.getPointAtLength(proxy.u * len); dot.setAttribute("cx", pt.x); dot.setAttribute("cy", pt.y); } }, start);
      }
    });
    pts.forEach((p, i) => {
      const g = el("g", { transform: `translate(${p.x} ${p.y})` }, s.draw);
      const box = el("g", {}, g);
      el("rect", { x: -200, y: -66, width: 400, height: 132, rx: 34, fill: "#11163a", stroke: i === pts.length - 1 ? accent : "#ffffff55", "stroke-width": 5 }, box);
      const label = el("text", { x: 0, y: 4, "text-anchor": "middle", "dominant-baseline": "middle", fill: "#fff", "font-family": "Inter, Noto Sans Tamil", "font-weight": 900, "font-size": 40 }, box);
      label.textContent = clip(items[i].label, 18);
      if (items[i].note) {
        const note = el("text", { x: 0, y: 100, "text-anchor": "middle", fill: "#ffffffcc", "font-family": "Inter, Noto Sans Tamil", "font-weight": 700, "font-size": 30 }, g);
        note.textContent = clip(items[i].note, 26);
        tl.fromTo(note, { opacity: 0 }, { opacity: 1, duration: 0.3 }, s.t0 + i * step * 1.6 + 0.25);
      }
      tl.fromTo(box, { scale: 0.3, opacity: 0, transformOrigin: "50% 50%" }, { scale: 1, opacity: 1, duration: 0.45, ease: "back.out(1.8)" }, s.t0 + i * step * 1.6);
    });
  }

  // ---------------------------------------------------------------- chart: bars that grow and count
  function chart(root, shot, tl, accent) {
    const s = stage(root, shot, tl, accent);
    const items = shot.anim.items.slice(0, 5);
    const max = Math.max(...items.map((i) => Math.abs(Number(i.value) || 0)), 1);
    const rowH = Math.min(130, 520 / items.length);
    items.forEach((it, i) => {
      const y = 500 + i * rowH;
      const v = Math.abs(Number(it.value) || 0);
      const w = Math.max(24, (v / max) * 720);
      const best = v === max;
      const label = el("text", { x: 150, y: y, fill: "#fff", "font-family": "Inter, Noto Sans Tamil", "font-weight": 900, "font-size": 38 }, s.draw);
      label.textContent = clip(it.label, 24);
      const track = el("rect", { x: 150, y: y + 22, width: 780, height: 54, rx: 27, fill: "#ffffff14" }, s.draw);
      const bar = el("rect", { x: 150, y: y + 22, width: 0, height: 54, rx: 27, fill: best ? accent : "#ffffffcc" }, s.draw);
      const val = el("text", { x: 170, y: y + 62, fill: best ? "#14163a" : "#14163a", "font-family": "Inter, Noto Sans Tamil", "font-weight": 900, "font-size": 32 }, s.draw);
      const at = s.t0 + i * 0.22;
      const proxy = { w: 0 };
      tl.fromTo(label, { opacity: 0, x: -30 }, { opacity: 1, x: 0, duration: 0.3, ease: "power3.out" }, at);
      tl.fromTo(proxy, { w: 0 }, { w, duration: 1.1, ease: "power3.out",
        onUpdate: () => {
          bar.setAttribute("width", proxy.w);
          val.textContent = fmtLike((proxy.w / w) * v, v) + (shot.anim.unit ? " " + shot.anim.unit : "");
          const tw = val.getComputedTextLength();
          const inside = proxy.w > tw + 50;
          val.setAttribute("x", inside ? 150 + proxy.w - 22 - tw : 150 + proxy.w + 18);
          val.setAttribute("fill", inside ? "#14163a" : "#ffffff");
        } }, at + 0.1);
      void track;
    });
  }

  // ---------------------------------------------------------------- timeline: years down a glowing line
  function timeline(root, shot, tl, accent) {
    const s = stage(root, shot, tl, accent);
    const items = shot.anim.items.slice(0, 5);
    const top = 470, bottom = 1060, x = 210;
    const line = el("line", { x1: x, y1: top, x2: x, y2: bottom, stroke: "#ffffff66", "stroke-width": 6, "stroke-linecap": "round" }, s.draw);
    tl.fromTo(line, { attr: { y2: top } }, { attr: { y2: bottom }, duration: Math.min(1.6, s.span * 0.5), ease: "power2.inOut" }, s.t0);
    const step = (s.span - 1) / Math.max(1, items.length);
    items.forEach((it, i) => {
      const y = top + ((bottom - top) * (i + 0.5)) / items.length;
      const at = s.t0 + 0.2 + i * Math.min(0.7, step);
      const dot = el("circle", { cx: x, cy: y, r: 22, fill: accent, stroke: "#0b0d1c", "stroke-width": 6 }, s.draw);
      const ring = el("circle", { cx: x, cy: y, r: 22, fill: "none", stroke: accent, "stroke-width": 4 }, s.draw);
      const year = el("text", { x: x + 64, y: y - 6, fill: accent, "font-family": "Archivo Black, Noto Sans Tamil", "font-size": 62 }, s.draw);
      year.textContent = clip(it.label, 14);
      const note = el("text", { x: x + 66, y: y + 46, fill: "#fff", "font-family": "Inter, Noto Sans Tamil", "font-weight": 700, "font-size": 34 }, s.draw);
      note.textContent = clip(it.note, 34);
      tl.fromTo(dot, { scale: 0, transformOrigin: `${x}px ${y}px` }, { scale: 1, duration: 0.35, ease: "back.out(2.4)" }, at);
      tl.fromTo(ring, { attr: { r: 22 }, opacity: 0.9 }, { attr: { r: 70 }, opacity: 0, duration: 0.8, ease: "power2.out" }, at + 0.05);
      tl.fromTo([year, note], { opacity: 0, x: 40 }, { opacity: 1, x: 0, duration: 0.35, stagger: 0.08, ease: "power3.out" }, at + 0.1);
    });
  }

  // ---------------------------------------------------------------- scale: sizes side by side
  function scale(root, shot, tl, accent) {
    const s = stage(root, shot, tl, accent);
    const items = shot.anim.items.slice(0, 4).map((it) => ({ ...it, v: Math.abs(Number(it.value) || 1) }));
    items.sort((a, b) => a.v - b.v);
    const max = items[items.length - 1].v;
    let ds = items.map((it) => Math.max(36, (it.v / max) * 500));
    const gap = 50, total = ds.reduce((a, b) => a + b, 0) + gap * (items.length - 1);
    if (total > 940) ds = ds.map((d) => Math.max(30, (d * (940 - gap * (items.length - 1))) / (total - gap * (items.length - 1))));
    let x = (W - (ds.reduce((a, b) => a + b, 0) + gap * (items.length - 1))) / 2;
    const base = 1000;
    items.forEach((it, i) => {
      const d = ds[i], cx = x + d / 2, cy = base - d / 2;
      x += d + gap;
      const big = i === items.length - 1;
      const c = el("circle", { cx, cy, r: d / 2, fill: big ? accent : "#7aa2ff", opacity: 0.92 }, s.draw);
      el("circle", { cx: cx - d * 0.15, cy: cy - d * 0.18, r: d * 0.16, fill: "#ffffff", opacity: 0.25 }, s.draw);
      const label = el("text", { x: cx, y: base + 64, "text-anchor": "middle", fill: "#fff", "font-family": "Inter, Noto Sans Tamil", "font-weight": 900, "font-size": 36 }, s.draw);
      label.textContent = clip(it.label, 16);
      const at = s.t0 + i * 0.45;
      tl.fromTo(c, { scale: 0, transformOrigin: `${cx}px ${base}px` }, { scale: 1, duration: big ? 1.0 : 0.55, ease: big ? "power4.out" : "back.out(1.6)" }, at);
      tl.fromTo(label, { opacity: 0, y: 20 }, { opacity: 1, y: 0, duration: 0.3 }, at + 0.25);
    });
    el("line", { x1: 90, y1: base, x2: W - 90, y2: base, stroke: "#ffffff55", "stroke-width": 4 }, s.draw);
    if (items.length > 1 && items[0].v > 0) {
      const bd = ds[ds.length - 1], bx = x - gap - bd / 2, by = base - bd / 2;
      const ratio = el("text", { x: bx, y: by + bd * 0.12, "text-anchor": "middle", fill: "#14163a", "font-family": "Archivo Black, Noto Sans Tamil", "font-size": Math.max(40, Math.min(110, bd * 0.3)) }, s.draw);
      ratio.textContent = `×${fmt(max / items[0].v)}`;
      tl.fromTo(ratio, { opacity: 0, scale: 0.6, transformOrigin: `${bx}px ${by}px` }, { opacity: 1, scale: 1, duration: 0.45, ease: "back.out(2)" }, s.t0 + items.length * 0.45 + 0.4);
    }
  }

  // ---------------------------------------------------------------- stat: one big number in a ring
  function stat(root, shot, tl, accent) {
    const s = stage(root, shot, tl, accent);
    const it = shot.anim.items[0] || { label: "", value: 0 };
    const v = Number(it.value) || 0;
    const unit = shot.anim.unit || "";
    const cx = W / 2, cy = 740, r = 260;
    el("circle", { cx, cy, r, fill: "none", stroke: "#ffffff1f", "stroke-width": 34 }, s.draw);
    const arc = el("circle", { cx, cy, r, fill: "none", stroke: accent, "stroke-width": 34, "stroke-linecap": "round",
      transform: `rotate(-90 ${cx} ${cy})` }, s.draw);
    const len = 2 * Math.PI * r;
    const frac = unit.trim() === "%" ? Math.min(1, Math.max(0.02, v / 100)) : 1;
    arc.style.strokeDasharray = `${len}`;
    const num = el("text", { x: cx, y: cy + 10, "text-anchor": "middle", "dominant-baseline": "middle", fill: "#fff", "font-family": "Archivo Black, Noto Sans Tamil", "font-size": String(v).length > 6 ? 108 : 150 }, s.draw);
    const u = el("text", { x: cx, y: cy + 120, "text-anchor": "middle", fill: accent, "font-family": "Inter, Noto Sans Tamil", "font-weight": 900, "font-size": 52 }, s.draw);
    u.textContent = unit.trim() === "%" ? "" : clip(unit, 14);
    const cap = el("text", { x: cx, y: cy + r + 80, "text-anchor": "middle", fill: "#fff", "font-family": "Inter, Noto Sans Tamil", "font-weight": 900, "font-size": 44 }, s.draw);
    cap.textContent = clip(it.label, 30);
    const proxy = { p: 0 };
    tl.fromTo(proxy, { p: 0 }, { p: 1, duration: 1.6, ease: "power2.out",
      onUpdate: () => { arc.style.strokeDashoffset = `${len * (1 - frac * proxy.p)}`; num.textContent = fmtLike(v * proxy.p, v) + (unit.trim() === "%" ? "%" : ""); } }, s.t0);
    tl.fromTo([u, cap], { opacity: 0, y: 20 }, { opacity: 1, y: 0, duration: 0.35, stagger: 0.1 }, s.t0 + 0.5);
    tl.fromTo(arc, { opacity: 0.6 }, { opacity: 1, duration: 0.3, repeat: reps(s.span, 0.6), yoyo: true, ease: "sine.inOut" }, s.t0 + 1.6);
  }

  // ---------------------------------------------------------------- orbit: bodies circling a centre
  function orbit(root, shot, tl, accent) {
    const s = stage(root, shot, tl, accent);
    const items = shot.anim.items.slice(0, 5);
    const cx = W / 2, cy = 800;
    const sun = el("circle", { cx, cy, r: 90, fill: accent }, s.draw);
    el("circle", { cx, cy, r: 150, fill: accent, opacity: 0.18 }, s.draw);
    const centre = el("text", { x: cx, y: cy + 12, "text-anchor": "middle", fill: "#14163a", "font-family": "Inter, Noto Sans Tamil", "font-weight": 900, "font-size": 30 }, s.draw);
    centre.textContent = clip(shot.anim.variant || "", 10);
    tl.fromTo(sun, { scale: 0, transformOrigin: `${cx}px ${cy}px` }, { scale: 1, duration: 0.6, ease: "back.out(1.7)" }, s.t0 - 0.1);
    items.forEach((it, i) => {
      const r = 180 + i * 78;
      const ring = el("ellipse", { cx, cy, rx: r, ry: r * 0.42, fill: "none", stroke: "#ffffff40", "stroke-width": 3 }, s.draw);
      const body = el("circle", { r: 20 + (i % 3) * 6, fill: ["#7aa2ff", "#ff9d6e", "#9cf0c0", "#f7a8ff", "#ffffff"][i] }, s.draw);
      const label = el("text", { "text-anchor": "middle", fill: "#fff", "font-family": "Inter, Noto Sans Tamil", "font-weight": 900, "font-size": 30 }, s.draw);
      label.textContent = clip(it.label, 14);
      const proxy = { a: (i * 1.3) % (Math.PI * 2) };
      const speed = 2.6 / (1 + i * 0.45); // inner bodies move faster
      tl.fromTo(ring, { opacity: 0 }, { opacity: 1, duration: 0.4 }, s.t0 + i * 0.15);
      tl.fromTo(proxy, { a: proxy.a }, { a: proxy.a + speed * (s.t1 - s.t0 + 0.4), duration: s.t1 - s.t0 + 0.4, ease: "none",
        onUpdate: () => {
          const x = cx + Math.cos(proxy.a) * r, y = cy + Math.sin(proxy.a) * r * 0.42;
          body.setAttribute("cx", x); body.setAttribute("cy", y);
          label.setAttribute("x", x); label.setAttribute("y", i % 2 ? y + 58 : y - 36);
        } }, s.t0 - 0.2);
      tl.fromTo([body, label], { opacity: 0 }, { opacity: 1, duration: 0.3 }, s.t0 + i * 0.15);
    });
  }

  // ---------------------------------------------------------------- wave: heartbeat, sound or signal line
  function wave(root, shot, tl, accent) {
    const s = stage(root, shot, tl, accent);
    const v = (shot.anim.variant || "").toLowerCase();
    const kind = /heart|ecg|pulse/.test(v) ? "heart" : /sound|voice|music/.test(v) ? "sound" : "sine";
    const y0 = 800, amp = 170, width = W + 400;
    const pathFor = (phase) => {
      let d = "";
      for (let x = -200; x <= width; x += 6) {
        const t = (x + phase) / 260;
        let y;
        if (kind === "heart") {
          const k = ((t % 1) + 1) % 1;
          y = k < 0.42 ? 0 : k < 0.46 ? -0.25 : k < 0.5 ? 1.0 : k < 0.54 ? -0.55 : k < 0.6 ? 0.12 : 0;
        } else if (kind === "sound") {
          y = Math.sin(t * 7.3) * Math.sin(t * 1.7) * (0.6 + 0.4 * Math.sin(t * 0.7));
        } else {
          y = Math.sin(t * Math.PI * 2) * 0.8;
        }
        d += (d ? " L " : "M ") + x + " " + (y0 - y * amp);
      }
      return d;
    };
    const glow = el("path", { fill: "none", stroke: accent, "stroke-width": 26, opacity: 0.25, "stroke-linejoin": "round" }, s.draw);
    const line = el("path", { fill: "none", stroke: accent, "stroke-width": 9, "stroke-linejoin": "round", "stroke-linecap": "round" }, s.draw);
    const proxy = { ph: 0 };
    tl.fromTo(proxy, { ph: 0 }, { ph: 520 * s.span, duration: s.span + 0.5, ease: "none",
      onUpdate: () => { const d = pathFor(proxy.ph); line.setAttribute("d", d); glow.setAttribute("d", d); } }, shot.start - 0.2);
    tl.fromTo([line, glow], { opacity: 0 }, { opacity: (i) => (i ? 0.25 : 1), duration: 0.4 }, s.t0 - 0.2);
    const it = shot.anim.items[0];
    if (it && it.label) {
      const big = el("text", { x: W / 2, y: 560, "text-anchor": "middle", fill: "#fff", "font-family": "Archivo Black, Noto Sans Tamil", "font-size": 92 }, s.draw);
      big.textContent = clip((it.value ? fmt(Number(it.value)) + " " : "") + it.label, 18);
      tl.fromTo(big, { opacity: 0, y: 30 }, { opacity: 1, y: 0, duration: 0.4, ease: "power3.out" }, s.t0 + 0.4);
    }
  }

  // ---------------------------------------------------------------- globe: turning wireframe Earth with a pin
  function globe(root, shot, tl, accent) {
    const s = stage(root, shot, tl, accent);
    const a = shot.anim;
    const lat = Math.max(-80, Math.min(80, Number(a.lat) || 0)) * Math.PI / 180;
    const lon = (Number(a.lon) || 0) * Math.PI / 180;
    const cx = W / 2, cy = 770, R = 290;
    el("circle", { cx, cy, r: R + 40, fill: accent, opacity: 0.08 }, s.draw);
    el("circle", { cx, cy, r: R, fill: "#0b1a3f", stroke: "#7aa2ff", "stroke-width": 4 }, s.draw);
    const lines = el("g", { fill: "none", stroke: "#7aa2ff", "stroke-width": 2.5, opacity: 0.7 }, s.draw);
    const merid = [], paral = [];
    for (let i = 0; i < 12; i++) merid.push(el("path", {}, lines));
    for (let i = 1; i < 6; i++) paral.push(el("path", {}, lines));
    const pin = el("g", {}, s.draw);
    const pulse = el("circle", { r: 26, fill: "none", stroke: accent, "stroke-width": 5 }, pin);
    el("circle", { r: 16, fill: accent, stroke: "#fff", "stroke-width": 5 }, pin);
    const tilt = 0.35;
    const project = (la, lo, rot) => {
      // Orthographic projection with the globe turned by `rot` and tipped by `tilt`.
      const x0 = Math.cos(la) * Math.sin(lo + rot), y0 = Math.sin(la), z0 = Math.cos(la) * Math.cos(lo + rot);
      const y1 = y0 * Math.cos(tilt) - z0 * Math.sin(tilt), z1 = y0 * Math.sin(tilt) + z0 * Math.cos(tilt);
      return { x: cx + x0 * R, y: cy - y1 * R, z: z1 };
    };
    const curve = (fn, steps) => {
      let d = "", pen = false;
      for (let k = 0; k <= steps; k++) {
        const p = fn(k / steps);
        if (p.z < 0) { pen = false; continue; }
        d += (pen ? " L " : " M ") + p.x.toFixed(1) + " " + p.y.toFixed(1);
        pen = true;
      }
      return d || "M 0 0";
    };
    const end = -lon; // finish with the pin facing the viewer
    const proxy = { rot: end - 2.4 };
    const draw = () => {
      merid.forEach((m, i) => m.setAttribute("d", curve((u) => project(-Math.PI / 2 + u * Math.PI, (i * Math.PI) / 6, proxy.rot), 48)));
      paral.forEach((p, i) => { const la = -Math.PI / 2 + ((i + 1) * Math.PI) / 6; p.setAttribute("d", curve((u) => project(la, u * Math.PI * 2, proxy.rot), 72)); });
      const q = project(lat, lon, proxy.rot);
      pin.setAttribute("transform", `translate(${q.x} ${q.y})`);
      pin.setAttribute("opacity", q.z > 0.05 ? 1 : 0);
    };
    tl.fromTo(proxy, { rot: end - 2.4 }, { rot: end, duration: Math.min(2.6, s.span * 0.7), ease: "power2.inOut", onUpdate: draw }, s.t0 - 0.3);
    tl.fromTo(pulse, { attr: { r: 18 }, opacity: 1 }, { attr: { r: 60 }, opacity: 0, duration: 1.1, repeat: reps(s.span, 1.1), ease: "power2.out" }, s.t0);
    draw();
    const it = a.items[0];
    if (it && it.label) {
      const card = html("div", "anim-pin-label", clip(it.label, 26), root);
      tl.fromTo(card, { opacity: 0, y: 30 }, { opacity: 1, y: 0, duration: 0.4, ease: "back.out(1.7)" }, s.t0 + Math.min(2.6, s.span * 0.7) - 0.2);
    }
  }

  const BUILDERS = { diagram, chart, timeline, scale, stat, orbit, wave, globe };
  window.buildAnim = (root, shot, tl, accent) => (BUILDERS[shot.anim.type] || stat)(root, shot, tl, accent || "#ffd21f");
})();
