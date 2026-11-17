// Loads anim.js in a bare fake page and builds every scene type in every theme, so a crash at load shows here.
const fs = require("fs"), vm = require("vm"), path = require("path");
const node = () => new Proxy({ style: {}, classList: { add() {} } }, {
  get: (o, k) => (k in o ? o[k] : k === "appendChild" ? (c) => c : () => 100),  // any browser method: answer 100
  set: (o, k, v) => ((o[k] = v), true),
});
const window = {};
const document = { createElementNS: node, createElement: node };
vm.runInNewContext(fs.readFileSync(path.join(__dirname, "../shorts/template/assets/anim.js"), "utf8"), { window, document, Math, Number, String, Object, Array, JSON });
if (typeof window.buildAnim !== "function") throw new Error("anim.js did not define buildAnim");
const tl = new Proxy({}, { get: () => function () { return tl; } });
const shot = (type) => ({ start: 0, end: 4, anim: { type, title: "t", unit: "", lat: 10, lon: 78, items: [{ label: "a", value: 2, note: "" }, { label: "b", value: 5, note: "" }] } });
for (const theme of ["night", "heritage", "ocean", "nature", "space", "tech", "kids", "unknown"])
  for (const type of ["diagram", "chart", "timeline", "scale", "stat", "orbit", "wave", "globe"]) window.buildAnim(node(), shot(type), tl, "#ffd21f", theme);
console.log("anim ok");
