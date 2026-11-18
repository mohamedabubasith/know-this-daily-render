// Sample lesson (AI for Everyone, part 4): one station per line. Each entry builds its props into g and returns
// update(lt), called every frame with the seconds since its line started.
export default [
  // 0: AI knows a lot. Who taught it?
  (g, K) => {
    const { THREE, gloss, metal, rbox, t3, label, docTex, soft, pop, back, out3, io3, sstep, cl, rnd, chip, TEAL, SAF, CORAL, LAV, CREAM, INK, GOLD, GREEN } = K;
    const c = chip(); g.add(c);
    const ring = new THREE.Mesh(new THREE.TorusGeometry(1.75, 0.022, 16, 160), new THREE.MeshStandardMaterial({ color: 0x0, emissive: 0x4FD1C5, emissiveIntensity: 2 })); ring.position.set(0, 0.4, -0.3); g.add(ring);
    const qs = [SAF, CORAL, LAV].map(col => { const q = t3("?", 0.9, col, 0.25); g.add(q); return q; });
    return (lt) => {
      pop(c, lt, 0.0, 0.8); c.rotation.y = -0.35 + 0.25 * Math.sin(lt * 0.7); c.rotation.x = 0.1 * Math.sin(lt * 0.9); c.position.y = 0.4 + 0.08 * Math.sin(lt * 1.4);
      ring.material.emissiveIntensity = 2.2 + 1.2 * Math.sin(lt * 3); ring.rotation.z = lt * 0.4; pop(ring, lt, 0.3, 0.9);
      qs.forEach((q, k) => { pop(q, lt, 2.2 + k * 0.22, 0.5); const a = lt * 0.55 + k * 2.1; q.position.set(Math.cos(a) * 2.5, 0.4 + 1.1 * Math.sin(a * 1.2 + k), Math.sin(a) * 1.2 + 0.4); q.rotation.y = Math.sin(lt + k) * 0.6; });
    };
  },
  // 1: chatbot words -> where did it learn?
  (g, K) => {
    const { THREE, gloss, metal, rbox, t3, label, docTex, soft, pop, back, out3, io3, sstep, cl, rnd, chip, TEAL, SAF, CORAL, LAV, CREAM, INK, GOLD, GREEN } = K;
    const bub = new THREE.Group(); g.add(bub); bub.position.y = 0.45;
    bub.add(rbox(5.4, 2.7, 0.22, 0.45, gloss(0xC9DCD9, { roughness: 0.3 })));
    const tail = new THREE.Mesh(new THREE.ConeGeometry(0.42, 0.9, 4), gloss(0xC9DCD9)); tail.rotation.z = Math.PI * 0.82; tail.position.set(-1.9, -1.45, 0); bub.add(tail);
    const words = [["வானம்", TEAL, 1.6], ["நீல", SAF, 1.15], ["நிறம்", CORAL, 1.45], ["…", LAV, 0.8]];
    const xs = [-1.55, 0.05, 1.45, 0.05]; const ys = [0.5, 0.5, 0.5, -0.5];
    const tiles = words.map(([w, col, wd], k) => { const t = new THREE.Group(); t.add(rbox(wd, 0.72, 0.28, 0.34, gloss(col))); const l = label(w, { w: wd, h: 0.72, fill: 0.7 }); l.position.z = 0.15; t.add(l); t.position.set(xs[k] - (k === 3 ? 1.4 : 0), ys[k], 0.2); t.userData.y = ys[k]; bub.add(t); return t; });
    const qb = new THREE.Group(); qb.add(new THREE.Mesh(new THREE.SphereGeometry(0.62, 48, 32), gloss(INK))); const qq = t3("?", 0.62, SAF, 0.12); qq.position.z = 0.55; qb.add(qq); qb.position.set(2.6, -1.0, 0.6); g.add(qb);
    return (lt) => {
      pop(bub, lt, 0, 0.7); bub.rotation.y = -0.12 + 0.05 * Math.sin(lt * 0.6);
      tiles.forEach((t, k) => { const e = out3((lt - 0.5 - k * 0.42) / 0.5); t.visible = e > 0; t.position.y = t.userData.y + (1 - e) * 1.2; t.rotation.x = (1 - e) * -0.9; t.scale.setScalar(Math.max(1e-4, back((lt - 0.5 - k * 0.42) / 0.5))); });
      pop(qb, lt, 3.35, 0.6); qb.rotation.y = 0.5 * Math.sin(lt * 1.5); qb.position.y = -1.0 + 0.1 * Math.sin(lt * 2);
    };
  },
  // 2: training data streams into the model
  (g, K) => {
    const { THREE, gloss, metal, rbox, t3, label, docTex, soft, pop, back, out3, io3, sstep, cl, rnd, chip, TEAL, SAF, CORAL, LAV, CREAM, INK, GOLD, GREEN } = K;
    const c = chip(0.62); g.add(c);
    const ND = 60, A = [], RAD = [], Y0 = [], ROT = [];
    for (let k = 0; k < ND; k++) { A.push(rnd() * 6.28); RAD.push(3.2 + rnd() * 2.4); Y0.push(rnd() * 3.2 - 0.6); ROT.push(rnd() - 0.5); }
    const docs = new THREE.InstancedMesh(new THREE.PlaneGeometry(0.78, 1.0), new THREE.MeshStandardMaterial({ map: docTex("#1F9A93"), side: THREE.DoubleSide, roughness: 0.5 }), ND); docs.castShadow = true; g.add(docs);
    const tag = label("டிரெய்னிங் டேட்டா", { w: 3.6, h: 0.78, bg: "#F2B544", color: "#1c1f26" }); tag.position.set(0, 1.55, 0.4); g.add(tag);
    return (lt) => {
      pop(c, lt, 0, 0.6); c.position.y = -0.55; c.rotation.y = 0.25 * Math.sin(lt * 0.8);
      const d = new THREE.Object3D(); let inside = 0;
      for (let k = 0; k < ND; k++) {
        const q = cl((lt - 0.15 - k * 0.045) / 1.5), e = q * q * (3 - 2 * q), a = A[k] + e * 2.4, r = RAD[k] * (1 - e);
        d.position.set(Math.cos(a) * r, -0.55 + Y0[k] * (1 - e) + 0.15, Math.sin(a) * r * 0.5 + 0.3); d.rotation.set(0.4 * (1 - e), a + 1.2, ROT[k] * (1 - e)); d.scale.setScalar(q <= 0 || q >= 1 ? 1e-4 : 0.55 * (1 - 0.7 * e));
        if (q >= 1) inside++; d.updateMatrix(); docs.setMatrixAt(k, d.matrix);
      }
      docs.instanceMatrix.needsUpdate = true;
      c.children[1].material.emissive.setHex(0x4FD1C5); c.children[1].material.emissiveIntensity = 0.15 + 0.5 * (inside / ND) * (0.6 + 0.4 * Math.sin(lt * 9));
      pop(tag, lt, 1.6, 0.6);
    };
  },
  // 3: library — the model reads a lot
  (g, K) => {
    const { THREE, gloss, metal, rbox, t3, label, docTex, soft, pop, back, out3, io3, sstep, cl, rnd, chip, TEAL, SAF, CORAL, LAV, CREAM, INK, GOLD, GREEN } = K;
    const wood = new THREE.MeshStandardMaterial({ color: 0x7a4f30, roughness: 0.55 });
    const cols = [TEAL, SAF, CORAL, LAV, 0x3B7DD8, CREAM];
    const books = [];
    for (let r = 0; r < 3; r++) {
      const sh = rbox(6.6, 0.14, 0.9, 0.05, wood); sh.position.set(0, -1.3 + r * 1.1, 0); g.add(sh);
      let x = -3.05; for (let k = 0; k < 12; k++) { const w = 0.34 + rnd() * 0.16, h = 0.75 + rnd() * 0.3, col = cols[Math.floor(rnd() * cols.length)];
        const b = rbox(w, h, 0.62, 0.04, gloss(col, { emissive: 0xffe2a8, emissiveIntensity: 0 })); b.position.set(x + w / 2, -1.23 + r * 1.1 + h * 0.85 / 2, 0); b.scale.y = 0.85; b.userData.z = 0; b.rotation.z = k === 11 ? -0.12 : 0; g.add(b); books.push(b); x += w + 0.06; }
    }
    const sweep = new THREE.Mesh(new THREE.PlaneGeometry(0.5, 4.2), new THREE.MeshBasicMaterial({ map: soft, color: 0xffe2a8, transparent: true, opacity: 0, blending: THREE.AdditiveBlending, depthWrite: false, toneMapped: false })); sweep.position.set(0, -0.15, 0.55); g.add(sweep);
    return (lt) => {
      books.forEach((b, k) => { const e = out3((lt - 0.1 - (k % 12) * 0.05 - Math.floor(k / 12) * 0.18) / 0.55); b.visible = e > 0; b.position.z = b.userData.z - (1 - e) * 1.5; b.rotation.x = -(1 - e) * 0.5; });
      const sx = -3.4 + 6.8 * cl((lt - 1.4) / 2.6); sweep.position.x = sx; sweep.material.opacity = 0.75 * Math.sin(cl((lt - 1.4) / 2.6) * Math.PI);
      books.forEach(b => { const d = Math.abs(b.position.x - sx); b.material.emissiveIntensity = d < 0.5 ? (1 - d / 0.5) * 0.9 * sweep.material.opacity : 0; });
    };
  },
  // 4: one book only
  (g, K) => {
    const { THREE, gloss, metal, rbox, t3, label, docTex, soft, pop, back, out3, io3, sstep, cl, rnd, chip, TEAL, SAF, CORAL, LAV, CREAM, INK, GOLD, GREEN } = K;
    const one = new THREE.Group(); one.position.x = -1.9; g.add(one);
    one.add(rbox(1.3, 1.8, 0.32, 0.06, gloss(CORAL))); const sp = rbox(0.14, 1.8, 0.34, 0.04, gloss(0xb8473a)); sp.position.x = -0.58; one.add(sp);
    const badge = t3("1", 0.55, SAF, 0.18); badge.position.set(-1.0, 1.65, 0.4); g.add(badge);
    const grey = []; for (let k = 0; k < 12; k++) { const b = rbox(0.42, 0.85, 0.3, 0.04, gloss(0x4a5563, { roughness: 0.5 })); b.position.set(0.55 + (k % 4) * 0.62, -0.95 + Math.floor(k / 4) * 1.0 + 0.42, 0); g.add(b); grey.push(b); }
    const no = new THREE.Mesh(new THREE.TorusGeometry(1.55, 0.08, 16, 120), new THREE.MeshStandardMaterial({ color: 0, emissive: CORAL, emissiveIntensity: 2 }));
    const slash = new THREE.Mesh(new THREE.BoxGeometry(3.1, 0.15, 0.08), no.material); slash.rotation.z = -Math.PI / 4; no.add(slash); no.position.set(1.48, 0.55, 0.45); g.add(no);
    return (lt) => {
      pop(one, lt, 0.1, 0.7); one.rotation.y = 0.35 * Math.sin(lt * 0.9) - 0.2; one.position.y = 0.3 + 0.08 * Math.sin(lt * 1.6);
      pop(badge, lt, 0.7, 0.5);
      grey.forEach((b, k) => { const e = out3((lt - 1.0 - k * 0.04) / 0.5); b.visible = e > 0; b.scale.setScalar(Math.max(1e-4, e)); });
      pop(no, lt, 2.3, 0.5); no.material.emissiveIntensity = 2 + Math.sin(lt * 6);
    };
  },
  // 5: Amma's one curry, every day
  (g, K) => {
    const { THREE, gloss, metal, rbox, t3, label, docTex, soft, pop, back, out3, io3, sstep, cl, rnd, chip, TEAL, SAF, CORAL, LAV, CREAM, INK, GOLD, GREEN } = K;
    const pot = new THREE.Group(); pot.position.y = -0.3; pot.scale.setScalar(0.85); g.add(pot);
    const prof = [[0, 0], [0.9, 0], [1.2, 0.1], [1.38, 0.45], [1.45, 0.95], [1.52, 1.05]].map(([x, y]) => new THREE.Vector2(x, y));
    const body = new THREE.Mesh(new THREE.LatheGeometry(prof, 64), new THREE.MeshStandardMaterial({ color: 0xc27a45, metalness: 1, roughness: 0.26, side: THREE.DoubleSide })); body.castShadow = true; pot.add(body);
    const curry = new THREE.Mesh(new THREE.CircleGeometry(1.4, 64), new THREE.MeshStandardMaterial({ color: 0xE07A1F, roughness: 0.45 })); curry.rotation.x = -Math.PI / 2; curry.position.y = 0.88; pot.add(curry);
    for (const s of [-1, 1]) { const h = new THREE.Mesh(new THREE.TorusGeometry(0.22, 0.05, 12, 32, Math.PI), body.material); h.position.set(s * 1.55, 0.85, 0); h.rotation.z = s * -Math.PI / 2; pot.add(h); }
    const steam = Array.from({ length: 18 }, () => { const s = new THREE.Sprite(new THREE.SpriteMaterial({ map: soft, color: 0xffffff, transparent: true, depthWrite: false })); g.add(s); return s; });
    const names = ["திங்கள்", "செவ்வாய்", "புதன்", "வியாழன்", "வெள்ளி", "சனி", "ஞாயிறு"];
    const days = names.map((n, k) => { const d = new THREE.Group(); d.add(rbox(0.92, 0.86, 0.1, 0.1, gloss(0xd9d2c6))); const l = label(n, { w: 0.86, h: 0.32, color: "#1c1f26", fill: 0.86 }); l.position.set(0, 0.2, 0.06); d.add(l);
      const dot = new THREE.Mesh(new THREE.SphereGeometry(0.14, 24, 16), gloss(0xE07A1F)); dot.position.set(0, -0.15, 0.08); dot.scale.z = 0.4; d.add(dot);
      const a = (k - 3) * 0.1; d.scale.setScalar(0.74); d.position.set(Math.sin(a) * 7, -1.15, 1.2 - (1 - Math.cos(a)) * 7); d.rotation.y = -a; g.add(d); return d; });
    return (lt) => {
      pop(pot, lt, 0, 0.7); pot.rotation.y = lt * 0.2;
      steam.forEach((s, k) => { const ph = (lt * 0.55 + k / steam.length) % 1; s.position.set(Math.sin(k * 7.1 + lt) * 0.45 * ph + (k % 5 - 2) * 0.18, 0.7 + ph * 2.4, Math.cos(k * 3.3) * 0.3); s.material.opacity = 0.32 * Math.sin(ph * Math.PI) * cl(lt / 0.8); s.scale.setScalar(0.5 + ph * 1.1); });
      days.forEach((d, k) => { pop(d, lt, 0.9 + k * 0.17, 0.5); d.position.y = -1.15 + 0.05 * Math.sin(lt * 2 + k); });
    };
  },
  // 6: one-sided examples tip the scale -> wrong answer
  (g, K) => {
    const { THREE, gloss, metal, rbox, t3, label, docTex, soft, pop, back, out3, io3, sstep, cl, rnd, chip, TEAL, SAF, CORAL, LAV, CREAM, INK, GOLD, GREEN } = K;
    const sc = new THREE.Group(); sc.position.y = -0.3; g.add(sc); const dark = gloss(0x2a3240, { roughness: 0.4 });
    const post = rbox(0.18, 2.9, 0.18, 0.06, dark); post.position.y = -0.5; sc.add(post); const base = rbox(1.8, 0.16, 0.9, 0.06, dark); base.position.y = -1.9; sc.add(base);
    const beam = new THREE.Group(); beam.position.y = 0.95;  sc.add(beam); beam.add(rbox(5.2, 0.13, 0.13, 0.05, metal(GOLD)));
    const pan = (x) => { const p = new THREE.Group(); p.position.x = x; beam.add(p); const rod = rbox(0.04, 1.2, 0.04, 0.015, metal(GOLD)); rod.position.y = -0.6; p.add(rod); const d = new THREE.Mesh(new THREE.CylinderGeometry(0.85, 0.65, 0.12, 48), metal(GOLD)); d.position.y = -1.2; d.castShadow = true; p.add(d); return p; };
    const panL = pan(-2.4), panR = pan(2.4);
    const ballsL = [[-0.4, 0], [0, 0], [0.4, 0], [-0.2, 0.36], [0.2, 0.36], [0, 0.7]].map(([x, y]) => { const b = new THREE.Mesh(new THREE.SphereGeometry(0.2, 32, 24), gloss(TEAL)); b.castShadow = true; b.position.set(x, -0.94 + y, 0); panL.add(b); return b; });
    const ballR = new THREE.Mesh(new THREE.SphereGeometry(0.2, 32, 24), gloss(SAF)); ballR.position.y = -0.94; panR.add(ballR);
    const bad = new THREE.Group(); bad.add(new THREE.Mesh(new THREE.SphereGeometry(0.55, 48, 32), gloss(CORAL)));
    for (const r of [1, -1]) { const x = rbox(0.6, 0.13, 0.1, 0.05, gloss(0xffffff)); x.rotation.z = r * Math.PI / 4; x.position.z = 0.52; bad.add(x); }
    bad.position.set(2.6, 1.55, 0.6); g.add(bad);
    return (lt) => {
      pop(sc, lt, 0, 0.7); const tilt = 0.24 * out3((lt - 1.0) / 1.1) + 0.02 * Math.sin(lt * 3) * cl(lt - 1.0);
      beam.rotation.z = tilt; panL.rotation.z = -tilt; panR.rotation.z = -tilt;
      ballsL.forEach((b, k) => pop(b, lt, 0.3 + k * 0.08, 0.4)); pop(ballR, lt, 0.75, 0.4);
      pop(bad, lt, 3.2, 0.5); bad.rotation.y = 0.3 * Math.sin(lt * 2);
    };
  },
  // 7: confidently wrong
  (g, K) => {
    const { THREE, gloss, metal, rbox, t3, label, docTex, soft, pop, back, out3, io3, sstep, cl, rnd, chip, TEAL, SAF, CORAL, LAV, CREAM, INK, GOLD, GREEN } = K;
    K.shake(2.1);  // the stamp lands
    const bub = new THREE.Group(); bub.position.y = 0.55; g.add(bub); bub.add(rbox(5.2, 2.2, 0.24, 0.5, gloss(0xC9DCD9)));
    const eq = t3("2 + 2 = 5", 0.62, INK, 0.14); eq.position.z = 0.2; bub.add(eq);
    const stamp = label("100% உறுதி!", { w: 3.3, h: 1.0, bg: "#E8604C", color: "#fff", fill: 0.78 }); stamp.material.depthTest = false; stamp.renderOrder = 5; stamp.position.set(1.2, -0.85, 0.9); stamp.rotation.z = -0.16; g.add(stamp);
    return (lt) => {
      pop(bub, lt, 0, 0.6); bub.rotation.y = -0.1 + 0.05 * Math.sin(lt * 0.8);
      const e = cl((lt - 1.9) / 0.22); stamp.visible = lt > 1.9; stamp.scale.setScalar(Math.max(1e-4, 2.4 - 1.4 * e * e)); stamp.material.opacity = cl((lt - 1.9) / 0.12);
    };
  },
  // 8: double-check with a second source
  (g, K) => {
    const { THREE, gloss, metal, rbox, t3, label, docTex, soft, pop, back, out3, io3, sstep, cl, rnd, chip, TEAL, SAF, CORAL, LAV, CREAM, INK, GOLD, GREEN } = K;
    const card = (x, stripe) => { const c = new THREE.Group(); c.position.x = x; c.add(rbox(2.3, 2.95, 0.12, 0.14, gloss(0xd9d4ca))); const f = new THREE.Mesh(new THREE.PlaneGeometry(2.1, 2.7), new THREE.MeshStandardMaterial({ map: docTex(stripe), transparent: true, color: 0xcfcac0 })); f.position.z = 0.065; c.add(f); g.add(c); return c; };
    const cA = card(-1.45, "#1F9A93"), cB = card(1.45, "#8A7BEA");
    const mag = new THREE.Group(); g.add(mag);
    mag.add(new THREE.Mesh(new THREE.TorusGeometry(0.62, 0.09, 24, 80), metal(0x2a3240, 0.3)));
    mag.add(new THREE.Mesh(new THREE.CircleGeometry(0.6, 48), new THREE.MeshPhysicalMaterial({ color: 0xdff6ff, transmission: 1, roughness: 0.04, thickness: 0.4, ior: 1.45, transparent: true, opacity: 0.6 })));
    const hd = rbox(0.18, 1.1, 0.18, 0.08, gloss(INK)); hd.position.set(0.62, -0.9, 0); hd.rotation.z = 0.6; mag.add(hd);
    const okBadge = (x) => { const b = new THREE.Group(); b.add(new THREE.Mesh(new THREE.SphereGeometry(0.4, 40, 28), gloss(GREEN))); const a = rbox(0.22, 0.09, 0.08, 0.03, gloss(0xffffff)); a.position.set(-0.1, -0.04, 0.38); a.rotation.z = -0.8; const c2 = rbox(0.44, 0.09, 0.08, 0.03, gloss(0xffffff)); c2.position.set(0.08, 0.04, 0.38); c2.rotation.z = 0.9; b.add(a, c2); b.position.set(x + 0.95, 1.35, 0.4); g.add(b); return b; };
    const okA = okBadge(-1.45), okB = okBadge(1.45);
    return (lt) => {
      pop(cA, lt, 0, 0.55); pop(cB, lt, 0.3, 0.55);
      const m = io3((lt - 0.6) / 2.0); mag.position.set(-1.45 + 2.9 * m, 0.35 + 0.35 * Math.sin(lt * 2.4), 0.9); mag.rotation.z = -0.5 + 0.1 * Math.sin(lt * 2); pop(mag, lt, 0.4, 0.5);
      pop(okA, lt, 1.2, 0.45); pop(okB, lt, 2.9, 0.45);
    };
  },
  // 9: compare prices -> follow for part 5
  (g, K) => {
    const { THREE, gloss, metal, rbox, t3, label, docTex, soft, pop, back, out3, io3, sstep, cl, rnd, chip, TEAL, SAF, CORAL, LAV, CREAM, INK, GOLD, GREEN } = K;
    const shape = new THREE.Shape(); shape.moveTo(0, 0); shape.lineTo(1.25, 0); shape.lineTo(1.75, 0.5); shape.lineTo(1.25, 1); shape.lineTo(0, 1); shape.closePath();
    const hole = new THREE.Path(); hole.absarc(1.33, 0.5, 0.09, 0, Math.PI * 2, true); shape.holes.push(hole);
    const tg = new THREE.ExtrudeGeometry(shape, { depth: 0.16, bevelEnabled: true, bevelThickness: 0.04, bevelSize: 0.04, bevelSegments: 4 }); tg.center();
    const tags = [["₹42", TEAL], ["₹40", SAF], ["₹45", LAV]].map(([p, col], k) => { const t = new THREE.Group(); const m = new THREE.Mesh(tg, gloss(col, { emissive: col, emissiveIntensity: 0 })); m.castShadow = true; t.add(m); const l = label(p, { w: 1.1, h: 0.62, fam: "Inter", weight: 700, color: k === 1 ? "#1c1f26" : "#fff" }); l.position.set(-0.22, 0, 0.15); t.add(l); t.position.set(-2.0 + k * 2.0, 0.75, 0); g.add(t); return t; });
    const cta = new THREE.Group(); cta.add(rbox(3.6, 0.95, 0.26, 0.46, gloss(INK))); const cl2 = label("பாகம் 5  →", { w: 3.2, h: 0.85, color: "#F2B544", fill: 0.7 }); cl2.position.z = 0.15; cta.add(cl2); cta.position.set(0, -0.75, 0.6); g.add(cta);
    return (lt) => {
      tags.forEach((t, k) => { pop(t, lt, 0.15 + k * 0.2, 0.55); t.rotation.y = 0.25 * Math.sin(lt * 1.1 + k); });
      const w = out3((lt - 1.4) / 0.6); tags[1].position.y = 0.75 + 0.4 * w; tags[1].scale.setScalar(Math.max(1e-4, tags[1].userData.s * (lt > 0.35 ? back((lt - 0.35) / 0.55) : 0) * (1 + 0.15 * w)));
      tags[1].children[0].material.emissiveIntensity = 0.35 * w;
      const e = pop(cta, lt, 2.5, 0.6); if (e >= 1) cta.scale.setScalar(1 + 0.035 * Math.sin((lt - 3.1) * 6));
    };
  },
];
