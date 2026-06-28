"""Admin/license/payment boundary E2E runner with redacted output."""

from __future__ import annotations

import base64
import json
import tempfile
from datetime import UTC, date, datetime
from pathlib import Path

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from licensing import (
    ACTIVE_STATUS,
    BAD_SIGNATURE_STATUS,
    PAID_ACTIVE_STATE,
    PAID_SUSPENDED_STATE,
    PAYMENT_ACTIVE_STATUS,
    PAYMENT_EXPIRED_STATUS,
    PAYMENT_SUSPENDED_STATUS,
    SYNC_ACTIVE_STATUS,
    SYNC_DISABLED_STATUS,
    AdminLicensePaymentResponse,
    BackupHealth,
    FeatureEntitlements,
    LicenseDocument,
    LicenseSyncError,
    LicenseSyncResponse,
    LicenseValidationResult,
    PaymentEntitlement,
    PaymentEntitlementError,
    build_license_check_in_payload,
    canonical_license_bytes,
    ensure_installation_identity,
    evaluate_admin_license_payment_boundary,
    load_admin_license_payment_state,
    sync_admin_license_payment_boundary,
    sync_grace_expiry,
    verify_license_document,
)


def run_admin_license_payment_e2e(workspace: Path | None = None) -> dict[str, object]:
    """Validate the commercial admin/payment boundary without document data."""

    if workspace is None:
        with tempfile.TemporaryDirectory(prefix="dv-admin-license-payment-") as temporary_dir:
            return run_admin_license_payment_e2e(Path(temporary_dir))

    workspace.mkdir(parents=True, exist_ok=True)
    generated_at = datetime(2026, 6, 28, 9, 30, tzinfo=UTC)
    sync_state_path = workspace / "settings" / "license-sync.json"
    payment_state_path = workspace / "settings" / "payment-entitlement.json"
    identity = ensure_installation_identity(workspace / "settings" / "installation.json")
    public_key_pem, license_document = _signed_license(identity.installation_id)
    license_result = verify_license_document(
        license_document,
        public_key_pem,
        identity.installation_id,
        as_of=date(2026, 6, 28),
    )
    if license_result.status != ACTIVE_STATUS:
        raise AssertionError(f"unexpected license status: {license_result.status}")

    payload = build_license_check_in_payload(
        installation_id=identity.installation_id,
        app_version="0.1.0",
        device_nickname="Nairobi Windows Workstation",
        license_result=license_result,
        backup_health=BackupHealth(status="healthy", last_success_age_hours=3),
        generated_at=generated_at,
    )
    outbound_payload = payload.to_mapping()
    _assert_no_forbidden_material(outbound_payload)

    active_response = sync_admin_license_payment_boundary(
        payload=payload,
        transport=_fixed_transport(_active_backend_response(generated_at)),
        sync_state_path=sync_state_path,
        payment_state_path=payment_state_path,
    )
    sync_state, payment_state = load_admin_license_payment_state(
        sync_state_path=sync_state_path,
        payment_state_path=payment_state_path,
    )
    active_decision = evaluate_admin_license_payment_boundary(
        license_result,
        sync_state=sync_state,
        payment_entitlement=payment_state,
        as_of=generated_at,
    )
    assert active_decision.paid_features_enabled
    assert active_decision.cloud_backup_enabled
    assert active_decision.matter_rag_enabled
    assert not active_decision.hosted_ai_enabled
    assert active_decision.local_export_allowed
    assert active_decision.local_restore_allowed

    disabled_decision = _decision_for_response(
        license_result,
        _disabled_backend_response(generated_at),
        generated_at,
    )
    assert not disabled_decision.paid_features_enabled
    assert not disabled_decision.cloud_backup_enabled
    assert not disabled_decision.matter_rag_enabled
    assert disabled_decision.local_export_allowed
    assert disabled_decision.local_restore_allowed

    suspended_payment_decision = _decision_for_response(
        license_result,
        _payment_backend_response(generated_at, PAYMENT_SUSPENDED_STATUS),
        generated_at,
    )
    assert suspended_payment_decision.paid_entitlement_state == PAYMENT_SUSPENDED_STATUS
    assert not suspended_payment_decision.paid_features_enabled
    assert suspended_payment_decision.local_restore_allowed

    expired_payment_decision = _decision_for_response(
        license_result,
        _payment_backend_response(generated_at, PAYMENT_EXPIRED_STATUS),
        generated_at,
    )
    assert expired_payment_decision.paid_entitlement_state == PAYMENT_EXPIRED_STATUS
    assert not expired_payment_decision.paid_features_enabled
    assert expired_payment_decision.local_export_allowed

    missing_payment_decision = evaluate_admin_license_payment_boundary(
        license_result,
        sync_state=sync_state,
        payment_entitlement=None,
        as_of=generated_at,
    )
    assert not missing_payment_decision.paid_features_enabled
    assert missing_payment_decision.local_restore_allowed

    tampered_decision = evaluate_admin_license_payment_boundary(
        LicenseValidationResult(BAD_SIGNATURE_STATUS, reason="tampered"),
        sync_state=sync_state,
        payment_entitlement=payment_state,
        as_of=generated_at,
    )
    assert not tampered_decision.local_export_allowed
    assert not tampered_decision.local_restore_allowed

    _assert_privacy_rejections(generated_at)

    report = {
        "payload_fields": sorted(outbound_payload),
        "active_response_fields": sorted(active_response.to_mapping()),
        "active_decision": active_decision.to_mapping(),
        "disabled_decision": disabled_decision.to_mapping(),
        "suspended_payment_decision": suspended_payment_decision.to_mapping(),
        "expired_payment_decision": expired_payment_decision.to_mapping(),
        "missing_payment_paid_features_enabled": missing_payment_decision.paid_features_enabled,
        "tampered_license_local_export_allowed": tampered_decision.local_export_allowed,
        "privacy_rejections_verified": True,
    }
    _assert_no_forbidden_material(report)
    return report


