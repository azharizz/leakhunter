from __future__ import annotations

import ast
import copy
import fnmatch
import hashlib
from dataclasses import dataclass, field
from pathlib import Path

from unspool.policy.engine import Policy
from unspool.analyzers.sources import exclusions, source_files

ANALYZER_VERSION = "python-flow-6"
# Whole entrypoint arguments are opaque records that may hold any policy field.
OPAQUE = "OPAQUE_RECORD"
SINKS = {
    "logging.debug": "APPLICATION_LOG", "logging.info": "APPLICATION_LOG",
    "logging.warning": "APPLICATION_LOG", "logging.error": "APPLICATION_LOG",
    "logging.exception": "APPLICATION_LOG", "logging.critical": "APPLICATION_LOG",
    "print": "APPLICATION_LOG", "flask.jsonify": "HTTP_RESPONSE",
    "fastapi.responses.JSONResponse": "HTTP_RESPONSE", "starlette.responses.JSONResponse": "HTTP_RESPONSE",
    "requests.post": "WEBHOOK", "requests.put": "WEBHOOK", "requests.request": "WEBHOOK",
    "httpx.post": "WEBHOOK", "httpx.put": "WEBHOOK", "httpx.request": "WEBHOOK",
    "litellm.completion": "AI_PROMPT", "litellm.acompletion": "AI_PROMPT",
    "openai.chat.completions.create": "AI_PROMPT",
    "openai.responses.create": "AI_PROMPT",
    "anthropic.messages.create": "AI_PROMPT",
}
METHOD_SINKS = {
    "track": "THIRD_PARTY_ANALYTICS", "capture": "THIRD_PARTY_ANALYTICS",
    "jsonify": "HTTP_RESPONSE", "JSONResponse": "HTTP_RESPONSE",
}
EXCLUDED = exclusions("python")


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()[:24]


def _encode(node):
    if isinstance(node, ast.AST):
        return {"_type": type(node).__name__, **{key: _encode(value) for key, value in ast.iter_fields(node)},
                **{key: getattr(node, key) for key in ("lineno", "col_offset", "end_lineno", "end_col_offset") if hasattr(node, key)}}
    if isinstance(node, list):
        return [_encode(item) for item in node]
    if isinstance(node, bytes):
        return {"_bytes": node.hex()}
    if isinstance(node, complex):
        return {"_complex": [node.real, node.imag]}
    if node is Ellipsis:
        return {"_ellipsis": True}
    return node


def _decode(value):
    if isinstance(value, list):
        return [_decode(item) for item in value]
    if not isinstance(value, dict):
        return value
    if "_bytes" in value:
        return bytes.fromhex(value["_bytes"])
    if "_complex" in value:
        return complex(*value["_complex"])
    if "_ellipsis" in value:
        return Ellipsis
    node = getattr(ast, value["_type"])()
    for key, item in value.items():
        if key != "_type":
            setattr(node, key, _decode(item))
    return node


@dataclass
class Value:
    flows: dict = field(default_factory=dict)
    fields: dict = field(default_factory=dict)
    refs: set = field(default_factory=set)
    known: bool = False

    def all_flows(self):
        flows = dict(self.flows)
        for value in self.fields.values():
            flows.update(value.all_flows())
        return flows


_RECORD_METHODS = {"get", "items", "keys", "values", "copy", "to_dict", "dict", "model_dump", "__dict__"}


def _record_like(function, name):
    """Whether ``name`` is used as a record or collection of records, not a scalar such as an ID."""
    for node in ast.walk(function):
        if isinstance(node, (ast.Subscript, ast.Attribute)) and isinstance(node.value, ast.Name) and node.value.id == name:
            return True
        if isinstance(node, ast.Call):
            args = [item.value if isinstance(item, ast.Starred) else item for item in node.args]
            if (isinstance(node.func, ast.Name) and node.func.id in {"dict", "vars", "list", "asdict"}
                    and any(isinstance(item, ast.Name) and item.id == name for item in args)):
                return True
            if any(item.arg is None and isinstance(item.value, ast.Name) and item.value.id == name for item in node.keywords):
                return True
        if isinstance(node, ast.Dict) and any(key is None and isinstance(value, ast.Name) and value.id == name
                                              for key, value in zip(node.keys, node.values)):
            return True
        if isinstance(node, (ast.For, ast.AsyncFor, ast.comprehension)) and isinstance(node.iter, ast.Name) and node.iter.id == name:
            return True
    return False


