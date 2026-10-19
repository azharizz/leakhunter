import tempfile
from pathlib import Path

import unittest

from leakhunter.languages import entrypoint
from leakhunter.analyzers.registry import analyze_project
from leakhunter.policy.engine import Policy


class LanguageContractTest(unittest.TestCase):
    def test_protocol_commands_cannot_be_ignored_or_omitted(self):
        for language, file, command in (
            ("javascript", "service.js", ["node", "wrong.js"]),
            ("typescript", "service.ts", ["bun", "wrong.ts"]),
            ("go", "service.go", []),
            ("rust", "src/main.rs", []),
        ):
            with self.subTest(language=language), self.assertRaises(ValueError):
                entrypoint({"entrypoint": {"file": file, "callable": "run", "command": command}}, language)

    def test_constant_array_index_retains_taint_without_dynamic_coverage_gap(self):
        policy = Policy({"version": 1, "classifications": {"PUBLIC": 0, "SECRET": 1},
                         "sources": [{"selector": "*.password_hash", "class": "SECRET"}],
                         "sinks": [{"kind": "HTTP_RESPONSE", "allow": ["PUBLIC"]}]})
        sources = {
            "javascript": ("service.js", "export function run(record) { const values = [record.password_hash]; return values[0]; }"),
            "typescript": ("service.ts", "export function run(record: any) { const values = [record.password_hash]; return values[0]; }"),
            "go": ("service.go", 'package main\nfunc run(record map[string]any) any { values := []any{record["password_hash"]}; return values[0] }'),
            "rust": ("service.rs", "struct Record { password_hash: String }\nfn run(record: Record) -> String { let values = [record.password_hash]; values[0].clone() }"),
        }
        for language, (file, source) in sources.items():
            with self.subTest(language=language), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                (root / file).write_text(source)
                result = analyze_project(root, policy, entrypoints=["service.run"], language=language)
                self.assertTrue(any(item["sink"] == "HTTP_RESPONSE" for item in result["findings"]))
                self.assertFalse(result["coverage"]["parse_errors"])
                self.assertFalse(any(item["kind"] == "dynamic_field_access"
                                     for item in result["coverage"]["unsupported_constructs"]))
