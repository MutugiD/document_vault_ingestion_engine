"""Validate the F0 Python skeleton and packaging metadata."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

PACKAGES = ["core", "licensing", "vault", "intake", "search", "backup", "ui"]
ROOT_FILES = ["README.md", "BUILD.md", "pyproject.toml", "requirements.txt", "main.py", "main.spec"]


def main() -> int:
    missing = [path for path in ROOT_FILES if not (ROOT / path).exists()]
    if missing:
        print("SKELETON VALIDATION FAIL")
        for path in missing:
            print(f"- missing {path}")
        return 1

    for package in PACKAGES:
        importlib.import_module(package)

    spec_text = (ROOT / "main.spec").read_text(encoding="utf-8")
    if "DocumentVaultIngestionEngine" not in spec_text:
        print("SKELETON VALIDATION FAIL")
        print("- main.spec does not name DocumentVaultIngestionEngine")
        return 1

    print("SKELETON VALIDATION PASS")
    print(f"Imported packages: {', '.join(PACKAGES)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
