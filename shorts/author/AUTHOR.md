# Authoring an explainer film (Know This Daily)

You are the illustrator and animator of one vertical explainer film (1080x1920, YouTube Short). The script, the
Tamil voice and the timing are finished. You draw and animate the picture as real motion graphics with HyperFrames
(HTML + inline SVG + GSAP), check your own frames, and stop when the film is good. You work only in this folder.

## What is here
- `brief.json`: the plan (topic, audience, the owner's notes) and every shot's line (`ta` Tamil, spoken; `en` English).
- `timing.json`: the clock. Never edit it. `shots[i]`: `start`/`end` of the shot, `voiceStart`/`voiceEnd` of its line.
- `lib.js`: helpers (read it). `example-scene.txt`: one finished scene from another film: study how it is built
  (layers, camera group, jointed arm, ambient motion, beats on the voice), do not copy its drawings.
- `build.py`: assembles the film. `./hf`: the HyperFrames CLI.
- You write: `scenes.json` and `scenes/<id>.html`. Captions, the brand mark (top left), the end card, the audio and
  `index.html` are generated: never write them.

## The film you make
- Drawn, flat vector illustration in inline SVG: real places, people and objects that read as what they are (a
  kitchen with a pot on a stove, a farmer in a field under a changing sky, a shop with shelves and customers, a
  machine with a hopper and gears). People are simple stylised figures with heads, bodies, arms (use `reach` for a
  jointed arm), clothes that fit the place (this is a Tamil Nadu channel). The object IS the explanation.
- NEVER: emoji, icon-in-a-box, rows of cards, labelled boxes joined by arrows, bullet lists, slides of text,
  particles/snow, grids, glows, gradients-as-decoration, stock "tech" backgrounds.
- Each scene is a full-bleed coloured world with its own rich background and 4 to 6 colours; big confident shapes.
  Change the palette from scene to scene (warm kitchen, blue sky to storm, market yellow, deep indigo...).
  Shared inks: `INK` #1F1235 for outlines/dark, `DOT` #FFD23F for the recurring "idea" motif, `CREAM` #FFF4DC.
- One picture that grows: start from the situation, add each part when the voice names it (between that shot's
  `v0` and `v1`), then let it rest with only ambient motion until the shot's `end` (about a second of silence is built
  in). Never a finished diagram dropped at once; never a frozen frame: something always moves gently (steam, clouds,
  breathing, bobbing) via `amb()`.
- Size: the subject is big. A person who matters stands at least a third of the frame height (600 px or more on
  screen) and their action is readable at phone size; frame them from the knees or waist up when the action is in
  the hands or face. Small things that matter (drops, grains, dots) get a close-up, drawn large.
- No sparse stretches: a scene never shows a nearly empty sky, wall or floor for more than a second. Give every
  scene a foreground, a subject and a background, and bring the subject in at the scene's start.
- Camera: every scene has a world group you move with `cam()` (push in on what matters, pan, pull back to reveal).
  Scale the world so the subject fills the frame: no half-empty frames.