def _decision_for_response(
    license_result: LicenseValidationResult,
    response_mapping: dict[str, object],
    as_of: datetime,
):
    response = AdminLicensePaymentResponse.from_mapping(response_mapping)
    return evaluate_admin_license_payment_boundary(
        license_result,
        sync_state=_state_from_response(response.license_sync),
        payment_entitlement=response.payment_entitlement,
        as_of=as_of,
    )


def _state_from_response(response: LicenseSyncResponse):
    from licensing import record_license_sync_success

    return record_license_sync_success(response)


def _fixed_transport(response: dict[str, object]):
    def transport(payload: dict[str, object]) -> dict[str, object]:
        _assert_no_forbidden_material(payload)
        return response

    return transport


def _active_backend_response(server_time: datetime) -> dict[str, object]:
    return {
        "license_sync": {
            "installation_status": SYNC_ACTIVE_STATUS,
            "paid_entitlement_state": PAID_ACTIVE_STATE,
            "enabled_features": ["document_intake", "cloud_backup", "matter_rag"],
            "server_time": _datetime_to_text(server_time),
            "grace_expires_at": _datetime_to_text(sync_grace_expiry(server_time)),
            "reason": "",
        },
        "payment_entitlement": {
            "plan": "solo",
            "status": PAYMENT_ACTIVE_STATUS,
            "enabled_features": ["document_intake", "cloud_backup", "matter_rag"],
            "admin_override": "none",
            "reason": "",
            "synced_at": _datetime_to_text(server_time),
        },
    }