def _fields_only(flows):
    """Selecting one field/item of a record does not expose the whole record."""
    return {key: flow for key, flow in flows.items() if flow[1] != OPAQUE}


def _merge(*values):
    result = Value(known=all(value.known for value in values))
    for value in values:
        result.flows.update(value.flows)
        result.refs.update(value.refs)
        for key, child in value.fields.items():
            result.fields[key] = _merge(result.fields[key], child) if key in result.fields else copy.deepcopy(child)
    return result


def _join(*envs):
    return {key: _merge(*(env.get(key, Value()) for env in envs)) for key in set().union(*(env.keys() for env in envs))}


def _signature(env):
    def signature(value):
        return (value.known, sorted(value.flows), sorted(value.refs), [(str(key), signature(child)) for key, child in sorted(value.fields.items(), key=lambda item: str(item[0]))])
    return repr([(key, signature(value)) for key, value in sorted(env.items())])


class _Project:
    def __init__(self, trees, policy):
        self.trees, self.policy = trees, policy
        self.nodes, self.edges, self.findings = {}, {}, {}
        self.ids, self.owners, self.functions, self.imports = {}, {}, {}, {}
        self.modules = {self.module(path): path for path in trees}
        self.dependencies = {path: set() for path in trees}
        self.unresolved, self.errors = set(), []
        self.called = set()
        self.closures = {}
        for path, tree in trees.items():
            self.imports[path] = self._imports(path, tree)
            self._index(path, tree)
        for path, tree in trees.items():
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    name = self.resolve(path, node.func)
                    if name in self.functions:
                        self.called.add(name)
                        self.dependencies[path].add(self.functions[name][0])
            for name in self.imports[path].values():
                for module, dependency in self.modules.items():
                    if name == module or name.startswith(module + "."):
                        self.dependencies[path].add(dependency)

    @staticmethod
    def module(path):
        parts = path.removesuffix(".py").split("/")
        return ".".join(parts[:-1] if parts[-1] == "__init__" else parts)

    def _imports(self, path, tree):
        aliases = {}
        package = self.module(path).split(".")
        if not path.endswith("/__init__.py") and path != "__init__.py":
            package = package[:-1]
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    aliases[alias.asname or alias.name.split(".")[0]] = alias.name if alias.asname else alias.name.split(".")[0]
            elif isinstance(node, ast.ImportFrom):
                prefix = package[:len(package) - node.level + 1] if node.level else []
                module = ".".join(prefix + ([node.module] if node.module else []))
                for alias in node.names:
                    aliases[alias.asname or alias.name] = ".".join(filter(None, [module, alias.name]))
        return aliases

    def _index(self, path, tree):
        counter = 0
        def visit(node, scope="", parent=None):
            nonlocal counter
            identity = f"{path}:ast:{counter}"
            counter += 1
            self.ids[id(node)], self.owners[id(node)] = identity, path
            label = getattr(node, "name", getattr(node, "attr", getattr(node, "id", type(node).__name__)))
            self.nodes[identity] = {"id": identity, "label": str(label), "kind": type(node).__name__, "file": path,
                                    "line": getattr(node, "lineno", 1)}
            if parent:
                self.edge(parent, identity, "AST")
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                name = ".".join(filter(None, [self.module(path), scope, node.name]))
                self.functions[name] = (path, node)
                scope = ".".join(filter(None, [scope, node.name]))
            elif isinstance(node, ast.ClassDef):
                scope = ".".join(filter(None, [scope, node.name]))
            for child in ast.iter_child_nodes(node):
                visit(child, scope, identity)
        visit(tree)
        def cfg(body, follow=None, loop=None):
            for index, node in enumerate(body):
                identity = self.ids[id(node)]
                successor = self.ids[id(body[index + 1])] if index + 1 < len(body) else follow
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    if node.body:
                        self.edge(identity, self.ids[id(node.body[0])], "CFG")
                    cfg(node.body)
                elif isinstance(node, ast.If):
                    for branch in (node.body, node.orelse):
                        target = self.ids[id(branch[0])] if branch else successor
                        if target:
                            self.edge(identity, target, "CFG")
                        cfg(branch, successor, loop)
                elif isinstance(node, (ast.For, ast.AsyncFor, ast.While)):
                    if node.body:
                        self.edge(identity, self.ids[id(node.body[0])], "CFG")
                    cfg(node.body, identity, (successor, identity))
                    if node.orelse:
                        self.edge(identity, self.ids[id(node.orelse[0])], "CFG")
                        cfg(node.orelse, successor, loop)
                    elif successor:
                        self.edge(identity, successor, "CFG")
                elif isinstance(node, (ast.Return, ast.Raise)):
                    continue
                elif isinstance(node, (ast.Break, ast.Continue)):
                    target = loop[0 if isinstance(node, ast.Break) else 1] if loop else None
                    if target:
                        self.edge(identity, target, "CFG")
                elif successor:
                    self.edge(identity, successor, "CFG")
        cfg(tree.body)

    def edge(self, source, target, kind):
        identity = _hash(f"{source}|{target}|{kind}")
        self.edges[identity] = {"id": identity, "source": source, "target": target, "type": kind}

    def resolve(self, path, node):
        if isinstance(node, ast.Name):
            return self.imports[path].get(node.id, f"{self.module(path)}.{node.id}")
        if isinstance(node, ast.Attribute):
            return f"{self.resolve(path, node.value)}.{node.attr}"
        return "<dynamic>"

    def hop(self, value, node):
        identity = self.ids[id(node)]
        result = copy.deepcopy(value)
        def advance(item):
            for source, flow in list(item.flows.items()):
                symbol, classification, trace = flow
                self.edge(trace[-1], identity, "DATA_FLOW")
                item.flows[source] = (symbol, classification, trace if identity in trace else trace + [identity])
            for child in item.fields.values():
                advance(child)
        advance(result)
        return result

    def denied_field(self, symbol):
        return any(fnmatch.fnmatchcase(symbol, pattern)
                   for sink in self.policy.sinks.values() for pattern in sink.get("deny_fields", []))

    def ai_prompt_sink(self, path, node, name):
        """Recognize common SDK calls only when the module imports that provider."""
        imports = set(self.imports.get(path, {}).values())
        callee = ast.unparse(node.func).lower()
        providers = {value.split(".", 1)[0] for value in imports}
        if ("openai" in providers and ("chat.completions.create" in callee or "responses.create" in callee)):
            return "AI_PROMPT"
        if "anthropic" in providers and "messages.create" in callee:
            return "AI_PROMPT"
        if ("litellm" in providers and
                (name in {"litellm.completion", "litellm.acompletion"} or callee.endswith(".completion"))):
            return "AI_PROMPT"
        return None

    def source(self, value, symbol, node):
        classification = self.policy.classify(symbol)
        if classification != "PUBLIC" or self.denied_field(symbol):
            identity = self.ids[id(node)]
            value.flows[identity] = (symbol, classification, [identity])
            self.nodes[identity].update(classification=classification, symbol=symbol)
        return value

    def sink(self, value, kind, node, path, function):
        identity = self.ids[id(node)]
        self.nodes[identity].update(sink=kind)
        for source, (symbol, classification, trace) in self.expand(value.all_flows()):
            decision = self.policy.evaluate(classification, kind, symbol=symbol)
            self.edge(trace[-1], identity, "DATA_FLOW")
            if decision["allowed"]:
                continue
            whole = source.endswith("#whole")
            finding_id = _hash(f"{path}|{function}|{source}|{identity}|{kind}")
            route = trace if trace[-1] == identity else trace + [identity]
            context_reasons = {"audience_unknown", "recipient_unknown", "required_contract_missing",
                               "authorization_required", "same_tenant_required", "tenant_context_unknown"}
            requirements = [reason for reason in decision["reasons"] if reason in context_reasons]
            self.findings[finding_id] = {
                "id": finding_id, "severity": "critical" if classification == "SECRET" else "high",
                "title": (f"Whole record containing {classification} field reaches {kind}" if whole
                          else f"{classification} data reaches {kind}"),
                "source": symbol, "exposure": "WHOLE_RECORD" if whole else "FIELD",
                "classification": classification, "sink": kind, "file": path, "line": getattr(node, "lineno", 1),
                "function": function, "path": route, "rule": f"policy_v{self.policy.version}",
                "reasons": decision["reasons"], "static_result": "POSSIBLE_FLOW", "status": "POSSIBLE",
                "context_requirements": requirements,
                "policy_violation": any(reason not in context_reasons for reason in decision["reasons"]),
            }

    def selectors(self):
        """Field selectors the policy classifies or denies, e.g. ``*.password_hash``."""
        patterns = {source["selector"] for source in self.policy.sources}
        patterns |= {pattern for sink in self.policy.sinks.values() for pattern in sink.get("deny_fields", [])}
        return sorted(pattern for pattern in patterns if pattern.startswith("*.") and len(pattern) > 2)

    def expand(self, flows):
        """Yield ordinary flows; an opaque record yields one flow per policy field it may hold."""
        for source, (symbol, classification, trace) in flows.items():
            if classification != OPAQUE:
                yield source, (symbol, classification, trace)
                continue
            for pattern in self.selectors():
                yield f"{source}|{pattern}#whole", (pattern, self.policy.classify(pattern), trace)

    def expr(self, node, env, path, function, stack):
        if node is None:
            return Value()
        if isinstance(node, ast.Name):
            return self.hop(env.get(node.id, Value(refs={self.resolve(path, node)})), node)
        if isinstance(node, ast.Constant):
            return Value(known=True)
        if isinstance(node, (ast.Attribute, ast.Subscript)):
            base = self.expr(node.value, env, path, function, stack)
            key = node.attr if isinstance(node, ast.Attribute) else node.slice.value if isinstance(node.slice, ast.Constant) else None
            if key in base.fields:
                return self.hop(base.fields[key], node)
            if base.known and key is not None and not base.flows:
                return Value(known=True)
            value = Value(flows=_fields_only(base.flows))
            if key is None:
                value = _merge(Value(flows=_fields_only(base.all_flows())), self.expr(node.slice, env, path, function, stack))
            value = self.hop(value, node)
            if isinstance(key, str):
                self.source(value, f"*.{key}", node)
            return value
        if isinstance(node, ast.Dict):
            value = Value(known=True)
            for key, item in zip(node.keys, node.values):
                child = self.expr(item, env, path, function, stack)
                if key is None:
                    value = _merge(value, child)
                elif isinstance(key, ast.Constant):
                    # Labels alone are not data; an explicit deny_fields rule,
                    # however, forbids serializing the named field at all.
                    if isinstance(key.value, str) and (not child.known or self.denied_field(f"*.{key.value}")):
                        child = self.source(child, f"*.{key.value}", item)
                    value.fields[key.value] = child
                else:
                    value = _merge(value, child, self.expr(key, env, path, function, stack))
            return self.hop(value, node)
        if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
            return self.hop(Value(fields={index: self.expr(item, env, path, function, stack) for index, item in enumerate(node.elts)}, known=True), node)
        if isinstance(node, (ast.ListComp, ast.SetComp, ast.GeneratorExp, ast.DictComp)):
            local = copy.deepcopy(env)
            for generator in node.generators:
                iterator = self.expr(generator.iter, local, path, function, stack)
                self.assign(generator.target, Value(flows=iterator.all_flows()), local, path, function, stack)
                for condition in generator.ifs:
                    self.expr(condition, local, path, function, stack)
            value = self.expr(node.value if isinstance(node, ast.DictComp) else node.elt, local, path, function, stack)
            return self.hop(Value(flows=value.all_flows()), node)
        if isinstance(node, ast.IfExp):
            self.expr(node.test, env, path, function, stack)
            return self.hop(_merge(self.expr(node.body, env, path, function, stack), self.expr(node.orelse, env, path, function, stack)), node)
        if isinstance(node, ast.NamedExpr):
            value = self.expr(node.value, env, path, function, stack)
            self.assign(node.target, value, env, path, function, stack)
            return self.hop(value, node)
        if isinstance(node, ast.Call):
            args = [self.expr(item, env, path, function, stack) for item in node.args]
            kwargs = {item.arg: self.expr(item.value, env, path, function, stack) for item in node.keywords}
            name = self.resolve(path, node.func)
            local = self.functions.get(name)
            if isinstance(node.func, ast.Name) and node.func.id in env:
                candidates = env[node.func.id].refs
                local_name = next((item for item in sorted(candidates) if item in self.functions), None)
                if local_name:
                    name, local = local_name, self.functions[local_name]
            if local and name not in stack:
                target_path, target = local
                self.dependencies[path].add(target_path)
                self.edge(self.ids[id(node)], self.ids[id(target)], "CALLS")
                value = self.invoke(name, args, kwargs, stack, entry=False)
                return self.hop(value, node)
            combined = _merge(*args, *kwargs.values())
            method = node.func.attr if isinstance(node.func, ast.Attribute) else node.func.id if isinstance(node.func, ast.Name) else ""
            kind = SINKS.get(name) or METHOD_SINKS.get(method) or self.ai_prompt_sink(path, node, name)
            if method in {"debug", "info", "warning", "error", "exception", "critical", "log"} and isinstance(node.func, ast.Attribute):
                receiver = ast.unparse(node.func.value).lower()
                if any(word in receiver for word in ("logger", "logging", "log")):
                    kind = "APPLICATION_LOG"
            if method == "print" and isinstance(node.func, ast.Name) and node.func.id not in env:
                kind = "APPLICATION_LOG"
            if kind:
                self.sink(combined, kind, node, path, function)
                return self.hop(combined, node) if kind == "HTTP_RESPONSE" else Value()
            if isinstance(node.func, ast.Attribute):
                receiver = self.expr(node.func.value, env, path, function, stack)
                if method in {"append", "extend", "add", "update"} and isinstance(node.func.value, ast.Name):
                    original = env.setdefault(node.func.value.id, Value())
                    if method == "update":
                        for argument in args:
                            original.fields.update(argument.fields)
                            original.flows.update(argument.flows)
                        original.fields.update(kwargs)
                    else:
                        original.flows.update(combined.all_flows())
                    return Value()
                if method == "get" and node.args and isinstance(node.args[0], ast.Constant):
                    key = node.args[0].value
                    if key in receiver.fields:
                        return self.hop(receiver.fields[key], node)
                    if receiver.known and not receiver.flows:
                        return self.hop(args[1] if len(args) > 1 else Value(known=True), node)
                    return self.source(self.hop(Value(flows=_fields_only(receiver.flows)), node), f"*.{key}", node)
                if method == "get" and node.args and not args[0].all_flows():
                    # A computed key that carries no data (e.g. names from a constant tuple) selects one field,
                    # like record[key]; keys taken from the record itself still expose the whole record.
                    return self.hop(_merge(Value(flows=_fields_only(receiver.all_flows())), *args), node)
                combined = _merge(combined, receiver)
            # Unknown/library transformations propagate their inputs, never sanitize them.
            self.unresolved.add((path, getattr(node, "lineno", 1), name))
            combined.known = False
            return self.hop(combined, node)
        value = Value(known=True)
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.expr):
                value = _merge(value, self.expr(child, env, path, function, stack))
        return self.hop(value, node)

    def assign(self, target, value, env, path, function, stack):
        value = self.hop(value, target)
        if isinstance(target, ast.Name):
            env[target.id] = value
        elif isinstance(target, (ast.Tuple, ast.List)):
            for index, item in enumerate(target.elts):
                self.assign(item, value.fields.get(index, Value(flows=value.all_flows())), env, path, function, stack)
        elif isinstance(target, (ast.Attribute, ast.Subscript)):
            key = target.attr if isinstance(target, ast.Attribute) else target.slice.value if isinstance(target.slice, ast.Constant) else None
            if isinstance(target.value, ast.Name):
                base = env.setdefault(target.value.id, Value())
                if key is None:
                    base.flows.update(value.all_flows())
                else:
                    if isinstance(key, str) and (not value.known or self.denied_field(f"*.{key}")):
                        value = self.source(value, f"*.{key}", target)
                    base.fields[key] = value

    def block(self, body, env, path, function, stack, entry=False):
        returned = Value(known=True)
        for node in body:
            identity = self.ids[id(node)]
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                name = f"{self.module(path)}.{node.name}" if function == "<module>" else f"{function}.{node.name}"
                env[node.name] = Value(refs={name})
                if function != "<module>":
                    self.closures[name] = copy.deepcopy(env)
                continue
            if isinstance(node, (ast.ClassDef, ast.Import, ast.ImportFrom)):
                continue
            if isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
                value = self.expr(node.value, env, path, function, stack)
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                if isinstance(node, ast.AugAssign):
                    value = _merge(value, self.expr(node.target, env, path, function, stack))
                for target in targets:
                    self.assign(target, value, env, path, function, stack)
                    if isinstance(target, ast.Name) and isinstance(node.value, ast.Name) and node.value.id in env and not isinstance(node, ast.AugAssign):
                        env[target.id] = env[node.value.id]
            elif isinstance(node, ast.Expr):
                self.expr(node.value, env, path, function, stack)
            elif isinstance(node, ast.Return):
                value = self.hop(self.expr(node.value, env, path, function, stack), node)
                if entry and node.value is not None:
                    self.sink(value, "HTTP_RESPONSE", node, path, function)
                return env, _merge(returned, value), False
            elif isinstance(node, ast.Raise):
                self.expr(node.exc, env, path, function, stack)
                return env, returned, False
            elif isinstance(node, (ast.Break, ast.Continue)):
                return env, returned, False
            elif isinstance(node, ast.If):
                self.expr(node.test, env, path, function, stack)
                branches = []
                for branch in (node.body, node.orelse):
                    if branch:
                        self.edge(identity, self.ids[id(branch[0])], "CFG")
                    branch_env, value, alive = self.block(branch, copy.deepcopy(env), path, function, stack, entry)
                    returned = _merge(returned, value)
                    if alive:
                        branches.append(branch_env)
                if not branches:
                    return env, returned, False
                env = _join(*branches)
            elif isinstance(node, (ast.For, ast.AsyncFor, ast.While)):
                before = copy.deepcopy(env)
                iterator = self.expr(node.iter if isinstance(node, (ast.For, ast.AsyncFor)) else node.test, env, path, function, stack)
                # Monotone may-flow join includes zero iterations and loop-carried values.
                for _ in range(sum(1 for _ in ast.walk(node)) + 1):
                    iteration = copy.deepcopy(env)
                    if isinstance(node, (ast.For, ast.AsyncFor)):
                        self.assign(node.target, Value(flows=iterator.all_flows()), iteration, path, function, stack)
                    if node.body:
                        self.edge(identity, self.ids[id(node.body[0])], "CFG")
                        self.edge(self.ids[id(node.body[-1])], identity, "CFG")
                    iteration, value, _ = self.block(node.body, iteration, path, function, stack, entry)
                    returned = _merge(returned, value)
                    joined = _join(before, env, iteration)
                    if _signature(joined) == _signature(env):
                        env = joined
                        break
                    env = joined
                env, value, _ = self.block(node.orelse, env, path, function, stack, entry)
                returned = _merge(returned, value)
            elif isinstance(node, (ast.Try, getattr(ast, "TryStar", ast.Try))):
                branches = [node.body] + [handler.body for handler in node.handlers]
                outcomes = [self.block(branch, copy.deepcopy(env), path, function, stack, entry) for branch in branches]
                env = _join(env, *(item[0] for item in outcomes))
                returned = _merge(returned, *(item[1] for item in outcomes))
                for branch in (node.orelse, node.finalbody):
                    env, value, _ = self.block(branch, env, path, function, stack, entry)
                    returned = _merge(returned, value)
            elif isinstance(node, (ast.With, ast.AsyncWith)):
                for item in node.items:
                    value = self.expr(item.context_expr, env, path, function, stack)
                    if item.optional_vars:
                        self.assign(item.optional_vars, value, env, path, function, stack)
                env, value, alive = self.block(node.body, env, path, function, stack, entry)
                returned = _merge(returned, value)
                if not alive:
                    return env, returned, False
            elif isinstance(node, ast.Delete):
                for target in node.targets:
                    self.assign(target, Value(), env, path, function, stack)
            else:
                for child in ast.iter_child_nodes(node):
                    if isinstance(child, ast.expr):
                        self.expr(child, env, path, function, stack)
        return env, returned, True

    def invoke(self, name, args, kwargs, stack, entry=False):
        path, function = self.functions[name]
        env = copy.deepcopy(self.closures.get(name, getattr(self, "globals", {}).get(path, {})))
        params = function.args.posonlyargs + function.args.args
        defaults = [None] * (len(params) - len(function.args.defaults)) + function.args.defaults
        for index, param in enumerate(params):
            value = args[index] if index < len(args) else kwargs.get(param.arg)
            if value is None:
                value = self.expr(defaults[index], env, path, name, stack) if defaults[index] is not None else Value()
                if (entry and defaults[index] is None and param.arg not in {"self", "cls"}
                        and _record_like(function, param.arg)):
                    identity = self.ids[id(param)]
                    value.flows[identity] = (f"{param.arg}.*", OPAQUE, [identity])
            env[param.arg] = self.hop(value, param)
        for param, default in zip(function.args.kwonlyargs, function.args.kw_defaults):
            value = kwargs[param.arg] if param.arg in kwargs else self.expr(default, env, path, name, stack)
            env[param.arg] = self.hop(value, param)
        if function.args.vararg:
            env[function.args.vararg.arg] = Value(fields={index: value for index, value in enumerate(args[len(params):])})
        if function.args.kwarg:
            env[function.args.kwarg.arg] = Value(fields={key: value for key, value in kwargs.items() if key not in {item.arg for item in params + function.args.kwonlyargs}})
        _, returned, _ = self.block(function.body, env, path, name, stack + [name], entry)
        return returned



