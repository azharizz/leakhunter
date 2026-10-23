// Run with: node tests/test_dashboard.cjs
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const path = require("node:path");

class Element {
  constructor() {
    this.value = "";
    this.children = [];
    this.attrs = {};
    this.dataset = {};
    this.listeners = {};
    this.classes = new Set();
    this.classList = { toggle: (name, on) => on ? this.classes.add(name) : this.classes.delete(name) };
    this.parentElement = { clientWidth: 700 };
  }
  setAttribute(name, value) {
    this.attrs[name] = String(value);
    if (name === "class") this.classes = new Set(value.split(" "));
    if (name.startsWith("data-")) this.dataset[name.slice(5)] = String(value);
  }
  getAttribute(name) { return this.attrs[name]; }
  append(...items) { this.children.push(...items); }
  replaceChildren(...items) { this.children = items; }
  addEventListener(name, callback) { this.listeners[name] = callback; }
  focus() {}
  click() { this.listeners.click?.({ target: this }); }
  get options() { return this.children; }
  get selectedOptions() { return this.children.filter((item) => item.selected); }
  querySelectorAll(selector) {
    return this.children.flatMap((child) => child instanceof Element
      ? [...(child.classes.has(selector.slice(1)) ? [child] : []), ...child.querySelectorAll(selector)] : []);
  }
}
const root = path.join(__dirname, "../unspool/static");
const html = fs.readFileSync(path.join(root, "index.html"), "utf8");
const ids = [...html.matchAll(/\bid="([^"]+)"/g)].map((match) => match[1]);
assert.equal(new Set(ids).size, ids.length, "HTML IDs must stay unique");
const elements = Object.fromEntries(ids.map((id) => [id, new Element()]));
for (const [form, names] of Object.entries({ nodeForm: ["id", "label", "kind", "classification", "file"], edgeForm: ["id", "type", "source", "target"] })) {
  const fields = Object.fromEntries(names.map((name) => [name, new Element()]));
  elements[form].elements = { namedItem: (name) => fields[name] };
}
elements.nodeLimit.value = "30";
const context = vm.createContext({
  document: { getElementById: (id) => elements[id], createElementNS: () => new Element(), createElement: () => new Element() },
  Option: function (label, value) { this.label = label; this.value = value; },
});
const source = fs.readFileSync(path.join(root, "app.js"), "utf8").replace('action("Loading workspace", refresh);', "");
vm.runInContext(source, context);
const run = (code) => vm.runInContext(code, context);
run(`view = { nodes: [
  {id: 'a', kind: 'source', label: 'Request'},
  {id: 'b', kind: 'transform', label: 'Allowlist'},
  {id: 'c', kind: 'sink', label: 'Response'}
], edges: [
  {id: 'ab', source: 'a', target: 'b', type: 'DATA_FLOW'},
  {id: 'loop', source: 'b', target: 'b', type: 'CALLS'}
], findings: [] }; renderGraph(); renderEditors(); selectNode('a');`);
assert.equal(elements.nodeInspector.hidden, false);
assert.equal(elements.edgeInspector.hidden, true);
assert.equal(elements.nodeForm.elements.namedItem("id").readOnly, true);
assert.equal(elements.graphSvg.querySelectorAll(".node").filter((node) => node.classes.has("selected")).length, 1);
assert.equal(elements.graphSvg.querySelectorAll(".edge").filter((edge) => edge.classes.has("connected")).length, 1);
run("selectEdge('ab')");
assert.equal(elements.edgeInspector.hidden, false);
assert.equal(elements.nodeInspector.hidden, true);
assert.equal(elements.addRecord.textContent, "Add edge");
assert.equal(elements.graphSvg.querySelectorAll(".node").filter((node) => node.classes.has("selected")).length, 2);
run("snapshot = 'saved'; controls();");
for (const id of ["nodeFields", "edgeFields", "addRecord", "newNode", "newEdge", "deleteNode", "deleteEdge", "run"])
  assert.equal(elements[id].disabled, true, `${id} must lock for snapshots`);
assert.throws(() => run("requireLive()"), /Snapshots are immutable/);
run("snapshot = null; controls(); setGraphZoom(99)");
assert.equal(elements.zoomLevel.textContent, "200%");
run("setGraphZoom(-2)");
assert.equal(elements.zoomLevel.textContent, "25%");
elements.graphSearch.value = "missing";
run("renderGraph()");
assert.equal(elements.graphSvg.querySelectorAll(".node").length, 0);
elements.resetFilters.click();
assert.equal(elements.graphSvg.querySelectorAll(".node").length, 3);
elements.nodeLimit.value = "1.5";
run("renderGraph()");
assert.match(elements.graphStatus.textContent, /positive whole-number/);
elements.nodeLimit.value = "30";
run("view.nodes = Array.from({length:30}, (_, i) => ({id:String(i), kind:'Kind'+i})); view.edges = []; renderGraph();");
assert.equal(elements.graphSvg.getAttribute("viewBox").split(" ")[2], "900", "many node kinds must not create an unbounded horizontal canvas");
elements.nodeLimit.value = "2";
run("selectNode('29')");
assert.equal(elements.graphSvg.querySelectorAll(".node").length, 2);
assert.ok(elements.graphSvg.querySelectorAll(".node").some((node) => node.dataset.id === "29"), "selected records beyond the display limit stay visible");
run("selectNode(''); view.nodes.push({id:'boundary', kind:'sink'}); renderGraph();");
assert.equal(elements.graphSvg.querySelectorAll(".node")[0].dataset.id, "boundary", "boundaries take precedence over syntax details");
console.log("Dashboard checks passed: inspector, selection, snapshot locks, filters, zoom, and compact layout.");
