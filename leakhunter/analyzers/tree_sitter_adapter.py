from __future__ import annotations

import fnmatch
import hashlib
from pathlib import Path

from leakhunter.languages import DISPLAY_NAMES, extensions
from leakhunter.policy.engine import Policy
from leakhunter.analyzers.sources import exclusions, source_files

ANALYZER_VERSION = "tree-sitter-flow-2"
_EXCLUDED = exclusions("javascript")
_FUNCTIONS = {"function_declaration", "function_definition", "function_expression", "function_item",
              "method_declaration", "method_definition", "closure_expression", "arrow_function",
              "generator_function_declaration", "generator_function"}
_CLASSES = {"class_declaration", "class", "class_expression"}
_ASSIGNMENTS = {"variable_declarator", "assignment_expression", "augmented_assignment_expression",
                "assignment_statement", "short_var_declaration", "let_declaration", "var_spec", "const_spec"}
_BRANCHES = {"if_statement", "if_expression", "ternary_expression", "conditional_expression", "match_expression",
             "match_block", "switch_statement", "switch_body", "expression_switch_statement", "type_switch_statement",
             "select_statement"}
_LOOPS = {"for_statement", "for_in_statement", "while_statement", "do_statement", "for_expression",
          "while_expression", "loop_expression"}
_LITERALS = {"string", "string_literal", "raw_string_literal", "interpreted_string_literal", "char_literal",
             "rune_literal", "number", "integer_literal", "float_literal", "true", "false", "null", "nil"}
_IDENTIFIERS = {"identifier", "field_identifier", "property_identifier", "shorthand_property_identifier",
                "shorthand_property_identifier_pattern", "variable_name", "self"}


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()[:24]


def _language(name: str, *, tsx: bool = False):
    from tree_sitter import Language
    if name == "javascript":
        import tree_sitter_javascript as grammar
    elif name == "typescript":
        import tree_sitter_typescript as grammar
        return Language(grammar.language_tsx() if tsx else grammar.language_typescript())
    elif name == "go":
        import tree_sitter_go as grammar
    elif name == "rust":
        import tree_sitter_rust as grammar
    else:
        raise ValueError(f"unsupported language: {name}")
    return Language(grammar.language())


def _text(node, source: bytes) -> str:
    return source[node.start_byte:node.end_byte].decode("utf-8", "replace")


def _field(node, *names):
    for name in names:
        value = node.child_by_field_name(name)
        if value is not None:
            return value
    return None


def _name(node, source: bytes) -> str:
    name = _field(node, "name")
    if name is None and node.parent is not None and node.parent.type in {"variable_declarator", "assignment_expression", "pair", "let_declaration"}:
        name = _field(node.parent, "name", "left", "key", "pattern")
    return _text(name, source) if name is not None else f"<anonymous@{node.start_point.row + 1}:{node.start_point.column}>"


def _parameters(node, source):
    parameters = _field(node, "parameters", "parameter")
    if parameters is None:
        return []
    def names(item):
        if item.type in _IDENTIFIERS:
            return [_text(item, source)]
        target = _field(item, "pattern", "name", "left")
        if target is not None:
            targets = item.children_by_field_name("name") if item.child_by_field_name("name") is not None else [target]
            return [name for child in targets for name in names(child)]
        return [name for child in item.named_children if child.type not in {"type_annotation", "type_identifier", "predefined_type"}
                for name in names(child)]
    return list(dict.fromkeys(names(parameters)))


def _sink(call: str) -> str | None:
    value = call.lower().replace("::", ".")
    method = value.rsplit(".", 1)[-1]
    # Formatting functions produce strings; they do not write to a log.
    if value.startswith("fmt.") and method in {"sprint", "sprintf", "sprintln"}:
        return None
    if method in {"log", "debug", "info", "warn", "warning", "error", "fatal", "println", "eprintln", "printf", "print", "fprint", "fprintf", "fprintln"}:
        return "APPLICATION_LOG"
    if value in {"fetch", "http.request", "http.get", "http.post", "client.do"} or value.startswith("axios."):
        return "WEBHOOK"
    if method in {"track", "capture", "identify", "page"}:
        return "THIRD_PARTY_ANALYTICS"
    return None


