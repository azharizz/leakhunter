"""Shared language, entrypoint, and normalized-result contract."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


LANGUAGES = ("python", "javascript", "typescript", "go", "rust")
DISPLAY_NAMES = {
    "python": "Python",
    "javascript": "JavaScript",
    "typescript": "TypeScript",
    "go": "Go",
    "rust": "Rust",
}
_EXTENSIONS = {
    "python": (".py",),
    "javascript": (".js", ".jsx", ".mjs", ".cjs"),
    "typescript": (".ts", ".tsx",),
    "go": (".go",),
    "rust": (".rs",),
}


@dataclass(frozen=True)
class Entrypoint:
    language: str
    file: str
    callable: str
    command: tuple[str, ...] = ()


def _language(value: str) -> str:
    if not isinstance(value, str) or value not in LANGUAGES:
        raise ValueError(f"unsupported language: {value!r}")
    return value


def manifest_language(manifest: dict) -> str:
    """Return the one language a runtime manifest is allowed to execute."""
    declared = manifest.get("language", "python")
    declared = _language(declared)
    cases = manifest.get("cases")
    if not isinstance(cases, list) or not cases or any(not isinstance(case, dict) for case in cases):
        raise ValueError("manifest requires cases")
    return declared


def runtime_image(manifest: dict) -> str:
    if "docker_image" in manifest:
        return manifest["docker_image"]
    language = manifest_language(manifest)
    if language == "javascript" and any(entrypoint(case, language).file.endswith(".jsx")
                                        for case in manifest["cases"]):
        return "oven/bun:1"
    return {"python": "python:3.12-slim", "javascript": "node:22-bookworm-slim",
            "typescript": "oven/bun:1", "go": "golang:1.23-bookworm",
            "rust": "rust:1.82-bookworm"}[language]


def entrypoint(case: dict, language: str) -> Entrypoint:
    language = _language(language)
    if language == "python":
        return Entrypoint(language, f"{case['module'].replace('.', '/')}.py", case["callable"])
    spec = case.get("entrypoint")
    if not isinstance(spec, dict) or set(spec) - {"file", "callable", "command"}:
        raise ValueError("non-Python cases require an entrypoint object")
    file = spec.get("file", "")
    callable_name = spec.get("callable", "run")
    command = spec.get("command", [])
    if (not isinstance(file, str) or not file or "\\" in file or "\x00" in file
            or Path(file).is_absolute() or any(part in {"", ".", ".."} for part in file.split("/"))):
        raise ValueError("invalid non-Python entrypoint file")
    if (not isinstance(callable_name, str) or not callable_name
            or any(not part.isidentifier() or part.startswith("__") for part in callable_name.split("."))):
        raise ValueError("invalid non-Python entrypoint callable")
    if not isinstance(command, list) or any(not isinstance(item, str) or not item or "\x00" in item for item in command):
        raise ValueError("invalid non-Python entrypoint command")
    if language in {"javascript", "typescript"} and command:
        raise ValueError("JavaScript/TypeScript entrypoints do not accept commands")
    if language in {"go", "rust"} and not command:
        raise ValueError("Go/Rust entrypoints require a protocol command")
    if not file.endswith(_EXTENSIONS[language]):
        raise ValueError("entrypoint file extension does not match language")
    return Entrypoint(language, file, callable_name, tuple(command))


def extensions(language: str) -> tuple[str, ...]:
    return _EXTENSIONS[_language(language)]


def module_name(file: str) -> str:
    if not file:
        return ""
    parts = str(Path(file).with_suffix("")).split("/")
    return ".".join(parts[:-1] if parts[-1] == "__init__" else parts)


def entrypoint_name(case: dict, language: str = "python") -> str:
    if language == "python":
        return f"{case.get('module', '')}.{case.get('callable', '')}"
    spec = entrypoint(case, language)
    return f"{module_name(spec.file)}.{spec.callable}"


def manifest_entrypoints(manifest: dict | None) -> list[str]:
    if not manifest:
        return []
    language = manifest_language(manifest)
    return [entrypoint_name(case, language) for case in manifest["cases"]]


def finding_function(case: dict) -> str:
    function = case.get("finding", {}).get("function", "")
    module = case.get("module") or module_name(case.get("entrypoint", {}).get("file", ""))
    return function if not module or function.startswith(module + ".") else module + "." + function


def normalized_analysis(result: dict, language: str) -> dict:
    """Validate the cross-language analyzer result without changing Python output."""
    required = {"nodes", "edges", "findings", "coverage", "index", "incremental"}
    if not isinstance(result, dict) or required - set(result):
        raise ValueError("analyzer returned an invalid normalized result")
    coverage = result["coverage"]
    if not isinstance(coverage, dict) or coverage.get("language") != DISPLAY_NAMES[_language(language)]:
        raise ValueError("analyzer coverage does not identify its language")
    for key in ("unsupported_constructs", "parse_errors", "unresolved_calls"):
        if not isinstance(coverage.get(key), list):
            raise ValueError("analyzer coverage is missing normalized lists")
    return result
