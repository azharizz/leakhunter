"""Bounded, source-backed advisory review units from the analyzer's existing graph."""
from __future__ import annotations

from collections import defaultdict, deque
import hashlib
import json
from pathlib import Path

from unspool.languages import entrypoint_name, finding_function, manifest_language, module_name
from unspool.policy.engine import Policy
from unspool.providers.disclosure import MAX_CONTEXT_BYTES, SECRET_PATTERN, review_source

_MAX_UNITS = 24
_MAX_CONNECTED = 12
_MAX_NODES = 256
_MAX_EDGES = 768
_REQUEST_OVERHEAD = 16 * 1024
_FUNCTIONS = {"FunctionDef", "AsyncFunctionDef"}
_FINDING_KEYS = {"id", "severity", "title", "source", "classification", "sink", "file", "line",
                 "function", "path", "rule", "reasons", "static_result", "status",
                 "context_requirements", "policy_violation"}


def _safe(value):
    """Keep JSON evidence only; never forward exception text or arbitrary objects."""
    if isinstance(value, str):
        return "[withheld suspected credential]" if SECRET_PATTERN.search(value) else value
    if value is None or type(value) in (bool, int):
        return value
    if isinstance(value, list):
        return [_safe(item) for item in value]
    if isinstance(value, dict):
        return {_safe(key): _safe(item) for key, item in value.items() if isinstance(key, str)}
    return None



def _span(node):
    decorators = node.get("decorator_list", [])
    start = min([node.get("lineno", 1)] + [item.get("lineno", 1) for item in decorators])
    return start, node.get("end_lineno", node.get("lineno", 1))


def _source_layout(record):
    """Use cached AST spans, not another parse or cached literal values as source."""
    tree = record.get("ast", {})
    definitions, declarations = {}, []
    stack = [tree]
    while stack:
        node = stack.pop()
        if not isinstance(node, dict) or "_type" not in node:
            continue
        kind = node["_type"]
        if kind in _FUNCTIONS | {"ClassDef"}:
            definitions[(kind, node.get("lineno", 1), node.get("name"))] = node
        for value in node.values():
            if isinstance(value, dict):
                stack.append(value)
            elif isinstance(value, list):
                stack.extend(value)
    for node in tree.get("body", []):
        if node.get("_type") not in _FUNCTIONS | {"ClassDef"}:
            declarations.append(_span(node))
    return definitions, declarations
_ROUTE_METHODS = {"route", "get", "post", "put", "delete", "patch", "head", "options"}


def _is_route_definition(definition):
    for decorator in definition.get("decorator_list", []) if isinstance(definition, dict) else []:
        function = decorator.get("func", {}) if decorator.get("_type") == "Call" else decorator
        if isinstance(function, dict) and function.get("attr") in _ROUTE_METHODS:
            return True
    return False


def _parameters(definition):
    arguments = definition.get("args", {}) if isinstance(definition, dict) else {}
    names = []
    for key in ("posonlyargs", "args", "kwonlyargs"):
        names.extend(argument.get("arg") for argument in arguments.get(key, [])
                     if isinstance(argument, dict) and isinstance(argument.get("arg"), str))
    for key, prefix in (("vararg", "*"), ("kwarg", "**")):
        argument = arguments.get(key)
        if isinstance(argument, dict) and isinstance(argument.get("arg"), str):
            names.append(prefix + argument["arg"])
    return names


def _node_view(node, role=None):
    item = {key: node[key] for key in ("id", "label", "kind", "file", "line")
            if key in node}
    for key in ("classification", "symbol", "sink"):
        if key in node:
            item[key] = node[key]
    if role:
        item["role"] = role
    return _safe(item)


def _flow_paths(findings, nodes, kept):
    paths = []
    for finding in findings:
        route = [identity for identity in finding.get("path", []) if identity in nodes]
        if not route:
            continue
        path_nodes = [_node_view(nodes[identity], "sink" if nodes[identity].get("sink")
                                 else "source" if nodes[identity].get("classification") else "transform")
                      for identity in route if identity in kept]
        if not path_nodes:
            continue
        file = finding.get("file", "")
        predicates = [_node_view(node, "branch_predicate") | {"relation": "POTENTIAL_CONTROL_SCOPE",
                                                              "source_ref": f"{node['file']}:{node['line']}"}
                      for node in nodes.values()
                      if node.get("id") in kept and node.get("kind") in {"If", "IfExp"}
                      and node.get("file") == file]
        paths.append({"id": finding.get("id"), "status": finding.get("static_result", "POSSIBLE_FLOW"),
                      "source_ref": f"{finding.get('file', '')}:{finding.get('line', '')}",
                      "sink": finding.get("sink"), "steps": path_nodes,
                      "branch_predicates": predicates,
                      "omissions": (["Scoped graph omitted part of the flow path."]
                                    if len(path_nodes) != len(route) else [])})
    return paths


