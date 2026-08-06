"""Validate the daily digest: when it fires, and what it shows.

Two things make this worth testing carefully rather than by hand.

The schedule has four states that a wall clock cannot reach on demand -- the app
was closed at 08:00, the app was opened at 14:00, the digest was already shown
today, the user snoozed it. ``due_now`` takes the clock as a parameter so all
four are ordinary assertions.

And the presentation cannot be a tray balloon alone. Under
``QT_QPA_PLATFORM=offscreen``, which is what CI runs,
``QSystemTrayIcon.isSystemTrayAvailable()`` is False, so a balloon-only design
would be permanently untested. It would also be wrong on a real desktop, where
Windows Focus Assist drops toasts silently -- the firm believes it is covered
and never learns otherwise.
"""

from __future__ import annotations

import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from _dialog_harness import autofill_dialogs  # noqa: E402
from PySide6.QtWidgets import QCheckBox, QLineEdit, QListWidget, QPushButton  # noqa: E402

import ui.app as ui_app  # noqa: E402
from ui import MainWindow, create_app  # noqa: E402
from ui.app import DEV_UNLOCK_ENV_VAR  # noqa: E402
from ui.reminders import (  # noqa: E402
    ReminderSettings,
    due_now,
    load_settings,
    mark_shown,
    save_settings,
    snooze,
    summarise,
)


def at(hour: int, minute: int = 0, *, day: int = 6) -> datetime:
    return datetime(2026, 8, day, hour, minute)


def check_schedule() -> None:
    settings = ReminderSettings(enabled=True, hour=8, minute=0)

    assert not due_now(settings, now=at(7, 59)), "fired before the scheduled time"
    assert due_now(settings, now=at(8, 0)), "did not fire at the scheduled time"

    # The app was not running at 08:00 and is opened at 14:00. This is the
    # common case, not an edge case -- most firms open the application when they
    # sit down. ">= scheduled" rather than "== scheduled" is what handles it,
    # with no catch-up path needed.
    assert due_now(settings, now=at(14, 0)), "a missed window never caught up"

    shown = mark_shown(settings, now=at(8, 1))
    assert not due_now(shown, now=at(9, 0)), "showed twice in one day"
    assert not due_now(shown, now=at(23, 59)), "showed twice in one day"
    # Persisted, not in memory, so closing and reopening does not re-show it.
    assert shown.last_shown_date == "2026-08-06"
    # ...and tomorrow it is owed again.
    assert due_now(shown, now=at(8, 0, day=7)), "did not come back the next day"

    snoozed = snooze(settings, now=at(8, 5))
    assert not due_now(snoozed, now=at(8, 30)), "fired while snoozed"
    assert due_now(snoozed, now=at(9, 30)), "never came back after the snooze"

    assert not due_now(ReminderSettings(enabled=False), now=at(14, 0)), "fired while disabled"

    # A corrupted snooze must not silence the digest forever: the failure mode
    # of a reminder is silence, so every unclear case has to resolve towards
    # showing it.
    corrupt = ReminderSettings(enabled=True, hour=8, snoozed_until="not a timestamp")
    assert due_now(corrupt, now=at(14, 0)), "a corrupt snooze value silenced the reminder"


def check_settings_round_trip() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        path = Path(temp_dir) / "reminders.json"
        assert load_settings(path) == ReminderSettings(), "a missing file should give defaults"

        stored = ReminderSettings(enabled=False, hour=7, minute=30, horizon_days=3)
        save_settings(path, stored)
        assert load_settings(path) == stored

        # A settings file someone edited by hand must not stop the app opening.
        path.write_text("{ not json", encoding="utf-8")
        assert load_settings(path) == ReminderSettings()
        path.write_text('{"hour": 99, "minute": -4, "horizon_days": 0}', encoding="utf-8")
        recovered = load_settings(path)
        assert 0 <= recovered.hour <= 23 and 0 <= recovered.minute <= 59, recovered
        assert recovered.horizon_days >= 1, recovered


