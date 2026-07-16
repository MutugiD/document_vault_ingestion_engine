"""Enterprise admin, license sync, and payment entitlement boundary."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol

from licensing.core import LicenseValidationResult
from licensing.entitlements import (
    PaymentEntitlement,
    evaluate_payment_entitlements,
    load_payment_entitlement,
    write_payment_entitlement,
)
from licensing.sync import (
    ONLINE_FEATURES,
    EffectiveEntitlements,
    LicenseCheckInPayload,
    LicenseSyncResponse,
    LicenseSyncState,
    assert_payload_privacy,
    evaluate_effective_entitlements,
    load_license_sync_state,
    record_license_sync_success,
    write_license_sync_state,
)


class AdminBoundaryTransport(Protocol):
    """Transport callable for owner-backend check-ins."""

    def __call__(self, payload: dict[str, object]) -> dict[str, object]:
        """Send a privacy-safe check-in and return the backend response."""


@dataclass(frozen=True)
class AdminLicensePaymentResponse:
    """Owner-backend response containing admin sync and payment state."""

    license_sync: LicenseSyncResponse
    payment_entitlement: PaymentEntitlement

    @classmethod
    def from_mapping(cls, value: dict[str, Any]) -> AdminLicensePaymentResponse:
        _assert_admin_response_privacy(value)
        return cls(
            license_sync=LicenseSyncResponse.from_mapping(dict(value["license_sync"])),
            payment_entitlement=PaymentEntitlement.from_mapping(dict(value["payment_entitlement"])),
        )

    def to_mapping(self) -> dict[str, object]:
        payload = {
            "license_sync": self.license_sync.to_mapping(),
            "payment_entitlement": self.payment_entitlement.to_mapping(),
        }
        _assert_admin_response_privacy(payload)
        return payload


@dataclass(frozen=True)
class AdminBoundaryDecision:
    """Final local feature decision after license, admin, and payment checks."""

    installation_status: str
    paid_entitlement_state: str
    enabled_features: frozenset[str]
    paid_features_enabled: bool
    online_features_enabled: bool
    local_export_allowed: bool
    local_restore_allowed: bool
    cloud_backup_enabled: bool
    matter_rag_enabled: bool
    hosted_ai_enabled: bool
    reason: str = ""

    def to_mapping(self) -> dict[str, object]:
        return {
            "installation_status": self.installation_status,
            "paid_entitlement_state": self.paid_entitlement_state,
            "enabled_features": sorted(self.enabled_features),
            "paid_features_enabled": self.paid_features_enabled,
            "online_features_enabled": self.online_features_enabled,
            "local_export_allowed": self.local_export_allowed,
            "local_restore_allowed": self.local_restore_allowed,
            "cloud_backup_enabled": self.cloud_backup_enabled,
            "matter_rag_enabled": self.matter_rag_enabled,
            "hosted_ai_enabled": self.hosted_ai_enabled,
            "reason": self.reason,
        }


def sync_admin_license_payment_boundary(
    *,
    payload: LicenseCheckInPayload,
    transport: AdminBoundaryTransport,
    sync_state_path: Path,
    payment_state_path: Path,
) -> AdminLicensePaymentResponse:
    """Perform a privacy-safe owner-backend check-in and persist safe state."""

    outbound = payload.to_mapping()
    assert_payload_privacy(outbound)
    response = AdminLicensePaymentResponse.from_mapping(transport(outbound))
    sync_state = record_license_sync_success(response.license_sync)
    write_license_sync_state(sync_state_path, sync_state)
    write_payment_entitlement(payment_state_path, response.payment_entitlement)
    return response


def load_admin_license_payment_state(
    *,
    sync_state_path: Path,
    payment_state_path: Path,
) -> tuple[LicenseSyncState | None, PaymentEntitlement | None]:
    """Load last-known safe admin and payment state from local disk."""

    return (
        load_license_sync_state(sync_state_path),
        load_payment_entitlement(payment_state_path),
    )


def evaluate_admin_license_payment_boundary(
    license_result: LicenseValidationResult,
    *,
    sync_state: LicenseSyncState | None,
    payment_entitlement: PaymentEntitlement | None,
    as_of: datetime | None = None,
) -> AdminBoundaryDecision:
    """Combine offline license, admin sync, and payment state into one decision."""

    sync_effective = evaluate_effective_entitlements(
        license_result,
        sync_state=sync_state,
        as_of=as_of,
    )
    if payment_entitlement is None:
        return _decision_from_effective(
            sync_effective,
            payment_state=sync_effective.paid_entitlement_state,
            enabled_features=frozenset(),
            paid_features_enabled=False,
            online_features_enabled=False,
            reason="no payment entitlement has been recorded",
        )

    payment_effective = evaluate_payment_entitlements(license_result, payment_entitlement)
    final_features = frozenset(
        sync_effective.enabled_features.intersection(payment_effective.enabled_features)
    )
    paid_enabled = sync_effective.paid_features_enabled and payment_effective.paid_features_enabled
    online_enabled = (
        paid_enabled
        and sync_effective.online_features_enabled
        and payment_effective.online_features_enabled
        and bool(final_features.intersection(ONLINE_FEATURES))
    )
    reason = "; ".join(
        reason for reason in (sync_effective.reason, payment_effective.reason) if reason
    )
    return AdminBoundaryDecision(
        installation_status=sync_effective.status,
        paid_entitlement_state=payment_effective.paid_entitlement_state,
        enabled_features=final_features if paid_enabled else frozenset(),
        paid_features_enabled=paid_enabled,
        online_features_enabled=online_enabled,
        local_export_allowed=(
            sync_effective.allows_local_data_access and payment_effective.allows_local_data_access
        ),
        local_restore_allowed=(
            sync_effective.allows_local_data_access and payment_effective.allows_local_data_access
        ),
        cloud_backup_enabled=online_enabled and "cloud_backup" in final_features,
        matter_rag_enabled=paid_enabled and "matter_rag" in final_features,
        hosted_ai_enabled=online_enabled and "hosted_ai" in final_features,
        reason=reason,
    )


def _decision_from_effective(
    effective: EffectiveEntitlements,
    *,
    payment_state: str,
    enabled_features: frozenset[str],
    paid_features_enabled: bool,
    online_features_enabled: bool,
    reason: str,
) -> AdminBoundaryDecision:
    return AdminBoundaryDecision(
        installation_status=effective.status,
        paid_entitlement_state=payment_state,
        enabled_features=enabled_features,
        paid_features_enabled=paid_features_enabled,
        online_features_enabled=online_features_enabled,
        local_export_allowed=effective.allows_local_data_access,
        local_restore_allowed=effective.allows_local_data_access,
        cloud_backup_enabled=False,
        matter_rag_enabled=False,
        hosted_ai_enabled=False,
        reason=reason,
    )


def _assert_admin_response_privacy(payload: dict[str, object]) -> None:
    assert_payload_privacy(json.loads(json.dumps(payload, default=str)))