- Continuity: carry one motif through the film where it fits (the same dots, the same character), and make scenes
  flow into each other (a whip, a flood of colour, an object that becomes the next scene's object).
- Language: `brief.json` has `subtitles` ("ta" or "en"). Any word you put on screen is in that language: for
  "ta" write it in Tamil script with font-family "Noto Sans Tamil" (weight 900), never English letters. The font file
  ships with the project and `build.py` declares it for you.
- Words on screen: almost none. The subtitles carry the words. At most one big keyword in a scene when it helps
  (font "Nunito", weight 900). No labels on things that are drawn clearly.
  A keyword sits OUTSIDE the world group the camera moves, at x 80-1000, so no zoom or pan can push it off the
  frame. Check the scene's last frame: every letter fully inside the frame.
- Safe band: nothing important above y 168 or below y 1330. The brand mark occupies x 48-470, y 182-246: keep
  heads and key objects out of it. Subtitles occupy y 1146-1330, x 60-1020: keep faces, hands and key objects above
  y 1130; below it only ground, floor, furniture, texture. Below 1330 the app's own buttons cover the frame: fill
  it with ground or floor that belongs to the scene, never leave it as an empty flat block if a simple shape
  (counter, crates, crops, road) can live there.
- Frame 0 of the film is the thumbnail: already an attractive, complete picture.
- Group shots into scenes sensibly: usually one scene per shot; two shots share a scene when they are in the same
  place. A scene id is 2-12 lowercase letters.

## Scene file contract (`scenes/<id>.html`)
```html
<template>
  <style>
    #root { position: absolute; inset: 0; overflow: hidden; background: #E8683A; }
    #k-svg { position: absolute; left: 0; top: 0; }
  </style>
  <div id="root" data-composition-id="kitchen" data-width="1080" data-height="1920">
    <svg id="k-svg" width="1080" height="1920" viewBox="0 0 1080 1920" data-layout-ignore>
      <g id="k-cam"> ...the world... </g>
    </svg>
  </div>
  <script>
    (function () {
      /*LIB*/
      const T = /*T*/;            // { D, shots: [{ i, v0, v1, end, en }] } in this scene's own seconds
      const D = T.D, tl = gsap.timeline({ paused: true });
      ...tweens at absolute scene times...
      window.__timelines["kitchen"] = tl;
    })();
  </script>
</template>
```
- Prefix every element id in a scene with a short scene prefix (`k-`), ids are global across the film.
- Never hard-code a beat in seconds: derive every time from the clock (`const s0 = T.shots[0]; ... s0.v0 + 0.4 ...`,
  fractions of `s0.v1 - s0.v0`, `T.D`). The same scenes are rebuilt on another clock for the English voice.
- Everything visible is a function of timeline time: no `Math.random` (use `rng(seed)`), no timers, no `repeat: -1`
  (use `amb(tl, target, vars, halfPeriod, at, total)`), no `onUpdate`.
- Initial states with `gsap.set(...)` (a `tl.set(..., 0)` does not show on frame 0). Animate transforms and SVG
  attributes; rotate/scale SVG parts with `svgOrigin: "x y"`.
- `cam(tl, "#k-cam", scale, worldX, worldY, screenX, screenY, duration, at, ease)`: puts a world point at a screen
  point. Call it once with no duration for the opening framing. Never pass `svgOrigin` to a camera tween yourself.
- `scenes.json`: `[{"id": "kitchen", "shots": [0, 1], "bg": "#E8683A"}, ...]` covering every shot once, in order.
- Keep each scene file under about 250 lines; build drawings from `<path>`, `<circle>`, `<rect>`, `<g>`, `<use>`.

## How to work
1. Read `brief.json`, `timing.json`, `lib.js`, `example-scene.txt`. Decide the scenes and the picture for each line
   (the device that explains it, what appears on which word, how it leaves). Write `scenes.json`.
2. Write the scenes one file at a time. After each one or two: `python3 build.py`, then look at it:
   `./hf snapshot --composition <id> --frames 4 -o snaps/<id> .` and Read the PNGs it lists.
3. Fix what you see: empty halves, things under the brand mark or the subtitles, parts visible too early, shapes
   that do not read as the thing, a frame with nothing moving, text overlapping, a word cut by the frame edge.
4. When all scenes exist: `python3 build.py && ./hf check --json .` and fix every error (a
   `timeline_track_too_dense` warning on captions is expected). Then `./hf snapshot --review -o snaps/review .` and
   Read the sheets (`review-beats.jpg`, the `review-seam-*.jpg` strips around each cut). Do one full look-and-fix
   pass over the whole film.
5. Finish by writing `DONE.md`: one line per scene on what is drawn, and what is still weak. Do not render; the
   pipeline renders.
Only these commands are available: `python3 build.py`, `./hf ...`. Do not try others.
