"""Small executable cross-language contract checks, not inference-accuracy claims.

Run: PYTHONPATH=. python3 -m example.language_holdouts --output /tmp/language-holdouts
Rust embeds the opaque JSON request as a value; no third-party crates are needed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import yaml

from unspool.analyzers.registry import analyze_project
from unspool.execution.runtime import run_suite
from unspool.languages import LANGUAGES, entrypoint_name
from unspool.policy.engine import Policy

FAMILIES = ("response", "logging", "overwrite", "branch", "helper")
POLICY = {"version": 1, "classifications": {"PUBLIC": 0, "SECRET": 1},
          "sources": [{"selector": "*.password_hash", "class": "SECRET"}],
          "sinks": [{"kind": kind, "allow": ["PUBLIC"]}
                    for kind in ("HTTP_RESPONSE", "APPLICATION_LOG")]}


def source(language: str, family: str, vulnerable: bool) -> tuple[str, str, dict]:
    if language == "python":
        helper = "def forward(value):\n    return " + ("value" if vulnerable else "'public'") + "\n\n"
        value = "record['password_hash']" if vulnerable else "'public'"
        body = {
            "response": f"    return {{'ok': True, 'value': {value}}}\n",
            "logging": f"    logging.warning({value})\n    return {{'ok': True}}\n",
            "overwrite": "    value = record['password_hash']\n" + ("" if vulnerable else "    value = 'public'\n") + "    return {'ok': True, 'value': value}\n",
            "branch": "    value = 'public'\n    if record['enabled']:\n        value = " + value + "\n    return {'ok': True, 'value': value}\n",
            "helper": "    return {'ok': True, 'value': forward(record['password_hash'])}\n",
        }[family]
        return "service.py", "import logging\n" + (helper if family == "helper" else "") + "def run(record):\n" + body, {}
    if language in {"javascript", "typescript"}:
        typed = ": any" if language == "typescript" else ""
        helper = f"function forward(value{typed}) {{ return " + ("value" if vulnerable else "'public'") + "; }\n"
        value = "record.password_hash" if vulnerable else "'public'"
        body = {
            "response": f"return {{ok: true, value: {value}}};",
            "logging": f"console.error({value}); return {{ok: true}};",
            "overwrite": "let value = record.password_hash; " + ("" if vulnerable else "value = 'public'; ") + "return {ok: true, value};",
            "branch": "let value = 'public'; if (record.enabled) { value = " + value + "; } return {ok: true, value};",
            "helper": "return {ok: true, value: forward(record.password_hash)};",
        }[family]
        return "service." + ("ts" if typed else "js"), (helper if family == "helper" else "") + f"export function run(record{typed}) {{ {body} }}\n", {}
    if language == "go":
        value = 'record["password_hash"]' if vulnerable else '"public"'
        helper = 'func forward(value any) any { return ' + ("value" if vulnerable else '"public"') + ' }\n'
        body = {
            "response": f'return map[string]any{{"ok": true, "value": {value}}}',
            "logging": f'fmt.Fprintln(os.Stderr, {value}); return map[string]any{{"ok": true}}',
            "overwrite": 'value := record["password_hash"]; ' + ("" if vulnerable else 'value = "public"; ') + 'return map[string]any{"ok": true, "value": value}',
            "branch": 'var value any = "public"; if record["enabled"] == true { value = ' + value + ' }; return map[string]any{"ok": true, "value": value}',
            "helper": 'return map[string]any{"ok": true, "value": forward(record["password_hash"])}',
        }[family]
        code = 'package main\nimport ("encoding/json"; "os"' + ('; "fmt"' if family == "logging" else '') + ')\n'
        code += helper if family == "helper" else ""
        code += 'func run(record map[string]any) map[string]any { ' + body + ' }\n'
        code += 'func main() { var input struct { Args []map[string]any `json:"args"` }; if err := json.NewDecoder(os.Stdin).Decode(&input); err != nil { panic(err) }; if err := json.NewEncoder(os.Stdout).Encode(run(input.Args[0])); err != nil { panic(err) } }\n'
        return "service.go", code, {"command": ["go", "run", "service.go"]}
    value = "record.password_hash" if vulnerable else '"null".to_owned()'
    helper = 'fn forward(value: String) -> String { ' + ("value" if vulnerable else 'let _ = value; "null".to_owned()') + ' }\n'
    body = {
        "response": value,
        "logging": 'eprintln!("{}", ' + value + '); "null".to_owned()',
        "overwrite": 'let mut value = record.password_hash; ' + ("" if vulnerable else 'value = "null".to_owned(); ') + 'value',
        "branch": 'let mut value = "null".to_owned(); if record.enabled { value = ' + value + ' }; value',
        "helper": 'forward(record.password_hash)',
    }[family]
    code = 'use std::io::{self, Read};\nstruct Record { password_hash: String, enabled: bool }\n'
    code += helper if family == "helper" else ""
    code += 'fn run(record: Record) -> String { ' + body + ' }\n'
    code += 'fn main() { let mut input = String::new(); io::stdin().read_to_string(&mut input).unwrap(); let value = run(Record { password_hash: input, enabled: true }); println!("{{\\\"ok\\\":true,\\\"value\\\":{}}}", value); }\n'
    return "src/main.rs", code, {"command": ["cargo", "run", "--quiet", "--offline"]}


def run(output: Path, backend: str = "local") -> dict:
    output.mkdir(parents=True, exist_ok=True)
    if any(output.iterdir()):
        raise ValueError("output must be empty; preserve previous evidence")
    (output / "policy.yaml").write_text(yaml.safe_dump(POLICY, sort_keys=False))
    policy = Policy(POLICY)
    rows = []
    for language in LANGUAGES:
        for family in FAMILIES:
            for vulnerable in (False, True):
                ident = f"{language}-{family}-{'vulnerable' if vulnerable else 'safe'}"
                directory = output / ident
                repository = directory / "repository"
                repository.mkdir(parents=True)
                file, code, extra = source(language, family, vulnerable)
                path = repository / file
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(code)
                if language == "rust":
                    (repository / "Cargo.toml").write_text('[package]\nname = "language-holdout"\nversion = "0.1.0"\nedition = "2021"\n')
                marker = "SYNTHETIC_LANGUAGE_" + hashlib.sha256(ident.encode()).hexdigest()[:16]
                sink = "APPLICATION_LOG" if family == "logging" else "HTTP_RESPONSE"
                case = {"id": ident, "args": [{"password_hash": marker, "enabled": True}], "kwargs": {},
                        "sensitive": [{"marker": marker, "class": "SECRET", "symbol": "Record.password_hash"}],
                        "context": {"synthetic": True, "boundary_kind": sink, "recipient": "synthetic_public",
                                    "applicable_questions": ["unauthorized_disclosure_plausible"]},
                        "expect": {"ok": True}, "expected_violation": vulnerable,
                        "finding": {"file": file, "function": "run", "sink": sink, "symbol": "Record.password_hash"}}
                if language == "python":
                    case.update(module="service", callable="run")
                else:
                    case["entrypoint"] = {"file": file, "callable": "run", **extra}
                manifest = {"version": 1, "language": language, "cases": [case]}
                (directory / "runtime.yaml").write_text(yaml.safe_dump(manifest, sort_keys=False))
                scan = analyze_project(repository, policy, language=language,
                                       entrypoints=[entrypoint_name(case, language)])
                runtime = run_suite(repository, manifest, policy, backend=backend, timeout=60)
                (directory / "analysis.json").write_text(json.dumps(scan, indent=2) + "\n")
                (directory / "runtime.json").write_text(json.dumps(runtime, indent=2) + "\n")
                static_positive = any(finding["sink"] == sink for finding in scan["findings"])
                observed = any(item.get("violations") for item in runtime.get("cases", []))
                runtime_ok = (runtime.get("status") == "COMPLETED" and bool(runtime.get("cases"))
                              and all(item.get("passed") is True
                                      for item in runtime["cases"]))
                row = {"id": ident, "language": language, "family": family, "expected_violation": vulnerable,
                       "static_positive": static_positive, "runtime_positive": observed,
                       "runtime_completed": runtime_ok, "runtime_matches": runtime_ok and observed == vulnerable,
                       "parse_errors": scan["coverage"].get("parse_errors", []),
                       "unsupported_constructs": scan["coverage"].get("unsupported_constructs", []),
                       "unresolved_calls": scan["coverage"].get("unresolved_calls", []),
                       "source_sha256": hashlib.sha256(code.encode()).hexdigest()}
                rows.append(row)
                print(ident, "static=" + str(static_positive), "runtime=" + str(observed),
                      "completed=" + str(runtime_ok), flush=True)
    metrics = {}
    for language in LANGUAGES:
        subset = [row for row in rows if row["language"] == language]
        tp = sum(row["static_positive"] and row["expected_violation"] for row in subset)
        tn = sum(not row["static_positive"] and not row["expected_violation"] for row in subset)
        fp = sum(row["static_positive"] and not row["expected_violation"] for row in subset)
        fn = sum(not row["static_positive"] and row["expected_violation"] for row in subset)
        metrics[language] = {"cases": len(subset), "static_correct": tp + tn, "static_accuracy": (tp + tn) / len(subset),
                             "true_positive": tp, "true_negative": tn, "false_positive": fp, "false_negative": fn,
                             "precision": tp / (tp + fp) if tp + fp else None,
                             "recall": tp / (tp + fn) if tp + fn else None,
                             "runtime_correct": sum(row["runtime_matches"] for row in subset),
                             "runtime_errors": sum(not row["runtime_completed"] for row in subset)}
    result = {"kind": "paired_synthetic_static_runtime_holdout", "backend": backend,
              "inference_evaluated": False, "parity_claim": False, "metrics": metrics, "cases": rows}
    (output / "results.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--backend", choices=("local", "docker"), default="local")
    args = parser.parse_args()
    report = run(args.output, args.backend)
    print(json.dumps(report["metrics"], indent=2))
    raise SystemExit(0 if all(value["runtime_correct"] == value["cases"] for value in report["metrics"].values()) else 1)
