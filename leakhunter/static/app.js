"use strict";
const $ = (id) => document.getElementById(id);
const NS = "http://www.w3.org/2000/svg";
let live = { nodes: [], edges: [], findings: [] },
  view = live,
  snapshot = null;
let metrics = [],
  repairs = [],
  policies = [],
  snapshots = [],
  configuration = {};
let busy = false,
  latestEvaluation = null;
const text = (value) => (value == null ? "" : String(value));
const json = (value) => JSON.stringify(value, null, 2);
const array = (value) => (Array.isArray(value) ? value : []);
function element(tag, content, className) {
  const node = document.createElement(tag);
  if (content != null) node.textContent = text(content);
  if (className) node.className = className;
  return node;
}
function message(content, error = false) {
  $(error ? "error" : "activity").textContent = content;
  if (error) $("error").focus();
}
async function api(path, method = "GET", body) {
  const options = { method, headers: { Accept: "application/json" } };
  if (body !== undefined) {
    options.headers["Content-Type"] = "application/json";
    options.body = JSON.stringify(body);
  }
  const response = await fetch(path, options);
  const raw = await response.text();
  let result;
  try {
    result = raw ? JSON.parse(raw) : {};
  } catch (_) {
    throw new Error(
      `HTTP ${response.status}: server returned a non-JSON response.`,
    );
  }
  if (!response.ok)
    throw new Error(
      text(result.error || result.message || `HTTP ${response.status}`),
    );
  return result;
}
async function action(label, operation) {
  if (busy) return;
  busy = true;
  $("error").textContent = "";
  message(`${label}…`);
  controls();
  try {
    await operation();
    message(
      `${label} completed. Review the recorded status and evidence; completion alone does not mean verification passed.`,
    );
  } catch (error) {
    message(`${label}: ${error.message}`, true);
    message(`${label} did not complete successfully.`);
  } finally {
    busy = false;
    controls();
  }
}
function controls() {
  const locked = busy || snapshot !== null;
  for (const id of [
    "run",
    "runRepair",
    "runEvaluate",
    "nodeFields",
    "edgeFields",
    "approvalFields",
  ])
    $(id).disabled = locked;
  for (const id of [
    "refresh",
    "inspectSnapshot",
    "liveView",
    "snapshotSelect",
    "policySelect",
    "repairSelect",
    "nodeSelect",
    "edgeSelect",
  ])
    $(id).disabled = busy;
  $("inspectSnapshot").disabled = busy || !$("snapshotSelect").value;
  $("liveView").disabled = busy || snapshot === null;
  $("deleteNode").disabled = locked || !$("nodeSelect").value;
  $("deleteEdge").disabled = locked || !$("edgeSelect").value;
}
function options(select, records, label, empty, wanted = select.value) {
  select.replaceChildren();
  if (empty !== null) select.append(new Option(empty, ""));
  for (const record of records)
    select.append(new Option(label(record), text(record.id)));
  if ([...select.options].some((option) => option.value === wanted))
    select.value = wanted;
}
function normalizeGraph(record) {
  const graph = record.graph || record.knowledge || record;
  return {
    ...record,
    ...graph,
    nodes: array(graph.nodes),
    edges: array(graph.edges),
    findings: array(record.findings || graph.findings),
  };
}
function renderConfiguration() {
  const target = $("configuration");
  const runtimeConfig = live.runtime_config || {};
  const backend = configuration.runtime_backend || runtimeConfig.backend;
  const configured =
    configuration.runtime_configured ?? runtimeConfig.configured;
  target.replaceChildren();
  const fields = [
    [
      "Repository",
      configuration.repository ||
        configuration.repository_path ||
        "Not reported",
    ],
    [
      "Decision model (advisory; scoped source disclosed)",
      configuration.decision_model || "Not configured",
    ],
    [
      "Repair model (OpenRouter simulates Duo)",
      configuration.duo_model || "Not configured",
    ],
    [
      "Model provider",
      configuration.provider_configured === true
        ? "Configured; availability is determined by each request"
        : "Not configured — model advice and model repair unavailable",
    ],
    ["Runtime backend", backend || "Not reported"],
    [
      "Runtime prerequisites",
      configured === true
        ? "Configured; execution success is reported separately"
        : "Not configured / unavailable — inspect prerequisites below",
    ],
    [
      "Runtime manifest",
      configuration.runtime_manifest ||
        configuration.manifest ||
        runtimeConfig.manifest?.path ||
        (runtimeConfig.manifest
          ? json(runtimeConfig.manifest)
          : "Not reported"),
    ],
  ];
  for (const [key, value] of fields) {
    const row = element("div", null, "metric");
    row.append(element("span", key), element("span", value));
    target.append(row);
  }
  const details = element("details");
  details.append(
    element("summary", "Full configuration and missing prerequisites"),
    element("pre", json({ ...configuration, runtime_config: runtimeConfig })),
  );
  target.append(details);
  if (backend === "local")
    target.append(
      element(
        "p",
        "Local runtime executes trusted repository code on this host; it is not container isolation.",
        "warn",
      ),
    );
}
function updateTypeOptions(select, values) {
  const selected = new Set(
    [...select.selectedOptions].map((option) => option.value),
  );
  select.replaceChildren();
  for (const value of [...new Set(values)].sort()) {
    const option = new Option(value, value);
    option.selected = selected.has(value);
    select.append(option);
  }
}
const kindOf = (node) => text(node.kind || node.type || "unknown");
function renderGraph() {
  const svg = $("graphSvg");
  svg.replaceChildren();
  const addSvg = (tag, attrs, content, parent = svg) => {
    const node = document.createElementNS(NS, tag);
    for (const [key, value] of Object.entries(attrs))
      node.setAttribute(key, text(value));
    if (content != null) node.textContent = text(content);
    parent.append(node);
    return node;
  };
  addSvg("title", { id: "svgTitle" }, "Knowledge graph");
  addSvg(
    "desc",
    { id: "svgDescription" },
    "Filtered CPG and annotation nodes. Tab to a node then press Enter to inspect its full record in the editor.",
  );
  const kinds = new Set(
    [...$("nodeKinds").selectedOptions].map((option) => option.value),
  );
  const types = new Set(
    [...$("edgeTypes").selectedOptions].map((option) => option.value),
  );
  const query = $("graphSearch").value.toLocaleLowerCase();
  const limit = Number($("nodeLimit").value);
  if (!Number.isSafeInteger(limit) || limit < 1) {
    $("graphStatus").textContent =
      "Enter a positive whole-number display limit.";
    svg.setAttribute("width", "900");
    svg.setAttribute("height", "120");
    return;
  }
  const filtered = view.nodes.filter(
    (node) =>
      (!kinds.size || kinds.has(kindOf(node))) &&
      [node.id, node.label, node.file, node.line, node.classification]
        .map(text)
        .join(" ")
        .toLocaleLowerCase()
        .includes(query),
  );
  const nodes = filtered.slice(0, limit);
  const ids = new Set(nodes.map((node) => node.id));
  const edges = view.edges.filter(
    (edge) =>
      ids.has(edge.source) &&
      ids.has(edge.target) &&
      (!types.size || types.has(text(edge.type))),
  );
  const groups = [...new Set(nodes.map(kindOf))].sort();
  const positions = new Map(),
    rows = new Map();
  for (const node of nodes) {
    const kind = kindOf(node),
      row = rows.get(kind) || 0;
    positions.set(node.id, {
      x: 35 + groups.indexOf(kind) * 260,
      y: 50 + row * 92,
    });
    rows.set(kind, row + 1);
  }
  const width = Math.max(900, groups.length * 260 + 50),
    height = Math.max(
      150,
      ...[...rows.values()].map((count) => count * 92 + 65),
    );
  svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
  svg.setAttribute("width", width);
  svg.setAttribute("height", height);
  const defs = addSvg("defs", {});
  const marker = addSvg(
    "marker",
    {
      id: "arrow",
      markerWidth: 8,
      markerHeight: 8,
      refX: 7,
      refY: 3,
      orient: "auto",
    },
    null,
    defs,
  );
  addSvg("path", { d: "M0,0 L8,3 L0,6z", fill: "#6385b2" }, null, marker);
  for (const [index, kind] of groups.entries())
    addSvg(
      "text",
      { x: 35 + index * 260, y: 24, fill: "#b3c3db", "font-size": 12 },
      kind,
    );
  for (const edge of edges) {
    const a = positions.get(edge.source),
      b = positions.get(edge.target);
    const label = `${edge.id}: ${edge.source} → ${edge.target} · ${edge.type}`;
    let d;
    if (edge.source === edge.target)
      d = `M ${a.x + 220} ${a.y + 20} C ${a.x + 255} ${a.y - 20}, ${a.x + 255} ${a.y + 75}, ${a.x + 220} ${a.y + 42}`;
    else if (a.x === b.x)
      d = `M ${a.x + 220} ${a.y + 30} C ${a.x + 245} ${a.y + 30}, ${b.x + 245} ${b.y + 30}, ${b.x + 220} ${b.y + 30}`;
    else
      d = `M ${a.x + (b.x > a.x ? 220 : 0)} ${a.y + 30} L ${b.x + (b.x > a.x ? 0 : 220)} ${b.y + 30}`;
    const path = addSvg("path", {
      d,
      class: "edge",
      "marker-end": "url(#arrow)",
      tabindex: 0,
      role: "button",
      "aria-label": label,
    });
    addSvg("title", {}, label, path);
    path.addEventListener("click", () => selectEdge(edge.id));
    path.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        selectEdge(edge.id);
        $("edgeSelect").focus();
      }
    });
  }
  for (const node of nodes) {
    const p = positions.get(node.id),
      kind = kindOf(node);
    const description = `${node.label || node.id} · ${kind} · ${node.classification || "unclassified"} · ${node.file || "no location"}${node.line ? ":" + node.line : ""} · ID ${node.id}`;
    const group = addSvg("g", {
      class: `node ${["source", "sink"].includes(kind) ? kind : ""}`,
      transform: `translate(${p.x} ${p.y})`,
      tabindex: 0,
      role: "button",
      "aria-label": description,
    });
    addSvg("title", {}, description, group);
    addSvg("rect", { width: 220, height: 62, rx: 8 }, null, group);
    const label = text(node.label || node.id);
    addSvg(
      "text",
      { x: 10, y: 24 },
      label.length > 29 ? label.slice(0, 28) + "…" : label,
      group,
    );
    const subtitle = text(node.file || node.classification || kind);
    addSvg(
      "text",
      { x: 10, y: 45, class: "subtitle" },
      subtitle.length > 35 ? subtitle.slice(0, 34) + "…" : subtitle,
      group,
    );
    group.addEventListener("click", () => selectNode(node.id));
    group.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        selectNode(node.id);
        $("nodeSelect").focus();
      }
    });
  }
  if (!nodes.length)
    addSvg(
      "text",
      { x: 25, y: 65, fill: "#b3c3db" },
      "No nodes match these filters.",
    );
  $("graphStatus").textContent =
    `Showing ${nodes.length} of ${filtered.length} matching / ${view.nodes.length} total nodes · ${edges.length} of ${view.edges.length} total edges`;
}
function renderEditors() {
  options(
    $("nodeSelect"),
    view.nodes,
    (node) => `${node.label || node.id} · ${kindOf(node)} · ${node.id}`,
    "New node",
  );
  options(
    $("edgeSelect"),
    view.edges,
    (edge) => `${edge.type} · ${edge.source} → ${edge.target} · ${edge.id}`,
    "New edge",
  );
  const edgeForm = $("edgeForm");
  for (const name of ["source", "target"])
    options(
      edgeForm.elements.namedItem(name),
      view.nodes,
      (node) => `${node.label || node.id} · ${node.id}`,
      "Select a node",
    );
  const datalist = $("kindOptions");
  datalist.replaceChildren(
    ...[...new Set(["source", "transform", "sink", ...view.nodes.map(kindOf)])]
      .sort()
      .map((value) => new Option(value, value)),
  );
  const edgeOptions = $("edgeOptions");
  edgeOptions.replaceChildren(
    ...[
      ...new Set([
        "AST",
        "CFG",
        "CALLS",
        "DATA_FLOW",
        ...view.edges.map((edge) => text(edge.type)),
      ]),
    ]
      .sort()
      .map((value) => new Option(value, value)),
  );
  selectNode($("nodeSelect").value);
  selectEdge($("edgeSelect").value);
}
function selectNode(id) {
  $("nodeSelect").value = text(id);
  const node = view.nodes.find((item) => text(item.id) === text(id));
  const form = $("nodeForm");
  for (const name of ["id", "label", "kind", "classification", "file"])
    form.elements.namedItem(name).value = node
      ? text(node[name] ?? (name === "kind" ? kindOf(node) : ""))
      : name === "kind"
        ? "source"
        : "";
  form.elements.namedItem("id").readOnly = !!node;
  $("nodeLegend").textContent = node
    ? snapshot
      ? "Read snapshot node"
      : "Update node"
    : "Create node";
  $("saveNode").textContent = node ? "Save node changes" : "Create node";
  $("nodeRecord").textContent = node ? json(node) : "No node selected.";
  $("graphSelection").textContent = node
    ? `${snapshot ? "Snapshot" : "Live"} node selected: ${node.id}. Complete record available in the node editor.`
    : "Select a node to read its complete record below.";
  controls();
}
function selectEdge(id) {
  $("edgeSelect").value = text(id);
  const edge = view.edges.find((item) => text(item.id) === text(id));
  const form = $("edgeForm");
  for (const name of ["id", "source", "target", "type"])
    form.elements.namedItem(name).value = edge
      ? text(edge[name])
      : name === "type"
        ? "DATA_FLOW"
        : "";
  form.elements.namedItem("id").readOnly = !!edge;
  $("edgeLegend").textContent = edge
    ? snapshot
      ? "Read snapshot edge"
      : "Update edge"
    : "Create edge";
  $("saveEdge").textContent = edge ? "Save edge changes" : "Create edge";
  $("edgeRecord").textContent = edge ? json(edge) : "No edge selected.";
  controls();
}
function renderFindings() {
  const query = $("findingSearch").value.toLocaleLowerCase();
  const findings = view.findings.filter((finding) =>
    json(finding).toLocaleLowerCase().includes(query),
  );
  $("findingCount").textContent =
    `${findings.length} shown / ${view.findings.length} total`;
  const container = $("findings");
  container.replaceChildren();
  if (!findings.length)
    container.append(
      element(
        "p",
        view.findings.length
          ? "No findings match this filter."
          : "No static candidates recorded. This does not establish absence of leaks.",
        "empty",
      ),
    );
  for (const finding of findings) {
    const article = element("article", null, "finding");
    article.append(
      element("span", finding.status || "POSSIBLE", "badge"),
      element(
        "h3",
        finding.title ||
          `${finding.classification || "Sensitive data"} → ${finding.sink || "unknown sink"}`,
      ),
    );
    article.append(
      element(
        "p",
        `${finding.file || "Location not reported"}${finding.line ? ":" + finding.line : ""} · ${finding.source || "source not reported"}`,
        "small",
      ),
    );
    const path = array(finding.path);
    if (path.length) {
      article.append(element("div", "Static path (not runtime proof)", "help"));
      const list = element("ol");
      for (const part of path)
        list.append(
          element("li", typeof part === "object" ? json(part) : part),
        );
      article.append(list);
    }
    const evidence = finding.runtime_evidence;
    article.append(
      element(
        "p",
        evidence
          ? `Runtime: ${evidence.status || "status not reported"} · observed: ${evidence.observed === true ? "yes" : evidence.observed === false ? "no (executed scope only)" : "not reported"}`
          : "Runtime: NOT_RUN / no attached evidence.",
        "help",
      ),
    );
    const details = element("details");
    details.append(
      element("summary", "Finding, policy reasons & sanitized evidence"),
      element("pre", json(finding)),
    );
    article.append(details);
    container.append(article);
  }
}
function renderRuntime() {
  const runtime = view.runtime || view.last_runtime;
  const target = $("runtime");
  target.replaceChildren();
  if (!runtime) {
    target.append(
      element(
        "p",
        "NOT_RUN · No executed runtime evidence recorded. Configure a synthetic-case manifest and an available backend.",
        "warn",
      ),
    );
    $("runtimeRecord").textContent = "No runtime record.";
  } else {
    target.append(
      element(
        "p",
        `Status: ${runtime.status || "not reported"} · backend: ${runtime.backend || "not reported"}`,
      ),
    );
    target.append(
      element(
        "p",
        `Functional checks: ${runtime.functional_passed === true ? "passed" : runtime.functional_passed === false ? "not passed" : "not reported"} · case gate: ${runtime.passed === true ? "passed for executed cases only" : "not passed / not executed"}`,
        runtime.passed === true ? "pass" : "warn",
      ),
    );
    if (runtime.error || runtime.reason)
      target.append(element("p", runtime.error || runtime.reason, "fail"));
    for (const item of array(runtime.cases)) {
      const details = element("details", null, "case");
      details.append(
        element(
          "summary",
          `${item.id} · functionality ${item.passed === true ? "passed" : "not passed"} · observed ${item.observed === true ? "yes" : "no"} · ${array(item.violations).length} violations`,
        ),
        element("pre", json(item)),
      );
      target.append(details);
    }
    $("runtimeRecord").textContent = json(runtime);
  }
  renderDecisions();
}
function renderDecisions() {
  const advice = view.decision;
  $("decision").textContent =
    typeof advice === "string"
      ? advice
      : advice
        ? json(advice)
        : "No model advice recorded. Advice is never verification.";
  const target = $("decisionReviews");
  target.replaceChildren();
  if (!advice || !Array.isArray(advice.reviews)) return;
  const scope = advice.scope || {};
  target.append(
    element("p", `Review status: ${advice.status} · ${advice.reviews.length} selected · ${scope.omitted_review_units || 0} omitted`),
    element("p", "All model assessments remain UNRESOLVED. The scoped deterministic gate is separate; neither establishes whole-application safety.", "warn"),
  );
  if (scope.selection_complete === false)
    target.append(element("p", "Review coverage is incomplete; inspect selection limits and per-review evidence omissions.", "warn"));
  if (!advice.reviews.length)
    target.append(element("p", "No review units selected. This is not proof that no exposure boundaries exist.", "help"));
  for (const review of advice.reviews) {
    const context = review.context || {};
    const boundary = context.boundary || {};
    const article = element("article", null, "case");
    article.append(
      element("h4", `${boundary.function || boundary.kind || review.review_id} · ${boundary.file || "source unavailable"}:${boundary.line || "?"}`),
      element("p", `Verification: ${review.verification} · provider: ${review.provider_status}`),
      element("p", `Evidence: ${array(review.evidence_refs).join(", ") || "No source evidence available"}`, "help"),
    );
    const answers = review.decision?.answers;
    if (answers) {
      const list = element("ul");
      for (const [name, answer] of Object.entries(answers))
        list.append(element("li", `${name}: ${answer.noul} (model assessment, not measured exploit probability)`));
      article.append(list);
    } else if (typeof review.decision === "string") {
      article.append(element("p", review.decision, "warn"));
    }
    const missing = array(review.missing_evidence);
    if (missing.length) {
      article.append(element("h5", "Missing evidence / unknowns"));
      const list = element("ul");
      for (const item of missing) list.append(element("li", item));
      article.append(list);
    }
    const checks = array(review.next_checks);
    if (checks.length) {
      article.append(element("h5", "Next checks · not executed automatically"));
      const list = element("ul");
      for (const item of checks) list.append(element("li", item));
      article.append(list);
    }
    const details = element("details");
    details.append(
      element("summary", "Connected code, graph, policy and scoped runtime context"),
      element("pre", json(context)),
    );
    article.append(details);
    target.append(article);
  }
}
function renderMetrics() {
  const selected = snapshot
    ? array(view.metrics).length
      ? view.metrics[0]
      : view.metric
    : metrics[0];
  const target = $("metrics");
  target.replaceChildren();
  if (!selected)
    target.append(
      element("p", "No run metrics recorded for this view.", "empty"),
    );
  else {
    for (const [label, key] of [
      ["Run ID", "run_id"],
      ["Duration (ms)", "duration_ms"],
      ["Findings", "findings"],
      ["Runtime-confirmed findings", "confirmed"],
      ["Policy version", "policy_version"],
      ["Decision provider status", "decision_status"],
      ["Contextual review status", "decision_review_status"],
      ["Selected security reviews", "decision_reviews"],
      ["Omitted security reviews", "decision_omitted_reviews"],
      ["Repair provider status", "duo_status"],
      ["Repair verification passed", "repair_verification_passed"],
    ]) {
      if (selected[key] === undefined) continue;
      const row = element("div", null, "metric");
      row.append(element("span", label), element("span", selected[key]));
      target.append(row);
    }
  }
  $("metricRecords").textContent = snapshot
    ? json(view.metric || view.metrics || {})
    : json(metrics);
  const evaluation = snapshot
    ? view.evaluation || view.latest_evaluation
    : latestEvaluation || live.latest_evaluation || live.evaluation;
  $("evaluation").textContent = evaluation
    ? json(evaluation)
    : "No labeled evaluation recorded for this view. Use Evaluate labeled cases on live knowledge.";
}
function repairId(record, index) {
  return text(
    record.id ||
      record.repair_id ||
      record.commit_sha ||
      record.branch ||
      index,
  );
}
function renderRepairs() {
  const records = snapshot
    ? array(view.repairs).length
      ? view.repairs
      : view.repair && typeof view.repair === "object"
        ? [view.repair]
        : []
    : repairs;
  const select = $("repairSelect"),
    wanted = select.value;
  select.replaceChildren(new Option("Latest repair", ""));
  records.forEach((record, index) =>
    select.append(
      new Option(
        `${record.status || "Recorded"} · ${record.branch || record.timestamp || repairId(record, index)}`,
        text(index),
      ),
    ),
  );
  if ([...select.options].some((option) => option.value === wanted))
    select.value = wanted;
  const record = records[select.value === "" ? 0 : Number(select.value)];
  const gate = $("repairGate");
  gate.className = "notice";
  if (!record) {
    gate.textContent = snapshot
      ? "No repair recorded in this immutable snapshot."
      : "No repair executed. No verified gate result.";
    $("repairSummary").textContent = "No repair recorded.";
    $("verification").textContent = "No verification recorded.";
    $("repairDiff").textContent = "No diff recorded.";
    return;
  }
  const verification = record.verification || {};
  const passed = record.passed === true && verification.passed === true;
  gate.textContent = passed
    ? "PASS · Independent local repair checks passed for the recorded scope. Not approval to merge or deploy."
    : `NOT VERIFIED / BLOCKED · ${record.status || "No passing independent gate recorded"}. Model advice cannot pass this gate.`;
  gate.classList.add(passed ? "pass" : "warn");
  const summary = { ...record };
  delete summary.diff;
  delete summary.verification;
  $("repairSummary").textContent = json(summary);
  $("verification").textContent = json(verification);
  $("repairDiff").textContent =
    typeof record.diff === "string"
      ? record.diff
      : record.diff
        ? json(record.diff)
        : "No diff recorded.";
}
function policyContent(record) {
  return (
    record &&
    (record.policy ||
      record.raw ||
      (record.classifications && record.sources && record.sinks
        ? record
        : null))
  );
}
function renderPolicyRecord() {
  const record =
    $("policySelect").value === ""
      ? null
      : policies[Number($("policySelect").value)];
  $("approvalConsent").checked = false;
  $("policyStatus").textContent = record
    ? `Version ${record.version ?? policyContent(record)?.version ?? "not reported"} · lifecycle ${record.status || record.lifecycle?.status || policyContent(record)?.status || "not reported"} · approved by ${record.approved_by || record.lifecycle?.approved_by || "not recorded"}${snapshot ? " · Live policy registry (snapshot policy is in provenance above); approval disabled in snapshot mode." : ""}`
    : "No policy record selected.";
  $("policyRecord").textContent = record
    ? json(record)
    : "No policy record selected.";
  $("approvalPolicy").value = policyContent(record)
    ? json(policyContent(record))
    : "";
}
function renderRegistries() {
  const snapshotChoice = $("snapshotSelect").value;
  $("snapshotSelect").replaceChildren(
    new Option("Select a saved snapshot", ""),
  );
  for (const record of snapshots)
    $("snapshotSelect").append(
      new Option(
        `${record.timestamp || record.created_at || record.last_run || ""} · ${record.branch || "main"} · ${record.id || record.snapshot_id}`,
        text(record.id || record.snapshot_id),
      ),
    );
  if (
    [...$("snapshotSelect").options].some(
      (option) => option.value === snapshotChoice,
    )
  )
    $("snapshotSelect").value = snapshotChoice;
  const choice = $("policySelect").value;
  $("policySelect").replaceChildren(new Option("Select a policy", ""));
  policies.forEach((record, index) =>
    $("policySelect").append(
      new Option(
        `Version ${record.version ?? policyContent(record)?.version ?? "?"} · ${record.status || policyContent(record)?.status || "lifecycle not reported"}${record.active ? " · active" : ""}`,
        text(index),
      ),
    ),
  );
  if (choice !== "" && policies[Number(choice)])
    $("policySelect").value = choice;
  else if (policies.length)
    $("policySelect").value = text(
      Math.max(
        0,
        policies.findIndex((record) => record.active),
      ),
    );
  renderPolicyRecord();
}
function renderView() {
  const label = snapshot
    ? `Immutable snapshot ${snapshot} · read-only. Live annotations, scans, repairs, evaluation and approval are disabled until you return to live knowledge.`
    : `Live knowledge · user annotations survive analysis.${view.last_run ? " Last analysis: " + view.last_run : ""}`;
  $("viewStatus").textContent = label;
  $("historyPanel").classList.toggle("snapshot", snapshot !== null);
  const provenance = { ...view };
  for (const key of [
    "nodes",
    "edges",
    "findings",
    "graph",
    "knowledge",
    "decision",
    "runtime",
    "repairs",
    "repair",
    "metrics",
  ])
    delete provenance[key];
  $("provenance").textContent = json(provenance);
  updateTypeOptions($("nodeKinds"), view.nodes.map(kindOf));
  updateTypeOptions(
    $("edgeTypes"),
    view.edges.map((edge) => text(edge.type || "unknown")),
  );
  renderGraph();
  renderEditors();
  renderFindings();
  renderRuntime();
  renderMetrics();
  renderRepairs();
  controls();
}
async function refresh() {
  const endpoints = [
    "/api/knowledge",
    "/api/config",
    "/api/metrics",
    "/api/snapshots",
    "/api/repairs",
    "/api/policies",
  ];
  const results = await Promise.allSettled(endpoints.map((path) => api(path)));
  const failures = [];
  results.forEach((result, index) => {
    if (result.status === "rejected")
      failures.push(`${endpoints[index]}: ${result.reason.message}`);
  });
  if (results[0].status === "fulfilled") {
    live = normalizeGraph(results[0].value);
    if (!snapshot) view = live;
  }
  if (results[1].status === "fulfilled") configuration = results[1].value;
  if (results[2].status === "fulfilled") metrics = array(results[2].value);
  if (results[3].status === "fulfilled") snapshots = array(results[3].value);
  if (results[4].status === "fulfilled") repairs = array(results[4].value);
  if (results[5].status === "fulfilled") policies = array(results[5].value);
  renderConfiguration();
  renderRegistries();
  renderView();
  if (failures.length) throw new Error(failures.join("\n"));
}
function requireLive() {
  if (snapshot !== null)
    throw new Error(
      "Snapshots are immutable. Return to live knowledge before making changes.",
    );
}
$("run").addEventListener("click", () =>
  action("Analysis", async () => {
    requireLive();
    const result = await api("/api/analyze", "POST");
    await refresh();
    live = normalizeGraph({
      ...live,
      ...result,
      ...(result.graph || {}),
      runtime: result.runtime || live.runtime,
      decision: result.decision || live.decision,
    });
    view = live;
    renderView();
  }),
);
$("runRepair").addEventListener("click", () =>
  action("Independent repair", async () => {
    requireLive();
    const result = await api("/api/repair", "POST");
    await refresh();
    const record = result.repair || result;
    if (!repairs.length || repairId(repairs[0], 0) !== repairId(record, 0))
      repairs.unshift(record);
    $("repairSelect").value = "";
    renderRepairs();
  }),
);
$("runEvaluate").addEventListener("click", () =>
  action("Labeled-case evaluation", async () => {
    requireLive();
    latestEvaluation = await api("/api/evaluate", "POST");
    await refresh();
    renderMetrics();
  }),
);
$("refresh").addEventListener("click", () =>
  action("Live data refresh", refresh),
);
$("snapshotSelect").addEventListener("change", controls);
$("inspectSnapshot").addEventListener("click", () =>
  action("Snapshot inspection", async () => {
    const id = $("snapshotSelect").value;
    if (!id) throw new Error("Select a saved snapshot first.");
    const result = await api("/api/snapshots/" + encodeURIComponent(id));
    snapshot = id;
    view = normalizeGraph(result.snapshot || result);
    renderView();
    renderPolicyRecord();
  }),
);
$("liveView").addEventListener("click", () =>
  action("Returning to live knowledge", async () => {
    snapshot = null;
    view = live;
    await refresh();
  }),
);
for (const id of ["nodeKinds", "edgeTypes"])
  $(id).addEventListener("change", renderGraph);
