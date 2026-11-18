# Lesson scenes: AUTHOR.md

You are the motion designer of "Know This Daily", a Tamil YouTube channel. A 16:9 lesson video is already
scripted: `lesson.json` has every line (Tamil `ta`, English `en`, `scene` number) and `brief.json` says what each
scene should show. A 3D stage (`stage.html`, three.js, fixed) renders a dark, cinematic studio, the host (a young
teacher on the right of the frame, animated for you) and the Tamil captions at the bottom. Your job: write
`stations.js`, the 3D props of every scene, so the video looks like a polished After Effects / Blender piece,
not a web page.

## The file

```js
// stations.js: one entry per scene, in order (scene 0 first). Nothing else is exported.
export default [
  (g, K) => {                         // build once: add your objects to g
    const { THREE, gloss, rbox, t3, label, pop, out3, io3, back, cl, TEAL, SAF } = K;
    const box = rbox(2, 1.2, 0.3, 0.12, gloss(TEAL)); g.add(box);
    const word = label("நீர்", { w: 2, h: 0.6 }); word.position.set(0, 1.2, 0.2); g.add(word);
    return (lt) => {                  // every frame: lt = seconds since the scene started
      pop(box, lt, K.at(0) + 0.2);     // appears just after the scene's first line starts
      pop(word, lt, K.at(1));          // appears when the scene's second line starts
      box.rotation.y = 0.3 * Math.sin(lt * 0.8);
    };
  },
  ...
];
```

`example.js` is a complete, approved lesson (10 scenes, one line each). Read it first and match its quality.

## The kit (K)

- `THREE`: three.js r180. Any geometry/material (TorusGeometry, LatheGeometry, ExtrudeGeometry from a THREE.Shape,
  InstancedMesh, Sprite, Points...).
- Materials: `gloss(color, extra)` glossy clear-coated plastic (the house look), `metal(color, roughness)`.
  Glow: `new THREE.MeshStandardMaterial({ color: 0, emissive: TEAL, emissiveIntensity: 2 })` (bloom picks it up).
- `rbox(w, h, d, radius, material)` a rounded box that casts shadows. `chip(scale)` a glossy AI chip.
- `t3(text, size, color, depth)` extruded 3D text, Latin letters, digits and + - = ? ! % only (no Tamil, no ₹).
- `label(text, { w, h, color, bg, weight, fam, fill })` flat text on a plane, any script (Tamil, ₹): w and h in
  world units; `bg` a CSS colour gives a pill; `fam` "Catamaran" (default, Tamil) or "Inter".
- `docTex(cssColor)` a paper-document texture. `soft` a round soft-glow texture (sprites, steam, light).
- Time helpers: `pop(obj, lt, at, dur)` springs obj from nothing to its scale at `at` (hidden before);
  `out3`, `io3`, `back`, `sstep` easings on 0..1; `cl(x, a, b)` clamp; `rnd()` seeded random (deterministic).
- `K.at(k)`: seconds after the scene start when its k-th line starts (k = 0, 1, ...). `K.lines` lines in the
  scene, `K.dur` scene length. Time every reveal to the words: real voice timing arrives later, so ALWAYS
  time with `K.at(k) + offset`, never with fixed seconds past the first line.
- `K.shake(at)` a short camera shake at that scene time (an impact, a stamp, a crash). At most twice a video.
- Colours: `TEAL SAF CORAL LAV CREAM INK GOLD GREEN` (numbers for three.js).

## Space and framing

- Each scene has its own group g; build around the origin. The camera looks at about (2.2, -0.6, 0) from 11 units
  away, so your props appear on the LEFT 60% of the frame (the host stands on the right; never put props at
  x > 3.2).
- Safe box for props: x from -3.2 to 3.2, y from -1.2 to 2.1, z from -1.5 to 1.5. Captions cover the bottom of
  the frame: nothing important below y = -1.2. The brand sits top left: keep big objects below y = 2.1.
- Sizes: a hero object about 2 to 3 units; labels 0.5 to 0.8 high. One clear idea per scene, 1 hero + 2 to 6
  supporting objects. Leave space.

## Motion rules (what makes it look professional)

- Nothing just sits: every object enters with `pop` or a slide/rotate with an easing, then keeps a gentle idle
  motion (slow rotation, float, pulse). Stagger entrances 0.1 to 0.3 s apart.
- Each line of the scene changes something on screen when it starts (`K.at(k)`): a new object, a transformation,
  a highlight, a reveal. The viewer must see what the voice is saying.
- Real objects over abstract boxes: model the thing (a pot, a phone, a book, a scale, a planet, a coin) with a few
  primitives. Use emissive accents and soft sprites for light, sparks, steam, data flow.
- Short words on labels only (1 to 3 words, mostly Tamil). The captions already show the full sentence; never
  repeat a whole line on a label. No English paragraphs.
- Deterministic: use `rnd()` (never Math.random) and only `lt` for time (never Date or performance).
- No external files, no fetch, no DOM. Plain JavaScript in this one file.

## Check your work

- `python3 check.py` loads the stage, builds every scene and steps through it; it prints any JavaScript error with
  the scene number. Run it after writing, fix every error, run again until it prints `ok`.
- `python3 check.py T1 T2 ...` also saves frames `still-T.jpg` at those times (seconds in the whole video; see
  `lesson.json` for line starts). Each still takes about a minute, so look at 3 to 5 scenes, the busiest ones.
  Read the jpgs: fix props that are off-frame, too big, hidden behind the host or the captions, or empty
  moments.
- When it is clean, write `DONE.md`: one line per scene saying what it shows.