def check_summary() -> None:
    assert summarise([]) == "Nothing is scheduled today."
    line = summarise(
        [
            {"kind": "hearing"},
            {"kind": "hearing"},
            {"kind": "lodging_due"},
        ]
    )
    assert "2 hearings" in line, line
    assert "1 lodging due" in line, line


def check_window() -> None:
    """The digest must reach a real window, with the day's entries in it."""
    os.environ[DEV_UNLOCK_ENV_VAR] = "1"
    captured: dict[str, object] = {}
    original_exec = ui_app.DailyReminderDialog.exec

    def capture(dialog) -> int:
        listing = dialog.findChild(QListWidget, "dailyReminderList")
        captured["rows"] = [listing.item(i).text() for i in range(listing.count())]
        captured["summary"] = dialog.findChild(ui_app.QLabel, "dailyReminderSummaryLabel").text()
        return 1

    ui_app.DailyReminderDialog.exec = capture
    restore_dialogs = autofill_dialogs("REMIND", date_value=_today())
    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            os.environ["APPDATA"] = str(root / "appdata")
            app = create_app(["validate_daily_reminder"])
            window = MainWindow(workspace=root / "workspace")

            def button(name: str) -> QPushButton:
                found = window.findChild(QPushButton, name)
                assert found is not None, f"missing control: {name}"
                return found

            # Nothing to talk to yet: it must say so rather than raise.
            button("testDailyReminderButton").click()
            app.processEvents()
            assert "Start solo mode" in window.status_label.text(), window.status_label.text()

            button("startSoloButton").click()
            app.processEvents()

            # An empty day still shows, and says the day is empty.
            button("testDailyReminderButton").click()
            app.processEvents()
            assert captured.get("rows") == [], captured
            assert "Nothing is scheduled" in str(captured.get("summary")), captured

            button("newMatterButton").click()
            app.processEvents()
            assert window._current_matter_id, "a matter should be open"

            # A hearing today, through the real Add form.
            add = window.findChild(QPushButton, "activitiesTabAddButton")
            assert add is not None
            add.click()
            app.processEvents()

            captured.clear()
            button("testDailyReminderButton").click()
            app.processEvents()
            rows = captured.get("rows") or []
            assert rows, "today's hearing did not reach the digest"
            assert any("Hearing" in row for row in rows), rows

            # Having been shown, it must not be owed again today.
            assert window._reminder_settings.last_shown_date == _today()
            assert not due_now(window._reminder_settings, now=datetime.now())

            # The settings form must persist, and must reject nonsense clearly.
            time_input = window.findChild(QLineEdit, "dailyReminderTimeInput")
            enabled = window.findChild(QCheckBox, "dailyReminderEnabledCheckbox")
            assert time_input is not None and enabled is not None
            time_input.setText("half seven")
            button("saveReminderSettingsButton").click()
            app.processEvents()
            assert "HH:MM" in window.status_label.text(), window.status_label.text()

            time_input.setText("07:30")
            enabled.setChecked(False)
            button("saveReminderSettingsButton").click()
            app.processEvents()
            assert window._reminder_settings.hour == 7
            assert window._reminder_settings.minute == 30
            assert window._reminder_settings.enabled is False

            reloaded = load_settings(window._reminder_settings_file())
            assert reloaded.hour == 7 and reloaded.enabled is False, reloaded

            window.close()
            app.processEvents()
    finally:
        ui_app.DailyReminderDialog.exec = original_exec
        restore_dialogs()
        os.environ.pop(DEV_UNLOCK_ENV_VAR, None)


def _today() -> str:
    from wakilios.core import NAIROBI

    return datetime.now(NAIROBI).date().isoformat()


def main() -> None:
    check_schedule()
    check_settings_round_trip()
    check_summary()
    check_window()
    print("DAILY REMINDER VALIDATION PASS")


if __name__ == "__main__":
    main()
