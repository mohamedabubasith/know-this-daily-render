// Animated scenes for "anim" shots, in the paper look: drawn and moved entirely in code, every frame a function of
// timeline time (seeked, never played), so renders are identical. One builder per scene type.
// window.buildAnim(root, shot, tl, accent, theme) fills `root` (a 1080x1920 box) and adds tweens to `tl`.
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

  // The paper look: ink on a cream page, one accent colour per film (index.html picks it from the topic).
  // One palette per look (index.html passes the look). ink: lines and text; card: fills, and text on ink or accent;
  // paper: the page; soft, mute: faint lines and quiet text.
  const PALETTES = {
    editorial: { ink: "#1c1a17", card: "#fffaf0", paper: "#f3ecdd", soft: "rgba(28, 26, 23, 0.16)", mute: "rgba(28, 26, 23, 0.66)", display: "Fraunces", weight: 900, text: "Inter" },
    punch: { ink: "#ffffff", card: "#171a2c", paper: "#07080f", soft: "rgba(255, 255, 255, 0.18)", mute: "rgba(255, 255, 255, 0.7)", display: "Anton", weight: 400, text: "Inter" },
    blueprint: { ink: "#eaf6f4", card: "#0b222b", paper: "#06141a", soft: "rgba(234, 246, 244, 0.22)", mute: "rgba(234, 246, 244, 0.7)", display: "Space Grotesk", weight: 700, text: "JetBrains Mono" },
  };
  let T = PALETTES.editorial, LOOK = "editorial";
  let SERIF = {}, SANS = {}; // the look's display and text type, set in buildAnim

  // ---------------------------------------------------------------- shared stage
  // Returns `draw` (the older scenes' drawing space, moved and enlarged to fill the page under the title) and
  // `page` (plain page pixels, for the scenes laid out for this look).
  function stage(root, shot, tl) {
    root.classList.add("anim-stage");
    const svg = el("svg", { viewBox: `0 0 ${W} ${H}`, class: "anim-svg" }, root);
    const draw = el("g", { transform: "translate(-43 110) scale(1.08)" }, svg);
    const page = el("g", {}, svg);
    // Title at the top of the page; the marker runs under its last word.
    const a = shot.anim;
    if (a.title) {
      const text = clip((window.KTD_CALM || ((x) => x))(a.title), 34);
      const t = html("div", "anim-title" + (/[\u0b80-\u0bff]/.test(text) ? " ta" : ""), null, root);
      const words = text.split(/\s+/);
      const last = words.pop();
      if (words.length) t.appendChild(document.createTextNode(words.join(" ") + " "));
      const hl = html("span", "hl", last, t);
      const t0 = shot.start + 0.1;
      tl.fromTo(t, { opacity: 0, y: 30 }, { opacity: 1, y: 0, duration: 0.35, ease: "power3.out" }, t0);
      tl.fromTo(hl, { backgroundSize: "0% 100%" }, { backgroundSize: "100% 100%", duration: 0.45, ease: "power2.out" }, t0 + 0.25);
    }
    return { svg, draw, page, t0: shot.start + 0.35, t1: shot.end, span: shot.end - shot.start };
  }

  // ---------------------------------------------------------------- diagram: a pipeline that plays step by step
  // Every step is on the page from the start, the ones to come drawn faint. The voice walks down them: the step
  // it is on is lit in the accent colour, the ones behind it are plain cards joined by solid arrows.
  function diagram(root, shot, tl, accent) {
    const s = stage(root, shot, tl, accent);
    const items = shot.anim.items.slice(0, 5);
    const n = Math.max(1, items.length);
    const cw = 716, ch = 148, top = 500, shift = 160;
    const gapY = n === 1 ? 0 : Math.min(222, (1300 - top - ch) / (n - 1));
    const pts = items.map((it, i) => ({ x: 84 + (i % 2 ? shift : 0), y: top + i * gapY }));
    const each = Math.max(0.5, (s.span - 0.7) / n); // seconds one step holds the light
    const lit = (i) => s.t0 + i * each;
    // Arrows first, so the cards sit on top of them: dotted until the voice has crossed them.
    pts.slice(1).forEach((p, i) => {
      const q = pts[i];
      const x0 = q.x + cw / 2 + (i % 2 ? -150 : 150), y0 = q.y + ch + 12, x1 = p.x + cw / 2 + (i % 2 ? 150 : -150), y1 = p.y - 6;
      const d = `M ${x0} ${y0} C ${x0} ${(y0 + y1) / 2 + 10}, ${x1} ${(y0 + y1) / 2 - 10}, ${x1} ${y1}`;
      const faint = el("path", { d, fill: "none", stroke: T.soft, "stroke-width": 6, "stroke-linecap": "round", "stroke-dasharray": "3 16", opacity: 0 }, s.page);
      const path = el("path", { d, fill: "none", stroke: accent, "stroke-width": 7, "stroke-linecap": "round", opacity: 0 }, s.page);
      const len = path.getTotalLength();
      path.style.strokeDasharray = `${len}`;
      const at = lit(i + 1) - 0.4;
      tl.fromTo(faint, { opacity: 0 }, { opacity: 1, duration: 0.3 }, shot.start + 0.3 + i * 0.07);
      tl.set(path, { opacity: 1 }, at); // a round-capped line of no length would still show as a speck
      tl.fromTo(path, { strokeDashoffset: len }, { strokeDashoffset: 0, duration: 0.45, ease: "power2.inOut" }, at);
      tl.to(faint, { opacity: 0, duration: 0.2 }, at + 0.3);
    });
    pts.forEach((p, i) => {
      const g = el("g", { transform: `translate(${p.x} ${p.y})` }, s.page);
      const box = el("g", {}, g);
      const shadow = el("rect", { x: 12, y: 12, width: cw, height: ch, rx: 30, fill: T.ink, opacity: 0 }, box);
      const face = el("rect", { x: 0, y: 0, width: cw, height: ch, rx: 30, fill: T.paper, stroke: T.ink, "stroke-width": 4 }, box);
      const badge = el("circle", { cx: 2, cy: 0, r: 40, fill: T.ink }, box);
      const no = el("text", { x: 2, y: 3, "text-anchor": "middle", "dominant-baseline": "middle", fill: T.card, "font-size": 42, ...SERIF }, box);
      no.textContent = String(i + 1);
      const note = clip(items[i].note, 34);
      const label = el("text", { x: 60, y: note ? 68 : 92, fill: T.ink, "font-size": 54, ...SERIF }, box);
      label.textContent = clip(items[i].label, 22);
      const sub = el("text", { x: 62, y: 116, fill: T.ink, "font-size": 33, opacity: 0.8, ...SANS, "font-weight": 600 }, box);
      sub.textContent = note;
      void badge;
      // Arrive faint, all together.
      tl.fromTo(box, { opacity: 0, y: 30 }, { opacity: 0.45, y: 0, duration: 0.22, ease: "power3.out" }, shot.start + 0.05 + i * 0.04);
      // The light arrives on this step...
      tl.to(box, { opacity: 1, scale: 1.03, transformOrigin: "30% 50%", duration: 0.3, ease: "back.out(2)" }, lit(i));
      tl.to(face, { attr: { fill: accent }, duration: 0.25 }, lit(i));
      tl.to([label, sub], { attr: { fill: T.card }, duration: 0.25 }, lit(i));
      tl.to(shadow, { opacity: 1, duration: 0.25 }, lit(i));
      if (i < pts.length - 1) { // ...and moves on: this step stays as a finished card
        tl.to(box, { scale: 1, duration: 0.3, ease: "power2.inOut" }, lit(i + 1) - 0.05);
        tl.to(face, { attr: { fill: T.card }, duration: 0.3 }, lit(i + 1) - 0.05);
        tl.to([label, sub], { attr: { fill: T.ink }, duration: 0.3 }, lit(i + 1) - 0.05);
      }
    });
  }

  // ---------------------------------------------------------------- stepper: the pipeline of the punch look
  // A numbered rail down the left, a card for every step. The rail fills as the voice moves down it.
  function stepper(root, shot, tl, accent) {
    const s = stage(root, shot, tl, accent);
    const items = shot.anim.items.slice(0, 5);
    const n = Math.max(1, items.length);
    const top = 500, gap = 26, rowH = Math.min(180, (770 - (n - 1) * gap) / n), cx = 150, r = Math.min(72, rowH / 2 - 8);
    const yOf = (i) => top + i * (rowH + gap) + rowH / 2;
    const each = Math.max(0.5, (s.span - 0.7) / n), lit = (i) => s.t0 + i * each;
    el("line", { x1: cx, y1: yOf(0), x2: cx, y2: yOf(n - 1), stroke: T.soft, "stroke-width": 14, "stroke-linecap": "round" }, s.page);
    const fill = el("line", { x1: cx, y1: yOf(0), x2: cx, y2: yOf(0), stroke: accent, "stroke-width": 14, "stroke-linecap": "round" }, s.page);
    items.forEach((it, i) => {
      const y = yOf(i), g = el("g", {}, s.page);
      const card = el("rect", { x: 260, y: y - rowH / 2, width: 760, height: rowH, rx: 34, fill: T.card, stroke: "#2b2f47", "stroke-width": 3 }, g);
      const ring = el("circle", { cx, cy: y, r, fill: T.card, stroke: "#2b2f47", "stroke-width": 6 }, g);
      const no = el("text", { x: cx, y: y + 4, "text-anchor": "middle", "dominant-baseline": "middle", fill: T.mute, "font-size": r * 1.15, ...SERIF }, g);
      no.textContent = String(i + 1);
      const note = clip(it.note, 32);
      const label = el("text", { x: 304, y: note ? y - 4 : y + 22, fill: T.ink, "font-size": 60, ...SANS, "font-weight": 900 }, g);
      label.textContent = clip(it.label, 20);
      const sub = el("text", { x: 304, y: y + 48, fill: T.mute, "font-size": 36, ...SANS, "font-weight": 600 }, g);
      sub.textContent = note;
      tl.fromTo(g, { opacity: 0, x: 60 }, { opacity: 0.5, x: 0, duration: 0.22, ease: "power3.out" }, shot.start + 0.05 + i * 0.04);
      tl.to(g, { opacity: 1, duration: 0.25 }, lit(i));
      tl.to(card, { attr: { fill: accent, stroke: accent }, duration: 0.25 }, lit(i));
      tl.to([label, sub], { attr: { fill: T.paper }, duration: 0.25 }, lit(i));
      tl.to(ring, { attr: { stroke: accent }, duration: 0.25 }, lit(i));
      tl.to(no, { attr: { fill: accent }, duration: 0.25 }, lit(i));
      if (i) tl.to(fill, { attr: { y2: y }, duration: 0.4, ease: "power2.inOut" }, lit(i) - 0.3);
      if (i < n - 1) { // done: the number stays lit, the card goes quiet
        tl.to(card, { attr: { fill: T.card, stroke: "#2b2f47" }, duration: 0.3 }, lit(i + 1) - 0.05);
        tl.to(label, { attr: { fill: T.ink }, duration: 0.3 }, lit(i + 1) - 0.05);
        tl.to(sub, { attr: { fill: T.mute }, duration: 0.3 }, lit(i + 1) - 0.05);
        tl.to(ring, { attr: { fill: accent }, duration: 0.3 }, lit(i + 1) - 0.05);
        tl.to(no, { attr: { fill: T.paper }, duration: 0.3 }, lit(i + 1) - 0.05);
      }
    });
  }

  // ---------------------------------------------------------------- wired: the pipeline of the blueprint look
  // Boxes joined by right-angled wires; dots run along a wire once the voice has crossed it.
  function wired(root, shot, tl, accent) {
    const s = stage(root, shot, tl, accent);
    const items = shot.anim.items.slice(0, 5);
    const n = Math.max(1, items.length);
    const bw = 540, bh = 150, top = 540, gapY = n === 1 ? 0 : Math.min(250, (1290 - top - bh) / (n - 1));
    const pts = items.map((it, i) => ({ x: i % 2 ? 480 : 60, y: top + i * gapY }));
    const each = Math.max(0.5, (s.span - 0.7) / n), lit = (i) => s.t0 + i * each;
    pts.slice(1).forEach((p, i) => {
      const q = pts[i], x0 = q.x + bw / 2, y0 = q.y + bh, x1 = p.x + bw / 2, y1 = p.y - 44, ym = (y0 + y1) / 2;
      const d = `M ${x0} ${y0} V ${ym} H ${x1} V ${y1}`;
      el("path", { d, fill: "none", stroke: T.soft, "stroke-width": 4, "stroke-dasharray": "6 14" }, s.page);
      const wire = el("path", { d, fill: "none", stroke: accent, "stroke-width": 5, opacity: 0 }, s.page);
      const len = wire.getTotalLength();
      wire.style.strokeDasharray = `${len}`;
      const at = lit(i + 1) - 0.4;
      tl.set(wire, { opacity: 1 }, at);
      tl.fromTo(wire, { strokeDashoffset: len }, { strokeDashoffset: 0, duration: 0.45, ease: "power2.inOut" }, at);
      for (let k = 0; k < 3; k++) {
        const dot = el("circle", { r: 9, fill: accent, opacity: 0 }, s.page);
        const proxy = { u: 0 }, cyc = 1.5, start = at + 0.45 + (k * cyc) / 3;
        tl.set(dot, { opacity: 1 }, start);
        tl.fromTo(proxy, { u: 0 }, { u: 1, duration: cyc, ease: "none", repeat: reps(s.t1 - start, cyc),
          onUpdate: () => { const pt = wire.getPointAtLength(proxy.u * len); dot.setAttribute("cx", pt.x); dot.setAttribute("cy", pt.y); } }, start);
      }
    });
    pts.forEach((p, i) => {
      const g = el("g", { transform: `translate(${p.x} ${p.y})` }, s.page);
      const box = el("g", {}, g);
      const step = el("text", { x: 0, y: -14, fill: T.mute, "font-size": 26, "letter-spacing": "0.1em", ...SANS, "font-weight": 700 }, box);
      step.textContent = `STEP ${String(i + 1).padStart(2, "0")}`;
      const face = el("rect", { x: 0, y: 0, width: bw, height: bh, rx: 10, fill: T.paper, stroke: T.soft, "stroke-width": 3 }, box);
      const note = clip(it(items, i).note, 26);
      const label = el("text", { x: 30, y: note ? 66 : 90, fill: T.mute, "font-size": 50, ...SERIF }, box);
      label.textContent = clip(it(items, i).label, 18);
      const sub = el("text", { x: 30, y: 112, fill: T.mute, "font-size": 28, ...SANS, "font-weight": 500 }, box);
      sub.textContent = note;
      tl.fromTo(box, { opacity: 0, y: 24 }, { opacity: 1, y: 0, duration: 0.22, ease: "power3.out" }, shot.start + 0.05 + i * 0.04);
      tl.to(face, { attr: { fill: accent, stroke: accent }, duration: 0.25 }, lit(i));
      tl.to([label, sub], { attr: { fill: T.paper }, duration: 0.25 }, lit(i));
      tl.to(step, { attr: { fill: accent }, duration: 0.25 }, lit(i));
      if (i < n - 1) { // done: an outlined box in the accent colour
        tl.to(face, { attr: { fill: T.paper }, duration: 0.3 }, lit(i + 1) - 0.05);
        tl.to(label, { attr: { fill: T.ink }, duration: 0.3 }, lit(i + 1) - 0.05);
        tl.to(sub, { attr: { fill: T.mute }, duration: 0.3 }, lit(i + 1) - 0.05);
      }
    });
  }
  const it = (items, i) => items[i] || { label: "", note: "" };

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
      const label = el("text", { x: 150, y: y, fill: T.ink, ...SANS, "font-size": 38 }, s.draw);
      label.textContent = clip(it.label, 24);
      const track = el("rect", { x: 150, y: y + 22, width: 780, height: 54, rx: 27, fill: T.soft }, s.draw);
      const bar = el("rect", { x: 150, y: y + 22, width: 0, height: 54, rx: 27, fill: best ? accent : T.ink }, s.draw);
      const val = el("text", { x: 170, y: y + 62, fill: T.card, ...SANS, "font-size": 32 }, s.draw);
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
          val.setAttribute("fill", inside ? T.card : T.ink);
        } }, at + 0.1);
      void track;
    });
  }

  // ---------------------------------------------------------------- timeline: years down a glowing line
  function timeline(root, shot, tl, accent) {
    const s = stage(root, shot, tl, accent);
    const items = shot.anim.items.slice(0, 5);
    const top = 470, bottom = 1060, x = 210;
    const line = el("line", { x1: x, y1: top, x2: x, y2: bottom, stroke: T.ink, "stroke-width": 6, "stroke-linecap": "round" }, s.draw);
    tl.fromTo(line, { attr: { y2: top } }, { attr: { y2: bottom }, duration: Math.min(1.6, s.span * 0.5), ease: "power2.inOut" }, s.t0);
    const step = (s.span - 1) / Math.max(1, items.length);
    items.forEach((it, i) => {
      const y = top + ((bottom - top) * (i + 0.5)) / items.length;
      const at = s.t0 + 0.2 + i * Math.min(0.7, step);
      const dot = el("circle", { cx: x, cy: y, r: 22, fill: accent, stroke: T.ink, "stroke-width": 6 }, s.draw);
      const ring = el("circle", { cx: x, cy: y, r: 22, fill: "none", stroke: accent, "stroke-width": 4 }, s.draw);
      const year = el("text", { x: x + 64, y: y - 6, fill: accent, ...SERIF, "font-size": 62 }, s.draw);
      year.textContent = clip(it.label, 14);
      const note = el("text", { x: x + 66, y: y + 46, fill: T.ink, ...SANS, "font-weight": 600, "font-size": 34 }, s.draw);
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
      const c = el("circle", { cx, cy, r: d / 2, fill: big ? accent : T.card, stroke: T.ink, "stroke-width": 5 }, s.draw);
      const label = el("text", { x: cx, y: base + 64, "text-anchor": "middle", fill: T.ink, ...SANS, "font-size": 36 }, s.draw);
      label.textContent = clip(it.label, 16);
      const at = s.t0 + i * 0.45;
      tl.fromTo(c, { scale: 0, transformOrigin: `${cx}px ${base}px` }, { scale: 1, duration: big ? 1.0 : 0.55, ease: big ? "power4.out" : "back.out(1.6)" }, at);
      tl.fromTo(label, { opacity: 0, y: 20 }, { opacity: 1, y: 0, duration: 0.3 }, at + 0.25);
    });
    el("line", { x1: 90, y1: base, x2: W - 90, y2: base, stroke: T.ink, "stroke-width": 5, "stroke-linecap": "round" }, s.draw);
    if (items.length > 1 && items[0].v > 0) {
      const bd = ds[ds.length - 1], bx = x - gap - bd / 2, by = base - bd / 2;
      const ratio = el("text", { x: bx, y: by + bd * 0.12, "text-anchor": "middle", fill: T.card, ...SERIF, "font-size": Math.max(40, Math.min(110, bd * 0.3)) }, s.draw);
      ratio.textContent = `×${fmt(max / items[0].v)}`;
      tl.fromTo(ratio, { opacity: 0, scale: 0.6, transformOrigin: `${bx}px ${by}px` }, { opacity: 1, scale: 1, duration: 0.45, ease: "back.out(2)" }, s.t0 + items.length * 0.45 + 0.4);
    }
  }

  // ---------------------------------------------------------------- stat: the fact page
  // One big number that counts up, its unit, a ruler whose pin travels as it counts, then what the number means
  // beside a round crop of the story's picture.
  function stat(root, shot, tl, accent) {
    const s = stage(root, shot, tl, accent);
    const it = shot.anim.items[0] || { label: "", value: 0 };
    const v = Number(it.value) || 0;
    const unit = (shot.anim.unit || "").trim();
    const pct = unit === "%";
    const x = 80, y = shot.anim.title ? 760 : 560;
    const digits = fmtLike(v, v).length;
    const size = digits > 7 ? 190 : digits > 5 ? 250 : 320;
    const num = el("text", { x: x - 10, y, fill: T.ink, "font-size": size, "letter-spacing": "-0.04em", ...SERIF }, s.page);
    const u = el("text", { x, y: y + 118, fill: accent, "font-size": 100, ...SERIF }, s.page);
    u.textContent = pct ? "" : clip(unit, 16);
    // The ruler: 21 ticks, every fifth one long.
    const ry = y + (pct ? 110 : 230), rw = 920;
    const ruler = el("g", {}, s.page);
    el("line", { x1: x, y1: ry, x2: x + rw, y2: ry, stroke: T.ink, "stroke-width": 6, "stroke-linecap": "round" }, ruler);
    for (let k = 0; k <= 20; k++) el("line", { x1: x + (rw * k) / 20, y1: ry, x2: x + (rw * k) / 20, y2: ry + (k % 5 ? 20 : 40), stroke: T.ink, "stroke-width": 4 }, ruler);
    const pin = el("circle", { cx: x, cy: ry, r: 30, fill: accent, stroke: T.ink, "stroke-width": 6 }, s.page);
    const stop = pct ? Math.min(1, Math.max(0, v / 100)) : 1;
    const proxy = { p: 0 };
    tl.fromTo(ruler, { opacity: 0 }, { opacity: 1, duration: 0.3 }, s.t0 + 0.1);
    tl.fromTo(pin, { scale: 0, transformOrigin: `${x}px ${ry}px` }, { scale: 1, duration: 0.3, ease: "back.out(2)" }, s.t0 + 0.2);
    tl.fromTo(proxy, { p: 0 }, { p: 1, duration: 1.7, ease: "power2.out",
      onUpdate: () => { num.textContent = fmtLike(v * proxy.p, v) + (pct ? "%" : ""); pin.setAttribute("cx", x + rw * stop * proxy.p); } }, s.t0);
    tl.fromTo(u, { opacity: 0, y: 20 }, { opacity: 1, y: 0, duration: 0.35 }, s.t0 + 0.4);
    // What the number means, and the picture it belongs to.
    const ny = ry + 110;
    if (it.label) {
      const note = html("div", "anim-note", clip(it.label, 44), root);
      note.style.top = `${ny}px`;
      if (!shot.pic) note.style.width = "920px";
      tl.fromTo(note, { opacity: 0, y: 24 }, { opacity: 1, y: 0, duration: 0.4, ease: "power3.out" }, s.t0 + 1.0);
    }
    if (shot.pic) {
      const img = html("img", "anim-pic", null, root);
      img.src = shot.pic;
      Object.assign(img.style, { left: "672px", top: `${ny - 10}px` });
      tl.fromTo(img, { opacity: 0, scale: 0.6 }, { opacity: 1, scale: 1, duration: 0.5, ease: "back.out(1.6)" }, s.t0 + 0.8);
    }
  }

  // ---------------------------------------------------------------- stat of the punch look: one giant number, a stamp
  function statPunch(root, shot, tl, accent) {
    const s = stage(root, shot, tl, accent);
    const item = shot.anim.items[0] || { label: "", value: 0 };
    const v = Number(item.value) || 0, unit = (shot.anim.unit || "").trim(), pct = unit === "%";
    const digits = fmtLike(v, v).length, size = digits > 7 ? 230 : digits > 5 ? 320 : 420;
    const y = 880;
    const num = el("text", { x: W / 2, y, "text-anchor": "middle", fill: accent, "font-size": size, ...SERIF }, s.page);
    const u = el("text", { x: W / 2, y: y + 150, "text-anchor": "middle", fill: T.ink, "font-size": 140, ...SERIF }, s.page);
    u.textContent = pct ? "" : clip(unit, 14).toUpperCase();
    const proxy = { p: 0 };
    tl.fromTo(num, { scale: 0.7, opacity: 0, transformOrigin: `${W / 2}px ${y - 120}px` }, { scale: 1, opacity: 1, duration: 0.4, ease: "back.out(1.8)" }, s.t0 - 0.1);
    tl.fromTo(proxy, { p: 0 }, { p: 1, duration: 1.5, ease: "power2.out", onUpdate: () => { num.textContent = fmtLike(v * proxy.p, v) + (pct ? "%" : ""); } }, s.t0);
    tl.fromTo(u, { opacity: 0, y: 30 }, { opacity: 1, y: 0, duration: 0.35 }, s.t0 + 0.5);
    if (item.label) { // slammed on like a rubber stamp
      const stamp = html("div", "anim-stamp", clip(item.label, 44), root);
      stamp.style.top = `${y + 190}px`;
      tl.fromTo(stamp, { opacity: 0, scale: 2.2 }, { opacity: 1, scale: 1, duration: 0.3, ease: "power4.in" }, s.t0 + 1.3);
    }
  }

  // ---------------------------------------------------------------- stat of the blueprint look: a dial and a data row
  function statDial(root, shot, tl, accent) {
    const s = stage(root, shot, tl, accent);
    const item = shot.anim.items[0] || { label: "", value: 0 };
    const v = Number(item.value) || 0, unit = (shot.anim.unit || "").trim(), pct = unit === "%";
    const cx = W / 2, cy = 800, R = 330, N = 60;
    const stop = pct ? Math.min(1, Math.max(0.02, v / 100)) : 0.8;
    const ticks = [];
    for (let k = 0; k < N; k++) {
      const a = -Math.PI * 1.25 + (k / (N - 1)) * Math.PI * 1.5, long = k % 5 === 0;
      const r0 = R - (long ? 46 : 26);
      ticks.push(el("line", { x1: cx + Math.cos(a) * r0, y1: cy + Math.sin(a) * r0, x2: cx + Math.cos(a) * R, y2: cy + Math.sin(a) * R, stroke: T.soft, "stroke-width": long ? 7 : 4 }, s.page));
    }
    const digits = fmtLike(v, v).length;
    const num = el("text", { x: cx, y: cy + 40, "text-anchor": "middle", fill: T.ink, "font-size": digits > 6 ? 130 : 180, "letter-spacing": "-0.04em", ...SERIF }, s.page);
    const u = el("text", { x: cx, y: cy + 120, "text-anchor": "middle", fill: accent, "font-size": 42, "letter-spacing": "0.2em", ...SANS, "font-weight": 700 }, s.page);
    u.textContent = pct ? "" : clip(unit, 18).toUpperCase();
    const proxy = { p: 0 };
    tl.fromTo(proxy, { p: 0 }, { p: 1, duration: 1.7, ease: "power2.out", onUpdate: () => {
      num.textContent = fmtLike(v * proxy.p, v) + (pct ? "%" : "");
      const on = Math.round(N * stop * proxy.p);
      ticks.forEach((t, k) => t.setAttribute("stroke", k < on ? accent : T.soft));
    } }, s.t0);
    tl.fromTo(u, { opacity: 0 }, { opacity: 1, duration: 0.3 }, s.t0 + 0.4);
    if (item.label) {
      const row = html("div", "anim-row", null, root);
      html("b", null, "NOTE", row);
      html("span", null, clip(item.label, 60), row);
      row.style.top = `${cy + R - 60}px`;
      tl.fromTo(row, { opacity: 0, y: 24 }, { opacity: 1, y: 0, duration: 0.4, ease: "power3.out" }, s.t0 + 1.0);
    }
  }

  // ---------------------------------------------------------------- orbit: bodies circling a centre
  function orbit(root, shot, tl, accent) {
    const s = stage(root, shot, tl, accent);
    const items = shot.anim.items.slice(0, 5);
    const cx = W / 2, cy = 800;
    const sun = el("circle", { cx, cy, r: 90, fill: accent }, s.draw);
    el("circle", { cx, cy, r: 150, fill: accent, opacity: 0.18 }, s.draw);
    const centre = el("text", { x: cx, y: cy + 12, "text-anchor": "middle", fill: T.card, ...SANS, "font-size": 30 }, s.draw);
    centre.textContent = clip(shot.anim.variant || "", 10);
    tl.fromTo(sun, { scale: 0, transformOrigin: `${cx}px ${cy}px` }, { scale: 1, duration: 0.6, ease: "back.out(1.7)" }, s.t0 - 0.1);
    items.forEach((it, i) => {
      const r = 180 + i * 78;
      const ring = el("ellipse", { cx, cy, rx: r, ry: r * 0.42, fill: "none", stroke: T.soft, "stroke-width": 4 }, s.draw);
      const body = el("circle", { r: 20 + (i % 3) * 6, fill: [T.ink, accent, "#8a7f6a", T.ink, accent][i], stroke: T.paper, "stroke-width": 4 }, s.draw);
      const label = el("text", { "text-anchor": "middle", fill: T.ink, ...SANS, "font-size": 30 }, s.draw);
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
      const big = el("text", { x: W / 2, y: 560, "text-anchor": "middle", fill: T.ink, ...SERIF, "font-size": 92 }, s.draw);
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
    el("circle", { cx, cy, r: R, fill: T.card, stroke: T.ink, "stroke-width": 5 }, s.draw);
    const land = el("path", { fill: T.ink, opacity: 0.82 }, s.draw); // the continents (assets/land.js), under the grid lines
    const lines = el("g", { fill: "none", stroke: T.mute, "stroke-width": 2, opacity: 0.45 }, s.draw);
    const merid = [], paral = [];
    for (let i = 0; i < 12; i++) merid.push(el("path", {}, lines));
    for (let i = 1; i < 6; i++) paral.push(el("path", {}, lines));
    const pin = el("g", {}, s.draw);
    const pulse = el("circle", { r: 26, fill: "none", stroke: accent, "stroke-width": 5 }, pin);
    el("circle", { r: 16, fill: accent, stroke: T.card, "stroke-width": 6 }, pin);
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
    // Land rings, each point turned with the globe. Where a coast goes round to the far side, the outline follows
    // the rim of the disc (the short way) until the coast comes back into sight.
    const LAND = window.KTD_LAND || [];
    const rad = Math.PI / 180;
    const ang = (p) => Math.atan2(p.y - cy, p.x - cx);
    const landPath = () => {
      let d = "";
      for (const ring of LAND) {
        const n = ring.length / 2, P = new Array(n);
        let first = -1;
        for (let k = 0; k < n; k++) {
          P[k] = project(ring[2 * k + 1] * rad, ring[2 * k] * rad, proxy.rot);
          if (first < 0 && P[k].z >= 0) first = k;
        }
        if (first < 0) continue; // all of it is on the far side
        let seg = "", out = null; // out: the rim angle where the coast went out of sight
        for (let j = 0; j <= n; j++) {
          const pt = P[(first + j) % n];
          if (pt.z < 0) { if (out === null) out = ang(pt); continue; }
          if (out !== null) {
            let da = ang(pt) - out;
            while (da > Math.PI) da -= 2 * Math.PI;
            while (da < -Math.PI) da += 2 * Math.PI;
            const steps = Math.max(1, Math.ceil(Math.abs(da) / 0.1));
            for (let t = 0; t <= steps; t++) { const a = out + (da * t) / steps; seg += ` L ${(cx + Math.cos(a) * R).toFixed(1)} ${(cy + Math.sin(a) * R).toFixed(1)}`; }
            out = null;
          }
          seg += (seg ? " L " : " M ") + pt.x.toFixed(1) + " " + pt.y.toFixed(1);
        }
        d += seg + " Z";
      }
      return d || "M 0 0";
    };
    const draw = () => {
      land.setAttribute("d", landPath());
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
  const OWN = { punch: { diagram: stepper, stat: statPunch }, blueprint: { diagram: wired, stat: statDial } }; // scenes a look draws its own way
  window.buildAnim = (root, shot, tl, accent, theme, look) => {
    LOOK = PALETTES[look] ? look : "editorial";
    T = PALETTES[LOOK];
    SERIF = { "font-family": `${T.display}, Noto Sans Tamil`, "font-weight": T.weight };
    SANS = { "font-family": `${T.text}, Noto Sans Tamil`, "font-weight": 800 };
    const build = (OWN[LOOK] || {})[shot.anim.type] || BUILDERS[shot.anim.type] || (OWN[LOOK] || {}).stat || stat;
    return build(root, shot, tl, accent || "#c2491d");
  };
})();
