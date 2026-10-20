import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from leakhunter.analyzers import sources


class SourceBoundsTest(unittest.TestCase):
    def test_source_snapshot_is_sorted_and_prunes_excluded_directories(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "b.py").write_bytes(b"b = 1")
            (root / "a.py").write_bytes(b"a = 1")
            (root / ".venv").mkdir()
            os.mkfifo(root / ".venv" / "blocked.py")
            files = sources.source_files(root, {".py"}, sources.exclusions("python"))
            self.assertEqual([(p.name, b) for p, b in files], [("a.py", b"a = 1"), ("b.py", b"b = 1")])

    def test_analyzers_and_revision_hash_refuse_special_files(self):
        for language, suffix in (("python", ".py"), ("javascript", ".js"),
                                 ("typescript", ".ts"), ("go", ".go"), ("rust", ".rs")):
            with self.subTest(language=language), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                os.mkfifo(root / ("blocked" + suffix))
                code = f'''from pathlib import Path
from leakhunter.analyzers.registry import analyze_project
from leakhunter.application import service
from leakhunter.policy.engine import Policy
root = Path({str(root)!r})
policy = Policy({{"classifications": {{"PUBLIC": 0}}, "sources": [], "sinks": []}})
service.LANGUAGE = {language!r}
for operation in (lambda: analyze_project(root, policy, language={language!r}), lambda: service.revision_sha(root)):
    try:
        operation()
    except ValueError:
        pass
    else:
        raise AssertionError("Special file was accepted")
'''
                result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                                        cwd=Path(__file__).resolve().parents[1], timeout=10)
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_links_and_directory_replacement_cannot_escape_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "repository"
            root.mkdir()
            outside = Path(directory) / "outside"
            outside.mkdir()
            (outside / "private.py").write_text("private = True")
            link = root / "linked"
            link.symlink_to(outside, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, "links"):
                sources.source_files(root, {".py"}, set())
            link.unlink()
            link.mkdir()
            original = os.open

            def replace_directory(path, flags, *args, **kwargs):
                if path == "linked" and "dir_fd" in kwargs:
                    link.rmdir()
                    link.symlink_to(outside, target_is_directory=True)
                return original(path, flags, *args, **kwargs)

            with patch.object(sources.os, "open", side_effect=replace_directory):
                with self.assertRaisesRegex(ValueError, "safely"):
                    sources.source_files(root, {".py"}, set())

    def test_hardlinks_and_file_replacement_are_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "repository"
            root.mkdir()
            outside = Path(directory) / "private.py"
            outside.write_text("private = True")
            source = root / "source.py"
            os.link(outside, source)
            with self.assertRaisesRegex(ValueError, "regular file"):
                sources.source_files(root, {".py"}, set())
            source.unlink()
            source.write_text("public = True")
            original = os.open

            def replace_file(path, flags, *args, **kwargs):
                if path == "source.py" and "dir_fd" in kwargs:
                    source.unlink()
                    source.symlink_to(outside)
                return original(path, flags, *args, **kwargs)

            with patch.object(sources.os, "open", side_effect=replace_file):
                with self.assertRaisesRegex(ValueError, "safely"):
                    sources.source_files(root, {".py"}, set())

    def test_byte_file_entry_and_depth_limits_stop_instead_of_truncating(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "a.py").write_bytes(b"x" * (sources.MAX_FILE_BYTES + 1))
            with self.assertRaisesRegex(ValueError, "file byte"):
                sources.source_files(root, {".py"}, set())
            (root / "a.py").write_bytes(b"abc")
            (root / "b.py").write_bytes(b"def")
            with patch.object(sources, "MAX_TOTAL_BYTES", 6), patch.object(sources, "MAX_SOURCE_FILES", 2):
                self.assertEqual(len(sources.source_files(root, {".py"}, set())), 2)
            for name, limit, reason in (("MAX_TOTAL_BYTES", 5, "source byte"),
                                        ("MAX_SOURCE_FILES", 1, "file count"),
                                        ("MAX_ENTRIES", 1, "entry limit")):
                with self.subTest(limit=name), patch.object(sources, name, limit):
                    with self.assertRaisesRegex(ValueError, reason):
                        sources.source_files(root, {".py"}, set())
            (root / "nested").mkdir()
            with patch.object(sources, "MAX_DEPTH", 0), self.assertRaisesRegex(ValueError, "depth"):
                sources.source_files(root, {".py"}, set())

    def test_file_growth_after_stat_cannot_bypass_byte_limit(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "growing.py"
            path.write_bytes(b"x")
            original = os.fstat

            def grow(descriptor):
                info = original(descriptor)
                with path.open("ab") as source:
                    source.write(b"yz")
                return info

            with patch.object(sources, "MAX_FILE_BYTES", 2), patch.object(sources.os, "fstat", side_effect=grow):
                with self.assertRaisesRegex(ValueError, "source byte"):
                    sources.source_files(root, {".py"}, set())
