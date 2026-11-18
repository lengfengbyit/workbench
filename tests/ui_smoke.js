// Smoke test: run the UI scripts against a stub DOM and check the HTML they generate. Usage: node tests/ui_smoke.js data.json
const fs = require("fs"), vm = require("vm"), path = require("path");
const dataFile = process.argv[2];
const data = JSON.parse(fs.readFileSync(dataFile, "utf8"));
const writes = [];
const mk = (name) => new Proxy(function () {}, {
  get(t, k) {
    if (k === Symbol.toPrimitive) return () => "";
    if (k === "then") return undefined;
    if (k === "length") return 0;
    if (k === "dataset") return {};
    if (k === "classList") return {toggle() {}, add() {}, remove() {}, contains: () => false};
    if (k === "style") return {};
    return mk(name + "." + String(k));
  },
  set(t, k, v) { if (k === "innerHTML" || k === "textContent") writes.push([name + "." + k, String(v)]); return true; },
  apply() { return mk(name + "()"); },
});
const sandbox = {
  console, setInterval() {}, setTimeout() {}, clearTimeout() {}, URL, encodeURIComponent, decodeURIComponent,
  document: {querySelector: s => mk(s), querySelectorAll: () => [], getElementById: () => null, body: mk("body"),
             addEventListener() {}, createElement: () => mk("el")},
  location: {hash: "", reload() {}}, history: {replaceState() {}},
  addEventListener() {}, IntersectionObserver: class { observe() {} disconnect() {} },
  confirm: () => true, innerWidth: 1400, matchMedia: () => ({matches: false, addEventListener() {}}),
  fetch: async () => ({ok: true, status: 200, json: async () => data}),
};
sandbox.window = sandbox;
vm.createContext(sandbox);
const dir = path.join(__dirname, "..", "workbench", "static");
for (const f of ["core", "tip", "charts", "gantt", "views", "drawer", "local", "detail"]) {
  vm.runInContext(fs.readFileSync(path.join(dir, f + ".js"), "utf8"), sandbox, {filename: f + ".js"});
}
setImmediate(() => setImmediate(() => {
  const local = data.requirements.find(r => r.manual);
  const steps = [
    ["reqEdit", () => data.requirements.length && sandbox.reqEdit(data.requirements[0].id)],
    ["localNew", () => sandbox.localNew()],
    ["localEdit", () => local && sandbox.reqEdit(local.id)],
    ["configOpen", () => sandbox.configOpen()],
  ];
  for (const [name, step] of steps) {
    try { step(); } catch (e) { writes.push(["error", `undefined ${name}: ${e.message}`]); }
  }
  const html = writes.map(w => w[1]).join("\n");
  const problems = [];
  if (!html.length) problems.push("nothing rendered");
  for (const bad of ["undefined", "NaN", "[object Object]", "master"]) if (html.includes(bad)) problems.push(`output contains "${bad}"`);
  const first = data.requirements[0];
  if (first && !html.includes((data.idPrefix || "") + first.id)) problems.push("requirement label missing");
  console.log(`rendered ${html.length} chars in ${writes.length} writes`);
  if (problems.length) { console.log("PROBLEMS:", problems.join("; ")); process.exit(1); }
  console.log("ui smoke ok");
}));