def _runtime_event(event):
    return _safe({key: event[key] for key in
                  ("module", "callable", "role", "order", "returned_type", "returned_bool", "raised")
                  if key in event})


def _trace_line(line):
    return _safe({"file": line.get("file"), "line": line.get("line")})


def _runtime_evidence(runtime, manifest, functions, locations):
    declared = []
    language = manifest_language(manifest) if manifest else "python"
    for case in (manifest or {}).get("cases", []):
        entrypoint = entrypoint_name(case, language)
        mapping = case.get("finding", {})
        mapped = finding_function(case)
        if entrypoint in functions or (mapping.get("file"), mapped) in locations:
            declared.append(case)
    executed = {case.get("id"): case for case in runtime.get("cases", [])}
    cases = []
    for case in declared[:32]:
        captured = executed.get(case.get("id"))
        context = case.get("context", {})
        safe_context = {key: context[key] for key in ("audience", "recipient")
                        if isinstance(context.get(key), str)}
        safe_context.update({key: context[key] for key in ("authorized", "synthetic")
                             if type(context.get(key)) is bool})
        contract = context.get("contract")
        if isinstance(contract, (str, bool)) or isinstance(contract, list) and all(isinstance(item, str) for item in contract):
            safe_context["contract"] = contract
        tenant, source_tenant = context.get("tenant"), context.get("source_tenant")
        if tenant is not None and source_tenant is not None and tenant != "" and source_tenant != "":
            safe_context["same_tenant"] = tenant == source_tenant
        item = {"id": case.get("id"), "module": case.get("module"), "callable": case.get("callable"),
                "context": _safe(safe_context), "status": "NOT_RUN" if captured is None else runtime.get("status", "UNKNOWN")}
        if language != "python":
            item["entrypoint"] = _safe(case["entrypoint"])
        if captured is not None:
            item.update({key: captured[key] for key in ("passed", "observed") if type(captured.get(key)) is bool})
            item["execution_error"] = bool(captured.get("error"))
            item["observations"] = [_safe({key: observation[key] for key in ("sink", "symbol") if key in observation})
                                    for observation in captured.get("observations", [])[:32]]
            item["violations"] = [_safe({key: violation[key] for key in ("sink", "symbol", "classification", "reasons") if key in violation})
                                  for violation in captured.get("violations", [])[:32]]
            item["call_events"] = [_runtime_event(event) for event in captured.get("call_events", [])[:64]]
            item["executed_lines"] = [_trace_line(line) for line in captured.get("executed_lines", [])[:256]]
            item["omitted_observations"] = max(0, len(captured.get("observations", [])) - 32)
            item["omitted_violations"] = max(0, len(captured.get("violations", [])) - 32)
            item["omitted_call_events"] = max(0, len(captured.get("call_events", [])) - 64)
            item["omitted_trace_lines"] = max(0, len(captured.get("executed_lines", [])) - 256)
        cases.append(_safe(item))
    return {"status": _safe(runtime.get("status", "NOT_RUN")), "cases": cases,
            "omitted_cases": max(0, len(declared) - 32),
            "scope": "Only matched declared cases; observations apply only to those executed synthetic inputs, not universal safety."}


def _fits(review):
    # The runner JSON-encodes the state inside the typed request. Count that escaping too.
    return len(json.dumps(json.dumps(review, ensure_ascii=True), ensure_ascii=True).encode()) <= MAX_CONTEXT_BYTES - _REQUEST_OVERHEAD