class _Flow:
    def __init__(self, policy: Policy, language: str, entrypoints: list[str]):
        self.policy, self.language, self.entrypoints = policy, language, set(entrypoints)
        self.nodes, self.edges, self.findings = {}, {}, {}
        self.unresolved, self.unsupported = {}, {}
        self.functions = {}
        self.env, self.entry, self.boundary = {}, "<module>", False

    def node(self, node, path, kind=None, label=None):
        ident = f"{path}:ts:{node.start_byte}:{node.end_byte}:{node.type}"
        if ident not in self.nodes:
            self.nodes[ident] = {"id": ident, "label": label or node.type, "kind": kind or node.type,
                                 "file": path, "line": node.start_point.row + 1, "end_line": node.end_point.row + 1,
                                 "column": node.start_point.column, "end_column": node.end_point.column}
        return ident

    def edge(self, source, target, kind):
        ident = _hash(f"{source}|{target}|{kind}")
        self.edges[ident] = {"id": ident, "source": source, "target": target, "type": kind}

    def unsupported_at(self, node, path, kind=None):
        kind = kind or node.type
        self.unsupported[(path, node.start_point.row + 1, kind)] = {"file": path, "line": node.start_point.row + 1, "kind": kind}

    def index(self, root, path):
        module = Path(path).with_suffix("").as_posix().replace("/", ".")
        tree = {"_type": "Module", "body": [], "lineno": 1, "end_lineno": root.end_point.row + 1}
        def visit(node, parent=None, owner=tree, scope=module):
            function, cls = node.type in _FUNCTIONS, node.type in _CLASSES
            name = _name(node, self._source) if function or cls else None
            kind = "Module" if node == root else "FunctionDef" if function else "ClassDef" if cls else node.type
            ident = self.node(node, path, kind, name)
            if parent is not None:
                self.edge(parent, ident, "AST")
            if function or cls:
                record = {"_type": kind, "name": name, "lineno": node.start_point.row + 1,
                          "end_lineno": node.end_point.row + 1, "body": []}
                if function:
                    record["args"] = {"_type": "arguments", "args": [{"_type": "arg", "arg": name} for name in _parameters(node, self._source)]}
                    self.functions[ident] = (path, node, f"{scope}.{name}")
                owner["body"].append(record)
                owner, scope = record, f"{scope}.{name}"
            before = len(owner["body"])
            for child in node.named_children:
                visit(child, ident, owner, scope)
            if node.parent == root and not function and not cls and len(owner["body"]) == before:
                owner["body"].append({"_type": node.type, "lineno": node.start_point.row + 1, "end_lineno": node.end_point.row + 1})
            if node.type in {"ERROR", "await_expression", "yield_expression", "yield_statement", "decorator", "decorator_list",
                             "spread_element", "rest_pattern", "go_statement", "defer_statement", "unsafe_block", "try_expression",
                             "break_statement", "continue_statement", "break_expression", "continue_expression", "impl_item"}:
                self.unsupported_at(node, path)
        visit(root)
        return tree

    def flow(self, field, node, path):
        # With no receiver type inference, matching a policy's field suffix is conservative.
        selectors = [item["selector"] for item in self.policy.sources]
        selectors.extend(pattern for sink in self.policy.sinks.values() for pattern in sink.get("deny_fields", []))
        candidates = {f"*.{field}"}
        for selector in selectors:
            prefix, separator, suffix = selector.rpartition(".")
            if fnmatch.fnmatchcase(field, suffix):
                candidates.add(f"{prefix}.{field}" if separator else field)
        result = set()
        for symbol in sorted(candidates):
            classification = self.policy.classify(symbol)
            denied = any(fnmatch.fnmatchcase(symbol, pattern) for sink in self.policy.sinks.values() for pattern in sink.get("deny_fields", []))
            if classification == "PUBLIC" and not denied:
                continue
            ident = self.node(node, path)
            self.nodes[ident].update(classification=classification, symbol=symbol)
            result.add((symbol, classification, ident))
        return result

    def string_key(self, node):
        if node is None or node.type not in _LITERALS:
            return None
        fragments = node.named_children
        if fragments and all(child.type in {"string_fragment", "string_content", "raw_string_literal_content", "interpreted_string_literal_content"} for child in fragments):
            return "".join(_text(child, self._source) for child in fragments)
        return None

    def expr(self, node, path):
        if node is None or node.type in _FUNCTIONS | _CLASSES:
            return set()
        typ = node.type
        if typ in _IDENTIFIERS:
            return set(self.env.get(_text(node, self._source), set()))
        if typ in _LITERALS:
            return set()
        if typ in _ASSIGNMENTS | _BRANCHES | _LOOPS or typ in {"block", "statement_block", "return_expression", "return_statement"}:
            return self.statement(node, path)
        if typ in {"member_expression", "field_expression", "selector_expression", "attribute_expression", "subscript_expression", "index_expression"}:
            obj = _field(node, "object", "operand", "value", "argument")
            if obj is None and node.named_children:
                obj = node.named_children[0]
            prop = _field(node, "property", "field", "index")
            if prop is None and len(node.named_children) > 1:
                prop = node.named_children[-1]
            values = self.expr(obj, path)
            indexed = typ in {"subscript_expression", "index_expression"} or node.child_by_field_name("index") is not None
            field = self.string_key(prop) if indexed else _text(prop, self._source) if prop is not None else None
            if field is not None:
                return values | self.flow(field, node, path)
            if indexed and prop is not None and prop.type in {"number", "int_literal", "integer_literal"}:
                return values
            self.unsupported_at(node, path, "dynamic_field_access")
            return values | self.expr(prop, path)
        if typ in {"call_expression", "call", "function_call_expression", "method_call_expression"}:
            fn = _field(node, "function", "name", "method")
            call = _text(fn, self._source) if fn is not None else "<dynamic>"
            args = _field(node, "arguments", "args")
            values = self.expr(fn, path)
            if args is not None:
                for child in args.named_children:
                    values |= self.expr(child, path)
            kind = _sink(call)
            if kind:
                self.sink(values, kind, node, path)
                return set()
            self.unresolved[(path, node.start_point.row + 1, call)] = {"file": path, "line": node.start_point.row + 1, "call": call}
            return values
        if typ == "macro_invocation":
            macro = _field(node, "macro")
            call = _text(macro, self._source) if macro is not None else "<dynamic>"
            values = set()
            def tokens(item):
                nonlocal values
                if item.type in _LITERALS:
                    return
                if item.type in _IDENTIFIERS:
                    values |= self.expr(item, path)
                for index, child in enumerate(item.children):
                    if index and item.children[index - 1].type == "." and child.type in _IDENTIFIERS:
                        values |= self.flow(_text(child, self._source), child, path)
                    if child.is_named:
                        tokens(child)
            for child in node.named_children:
                if child != macro:
                    tokens(child)
            kind = _sink(call)
            if kind:
                self.sink(values, kind, node, path)
                return set()
            self.unsupported_at(node, path, "unexpanded_macro")
            self.unresolved[(path, node.start_point.row + 1, call)] = {"file": path, "line": node.start_point.row + 1, "call": call + "!"}
            return values
        result = set()
        for child in node.named_children:
            result |= self.expr(child, path)
        return result

    def sink(self, values, kind, node, path):
        target = self.node(node, path)
        self.nodes[target]["sink"] = kind
        for symbol, classification, source_id in values:
            self.edge(source_id, target, "DATA_FLOW")
            decision = self.policy.evaluate(classification, kind, symbol=symbol)
            if decision["allowed"]:
                continue
            finding_id = _hash(f"{path}|{self.entry}|{symbol}|{target}|{kind}")
            context_reasons = {"audience_unknown", "recipient_unknown", "required_contract_missing", "authorization_required", "same_tenant_required", "tenant_context_unknown"}
            self.findings[finding_id] = {"id": finding_id, "severity": "critical" if classification == "SECRET" else "high",
                "title": f"{classification} data reaches {kind}", "source": symbol, "classification": classification,
                "sink": kind, "file": path, "line": node.start_point.row + 1, "function": self.entry,
                "path": [source_id, target], "rule": f"policy_v{self.policy.version}", "reasons": decision["reasons"],
                "static_result": "POSSIBLE_FLOW", "status": "POSSIBLE",
                "context_requirements": [reason for reason in decision["reasons"] if reason in context_reasons],
                "policy_violation": any(reason not in context_reasons for reason in decision["reasons"])}

    @staticmethod
    def join(*envs):
        return {name: set().union(*(env.get(name, set()) for env in envs)) for name in set().union(*(env.keys() for env in envs))}

    def statement(self, node, path):
        typ = node.type
        if typ in _FUNCTIONS | _CLASSES:
            return set()
        if typ in {"return_statement", "return_expression"}:
            values = set()
            for child in node.named_children:
                values |= self.expr(child, path)
            if self.boundary:
                self.sink(values, "HTTP_RESPONSE", node, path)
            return values
        if typ in _ASSIGNMENTS:
            right = _field(node, "value", "right")
            left = _field(node, "left", "name", "pattern")
            values = self.expr(right, path)
            if left is not None:
                def bind(target):
                    if target.type in _IDENTIFIERS:
                        name = _text(target, self._source)
                        self.env[name] = self.env.get(name, set()) | values if typ == "augmented_assignment_expression" else set(values)
                    elif target.type in {"expression_list", "identifier_list", "tuple_pattern", "array_pattern", "object_pattern", "slice_pattern", "mut_pattern", "reference_pattern"}:
                        if target.type not in {"expression_list", "identifier_list", "mut_pattern", "reference_pattern"}:
                            self.unsupported_at(target, path, "destructuring_assignment")
                        for child in target.named_children:
                            bind(child)
                    else:
                        self.unsupported_at(target, path, "indirect_assignment")
                        self.expr(target, path)
                targets = node.children_by_field_name("name") if typ in {"var_spec", "const_spec"} else [left]
                for target in targets:
                    bind(target)
            return values
        if typ in _BRANCHES:
            condition = _field(node, "condition", "value")
            initializer = _field(node, "initializer")
            if initializer is not None:
                self.statement(initializer, path)
            self.expr(condition, path)
            values = set()
            before = self.join(self.env)
            branches = [before]
            for child in node.named_children:
                if child == condition or child == initializer:
                    continue
                self.env = self.join(before)
                values |= self.statement(child, path)
                branches.append(self.env)
            self.env = self.join(*branches)
            return values
        if typ in _LOOPS:
            # Finite taint sets reach a fixed point; no path or iteration-count inference.
            values = set()
            while True:
                before = self.join(self.env)
                for child in node.named_children:
                    values |= self.statement(child, path)
                self.env = self.join(before, self.env)
                if self.env == before:
                    return values
        if typ in {"block", "statement_block", "statement_list", "else_clause", "expression_statement", "lexical_declaration", "variable_declaration", "var_declaration", "const_declaration", "export_statement", "match_arm", "expression_case", "type_case", "communication_case", "default_case"}:
            values = set()
            for child in node.named_children:
                values = self.statement(child, path)
            return values
        return self.expr(node, path)

    def run_function(self, fn, path, qualified):
        self.env, self.entry, self.boundary = {}, qualified, qualified in self.entrypoints
        for name in _parameters(fn, self._source):
            self.env[name] = set()
        body = _field(fn, "body")
        if body is None:
            self.unsupported_at(fn, path, "function_without_body")
            return
        values = self.statement(body, path)
        concise = fn.type == "arrow_function" and body.type != "statement_block"
        tail = None
        if self.language == "rust" and body.type == "block" and body.named_children:
            last = body.named_children[-1]
            if last.type == "expression_statement" and not any(child.type == ";" for child in last.children):
                last = last.named_children[-1] if last.named_children else last
            if last.type not in {"expression_statement", "return_expression", "empty_statement"} and not last.type.endswith(("_declaration", "_item")):
                tail = last
        closure = fn.type == "closure_expression" and body.type != "block"
        if self.boundary and (concise or tail is not None or closure):
            self.sink(values, "HTTP_RESPONSE", tail if tail is not None else body, path)


