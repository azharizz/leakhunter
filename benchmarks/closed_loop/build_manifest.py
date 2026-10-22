"""Build a private runtime manifest from protected synthetic probe variables."""
from __future__ import annotations

import argparse
import os
from pathlib import Path

import yaml

from leakhunter.execution.runtime import load_manifest


_PREFIX = "UNSPOOL_CLOSED_LOOP_"


def build(template: Path, output: Path) -> None:
    manifest = yaml.safe_load(Path(template).read_text(encoding="utf-8"))
    if not isinstance(manifest, dict) or not isinstance(manifest.get("cases"), list):
        raise ValueError("Invalid closed-loop manifest template")
    for case in manifest["cases"]:
        for source in case.get("sensitive", []):
            name = source.pop("marker_env", None)
            if (not isinstance(name, str) or not name.startswith(_PREFIX)
                    or not name[len(_PREFIX):].replace("_", "").isalnum()):
                raise ValueError("Probe marker must use an approved environment variable")
            marker = os.environ.get(name)
            if not isinstance(marker, str) or len(marker) < 24 or any(char in marker for char in "\x00\r\n"):
                raise ValueError(f"Missing or invalid protected probe value: {name}")
            source["marker"] = marker
            symbol = source.get("symbol")
            if not isinstance(symbol, str) or "." not in symbol:
                raise ValueError("Probe source symbol must identify a field")
            case["args"], replacements = _replace_placeholder(
                case["args"], "unset", marker, symbol.rsplit(".", 1)[-1])
            if replacements != 1:
                raise ValueError("Probe marker must replace exactly one argument field")
    rendered = yaml.safe_dump(manifest, sort_keys=False).encode("utf-8")
    output = Path(output)
    if output.exists() or output.is_symlink():
        raise ValueError("Refusing to overwrite runtime manifest")
    output.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        with os.fdopen(descriptor, "wb") as target:
            target.write(rendered)
            target.flush()
            os.fsync(target.fileno())
        load_manifest(output)
    except BaseException:
        output.unlink(missing_ok=True)
        raise


def _replace_placeholder(value, placeholder, marker, leaf):
    replacements = 0
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            if key == leaf and item == placeholder:
                result[key] = marker
                replacements += 1
            else:
                result[key], count = _replace_placeholder(item, placeholder, marker, leaf)
                replacements += count
        return result, replacements
    if isinstance(value, list):
        result = []
        for item in value:
            item, count = _replace_placeholder(item, placeholder, marker, leaf)
            result.append(item)
            replacements += count
        return result, replacements
    return value, 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--template", type=Path, default=Path(__file__).with_name("runtime.template.yaml"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    build(args.template, args.output)


if __name__ == "__main__":
    main()
