"""Language-aware static-analysis dispatch."""
from __future__ import annotations

from pathlib import Path

from unspool.analyzers.python_ast import analyze_project as analyze_python
from unspool.languages import LANGUAGES, normalized_analysis


def analyze_project(root: Path, policy, previous: dict | None = None, *, entrypoints: list[str] | None = None,
                    language: str = "python") -> dict:
    if language == "python":
        return analyze_python(root, policy, previous=previous, entrypoints=entrypoints)
    if language not in LANGUAGES:
        raise ValueError(f"unsupported language: {language}")
    from unspool.analyzers.tree_sitter_adapter import analyze_project as analyze_tree_sitter
    return normalized_analysis(analyze_tree_sitter(root, policy, previous=previous, entrypoints=entrypoints,
                                                   language=language), language)