def analyze_project(root: Path, policy: Policy, previous: dict | None = None, *, entrypoints: list[str] | None = None, language: str) -> dict:
    from tree_sitter import Parser
    if language not in {"javascript", "typescript", "go", "rust"}:
        raise ValueError(f"unsupported language: {language}")
    root = Path(root).resolve()
    entrypoints = sorted(set(entrypoints or []))
    project = _Flow(policy, language, entrypoints)
    parsers, files, parse_errors = {}, {}, []
    for file, source in source_files(root, extensions(language), _EXCLUDED):
        relative = file.relative_to(root).as_posix()
        tsx = file.suffix == ".tsx"
        if tsx not in parsers:
            parsers[tsx] = Parser(_language(language, tsx=tsx))
        tree = parsers[tsx].parse(source)
        project._source = source
        if tree.root_node.has_error:
            parse_errors.append({"file": relative, "line": 1, "error": "SyntaxError"})
        files[relative] = {"hash": hashlib.sha256(source).hexdigest(), "ast": project.index(tree.root_node, relative)}
        for path, fn, qualified in list(project.functions.values()):
            if path == relative:
                project.run_function(fn, path, qualified)
        project.env, project.entry, project.boundary = {}, Path(relative).with_suffix("").as_posix().replace("/", "."), False
        project.statement(tree.root_node, relative)
    known = {qualified for _, _, qualified in project.functions.values()}
    unsupported = list(project.unsupported.values())
    unsupported.extend({"file": "", "line": 1, "kind": "unresolved_entrypoint", "entrypoint": name} for name in entrypoints if name not in known)
    coverage = {"language": DISPLAY_NAMES[language], "supported_language": DISPLAY_NAMES[language], "analyzer_version": ANALYZER_VERSION,
        "analyzed_files": len(files), "unsupported_constructs": sorted(unsupported, key=lambda item: (item["file"], item["line"], item["kind"])),
        "supported": ["tree-sitter parsing", "normalized function owners and source spans", "local aliases and conservative branch joins",
                      "direct and string-indexed sensitive fields", "configured entrypoint returns", "logging and request sinks"],
        "limitations": ["Bounded intraprocedural analysis; no parity claim with Python", "No framework, receiver type, import, closure, or interprocedural inference",
                        "Policy field suffix matches conservatively without receiver type proof", "Unknown calls propagate receiver and argument taint; their internal sinks are unresolved",
                        "Object fields are merged; computed keys, mutation, destructuring, and reflection may be incomplete",
                        "Rust logging macros use token-tree field and alias propagation, not macro expansion", "Branch and loop joins are path insensitive; exceptions and control transfers are not modeled"],
        "parse_errors": parse_errors, "unresolved_calls": sorted(project.unresolved.values(), key=lambda item: (item["file"], item["line"], item["call"]))}
    changed = sorted(files)
    deleted = sorted(set((previous or {}).get("files", {})) - set(files))
    return {"nodes": sorted(project.nodes.values(), key=lambda item: item["id"]), "edges": sorted(project.edges.values(), key=lambda item: item["id"]),
        "findings": sorted(project.findings.values(), key=lambda item: item["id"]),
        "index": {"analyzer_version": ANALYZER_VERSION, "policy_digest": policy.digest, "entrypoints": entrypoints, "files": files},
        "coverage": coverage, "incremental": {"mode": "full", "changed": changed, "deleted": deleted, "invalidated": changed, "reused": [], "reused_ast": []}}


def analyze_repository(root: Path, policy: Policy, *, language: str):
    result = analyze_project(root, policy, language=language)
    return result["nodes"], result["edges"], result["findings"]
