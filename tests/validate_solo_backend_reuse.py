"""Validate that solo mode reuses its own backend across runs.

Solo mode used to initialize its backend at a fixed path under
``tempfile.gettempdir()``. That directory is shared and persists between
runs, so every launch on a machine opened the same firm database -- matters
from an unrelated session appeared in the list, and a second launch while a
first was still open contended for the same SQLite file.

This exercises the two properties that fix must hold:

1. A window given a workspace keeps its backend inside that workspace, so two
   different workspaces never see each other's matters.
2. A second window on the *same* workspace reopens the same backend and sees
   the matter the first one created, exactly once.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PySide6.QtWidgets import QListWidget, QPushButton  # noqa: E402

from ui import MainWindow, create_app  # noqa: E402
from ui.app import DEV_UNLOCK_ENV_VAR  # noqa: E402


def _start_solo(workspace: Path) -> MainWindow:
    window = MainWindow(workspace=workspace)
    solo_button = window.findChild(QPushButton, "startSoloButton")
    assert solo_button is not None
    solo_button.click()
    assert window._backend_local is not None, "solo mode did not initialize a backend"
    return window


def _matter_labels(window: MainWindow) -> list[str]:
    refresh = window.findChild(QPushButton, "refreshMatterListButton")
    assert refresh is not None
    refresh.click()
    matter_list = window.findChild(QListWidget, "matterList")
    assert matter_list is not None
    return [matter_list.item(index).text() for index in range(matter_list.count())]


def main() -> None:
    os.environ[DEV_UNLOCK_ENV_VAR] = "1"
    try:
        app = create_app(["validate_solo_backend_reuse"])
        # A previous run of the old code may have left this behind; only a
        # directory created by *this* run indicates the regression is back.
        legacy_root = Path(tempfile.gettempdir()) / "wakilios-solo"
        legacy_existed = legacy_root.exists()
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace_a = Path(temp_dir) / "firm-a"
            workspace_b = Path(temp_dir) / "firm-b"

            first = _start_solo(workspace_a)
            assert first._backend_local is not None
            solo_root = workspace_a / "solo-backend"
            assert solo_root.exists(), f"solo backend was not created under {workspace_a}"
            assert legacy_existed or not legacy_root.exists(), (
                f"solo backend fell back to the shared fixed path {legacy_root}"
            )

            button = first.findChild(QPushButton, "newMatterButton")
            assert button is not None
            button.click()
            app.processEvents()
            assert first._current_matter_id
            first_labels = _matter_labels(first)
            assert len(first_labels) == 1, first_labels
            first.close()
            app.processEvents()

            # Same workspace: the matter is still there, and still only once.
            second = _start_solo(workspace_a)
            second_labels = _matter_labels(second)
            assert second_labels == first_labels, (second_labels, first_labels)
            second.close()
            app.processEvents()

            # Different workspace: a clean firm, not the previous one's matters.
            other = _start_solo(workspace_b)
            assert _matter_labels(other) == [], "a fresh workspace inherited another firm's matters"
            other.close()
            app.processEvents()
    finally:
        os.environ.pop(DEV_UNLOCK_ENV_VAR, None)

    print("SOLO BACKEND REUSE VALIDATION PASS")


if __name__ == "__main__":
    main()
