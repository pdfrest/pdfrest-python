# /// script
# requires-python = ">=3.11"
# ///
"""Reject tracked Git paths that are not UTF-8 NFC, including collisions."""

from __future__ import annotations

import argparse
import subprocess
import sys
import unicodedata
from pathlib import Path
from typing import Any


def tracked_filename_report(root: Path) -> dict[str, Any]:
    """Inspect raw index paths, not filesystem names or quoted Git status text."""
    process = subprocess.run(
        ["git", "ls-files", "--cached", "-z"],
        cwd=root,
        check=False,
        capture_output=True,
    )
    if process.returncode != 0:
        return {
            "checked": False,
            "error": process.stderr.decode("utf-8", errors="replace").strip(),
            "issues": [],
            "collisions": [],
        }

    paths: list[str] = []
    invalid_utf8: list[str] = []
    for raw_path in process.stdout.split(b"\0"):
        if not raw_path:
            continue
        try:
            paths.append(raw_path.decode("utf-8"))
        except UnicodeDecodeError:
            invalid_utf8.append(raw_path.decode("utf-8", errors="backslashreplace"))

    by_nfc: dict[str, list[str]] = {}
    for path in set(paths):
        by_nfc.setdefault(unicodedata.normalize("NFC", path), []).append(path)
    collisions = [
        {"nfc_path": normalized, "paths": sorted(originals)}
        for normalized, originals in sorted(by_nfc.items())
        if len(originals) > 1
    ]
    issues = [
        {
            "path": path,
            "nfc_path": normalized,
            "collides_with": sorted(other for other in originals if other != path),
        }
        for normalized, originals in sorted(by_nfc.items())
        for path in sorted(originals)
        if path != normalized
    ]
    return {
        "checked": True,
        "issues": issues,
        "collisions": collisions,
        "invalid_utf8": sorted(invalid_utf8),
    }


def main() -> int:
    """Print actionable failures for a local pre-commit hook."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    args = parser.parse_args()
    report = tracked_filename_report(args.repo)
    if not report["checked"]:
        print(f"Cannot inspect tracked filenames: {report['error']}", file=sys.stderr)
        return 2
    for issue in report["issues"]:
        print(f"Non-NFC tracked path: {issue['path']!r} -> {issue['nfc_path']!r}")
        if issue["collides_with"]:
            print(f"  Normalization collision with: {issue['collides_with']!r}")
    for path in report["invalid_utf8"]:
        print(f"Tracked path is not UTF-8: {path!r}")
    return 1 if report["issues"] or report["invalid_utf8"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
