"""
Clock-rollback guard for WakiliOS licensing (spec §6.2).

Stores a monotonic "last seen" UTC timestamp; if the system clock is ever
earlier than the stored value, the app locks. The store is abstracted so
the logic is testable headless; production uses the filesystem (no registry
needed on Linux/macOS). This is anti-CASUAL-tamper only — a local admin
can clear the file. A missing stored value is treated as first run.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

_TAMPERED = "System clock tampered - license revoked"


class InMemoryStore:
    """Test/abstract store — holds the stamp in memory."""

    def __init__(self, value: str | None = None):
        self._v = value

    def get(self) -> str | None:
        return self._v

    def set(self, value: str) -> None:
        self._v = value


class FileStore:
    """Production store: writes to a JSON file in the app data directory."""

    def __init__(self, path: Path):
        self.path = path

    def get(self) -> str | None:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return data.get("last_seen_utc")
        except (OSError, ValueError, KeyError):
            return None

    def set(self, value: str) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(
                json.dumps({"last_seen_utc": value}, indent=2),
                encoding="utf-8",
            )
        except OSError:
            pass  # degrade gracefully, never crash at launch


def ntp_utc(server: str = "pool.ntp.org", timeout: float = 2.0) -> datetime | None:
    """Best-effort UTC time from an NTP server. Returns None when unreachable."""
    try:
        import ntplib

        resp = ntplib.NTPClient().request(server, version=3, timeout=timeout)
        return datetime.fromtimestamp(resp.tx_time, tz=UTC)
    except Exception:
        return None


def check_clock(
    store,
    now: datetime | None = None,
    ntp: datetime | None = None,
    ntp_tolerance_days: int = 1,
) -> tuple[bool, str]:
    """Return (ok, reason). Locks if the system clock rolled back vs the stored stamp."""
    now = now or datetime.now(UTC)

    # NTP cross-check: system clock far behind true time => rolled back
    if ntp is not None and now < ntp - timedelta(days=ntp_tolerance_days):
        return False, _TAMPERED

    try:
        stored_raw = store.get()
    except OSError:
        stored_raw = None

    stored = None
    if stored_raw:
        try:
            stored = datetime.fromisoformat(stored_raw)
        except (ValueError, TypeError):
            stored = None

    if stored is not None:
        if now < stored:
            return False, _TAMPERED
        if now > stored:
            _safe_set(store, now)
    else:
        _safe_set(store, now)

    return True, ""


def _safe_set(store, now: datetime) -> None:
    """Persist the stamp, swallowing write failures so the guard degrades gracefully."""
    try:
        store.set(now.isoformat())
    except OSError:
        pass
