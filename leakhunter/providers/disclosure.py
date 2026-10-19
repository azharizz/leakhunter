"""Bounded source disclosure shared by model review and repair."""
from __future__ import annotations

import hashlib
from pathlib import Path, PurePosixPath
import re

from leakhunter.languages import LANGUAGES, extensions


_SOURCE_EXTENSIONS = {suffix for language in LANGUAGES for suffix in extensions(language)}

MAX_SOURCE_BYTES = 64 * 1024
MAX_CONTEXT_BYTES = 128 * 1024
SECRET_PATTERN = re.compile(
    r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|"
    r"\b(?:sk-(?:or-v1-)?[A-Za-z0-9_-]{16,}|gh[pousr]_[A-Za-z0-9]{20,}|"
    r"glpat-[A-Za-z0-9_-]{16,}|AKIA[A-Z0-9]{16})\b|"
    r"(?i:(?:api[_-]?key|access[_-]?token|auth[_-]?token|client[_-]?secret|password|"
    r"secret[_-]?key)[\"']?\s*[:=]\s*[\"'][^\"'\n]{6,}[\"'])|"
    r"[a-zA-Z][a-zA-Z0-9+.-]*://[^\s/:]+:[^\s/@]+@"
)


def read_source(path: Path) -> str:
    if path.stat().st_size > MAX_SOURCE_BYTES:
        raise ValueError("Scoped source file exceeds disclosure size limit")
    content = path.read_bytes()
    if len(content) > MAX_SOURCE_BYTES:
        raise ValueError("Scoped source file exceeds disclosure size limit")
    source = content.decode("utf-8")
    if "\x00" in source or SECRET_PATTERN.search(source):
        raise ValueError("Code disclosure blocked: binary content or suspected embedded credential")
    return source


def review_source(root: Path, relative: str, expected_sha: str) -> str:
    """Disclose only the exact analyzed, non-symlink source revision."""
    path = PurePosixPath(relative)
    if (not relative or "\\" in relative or "\x00" in relative or path.is_absolute()
            or path.as_posix() != relative or ".." in path.parts or path.suffix not in _SOURCE_EXTENSIONS
            or any(part.startswith(".") for part in path.parts)):
        raise ValueError("Invalid review source path")
    current = root.resolve(strict=True)
    for part in path.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError("Symlink review source is forbidden")
    if not current.is_file() or not current.resolve().is_relative_to(root.resolve()):
        raise ValueError("Review source must be inside the repository")
    source = read_source(current)
    if hashlib.sha256(source.encode("utf-8")).hexdigest() != expected_sha:
        raise ValueError("Review source differs from analyzed revision")
    return source
