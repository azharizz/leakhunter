"""Plant the known whole-record exposure in an isolated copy of the safe target."""
from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import stat


_SAFE = '''def account_summary(account):
    public = {field: account[field] for field in PUBLIC_FIELDS}
    public["display_name"] = " ".join(public["display_name"].split())
    return public
'''
_LEAK = '''def account_summary(account):
    summary = dict(account)
    summary["display_name"] = " ".join(summary["display_name"].split())
    return summary
'''


def seed(source: Path, output: Path) -> str:
    source, output = Path(source), Path(output)
    if source.is_symlink() or not source.is_file():
        raise ValueError("Safe baseline must be a regular file")
    original = source.read_text(encoding="utf-8")
    if original.count(_SAFE) != 1 or "dict(account)" in original:
        raise ValueError("Target does not match the frozen safe baseline")
    planted = original.replace(_SAFE, _LEAK, 1).encode("utf-8")
    output.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(output, flags, 0o600)
    except FileExistsError:
        raise ValueError("Refusing to overwrite the seeded target") from None
    with os.fdopen(descriptor, "wb") as target:
        target.write(planted)
        target.flush()
        os.fsync(target.fileno())
    return hashlib.sha256(planted).hexdigest()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path(__file__).parent / "target" / "accounts.py")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    print(seed(args.source, args.output))


if __name__ == "__main__":
    main()