def analyze_project(root: Path, policy: Policy, previous: dict | None = None, *, entrypoints: list[str] | None = None) -> dict:
    """Analyze Python flows; explicit callable entrypoints also define response sinks."""
    root = Path(root).resolve()
    entrypoints = sorted(set(entrypoints or []))
    previous = previous or {}
    previous = previous.get("index", previous)
    old = previous.get("files", {})
    compatible = (previous.get("analyzer_version") == ANALYZER_VERSION and previous.get("policy_digest") == policy.digest
                  and previous.get("entrypoints", []) == entrypoints)
    trees, records, parse_errors, changed, reused_ast = {}, {}, [], set(), []
    for path, content in source_files(root, {".py"}, EXCLUDED):
        relative = path.relative_to(root).as_posix()
        digest = hashlib.sha256(content).hexdigest()
        cached = old.get(relative, {})
        same = compatible and cached.get("hash") == digest and "ast" in cached
        if same:
            tree = _decode(cached["ast"])
            reused_ast.append(relative)
        else:
            changed.add(relative)
            try:
                tree = ast.parse(content, filename=relative)
            except (SyntaxError, UnicodeError) as error:
                parse_errors.append({"file": relative, "line": getattr(error, "lineno", 1), "error": type(error).__name__})
                records[relative] = {"hash": digest, "dependencies": [], "parse_error": True}
                continue
        trees[relative] = tree
        records[relative] = {"hash": digest, "ast": cached["ast"] if same else _encode(tree)}
    deleted = set(old) - set(records)
    project = _Project(trees, policy)
    invalidated = set(records) if not compatible else changed | deleted
    while True:
        dependencies = {path: set(old.get(path, {}).get("dependencies", [])) | project.dependencies.get(path, set()) for path in records}
        dependents = {path for path, targets in dependencies.items() if targets & invalidated}
        # Inline argument contexts can affect callees too; invalidate the connected
        # import/call component rather than cache context-dependent callee output.
        dependents.update(target for path in invalidated for target in dependencies.get(path, set()) if target in records)
        expanded = invalidated | dependents
        if expanded == invalidated:
            break
        invalidated = expanded
    # Reuse complete per-file outputs outside the dependency impact cone. Evaluating
    # the cone against the full function index preserves imported-call semantics.
    project.globals = {}
    for path, tree in trees.items():
        env, _, _ = project.block(tree.body, {}, path, "<module>", [])
        project.globals[path] = env
    for name, (path, function) in project.functions.items():
        if path not in invalidated:
            continue
        decorated = any(isinstance(item, ast.Call) and isinstance(item.func, ast.Attribute) and item.func.attr in {"route", "get", "post", "put", "delete", "patch"} for item in function.decorator_list)
        top_level = name == f"{project.module(path)}.{function.name}"
        if decorated or top_level or name in entrypoints:
            project.invoke(name, [], {}, [], entry=decorated or name in entrypoints or
                           not entrypoints and name not in project.called and not function.name.startswith("_"))
    nodes, edges, findings = {}, {}, {}
    for path, record in records.items():
        record["dependencies"] = sorted(project.dependencies.get(path, set()))
        if compatible and path not in invalidated and path in old:
            for key in ("nodes", "edges", "findings", "unresolved_calls"):
                record[key] = copy.deepcopy(old[path].get(key, []))
        else:
            record["nodes"] = [node for node in project.nodes.values() if node["file"] == path]
            record["edges"] = [edge for edge in project.edges.values() if project.nodes[edge["source"]]["file"] == path]
            record["findings"] = [finding for finding in project.findings.values() if finding["file"] == path]
            record["unresolved_calls"] = [{"file": file, "line": line, "call": call} for file, line, call in sorted(project.unresolved) if file == path]
        for key, target in (("nodes", nodes), ("edges", edges), ("findings", findings)):
            target.update({item["id"]: item for item in record[key]})
    # Inline imported calls may add context-dependent flow edges in other files.
    # Keep these with the caller's reusable result so deletion invalidates them.
    for edge in project.edges.values():
        if edge["source"] in nodes and edge["target"] in nodes:
            edges[edge["id"]] = edge
    coverage = {
        "language": "Python", "supported_language": "Python", "analyzer_version": ANALYZER_VERSION,
        "analyzed_files": len(trees),
        "unsupported_constructs": [{"file": path, "line": getattr(node, "lineno", 1), "kind": type(node).__name__}
                                   for path, tree in trees.items() for node in ast.walk(tree)
                                   if isinstance(node, (ast.Lambda, ast.Match, ast.Global, ast.Nonlocal, ast.Yield, ast.YieldFrom))],
        "supported": ["assignments and overwrite kills", "attributes and literal-key containers", "branch/loop may-flow joins",
                      "local and imported Python function arguments/returns", "route-decorated and uncalled public function returns",
                      "logging/print", "Flask jsonify and FastAPI JSONResponse", "requests/httpx egress", "analytics track/capture",
                      "whole entrypoint-argument records reaching a sink (dict(), **spread, copy, direct return)",
                      "OpenAI/Anthropic/LiteLLM prompt sinks (recognized SDK call shapes)"],
        "limitations": ["No implicit/control-dependence taint", "No reflection or dynamic dispatch resolution",
                        "No framework ORM/schema inference", "No proof of runtime recipient, tenant or authorization",
                        "Unknown calls propagate inputs conservatively; recursive calls use the same fallback",
                        "No native/third-party implementation analysis; no sanitizer inferred from names",
                        "No lambda/match/global/nonlocal/generator execution model; see unsupported_constructs",
                        "Container aliases are preserved for direct assignments, not arbitrary library mutations",
                        "Whole-record exposure is modeled for entrypoint arguments used as records (subscript, attribute,"
                        " get/items/copy, dict(), ** or iteration); ORM/query results are not inferred",
                        "Any subscript/attribute/get projection is treated as selecting one field of a whole record",
                        "AI SDK sink recognition is syntax/import based; dynamic clients and other providers are unresolved"],
        "parse_errors": parse_errors,
        "unresolved_calls": sorted([item for record in records.values() for item in record.get("unresolved_calls", [])], key=lambda item: (item["file"], item["line"], item["call"])),
    }
    return {
        "nodes": sorted(nodes.values(), key=lambda item: item["id"]),
        "edges": sorted(edges.values(), key=lambda item: item["id"]),
        "findings": sorted(findings.values(), key=lambda item: item["id"]),
        "index": {"analyzer_version": ANALYZER_VERSION, "policy_digest": policy.digest, "entrypoints": entrypoints, "files": records},
        "coverage": coverage,
        "incremental": {"mode": "incremental" if compatible else "full", "changed": sorted(changed), "deleted": sorted(deleted),
                        "invalidated": sorted(invalidated & set(records)), "reused": sorted(set(records) - invalidated), "reused_ast": sorted(reused_ast)},
    }


def analyze_repository(root: Path, policy: Policy) -> tuple[list[dict], list[dict], list[dict]]:
    """Return the analyzed graph and findings for a Python repository."""
    result = analyze_project(root, policy)
    return result["nodes"], result["edges"], result["findings"]

