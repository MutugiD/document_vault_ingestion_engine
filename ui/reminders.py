"""When to show the day's matters, and whether it has been shown yet.

Kept free of Qt on purpose. Under ``QT_QPA_PLATFORM=offscreen`` -- which is what
CI runs -- ``QSystemTrayIcon.isSystemTrayAvailable()`` is False and a tray
balloon can never be raised, so a schedule tangled up with the widget that shows
it would be untestable. Everything here is a pure function over a settings
record and an injected clock.

The clock is a parameter rather than a call to ``datetime.now`` for the same
reason: "the app was not running at 08:00" and "the user started it at 14:00"
are the two cases that actually matter, and neither can be exercised against a
real clock.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timedelta
from pathlib import Path

SETTINGS_FILENAME = "reminders.json"

DEFAULT_HOUR = 8
DEFAULT_MINUTE = 0
DEFAULT_HORIZON_DAYS = 1
DEFAULT_SNOOZE_MINUTES = 60


@dataclass(frozen=True)
class ReminderSettings:
    """How and when the daily digest appears.

    ``last_shown_date`` is persisted rather than held in memory so the digest
    survives a restart: an advocate who dismisses it at 08:05 and reopens the
    application at 09:00 should not be shown it again.
    """

    enabled: bool = True
    hour: int = DEFAULT_HOUR
    minute: int = DEFAULT_MINUTE
    horizon_days: int = DEFAULT_HORIZON_DAYS
    snooze_minutes: int = DEFAULT_SNOOZE_MINUTES
    last_shown_date: str = ""
    snoozed_until: str = ""


def due_now(settings: ReminderSettings, *, now: datetime) -> bool:
    """Whether the digest should be shown at ``now``.

    The comparison against the scheduled time is ``>=`` rather than ``==``, and
    that single choice answers both awkward cases. An application launched at
    14:00 having missed 08:00 shows the digest immediately; an application left
    running crosses 08:00 on its next timer tick. Neither needs a catch-up path,
    because "have we shown today's yet" is the actual question and
    ``last_shown_date`` is the actual answer.
    """
    if not settings.enabled:
        return False
    today = now.date().isoformat()
    if settings.last_shown_date == today:
        return False
    if settings.snoozed_until:
        try:
            if now < datetime.fromisoformat(settings.snoozed_until):
                return False
        except ValueError:
            # A corrupted snooze must not silence the reminder forever.
            pass
    scheduled = now.replace(
        hour=_clamp(settings.hour, 0, 23),
        minute=_clamp(settings.minute, 0, 59),
        second=0,
        microsecond=0,
    )
    return now >= scheduled


def mark_shown(settings: ReminderSettings, *, now: datetime) -> ReminderSettings:
    """Record that today's digest has been seen, and clear any snooze."""
    return replace(settings, last_shown_date=now.date().isoformat(), snoozed_until="")


def snooze(settings: ReminderSettings, *, now: datetime) -> ReminderSettings:
    """Push the digest back, without marking the day as shown."""
    until = now + timedelta(minutes=max(1, settings.snooze_minutes))
    return replace(settings, snoozed_until=until.isoformat(), last_shown_date="")


def settings_path(appdata_root: Path) -> Path:
    return appdata_root / SETTINGS_FILENAME


def load_settings(path: Path) -> ReminderSettings:
    """Read settings, falling back to defaults on anything unreadable.

    A malformed settings file must not stop the application opening, and the
    defaults are the behaviour a firm would want anyway.
    """
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ReminderSettings()
    if not isinstance(raw, dict):
        return ReminderSettings()
    defaults = ReminderSettings()
    known = {field: raw.get(field, getattr(defaults, field)) for field in asdict(defaults)}
    try:
        return ReminderSettings(
            enabled=bool(known["enabled"]),
            hour=_clamp(int(known["hour"]), 0, 23),
            minute=_clamp(int(known["minute"]), 0, 59),
            horizon_days=max(1, int(known["horizon_days"])),
            snooze_minutes=max(1, int(known["snooze_minutes"])),
            last_shown_date=str(known["last_shown_date"]),
            snoozed_until=str(known["snoozed_until"]),
        )
    except (TypeError, ValueError):
        return ReminderSettings()


def save_settings(path: Path, settings: ReminderSettings) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(settings), indent=2, sort_keys=True), encoding="utf-8")


def summarise(entries: list[dict[str, object]]) -> str:
    """One line naming what the day holds, for a tray balloon or a status bar."""
    if not entries:
        return "Nothing is scheduled today."
    counts: dict[str, int] = {}
    for entry in entries:
        counts[str(entry.get("kind", ""))] = counts.get(str(entry.get("kind", "")), 0) + 1
    labels = {
        "hearing": ("hearing", "hearings"),
        "lodging_due": ("lodging due", "lodgings due"),
        "decision": ("decision", "decisions"),
        "next_action": ("next action", "next actions"),
    }
    parts = [
        f"{count} {labels.get(kind, (kind, kind))[0 if count == 1 else 1]}"
        for kind, count in sorted(counts.items())
        if count
    ]
    return "Today: " + ", ".join(parts) + "."


def _clamp(value: int, low: int, high: int) -> int:
    return max(low, min(high, value))
