"""Validate the real Windows PyInstaller one-folder build."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST_APP = ROOT / "dist" / "DocumentVaultIngestionEngine"
FROZEN_EXE = DIST_APP / "DocumentVaultIngestionEngine.exe"


def main() -> None:
    if sys.platform != "win32":
        print("FROZEN BUILD VALIDATION SKIP: Windows-only validator")
        return

    for path in (ROOT / "build", ROOT / "dist"):
        if path.exists():
            shutil.rmtree(path)

    build = subprocess.run(
        [sys.executable, "-m", "PyInstaller", "--noconfirm", "main.spec"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert build.returncode == 0, build.stdout + build.stderr
    assert FROZEN_EXE.exists(), f"missing frozen executable: {FROZEN_EXE}"
    assert (DIST_APP / "_internal").exists(), "missing PyInstaller one-folder internals"

    frozen_selftest = subprocess.run(
        [str(FROZEN_EXE), "--selftest"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert frozen_selftest.returncode == 0, frozen_selftest.stdout + frozen_selftest.stderr

    frozen_products = subprocess.run(
        [str(FROZEN_EXE), "--products"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert frozen_products.returncode == 0, frozen_products.stdout + frozen_products.stderr

    print("FROZEN BUILD VALIDATION PASS")


if __name__ == "__main__":
    main()
