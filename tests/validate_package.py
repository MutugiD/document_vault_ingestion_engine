"""Validate F8 packaging configuration."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    spec_path = ROOT / "main.spec"
    spec_text = spec_path.read_text(encoding="utf-8")
    assert "DocumentVaultIngestionEngine" in spec_text
    assert "console=False" in spec_text
    assert "private" not in spec_text.lower()
    assert "secret" not in spec_text.lower()
    assert "credential" not in spec_text.lower()

    selftest = subprocess.run(
        [sys.executable, str(ROOT / "main.py"), "--selftest"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert selftest.returncode == 0, selftest.stdout + selftest.stderr
    assert "SELFTEST PASS" in selftest.stdout

    pyinstaller = subprocess.run(
        [sys.executable, "-m", "PyInstaller", "--version"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert pyinstaller.returncode == 0, pyinstaller.stdout + pyinstaller.stderr

    print("PACKAGE VALIDATION PASS")


if __name__ == "__main__":
    main()
