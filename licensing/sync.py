"""Privacy-safe admin and license sync boundary."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from licensing.core import ACTIVE_STATUS, LicenseValidationResult

SYNC_ACTIVE_STATUS = "active"
SYNC_DISABLED_STATUS = "disabled"
SYNC_SUSPENDED_STATUS = "suspended"
SYNC_EXPIRED_STATUS = "expired"
SYNC_GRACE_EXPIRED_STATUS = "sync_grace_expired"
SYNC_UNKNOWN_STATUS = "unknown"

PAID_ACTIVE_STATE = "paid_active"
PAID_SUSPENDED_STATE = "paid_suspended"
PAID_EXPIRED_STATE = "paid_expired"
PAID_DISABLED_STATE = "paid_disabled"
PAID_UNKNOWN_STATE = "paid_unknown"

DEFAULT_SYNC_GRACE_DAYS = 14
PAYLOAD_SCHEMA_VERSION = "1"

ONLINE_FEATURES = frozenset({"cloud_backup", "managed_restore"})
FORBIDDEN_PAYLOAD_KEY_MARKERS = (
    "matter",
    "client",
    "case",
    "filename",
    "file_name",
    "document",
    "ocr",
    "prompt",
    "hash",
    "sha256",
    "recovery",
    "secret",
    "credential",
)


class LicenseSyncError(Exception):
    """Raised when license sync data violates the local privacy contract."""


@dataclass(frozen=True)
class BackupHealth:
    """Coarse backup state allowed in owner-backend check-ins."""

    status: str = "unknown"
    last_success_age_hours: int | None = None
    pending_upload_count: int = 0

    def to_mapping(self) -> dict[str, object]:
        return {
            "status": self.status,
            "last_success_age_hours": self.last_success_age_hours,
            "pending_upload_count": self.pending_upload_count,
        }


@dataclass(frozen=True)
class LicenseCheckInPayload:
    """Payload sent to the owner backend for admin/license sync."""

    installation_id: str
    license_id: str
    app_version: str
    device_nickname: str
    license_status: str
    paid_entitlement_state: str
    feature_flags: dict[str, bool]
    coarse_backup_health: BackupHealth
    generated_at: datetime
    schema_version: str = PAYLOAD_SCHEMA_VERSION

    def to_mapping(self) -> dict[str, object]:
        payload = {
            "schema_version": self.schema_version,
            "installation_id": self.installation_id,
            "license_id": self.license_id,
            "app_version": self.app_version,
            "device_nickname": self.device_nickname,
            "license_status": self.license_status,
            "paid_entitlement_state": self.paid_entitlement_state,
            "feature_flags": dict(sorted(self.feature_flags.items())),
            "coarse_backup_health": self.coarse_backup_health.to_mapping(),
            "generated_at": _datetime_to_text(self.generated_at),
        }
        assert_payload_privacy(payload)
        return payload


@dataclass(frozen=True)
class LicenseSyncResponse:
    """Owner-backend response controlling paid/admin feature availability."""

    installation_status: str
    paid_entitlement_state: str
    enabled_features: frozenset[str]
    server_time: datetime
    grace_expires_at: datetime
    reason: str = ""

    @classmethod
    def from_mapping(cls, value: dict[str, Any]) -> LicenseSyncResponse:
        return cls(
            installation_status=str(value["installation_status"]),
            paid_entitlement_state=str(value["paid_entitlement_state"]),
            enabled_features=frozenset(str(item) for item in value.get("enabled_features", [])),
            server_time=_parse_datetime(str(value["server_time"])),
            grace_expires_at=_parse_datetime(str(value["grace_expires_at"])),
            reason=str(value.get("reason", "")),
        )

    def to_mapping(self) -> dict[str, object]:
        return {
            "installation_status": self.installation_status,
            "paid_entitlement_state": self.paid_entitlement_state,
            "enabled_features": sorted(self.enabled_features),
            "server_time": _datetime_to_text(self.server_time),
            "grace_expires_at": _datetime_to_text(self.grace_expires_at),
            "reason": self.reason,
        }


@dataclass(frozen=True)
class LicenseSyncState:
    """Persisted last-known admin/license sync state."""

    installation_status: str
    paid_entitlement_state: str
    enabled_features: frozenset[str]
    last_success_at: datetime
    grace_expires_at: datetime
    reason: str = ""

    @classmethod
    def from_mapping(cls, value: dict[str, Any]) -> LicenseSyncState:
        return cls(
            installation_status=str(value["installation_status"]),
            paid_entitlement_state=str(value["paid_entitlement_state"]),
            enabled_features=frozenset(str(item) for item in value.get("enabled_features", [])),
            last_success_at=_parse_datetime(str(value["last_success_at"])),
            grace_expires_at=_parse_datetime(str(value["grace_expires_at"])),
            reason=str(value.get("reason", "")),
        )

    def to_mapping(self) -> dict[str, object]:
        return {
            "installation_status": self.installation_status,
            "paid_entitlement_state": self.paid_entitlement_state,
            "enabled_features": sorted(self.enabled_features),
            "last_success_at": _datetime_to_text(self.last_success_at),
            "grace_expires_at": _datetime_to_text(self.grace_expires_at),
            "reason": self.reason,
        }


@dataclass(frozen=True)
class EffectiveEntitlements:
    """Combined offline license and admin sync decision."""

    status: str
    paid_entitlement_state: str
    enabled_features: frozenset[str]
    paid_features_enabled: bool
    online_features_enabled: bool
    allows_local_data_access: bool
    reason: str = ""

    def feature_enabled(self, feature_name: str) -> bool:
        return self.paid_features_enabled and feature_name in self.enabled_features

    def online_feature_enabled(self, feature_name: str) -> bool:
        return self.online_features_enabled and feature_name in self.enabled_features


def build_license_check_in_payload(
    *,
    installation_id: str,
    app_version: str,
    device_nickname: str,
    license_result: LicenseValidationResult,
    backup_health: BackupHealth | None = None,
    generated_at: datetime | None = None,
) -> LicenseCheckInPayload:
    """Build the privacy-allowlisted payload sent during periodic check-in."""

    license_document = license_result.license_document
    feature_flags = (
        _features_to_mapping(license_document.features)
        if license_document is not None and license_result.paid_features_enabled
        else _disabled_features()
    )
    payload = LicenseCheckInPayload(
        installation_id=installation_id,
        license_id=license_document.license_id if license_document is not None else "",
        app_version=app_version,
        device_nickname=device_nickname,
        license_status=license_result.status,
        paid_entitlement_state=(
            PAID_ACTIVE_STATE if license_result.paid_features_enabled else PAID_UNKNOWN_STATE
        ),
        feature_flags=feature_flags,
        coarse_backup_health=backup_health or BackupHealth(),
        generated_at=generated_at or datetime.now(UTC),
    )
    payload.to_mapping()
    return payload


def record_license_sync_success(response: LicenseSyncResponse) -> LicenseSyncState:
    """Convert a successful backend response into local persisted sync state."""

    _validate_response(response)
    return LicenseSyncState(
        installation_status=response.installation_status,
        paid_entitlement_state=response.paid_entitlement_state,
        enabled_features=response.enabled_features,
        last_success_at=response.server_time,
        grace_expires_at=response.grace_expires_at,
        reason=response.reason,
    )


def evaluate_effective_entitlements(
    license_result: LicenseValidationResult,
    *,
    sync_state: LicenseSyncState | None,
    as_of: datetime | None = None,
) -> EffectiveEntitlements:
    """Combine offline license state with last-known admin sync state."""

    now = as_of or datetime.now(UTC)
    if not license_result.allows_local_data_access:
        return EffectiveEntitlements(
            status=license_result.status,
            paid_entitlement_state=PAID_DISABLED_STATE,
            enabled_features=frozenset(),
            paid_features_enabled=False,
            online_features_enabled=False,
            allows_local_data_access=False,
            reason=license_result.reason,
        )

    if not license_result.paid_features_enabled or license_result.license_document is None:
        return EffectiveEntitlements(
            status=license_result.status,
            paid_entitlement_state=PAID_DISABLED_STATE,
            enabled_features=frozenset(),
            paid_features_enabled=False,
            online_features_enabled=False,
            allows_local_data_access=True,
            reason=license_result.reason,
        )

    local_features = _enabled_feature_names(license_result)
    if sync_state is None:
        return EffectiveEntitlements(
            status=SYNC_UNKNOWN_STATUS,
            paid_entitlement_state=PAID_UNKNOWN_STATE,
            enabled_features=frozenset(local_features),
            paid_features_enabled=True,
            online_features_enabled=False,
            allows_local_data_access=True,
            reason="no successful online check-in has been recorded",
        )

    if sync_state.installation_status != SYNC_ACTIVE_STATUS:
        return EffectiveEntitlements(
            status=sync_state.installation_status,
            paid_entitlement_state=sync_state.paid_entitlement_state,
            enabled_features=frozenset(),
            paid_features_enabled=False,
            online_features_enabled=False,
            allows_local_data_access=True,
            reason=sync_state.reason or "installation disabled by admin sync",
        )

    enabled_features = frozenset(local_features.intersection(sync_state.enabled_features))
    if now > sync_state.grace_expires_at:
        return EffectiveEntitlements(
            status=SYNC_GRACE_EXPIRED_STATUS,
            paid_entitlement_state=sync_state.paid_entitlement_state,
            enabled_features=enabled_features,
            paid_features_enabled=False,
            online_features_enabled=False,
            allows_local_data_access=True,
            reason="license sync grace window has expired",
        )

    return EffectiveEntitlements(
        status=SYNC_ACTIVE_STATUS,
        paid_entitlement_state=sync_state.paid_entitlement_state,
        enabled_features=enabled_features,
        paid_features_enabled=True,
        online_features_enabled=bool(enabled_features.intersection(ONLINE_FEATURES)),
        allows_local_data_access=True,
    )


def load_license_sync_state(path: Path) -> LicenseSyncState | None:
    if not path.exists():
        return None
    return LicenseSyncState.from_mapping(json.loads(path.read_text(encoding="utf-8")))


def write_license_sync_state(path: Path, state: LicenseSyncState) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state.to_mapping(), indent=2, sort_keys=True) + "\n")


def assert_payload_privacy(payload: dict[str, object]) -> None:
    """Reject check-in payloads that contain legal document identifiers or secrets."""

    for key_path, _value in _walk_mapping(payload):
        if key_path.startswith("feature_flags."):
            continue
        lowered = key_path.lower()
        if any(marker in lowered for marker in FORBIDDEN_PAYLOAD_KEY_MARKERS):
            raise LicenseSyncError(f"forbidden check-in field: {key_path}")


def sync_grace_expiry(server_time: datetime, *, days: int = DEFAULT_SYNC_GRACE_DAYS) -> datetime:
    return server_time.astimezone(UTC) + timedelta(days=days)


def _validate_response(response: LicenseSyncResponse) -> None:
    allowed_statuses = {
        SYNC_ACTIVE_STATUS,
        SYNC_DISABLED_STATUS,
        SYNC_SUSPENDED_STATUS,
        SYNC_EXPIRED_STATUS,
    }
    if response.installation_status not in allowed_statuses:
        raise LicenseSyncError("unknown installation status from license sync")
    if response.grace_expires_at < response.server_time:
        raise LicenseSyncError("license sync grace expiry cannot predate server time")


def _features_to_mapping(features) -> dict[str, bool]:
    return {
        "cloud_backup": features.cloud_backup,
        "document_intake": features.document_intake,
        "managed_restore": features.managed_restore,
        "matter_rag": features.matter_rag,
    }


def _disabled_features() -> dict[str, bool]:
    return {
        "cloud_backup": False,
        "document_intake": False,
        "managed_restore": False,
        "matter_rag": False,
    }


def _enabled_feature_names(license_result: LicenseValidationResult) -> set[str]:
    if license_result.license_document is None or license_result.status != ACTIVE_STATUS:
        return set()
    return {
        feature_name
        for feature_name, enabled in _features_to_mapping(
            license_result.license_document.features
        ).items()
        if enabled
    }


def _walk_mapping(value: object, *, prefix: str = "") -> tuple[tuple[str, object], ...]:
    items: list[tuple[str, object]] = []
    if isinstance(value, dict):
        for key, child in value.items():
            key_path = f"{prefix}.{key}" if prefix else str(key)
            items.append((key_path, child))
            items.extend(_walk_mapping(child, prefix=key_path))
    elif isinstance(value, list | tuple):
        for index, child in enumerate(value):
            items.extend(_walk_mapping(child, prefix=f"{prefix}[{index}]"))
    return tuple(items)


def _datetime_to_text(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _parse_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)
