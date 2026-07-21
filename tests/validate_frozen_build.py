"""Validate the real Windows PyInstaller one-folder build."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import time
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

    default_gui = subprocess.Popen([str(FROZEN_EXE)], cwd=ROOT)
    try:
        time.sleep(2)
        assert default_gui.poll() is None, (
            f"double-click launch exited before opening the GUI: exit={default_gui.returncode}"
        )
    finally:
        if default_gui.poll() is None:
            default_gui.terminate()
        try:
            default_gui.wait(timeout=10)
        except subprocess.TimeoutExpired:
            default_gui.kill()
            default_gui.wait(timeout=10)
    print("DEFAULT GUI LAUNCH PASS")

    frozen_selftest = subprocess.run(
        [str(FROZEN_EXE), "--selftest"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert frozen_selftest.returncode == 0, frozen_selftest.stdout + frozen_selftest.stderr

    gui_smoke_result = Path(tempfile.gettempdir()) / "WakiliOS_gui_smoke.txt"
    gui_smoke_result.unlink(missing_ok=True)
    frozen_gui_smoke = subprocess.run(
        [str(FROZEN_EXE), "--gui-smoke", "1000"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
    )
    assert frozen_gui_smoke.returncode == 0, frozen_gui_smoke.stdout + frozen_gui_smoke.stderr
    assert gui_smoke_result.exists(), "frozen GUI smoke did not write a startup result"
    gui_smoke_text = gui_smoke_result.read_text(encoding="utf-8")
    assert "GUI START PASS" in gui_smoke_text, gui_smoke_text
    assert "visible=True" in gui_smoke_text, gui_smoke_text
    assert "window_id=0" not in gui_smoke_text, gui_smoke_text

    frozen_products = subprocess.run(
        [str(FROZEN_EXE), "--products"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert frozen_products.returncode == 0, frozen_products.stdout + frozen_products.stderr

    frozen_providers = subprocess.run(
        [str(FROZEN_EXE), "--providers"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert frozen_providers.returncode == 0, frozen_providers.stdout + frozen_providers.stderr

    frozen_admin = subprocess.run(
        [str(FROZEN_EXE), "--admin-license-payment-e2e"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert frozen_admin.returncode == 0, frozen_admin.stdout + frozen_admin.stderr
    assert "active_decision" in frozen_admin.stdout

    frozen_cloud = subprocess.run(
        [str(FROZEN_EXE), "--managed-cloud-backup-e2e"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert frozen_cloud.returncode == 0, frozen_cloud.stdout + frozen_cloud.stderr
    assert "interrupted_upload_blocked" in frozen_cloud.stdout

    frozen_wakili = subprocess.run(
        [str(FROZEN_EXE), "--wakili-mkononi-e2e"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert frozen_wakili.returncode == 0, frozen_wakili.stdout + frozen_wakili.stderr
    assert "audit_event_recorded" in frozen_wakili.stdout

    frozen_hosted_ai = subprocess.run(
        [str(FROZEN_EXE), "--hosted-ai-e2e"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert frozen_hosted_ai.returncode == 0, frozen_hosted_ai.stdout + frozen_hosted_ai.stderr
    assert "hosted_audit_recorded" in frozen_hosted_ai.stdout

    print("FROZEN BUILD VALIDATION PASS")


if __name__ == "__main__":
    main()
