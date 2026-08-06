"""Validate the automation seam, and that it is inert unless switched on.

The seam exists so the packaged application can be driven without native file
dialogs, and so a harness can assert on what the window believes rather than on
label text. Both are only acceptable if they are genuinely off by default, so
that is most of what this asserts.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from PySide6.QtWidgets import QPushButton  # noqa: E402

import ui.app as ui_app  # noqa: E402
from ui import MainWindow, create_app  # noqa: E402
from ui.app import DEV_UNLOCK_ENV_VAR  # noqa: E402
from ui.automation import (  # noqa: E402
    AUTOMATION_ENV_VAR,
    QUEUE_ENV_VAR,
    STATE_ENV_VAR,
    automation_enabled,
    queued_selection,
    write_state,
)

JUDGMENT = ROOT / "test-output" / "maua-corpus" / "meru-hc-mrima-2019-2805.pdf"


def _clear() -> None:
    for name in (AUTOMATION_ENV_VAR, QUEUE_ENV_VAR, STATE_ENV_VAR):
        os.environ.pop(name, None)


def main() -> None:
    # ── Off by default ───────────────────────────────────────────────────
    _clear()
    assert automation_enabled() is False
    assert queued_selection() == [], "the queue must not be read when off"

    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        state_path = root / "state.json"
        queue_path = root / "queue.txt"
        queue_path.write_text("C:/should-never-be-read.pdf", encoding="utf-8")

        # Even with paths configured, nothing happens while the flag is unset.
        os.environ[QUEUE_ENV_VAR] = str(queue_path)
        os.environ[STATE_ENV_VAR] = str(state_path)
        assert queued_selection() == []
        write_state({"leaked": True})
        assert not state_path.exists(), "state must not be published when off"
        assert queue_path.read_text(encoding="utf-8").strip(), "queue must not be consumed when off"

        # ── Switched on ──────────────────────────────────────────────────
        os.environ[AUTOMATION_ENV_VAR] = "1"
        assert automation_enabled() is True

        # The queue is consumed one selection at a time, in order.
        queue_path.write_text("first.pdf\nsecond.pdf|third.pdf\n", encoding="utf-8")
        assert queued_selection() == ["first.pdf"]
        assert queued_selection() == ["second.pdf", "third.pdf"], "one line may hold several paths"
        assert queued_selection() == [], "an exhausted queue yields nothing"

        write_state({"published": 1})
        assert json.loads(state_path.read_text(encoding="utf-8")) == {"published": 1}

    _clear()

    # ── The window publishes real state, and takes queued selections ─────
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        os.environ["APPDATA"] = str(root / "appdata")
        os.environ[DEV_UNLOCK_ENV_VAR] = "1"
        os.environ[AUTOMATION_ENV_VAR] = "1"
        queue_path = root / "queue.txt"
        state_path = root / "state.json"
        os.environ[QUEUE_ENV_VAR] = str(queue_path)
        os.environ[STATE_ENV_VAR] = str(state_path)

        app = create_app(["validate_automation_seam"])
        window = MainWindow(workspace=root / "workspace")

        def button(name: str) -> QPushButton:
            found = window.findChild(QPushButton, name)
            assert found is not None, f"missing control: {name}"
            return found

        button("startSoloButton").click()
        app.processEvents()

        state = json.loads(state_path.read_text(encoding="utf-8"))
        assert state["license_active"] is True
        assert state["backend"] == "solo", state["backend"]
        assert state["destinations"] == [
            "Matters",
            "Documents",
            "Filing record",
            "Search",
            "Reminders",
            "Reports",
            "Settings",
        ], state["destinations"]
        assert state["current_matter_id"] == ""

        # A queued selection replaces the native picker entirely.
        if JUDGMENT.exists():
            queue_path.write_text(str(JUDGMENT), encoding="utf-8")
            captured: dict[str, str] = {}
            original = ui_app.MatterDialog.exec

            def accept(dialog):
                captured.update(dialog.values())
                dialog._on_accept()
                return 1

            ui_app.MatterDialog.exec = accept
            try:
                button("newMatterFromDocumentButton").click()
                app.processEvents()
            finally:
                ui_app.MatterDialog.exec = original

            assert queue_path.read_text(encoding="utf-8").strip() == "", "queue was not consumed"
            # Read off a real Meru High Court judgment.
            assert captured.get("case_number") == "CIVIL APPEAL NO. 109 OF 2018", captured
            assert captured.get("court") == "High Court", captured
            assert captured.get("station") == "Meru", captured

            state = json.loads(state_path.read_text(encoding="utf-8"))
            assert state["current_matter_id"], "a matter should now be open"
            assert len(state["matters"]) == 1, state["matters"]

        window.close()
        app.processEvents()

    _clear()
    os.environ.pop(DEV_UNLOCK_ENV_VAR, None)
    print("AUTOMATION SEAM VALIDATION PASS")


if __name__ == "__main__":
    main()
