"""Validate manual-style Windows app flows through the UI/session boundary."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.create_manual_e2e_corpus import create_manual_e2e_corpus  # noqa: E402
from scripts.manual_windows_app_e2e import run_manual_windows_app_e2e  # noqa: E402


def main() -> None:
    with tempfile.TemporaryDirectory() as temporary_dir:
        workspace = Path(temporary_dir)
        source_dir = workspace / "manual-source-documents"
        create_manual_e2e_corpus(source_dir)
        run_manual_windows_app_e2e(source_dir)

    print("MANUAL WINDOWS APP E2E VALIDATION PASS")


if __name__ == "__main__":
    main()