def build_review_contexts(repository: Path, analysis: dict, policy: Policy, runtime: dict,
                          manifest: dict | None, revision: str) -> dict:
    language = manifest_language(manifest) if manifest else "python"
    nodes = {node["id"]: node for node in analysis.get("nodes", [])}
    edges = analysis.get("edges", [])
    children, parents = defaultdict(list), {}
    for edge in edges:
        if edge.get("type") == "AST" and edge["source"] in nodes and edge["target"] in nodes:
            children[edge["source"]].append(edge["target"])
            parents[edge["target"]] = edge["source"]
    owners, names, members = {}, {}, defaultdict(set)
    roots = sorted(identity for identity, node in nodes.items() if node.get("kind") == "Module")
    for root in roots:
        stack = [(root, root, module_name(nodes[root]["file"]))]
        while stack:
            identity, owner, qualified = stack.pop()
            if identity in owners:
                continue
            node = nodes[identity]
            if node.get("kind") in _FUNCTIONS | {"ClassDef"}:
                qualified += "." + node["label"]
            if node.get("kind") in _FUNCTIONS:
                owner = identity
            owners[identity] = owner
            members[owner].add(identity)
            names[owner] = qualified if identity == owner else names.get(owner, qualified)
            stack.extend((child, owner, qualified) for child in reversed(children[identity]))
    files = analysis.get("index", {}).get("files", {})
    layouts = {path: _source_layout(record) for path, record in files.items()}
    triggers, related_findings = defaultdict(list), defaultdict(list)
    for identity, node in nodes.items():
        if node.get("sink") and identity in owners:
            triggers[owners[identity]].append({"node_id": identity, "kind": node["sink"], "line": node["line"]})
    entrypoint_declarations = defaultdict(set)
    for qualified in analysis.get("index", {}).get("entrypoints", []):
        entrypoint_declarations[qualified].add("analysis")
    for case in (manifest or {}).get("cases", []):
        qualified = entrypoint_name(case, language)
        entrypoint_declarations[qualified].add("manifest")
    for owner, qualified in names.items():
        node = nodes.get(owner, {})
        definition = layouts.get(node.get("file"), ({}, []))[0].get(
            (node.get("kind"), node.get("line"), node.get("label")))
        if _is_route_definition(definition):
            entrypoint_declarations[qualified].add("route_decorator")
    for owner, qualified in names.items():
        declared_by = sorted(entrypoint_declarations.get(qualified, ()))
        if declared_by:
            triggers[owner].append({"node_id": owner, "kind": "DECLARED_ENTRYPOINT",
                                    "line": nodes[owner]["line"], "declared_by": declared_by})
    by_location = defaultdict(list)
    for identity, node in nodes.items():
        if identity in owners:
            by_location[(node.get("file"), node.get("line"))].append(identity)

    def enclosing(file, line, function=None):
        candidates = by_location.get((file, line), [])
        if function:
            matching = [owner for owner in members if nodes[owner].get("file") == file and names.get(owner) == function]
            if matching:
                return matching[0]
        calls = [identity for identity in candidates if nodes[identity].get("kind") == "Call"]
        return owners.get((calls or candidates)[0]) if calls or candidates else None

    unresolved_by_owner = defaultdict(list)
    for call in analysis.get("coverage", {}).get("unresolved_calls", []):
        owner = enclosing(call.get("file"), call.get("line"))
        if owner is not None:
            unresolved_by_owner[owner].append(call)
            triggers[owner].append({"node_id": next((identity for identity in by_location[(call["file"], call["line"])]
                                                       if nodes[identity].get("kind") == "Call"), owner),
                                    "kind": "UNRESOLVED_CALL", "line": call["line"]})
    for finding in analysis.get("findings", []):
        owner = enclosing(finding.get("file"), finding.get("line"), finding.get("function"))
        if owner is not None:
            related_findings[owner].append(finding)
            triggers[owner].append({"node_id": finding.get("path", [owner])[-1] if finding.get("path") else owner,
                                    "kind": finding.get("sink", "FINDING"), "line": finding.get("line", nodes[owner]["line"])})
    connected = defaultdict(set)
    for edge in edges:
        if edge.get("type") == "CALLS":
            source, target = owners.get(edge["source"]), owners.get(edge["target"])
            if source is not None and target is not None and source != target:
                connected[source].add(target)
                connected[target].add(source)
    ordered = sorted(triggers, key=lambda owner: (nodes[owner]["file"], nodes[owner]["line"], owner))
    source_cache = {}
    reviews, limitations = [], []
    omitted_units = max(0, len(ordered) - _MAX_UNITS)
    if omitted_units:
        limitations.append(f"Review unit limit: {omitted_units} units omitted (maximum {_MAX_UNITS}).")
    coverage_incomplete = bool(analysis.get("coverage", {}).get("parse_errors") or
                               analysis.get("coverage", {}).get("unsupported_constructs"))
    if coverage_incomplete:
        limitations.append("Analyzer reports parse errors or unsupported constructs; repository coverage is incomplete.")
    for owner in ordered[:_MAX_UNITS]:
        omissions = []
        selected, queue = {owner}, deque([owner])
        while queue and len(selected) < _MAX_CONNECTED:
            current = queue.popleft()
            for neighbor in sorted(connected[current]):
                if neighbor not in selected and len(selected) < _MAX_CONNECTED:
                    selected.add(neighbor)
                    queue.append(neighbor)
        if any(connected[item] - selected for item in selected):
            omissions.append(f"Connected caller/callee scope limit reached ({_MAX_CONNECTED}); additional code omitted.")
        wanted = set().union(*(members[item] for item in selected))
        for identity in list(wanted):
            parent = parents.get(identity)
            while parent and parent not in wanted:
                wanted.add(parent)
                parent = parents.get(parent)
        primary = sorted(triggers[owner], key=lambda item: (
            {"DECLARED_ENTRYPOINT": 2, "UNRESOLVED_CALL": 1}.get(item["kind"], 0),
            item["line"], item["node_id"]))[0]
        priority = {owner, primary["node_id"]} | selected
        node_ids = sorted(wanted, key=lambda identity: (identity not in priority, nodes[identity].get("kind") not in _FUNCTIONS | {"Call", "Return"}, identity))[:_MAX_NODES]
        kept = set(node_ids)
        if wanted - kept:
            omissions.append(f"Graph node limit: {len(wanted - kept)} scoped nodes omitted.")
        relevant_edges = [edge for edge in edges if edge["source"] in kept and edge["target"] in kept]
        graph_edges = sorted(relevant_edges, key=lambda edge: (edge["type"] != "CALLS", edge["id"]))[:_MAX_EDGES]
        if len(relevant_edges) > len(graph_edges):
            omissions.append(f"Graph edge limit: {len(relevant_edges) - len(graph_edges)} scoped edges omitted.")
        if any(edge["type"] != "AST" and (edge["source"] in wanted) != (edge["target"] in wanted) for edge in edges):
            omissions.append("Graph edges crossing the selected caller/callee scope are omitted.")
        ranges = defaultdict(list)
        for item in sorted(selected, key=lambda identity: (identity != owner, nodes[identity]["file"], nodes[identity]["line"])):
            node = nodes[item]
            path = node["file"]
            definitions, declarations = layouts.get(path, ({}, []))
            if node["kind"] == "Module":
                ranges[path].append((1, None))
            else:
                definition = definitions.get((node["kind"], node["line"], node["label"]))
                if definition:
                    ranges[path].append(_span(definition))
                else:
                    omissions.append("Cached AST span unavailable; function source omitted.")
                ranges[path].extend(declarations)
                parent = parents.get(item)
                while parent:
                    ancestor = nodes[parent]
                    if ancestor["kind"] == "ClassDef":
                        definition = definitions.get((ancestor["kind"], ancestor["line"], ancestor["label"]))
                        if definition and definition.get("body"):
                            ranges[path].append((_span(definition)[0], max(ancestor["line"], definition["body"][0]["lineno"] - 1)))
                    elif ancestor["kind"] in _FUNCTIONS:
                        omissions.append("Enclosing function body/closure context is not fully included.")
                    parent = parents.get(parent)
        code, refs = [], [f"revision:{revision}", f"policy:{policy.digest}"]
        for path, spans in ranges.items():
            if path not in source_cache:
                try:
                    source_cache[path] = review_source(Path(repository), path, files.get(path, {}).get("hash", ""))
                except (OSError, ValueError, UnicodeError, RuntimeError):
                    source_cache[path] = None
            source = source_cache[path]
            if source is None:
                omissions.append(f"Source withheld for {_safe(path)}: disclosure checks failed.")
                continue
            lines = source.splitlines(keepends=True)
            merged = []
            for start, end in sorted((start, len(lines) if end is None else end) for start, end in spans):
                if merged and start <= merged[-1][1] + 1:
                    merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
                else:
                    merged.append((start, end))
            for start, end in merged:
                code.append({"file": path, "start_line": start, "end_line": end,
                             "text": "".join(lines[start - 1:end]), "sha256": files[path]["hash"]})
        findings = [finding for item in sorted(selected) for finding in related_findings[item]]
        flow_paths = _flow_paths(findings, nodes, kept)
        safe_findings = []
        for finding in findings[:64]:
            item = _safe({key: value for key, value in finding.items() if key in _FINDING_KEYS})
            evidence = finding.get("runtime_evidence", {})
            item["runtime_evidence"] = _safe({key: evidence[key] for key in ("version", "status", "observed", "case_ids") if key in evidence})
            safe_findings.append(item)
        if len(findings) > 64:
            omissions.append(f"Finding limit: {len(findings) - 64} findings omitted.")
        evidence = _runtime_evidence(runtime, manifest, {names[item] for item in selected},
                                     {(nodes[item]["file"], names[item]) for item in selected})
        if evidence["omitted_cases"] or any(
                case.get("omitted_observations") or case.get("omitted_violations")
                or case.get("omitted_call_events") or case.get("omitted_trace_lines")
                for case in evidence["cases"]):
            omissions.append("Runtime evidence limits reached; cases, observations or traces omitted.")
        unknowns = ["Static classifications, including PUBLIC or no findings, do not establish that data is safe to disclose.",
                    "Runtime audience, recipient, authorization and tenant isolation are not proven by this static graph.",
                    "External database schema/data contracts, authentication/authorization implementations and third-party behavior are unknown unless explicitly supplied in reviewed source or matched evidence.",
                    "Imports and module declarations are source context, not proof of dependency behavior or execution coverage."]
        for item in sorted(selected):
            unknowns.extend(f"Unresolved external/dynamic call at {_safe(call['file'])}:{call['line']}: {_safe(call['call'])}; potential boundary, not an established sink."
                            for call in unresolved_by_owner[item][:32])
            if len(unresolved_by_owner[item]) > 32:
                omissions.append("Additional unresolved calls omitted from unknowns.")
        unknowns.extend(_safe(analysis.get("coverage", {}).get("limitations", [])[:32]))
        coverage = analysis.get("coverage", {})
        if coverage.get("parse_errors") or coverage.get("unsupported_constructs"):
            omissions.append("Analyzer reports parse errors or unsupported constructs; repository coverage is incomplete.")
        owner_name = names[owner]
        definition = layouts.get(nodes[owner]["file"], ({}, []))[0].get(
            (nodes[owner].get("kind"), nodes[owner].get("line"), nodes[owner].get("label")))
        callers, callees = set(), set()
        for edge in edges:
            if edge.get("type") != "CALLS":
                continue
            source_owner, target_owner = owners.get(edge.get("source")), owners.get(edge.get("target"))
            if target_owner == owner and source_owner in names:
                callers.add(names[source_owner])
            if source_owner == owner and target_owner in names:
                callees.add(names[target_owner])
        declared_cases = [
            case for case in (manifest or {}).get("cases", [])
            if entrypoint_name(case, language) == owner_name
        ]
        recipients = {node.get("sink") for identity, node in nodes.items()
                      if identity in kept and node.get("sink")}
        recipient_contracts, applicable_questions, security_contexts, boundary_kinds = [], set(), set(), set()
        for case in declared_cases:
            case_context = case.get("context", {})
            recipient = case_context.get("recipient")
            boundary_kind = case_context.get("boundary_kind")
            if isinstance(recipient, str):
                recipients.add(recipient)
            if isinstance(boundary_kind, str):
                boundary_kinds.add(boundary_kind)
                recipients.add(boundary_kind)
            if isinstance(case_context.get("applicable_questions"), list):
                applicable_questions.update(
                    item for item in case_context["applicable_questions"] if isinstance(item, str)
                )
            if isinstance(case_context.get("security_contexts"), list):
                security_contexts.update(
                    item for item in case_context["security_contexts"] if isinstance(item, str)
                )
            contract = case_context.get("contract")
            if isinstance(recipient, str) or isinstance(boundary_kind, str) or contract is not None:
                recipient_contracts.append(_safe({
                    "case_id": case.get("id"),
                    "recipient": recipient,
                    "boundary_kind": boundary_kind,
                    "contract": contract,
                    "audience": case_context.get("audience"),
                    "authorized": case_context.get("authorized"),
                    "same_tenant": case_context.get("same_tenant"),
                }))
        if boundary_kinds:
            recipients = boundary_kinds
        source_locations = [{"file": nodes.get(item.get("node_id"), nodes[owner]).get("file"),
                            "line": item["line"]}
                           for item in triggers[owner] if isinstance(item.get("line"), int)]
        boundary = {**primary, "file": nodes[owner]["file"], "function": owner_name,
                    "entrypoint": {"file": nodes[owner]["file"], "line": nodes[owner]["line"],
                                   "function": owner_name,
                                   "declared": owner_name in entrypoint_declarations,
                                   "declared_by": sorted(entrypoint_declarations.get(owner_name, ()))},
                    "callers": sorted(callers), "callees": sorted(callees),
                    "connected_functions": sorted(names[item] for item in selected - {owner} if item in names),
                    "input_fields": _parameters(definition),
                    "output_recipients": sorted(item for item in recipients if isinstance(item, str)),
                    "source_locations": source_locations[:32]}
        if len(boundary_kinds) == 1:
            boundary["boundary_kind"] = next(iter(boundary_kinds))
        elif boundary_kinds:
            boundary["boundary_kinds"] = sorted(boundary_kinds)
        if recipient_contracts:
            boundary["recipient_contracts"] = recipient_contracts
        if applicable_questions:
            boundary["applicable_questions"] = sorted(applicable_questions)
        if security_contexts:
            boundary["security_contexts"] = sorted(security_contexts)
        review = {"review_id": hashlib.sha256(f"{nodes[owner]['file']}|{owner_name}|{owner}".encode()).hexdigest()[:24],
                  "objective": "Assess plausible unauthorized disclosure at this boundary using only supplied source, configured policy and scoped evidence; identify missing context and targeted runtime checks, not release approval.",
                  "boundary": _safe(boundary),
                  "scope": {"complete": False, "omissions": omissions}, "code": code,
                  "flow_paths": _safe(flow_paths),
                  "graph": {"nodes": [_safe({key: nodes[identity][key] for key in ("id", "label", "kind", "file", "line", "sink", "classification", "symbol") if key in nodes[identity]}) for identity in node_ids],
                            "edges": [_safe(edge) for edge in graph_edges]},
                  "findings": safe_findings,
                  "policy": {"origin": "configured_policy", "rules": _safe({key: value for key, value in policy.raw.items() if key != "approved_by"})},
                  "runtime_evidence": evidence, "unknowns": unknowns, "evidence_refs": refs}
        # Drop whole evidence records, never misleading partial source snippets.
        while not _fits(review) and review["code"]:
            review["code"].pop()
            if "Request size limit: whole source excerpts omitted." not in omissions:
                omissions.append("Request size limit: whole source excerpts omitted.")
        if not _fits(review):
            review["graph"] = {"nodes": [], "edges": []}
            omissions.append("Request size limit: scoped graph omitted.")
        if not _fits(review):
            omitted_units += 1
            limitations.append("Review unit omitted because its required metadata exceeds the request size limit.")
            continue
        refs.extend(f"source:{entry['file']}:{entry['start_line']}-{entry['end_line']}:sha256:{entry['sha256']}" for entry in review["code"])
        refs.extend(f"finding:{finding['id']}" for finding in safe_findings if "id" in finding)
        refs.extend(f"runtime:{case['id']}" for case in evidence["cases"])
        # Evidence references also count toward the disclosure budget.
        if not _fits(review):
            omitted_units += 1
            limitations.append("Review unit omitted because evidence references exceed the request size limit.")
            continue
        reviews.append(review)
    return {"version": 2, "revision_sha": revision, "policy_digest": policy.digest,
            "scope": {"review_unit_count": len(reviews), "omitted_review_units": omitted_units,
                      "selection_complete": not omitted_units and not coverage_incomplete and not any(review["scope"]["omissions"] for review in reviews),
                      "limitations": limitations}, "reviews": reviews}
