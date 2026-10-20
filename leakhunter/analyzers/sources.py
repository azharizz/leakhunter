"""Bounded source snapshots; never follow repository links or read special files."""
from __future__ import annotations

import os
from pathlib import Path
import stat


MAX_FILE_BYTES = 1024 * 1024
MAX_TOTAL_BYTES = 32 * 1024 * 1024
MAX_SOURCE_FILES = 2000
MAX_ENTRIES = 20000
MAX_DEPTH = 64


def exclusions(language):
    common = {".git", "__pycache__", ".venv", "venv", "node_modules"}
    return common | ({"data"} if language == "python" else {"vendor", "target"})


def source_files(root: Path, suffixes, excluded):
    files, total, entries = [], 0, 0

    def visit(directory, relative, depth):
        nonlocal total, entries
        if depth > MAX_DEPTH:
            raise ValueError("Repository source directory depth limit exceeded")
        with os.scandir(directory) as scan:
            for entry in scan:
                entries += 1
                if entries > MAX_ENTRIES:
                    raise ValueError("Repository entry limit exceeded")
                if entry.name in excluded:
                    continue
                path = relative / entry.name
                if entry.is_symlink():
                    raise ValueError("Repository links are unsupported; use a regular-file source snapshot")
                if entry.is_dir(follow_symlinks=False):
                    child = os.open(entry.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                                    dir_fd=directory)
                    try:
                        visit(child, path, depth + 1)
                    finally:
                        os.close(child)
                elif suffixes is None or path.suffix in suffixes:
                    if len(files) >= MAX_SOURCE_FILES:
                        raise ValueError("Repository source file count limit exceeded")
                    descriptor = os.open(entry.name, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW,
                                         dir_fd=directory)
                    with os.fdopen(descriptor, "rb") as source:
                        info = os.fstat(source.fileno())
                        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                            raise ValueError("Repository source must be a single-link regular file")
                        if info.st_size > MAX_FILE_BYTES:
                            raise ValueError("Repository source file byte limit exceeded")
                        limit = min(MAX_FILE_BYTES, MAX_TOTAL_BYTES - total)
                        content = source.read(limit + 1)
                    if len(content) > limit:
                        raise ValueError("Repository source byte limit exceeded")
                    total += len(content)
                    files.append((root / path, content))

    try:
        directory = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            visit(directory, Path(), 0)
        finally:
            os.close(directory)
    except OSError as error:
        raise ValueError("Repository source could not be read safely") from error
    return sorted(files, key=lambda item: item[0])
