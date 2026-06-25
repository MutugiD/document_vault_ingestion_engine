"""Installation identity persistence."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4


@dataclass(frozen=True)
class InstallationIdentity:
    installation_id: str
    created_at: datetime


def ensure_installation_identity(settings_path: Path) -> InstallationIdentity:
    """Load or create a stable random installation identity."""

    settings_path.parent.mkdir(parents=True, exist_ok=True)
    if settings_path.exists():
        raw = json.loads(settings_path.read_text(encoding="utf-8"))
        return InstallationIdentity(
            installation_id=str(raw["installation_id"]),
            created_at=_parse_datetime(str(raw["created_at"])),
        )

    identity = InstallationIdentity(
        installation_id=str(uuid4()),
        created_at=datetime.now(UTC),
    )
    settings_path.write_text(
        json.dumps(
            {
                "installation_id": identity.installation_id,
                "created_at": identity.created_at.isoformat().replace("+00:00", "Z"),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return identity


def _parse_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)