def _disabled_backend_response(server_time: datetime) -> dict[str, object]:
    return {
        "license_sync": {
            "installation_status": SYNC_DISABLED_STATUS,
            "paid_entitlement_state": PAID_SUSPENDED_STATE,
            "enabled_features": [],
            "server_time": _datetime_to_text(server_time),
            "grace_expires_at": _datetime_to_text(sync_grace_expiry(server_time)),
            "reason": "installation disabled by admin",
        },
        "payment_entitlement": {
            "plan": "solo",
            "status": PAYMENT_ACTIVE_STATUS,
            "enabled_features": ["document_intake", "cloud_backup", "matter_rag"],
            "admin_override": "none",
            "reason": "",
            "synced_at": _datetime_to_text(server_time),
        },
    }


def _payment_backend_response(server_time: datetime, status: str) -> dict[str, object]:
    return {
        "license_sync": {
            "installation_status": SYNC_ACTIVE_STATUS,
            "paid_entitlement_state": status,
            "enabled_features": ["document_intake", "cloud_backup", "matter_rag"],
            "server_time": _datetime_to_text(server_time),
            "grace_expires_at": _datetime_to_text(sync_grace_expiry(server_time)),
            "reason": "",
        },
        "payment_entitlement": {
            "plan": "solo",
            "status": status,
            "enabled_features": ["document_intake", "cloud_backup", "matter_rag"],
            "admin_override": "none",
            "reason": f"payment {status}",
            "synced_at": _datetime_to_text(server_time),
        },
    }


def _assert_privacy_rejections(server_time: datetime) -> None:
    unsafe_response = _active_backend_response(server_time)
    unsafe_response["license_sync"]["client_name"] = "not allowed"  # type: ignore[index]
    try:
        AdminLicensePaymentResponse.from_mapping(unsafe_response)
    except LicenseSyncError:
        pass
    else:
        raise AssertionError("admin response accepted client data")

    unsafe_payment = {
        "plan": "solo",
        "status": PAYMENT_ACTIVE_STATUS,
        "enabled_features": ["document_intake"],
        "client_name": "not allowed",
    }
    try:
        PaymentEntitlement.from_mapping(unsafe_payment).to_mapping()
    except PaymentEntitlementError:
        pass
    else:
        raise AssertionError("payment entitlement accepted client data")


def _assert_no_forbidden_material(payload: dict[str, object]) -> None:
    serialized = json.dumps(payload, sort_keys=True).lower()
    for forbidden in (
        "client_name",
        "matter_name",
        "case_number",
        "filename",
        "ocr_text",
        "prompt",
        "sha256",
        "recovery",
        "api_key",
        "secret",
    ):
        if forbidden in serialized:
            raise AssertionError(f"forbidden admin/payment payload material: {forbidden}")


def _signed_license(installation_id: str) -> tuple[bytes, LicenseDocument]:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    unsigned_document = LicenseDocument(
        installation_id=installation_id,
        license_id="LIC-ADMIN-PAYMENT-E2E",
        firm_display_name="Admin Payment Advocates",
        plan="solo",
        features=FeatureEntitlements(
            document_intake=True,
            cloud_backup=True,
            managed_restore=False,
            matter_rag=True,
        ),
        expiry=date(2099, 12, 31),
        issued_at=datetime(2026, 6, 28, 8, 0, tzinfo=UTC),
        signature="",
    )
    signature = private_key.sign(
        canonical_license_bytes(unsigned_document),
        padding.PSS(
            mgf=padding.MGF1(hashes.SHA256()),
            salt_length=padding.PSS.MAX_LENGTH,
        ),
        hashes.SHA256(),
    )
    return public_key_pem, LicenseDocument(
        installation_id=unsigned_document.installation_id,
        license_id=unsigned_document.license_id,
        firm_display_name=unsigned_document.firm_display_name,
        plan=unsigned_document.plan,
        features=unsigned_document.features,
        expiry=unsigned_document.expiry,
        issued_at=unsigned_document.issued_at,
        signature=base64.b64encode(signature).decode("ascii"),
    )


def _datetime_to_text(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


if __name__ == "__main__":
    print(json.dumps(run_admin_license_payment_e2e(), indent=2, sort_keys=True))
