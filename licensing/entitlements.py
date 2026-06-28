"""Payment plan and entitlement decisions."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from licensing.core import ACTIVE_STATUS, LicenseValidationResult
from licensing.sync import ONLINE_FEATURES, EffectiveEntitlements

PAYMENT_ACTIVE_STATUS = "active"
PAYMENT_SUSPENDED_STATUS = "suspended"
PAYMENT_EXPIRED_STATUS = "expired"
PAYMENT_DISABLED_STATUS = "disabled"

ADMIN_OVERRIDE_NONE = "none"
ADMIN_OVERRIDE_FORCE_ENABLED = "force_enabled"
ADMIN_OVERRIDE_FORCE_DISABLED = "force_disabled"

PLAN_FEATURES: dict[str, frozenset[str]] = {
    "trial": frozenset({"document_intake"}),
    "solo": frozenset({"document_intake", "cloud_backup", "matter_rag"}),
    "firm": frozenset({"document_intake", "cloud_backup", "managed_restore", "matter_rag"}),
}


class PaymentEntitlementError(Exception):
    """Raised when a payment entitlement payload is unsafe or unsupported."""


@dataclass(frozen=True)
class PaymentEntitlement:
    """Payment state returned by the owner backend without document data."""

    plan: str
    status: str
    enabled_features: frozenset[str]
    admin_override: str = ADMIN_OVERRIDE_NONE
    reason: str = ""
    synced_at: datetime | None = None

    @classmethod
    def from_mapping(cls, value: dict[str, Any]) -> PaymentEntitlement:
        assert_payment_entitlement_privacy(value)
        return cls(
            plan=str(value["plan"]),
            status=str(value["status"]),
            enabled_features=frozenset(str(item) for item in value.get("enabled_features", [])),
            admin_override=str(value.get("admin_override", ADMIN_OVERRIDE_NONE)),
            reason=str(value.get("reason", "")),
            synced_at=(
                _parse_datetime(str(value["synced_at"])) if value.get("synced_at") else None
            ),
        )

    def to_mapping(self) -> dict[str, object]:
        payload = {
            "plan": self.plan,
            "status": self.status,
            "enabled_features": sorted(self.enabled_features),
            "admin_override": self.admin_override,
            "reason": self.reason,
            "synced_at": _datetime_to_text(self.synced_at) if self.synced_at else None,
        }
        assert_payment_entitlement_privacy(payload)
        return payload


def evaluate_payment_entitlements(
    license_result: LicenseValidationResult,
    entitlement: PaymentEntitlement,
) -> EffectiveEntitlements:
    """Apply payment/admin entitlement state to a valid offline license."""

    _validate_entitlement(entitlement)
    if not license_result.allows_local_data_access:
        return EffectiveEntitlements(
            status=license_result.status,
            paid_entitlement_state=PAYMENT_DISABLED_STATUS,
            enabled_features=frozenset(),
            paid_features_enabled=False,
            online_features_enabled=False,
            allows_local_data_access=False,
            reason=license_result.reason,
        )

    if license_result.license_document is None or license_result.status != ACTIVE_STATUS:
        return EffectiveEntitlements(
            status=license_result.status,
            paid_entitlement_state=PAYMENT_DISABLED_STATUS,
            enabled_features=frozenset(),
            paid_features_enabled=False,
            online_features_enabled=False,
            allows_local_data_access=True,
            reason=license_result.reason,
        )

    local_features = _enabled_license_features(license_result)
    plan_features = PLAN_FEATURES[entitlement.plan]
    enabled_features = frozenset(
        local_features.intersection(plan_features).intersection(entitlement.enabled_features)
    )

    if entitlement.admin_override == ADMIN_OVERRIDE_FORCE_DISABLED:
        return _disabled_decision(
            status=PAYMENT_DISABLED_STATUS,
            entitlement=entitlement,
            reason=entitlement.reason or "disabled by admin override",
        )

    if entitlement.admin_override == ADMIN_OVERRIDE_FORCE_ENABLED:
        override_features = frozenset(local_features.intersection(plan_features))
        return EffectiveEntitlements(
            status=PAYMENT_ACTIVE_STATUS,
            paid_entitlement_state=PAYMENT_ACTIVE_STATUS,
            enabled_features=override_features,
            paid_features_enabled=True,
            online_features_enabled=bool(override_features.intersection(ONLINE_FEATURES)),
            allows_local_data_access=True,
            reason=entitlement.reason,
        )

    if entitlement.status != PAYMENT_ACTIVE_STATUS:
        return _disabled_decision(
            status=entitlement.status,
            entitlement=entitlement,
            reason=entitlement.reason or f"payment entitlement is {entitlement.status}",
        )

    return EffectiveEntitlements(
        status=PAYMENT_ACTIVE_STATUS,
        paid_entitlement_state=PAYMENT_ACTIVE_STATUS,
        enabled_features=enabled_features,
        paid_features_enabled=True,
        online_features_enabled=bool(enabled_features.intersection(ONLINE_FEATURES)),
        allows_local_data_access=True,
        reason=entitlement.reason,
    )


def plan_features(plan: str) -> frozenset[str]:
    try:
        return PLAN_FEATURES[plan]
    except KeyError as exc:
        raise PaymentEntitlementError(f"unknown payment plan: {plan}") from exc


def load_payment_entitlement(path: Path) -> PaymentEntitlement | None:
    if not path.exists():
        return None
    return PaymentEntitlement.from_mapping(json.loads(path.read_text(encoding="utf-8")))


def write_payment_entitlement(path: Path, entitlement: PaymentEntitlement) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(entitlement.to_mapping(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def assert_payment_entitlement_privacy(payload: dict[str, object]) -> None:
    forbidden_markers = (
        "matter",
        "client",
        "case",
        "filename",
        "ocr",
        "prompt",
        "hash",
        "recovery",
        "credential",
    )
    for key_path, _value in _walk_mapping(payload):
        lowered = key_path.lower()
        if any(marker in lowered for marker in forbidden_markers):
            raise PaymentEntitlementError(f"forbidden entitlement field: {key_path}")


def _disabled_decision(
    *,
    status: str,
    entitlement: PaymentEntitlement,
    reason: str,
) -> EffectiveEntitlements:
    return EffectiveEntitlements(
        status=status,
        paid_entitlement_state=entitlement.status,
        enabled_features=frozenset(),
        paid_features_enabled=False,
        online_features_enabled=False,
        allows_local_data_access=True,
        reason=reason,
    )


def _enabled_license_features(license_result: LicenseValidationResult) -> set[str]:
    if license_result.license_document is None:
        return set()
    features = license_result.license_document.features
    return {
        "cloud_backup" if features.cloud_backup else "",
        "document_intake" if features.document_intake else "",
        "managed_restore" if features.managed_restore else "",
        "matter_rag" if features.matter_rag else "",
    } - {""}


def _validate_entitlement(entitlement: PaymentEntitlement) -> None:
    if entitlement.plan not in PLAN_FEATURES:
        raise PaymentEntitlementError(f"unknown payment plan: {entitlement.plan}")
    if entitlement.status not in {
        PAYMENT_ACTIVE_STATUS,
        PAYMENT_SUSPENDED_STATUS,
        PAYMENT_EXPIRED_STATUS,
        PAYMENT_DISABLED_STATUS,
    }:
        raise PaymentEntitlementError(f"unknown payment status: {entitlement.status}")
    if entitlement.admin_override not in {
        ADMIN_OVERRIDE_NONE,
        ADMIN_OVERRIDE_FORCE_ENABLED,
        ADMIN_OVERRIDE_FORCE_DISABLED,
    }:
        raise PaymentEntitlementError(f"unknown admin override: {entitlement.admin_override}")
    unknown_features = entitlement.enabled_features - PLAN_FEATURES["firm"]
    if unknown_features:
        raise PaymentEntitlementError(f"unknown entitlement features: {sorted(unknown_features)}")


def _datetime_to_text(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _parse_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


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