for (const id of ["graphSearch", "nodeLimit"])
  $(id).addEventListener("input", renderGraph);
$("findingSearch").addEventListener("input", renderFindings);
$("nodeSelect").addEventListener("change", (event) =>
  selectNode(event.target.value),
);
$("edgeSelect").addEventListener("change", (event) =>
  selectEdge(event.target.value),
);
$("newNode").addEventListener("click", () => {
  selectNode("");
  $("nodeForm").elements.namedItem("label").focus();
});
$("newEdge").addEventListener("click", () => {
  selectEdge("");
  $("edgeForm").elements.namedItem("type").focus();
});
for (const type of ["node", "edge"]) {
  $(type + "Form").addEventListener("submit", (event) => {
    event.preventDefault();
    const data = Object.fromEntries(new FormData(event.target));
    const id = $(type + "Select").value;
    action(`Saving ${type}`, async () => {
      requireLive();
      if (!data.id) delete data.id;
      const result = await api(
        `/api/knowledge/${type}s` + (id ? "/" + encodeURIComponent(id) : ""),
        id ? "PUT" : "POST",
        data,
      );
      await refresh();
      (type === "node" ? selectNode : selectEdge)(result.id || id);
    });
  });
  $("delete" + (type === "node" ? "Node" : "Edge")).addEventListener(
    "click",
    () => {
      const id = $(type + "Select").value;
      if (
        !id ||
        !window.confirm(
          `Delete ${type} ${id}?${type === "node" ? " Connected edges will also be deleted." : ""} This updates live annotations only; immutable snapshots are unchanged.`,
        )
      )
        return;
      action(`Deleting ${type}`, async () => {
        requireLive();
        await api(
          `/api/knowledge/${type}s/` + encodeURIComponent(id),
          "DELETE",
        );
        await refresh();
        (type === "node" ? selectNode : selectEdge)("");
      });
    },
  );
}
$("repairSelect").addEventListener("change", renderRepairs);
$("policySelect").addEventListener("change", renderPolicyRecord);
$("approvalPolicy").addEventListener("input", () => {
  $("approvalConsent").checked = false;
});
$("approvalForm").addEventListener("submit", (event) => {
  event.preventDefault();
  action("Explicit operator policy approval", async () => {
    requireLive();
    if (!$("approvalConsent").checked)
      throw new Error("Explicit operator confirmation is required.");
    let policy;
    try {
      policy = JSON.parse($("approvalPolicy").value);
    } catch (_) {
      throw new Error("Policy must be valid JSON.");
    }
    if (!policy || typeof policy !== "object" || Array.isArray(policy))
      throw new Error("Policy must be a JSON object.");
    const approved_by = $("approvedBy").value.trim();
    if (!approved_by) throw new Error("Operator identity is required.");
    await api("/api/policies/approve", "POST", { policy, approved_by });
    await refresh();
  });
});
action("Loading dashboard", refresh);
