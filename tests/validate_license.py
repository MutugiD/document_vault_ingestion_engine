"""Validate F1 offline licensing behavior."""

from __future__ import annotations

import base64
import sys
import tempfile
from datetime import UTC, date, datetime
from pathlib import Path

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from licensing import (  # noqa: E402
    ACTIVE_STATUS,
    ADMIN_OVERRIDE_FORCE_DISABLED,
    ADMIN_OVERRIDE_FORCE_ENABLED,
    BAD_SIGNATURE_STATUS,
    DISABLED_STATUS,
    EXPIRED_STATUS,
    INSTALLATION_MISMATCH_STATUS,
    PAID_ACTIVE_STATE,
    PAID_DISABLED_STATE,
    PAID_SUSPENDED_STATE,
    PAYMENT_ACTIVE_STATUS,
    PAYMENT_EXPIRED_STATUS,
    PAYMENT_SUSPENDED_STATUS,
    SYNC_ACTIVE_STATUS,
    SYNC_DISABLED_STATUS,
    SYNC_GRACE_EXPIRED_STATUS,
    BackupHealth,
    FeatureEntitlements,
    LicenseDocument,
    LicenseSyncError,
    LicenseSyncResponse,
    LicenseValidationResult,
    PaymentEntitlement,
    PaymentEntitlementError,
    assert_payload_privacy,
    assert_payment_entitlement_privacy,
    build_license_check_in_payload,
    canonical_license_bytes,
    ensure_installation_identity,
    evaluate_effective_entitlements,
    evaluate_payment_entitlements,
    read_license_file,
    record_license_sync_success,
    sync_grace_expiry,
    verify_license_document,
    write_license_file,
)

VALIDATION_DATE = date(2026, 6, 25)


def main() -> None:
    with tempfile.TemporaryDirectory() as temporary_dir:
        workspace = Path(temporary_dir)
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        public_key_pem = private_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )

        identity_path = workspace / "settings" / "installation.json"
        identity = ensure_installation_identity(identity_path)
        persisted_identity = ensure_installation_identity(identity_path)
        assert persisted_identity.installation_id == identity.installation_id

        active_license = _signed_license(
            private_key=private_key,
            installation_id=identity.installation_id,
            expiry=date(2099, 12, 31),
        )

        license_path = workspace / "license.json"
        write_license_file(license_path, active_license)
        loaded_license = read_license_file(license_path)

        active_result = verify_license_document(
            loaded_license,
            public_key_pem,
            identity.installation_id,
            as_of=VALIDATION_DATE,
        )
        assert active_result.status == ACTIVE_STATUS
        assert active_result.is_active
        assert active_result.allows_local_data_access
        assert active_result.paid_features_enabled
        assert active_result.feature_enabled("document_intake")
        assert active_result.feature_enabled("cloud_backup")
        assert active_result.feature_enabled("matter_rag")
        assert not active_result.feature_enabled("managed_restore")

        tampered_license = LicenseDocument(
            installation_id=loaded_license.installation_id,
            license_id=loaded_license.license_id,
            firm_display_name="Tampered Advocates",
            plan=loaded_license.plan,
            features=loaded_license.features,
            expiry=loaded_license.expiry,
            issued_at=loaded_license.issued_at,
            signature=loaded_license.signature,
        )
        tampered_result = verify_license_document(
            tampered_license,
            public_key_pem,
            identity.installation_id,
            as_of=VALIDATION_DATE,
        )
        assert tampered_result.status == BAD_SIGNATURE_STATUS
        assert not tampered_result.allows_local_data_access

        mismatch_result = verify_license_document(
            active_license,
            public_key_pem,
            "different-installation-id",
            as_of=VALIDATION_DATE,
        )
        assert mismatch_result.status == INSTALLATION_MISMATCH_STATUS
        assert not mismatch_result.paid_features_enabled

        expired_license = _signed_license(
            private_key=private_key,
            installation_id=identity.installation_id,
            expiry=date(2020, 1, 1),
        )
        expired_result = verify_license_document(
            expired_license,
            public_key_pem,
            identity.installation_id,
            as_of=VALIDATION_DATE,
        )
        assert expired_result.status == EXPIRED_STATUS
        assert expired_result.allows_local_data_access
        assert not expired_result.paid_features_enabled
        assert not expired_result.feature_enabled("cloud_backup")

        disabled_result = verify_license_document(
            active_license,
            public_key_pem,
            identity.installation_id,
            as_of=VALIDATION_DATE,
            disabled=True,
        )
        assert disabled_result.status == DISABLED_STATUS
        assert disabled_result.allows_local_data_access
        assert not disabled_result.paid_features_enabled
        assert not disabled_result.feature_enabled("cloud_backup")

        _validate_admin_license_sync_boundary(
            identity.installation_id,
            active_result,
        )
        _validate_payment_entitlements(active_result)

    print("LICENSE VALIDATION PASS")


def _validate_admin_license_sync_boundary(
    installation_id: str,
    active_result: LicenseValidationResult,
) -> None:
    generated_at = datetime(2026, 6, 25, 12, 0, tzinfo=UTC)
    payload = build_license_check_in_payload(
        installation_id=installation_id,
        app_version="0.1.0",
        device_nickname="Nairobi Office Laptop",
        license_result=active_result,
        backup_health=BackupHealth(
            status="healthy",
            last_success_age_hours=2,
            pending_upload_count=0,
        ),
        generated_at=generated_at,
    )
    mapping = payload.to_mapping()
    assert set(mapping) == {
        "schema_version",
        "installation_id",
        "license_id",
        "app_version",
        "device_nickname",
        "license_status",
        "paid_entitlement_state",
        "feature_flags",
        "coarse_backup_health",
        "generated_at",
    }
    serialized = str(mapping).lower()
    for forbidden in (
        "matter_name",
        "client_name",
        "case_number",
        "filename",
        "ocr_text",
        "prompt",
        "sha256",
        "recovery",
    ):
        assert forbidden not in serialized

    try:
        assert_payload_privacy({"client_name": "not allowed"})
    except LicenseSyncError:
        pass
    else:
        raise AssertionError("client data was allowed in license check-in payload")

    active_sync = LicenseSyncResponse(
        installation_status=SYNC_ACTIVE_STATUS,
        paid_entitlement_state=PAID_ACTIVE_STATE,
        enabled_features=frozenset({"document_intake", "cloud_backup"}),
        server_time=generated_at,
        grace_expires_at=sync_grace_expiry(generated_at),
    )
    sync_state = record_license_sync_success(active_sync)
    effective = evaluate_effective_entitlements(
        active_result,
        sync_state=sync_state,
        as_of=generated_at,
    )
    assert effective.status == SYNC_ACTIVE_STATUS
    assert effective.paid_features_enabled
    assert effective.online_feature_enabled("cloud_backup")
    assert not effective.feature_enabled("matter_rag")
    assert effective.allows_local_data_access

    disabled_sync = record_license_sync_success(
        LicenseSyncResponse(
            installation_status=SYNC_DISABLED_STATUS,
            paid_entitlement_state=PAID_SUSPENDED_STATE,
            enabled_features=frozenset(),
            server_time=generated_at,
            grace_expires_at=sync_grace_expiry(generated_at),
            reason="disabled by admin",
        )
    )
    disabled_effective = evaluate_effective_entitlements(
        active_result,
        sync_state=disabled_sync,
        as_of=generated_at,
    )
    assert disabled_effective.status == SYNC_DISABLED_STATUS
    assert disabled_effective.allows_local_data_access
    assert not disabled_effective.paid_features_enabled
    assert not disabled_effective.online_features_enabled
    assert not disabled_effective.feature_enabled("document_intake")

    expired_grace_effective = evaluate_effective_entitlements(
        active_result,
        sync_state=sync_state,
        as_of=generated_at.replace(year=2026, month=7, day=25),
    )
    assert expired_grace_effective.status == SYNC_GRACE_EXPIRED_STATUS
    assert expired_grace_effective.allows_local_data_access
    assert not expired_grace_effective.paid_features_enabled
    assert not expired_grace_effective.online_features_enabled

    no_local_data_effective = evaluate_effective_entitlements(
        LicenseValidationResult(BAD_SIGNATURE_STATUS, reason="tampered"),
        sync_state=sync_state,
        as_of=generated_at,
    )
    assert no_local_data_effective.paid_entitlement_state == PAID_DISABLED_STATE
    assert not no_local_data_effective.allows_local_data_access


def _validate_payment_entitlements(active_result: LicenseValidationResult) -> None:
    active_entitlement = PaymentEntitlement(
        plan="solo",
        status=PAYMENT_ACTIVE_STATUS,
        enabled_features=frozenset({"document_intake", "cloud_backup", "matter_rag"}),
        synced_at=datetime(2026, 6, 25, 12, 30, tzinfo=UTC),
    )
    active_effective = evaluate_payment_entitlements(active_result, active_entitlement)
    assert active_effective.paid_features_enabled
    assert active_effective.feature_enabled("document_intake")
    assert active_effective.feature_enabled("cloud_backup")
    assert active_effective.feature_enabled("matter_rag")
    assert not active_effective.feature_enabled("managed_restore")
    assert active_effective.allows_local_data_access

    suspended_effective = evaluate_payment_entitlements(
        active_result,
        PaymentEntitlement(
            plan="solo",
            status=PAYMENT_SUSPENDED_STATUS,
            enabled_features=frozenset({"document_intake", "cloud_backup", "matter_rag"}),
            reason="payment failed",
        ),
    )
    assert suspended_effective.status == PAYMENT_SUSPENDED_STATUS
    assert suspended_effective.allows_local_data_access
    assert not suspended_effective.paid_features_enabled
    assert not suspended_effective.online_feature_enabled("cloud_backup")
    assert not suspended_effective.feature_enabled("matter_rag")

    expired_effective = evaluate_payment_entitlements(
        active_result,
        PaymentEntitlement(
            plan="firm",
            status=PAYMENT_EXPIRED_STATUS,
            enabled_features=frozenset({"document_intake", "cloud_backup", "matter_rag"}),
        ),
    )
    assert expired_effective.allows_local_data_access
    assert not expired_effective.paid_features_enabled

    admin_disabled_effective = evaluate_payment_entitlements(
        active_result,
        PaymentEntitlement(
            plan="firm",
            status=PAYMENT_ACTIVE_STATUS,
            enabled_features=frozenset({"document_intake", "cloud_backup", "matter_rag"}),
            admin_override=ADMIN_OVERRIDE_FORCE_DISABLED,
            reason="manual admin block",
        ),
    )
    assert admin_disabled_effective.allows_local_data_access
    assert not admin_disabled_effective.paid_features_enabled
    assert not admin_disabled_effective.feature_enabled("matter_rag")

    admin_enabled_effective = evaluate_payment_entitlements(
        active_result,
        PaymentEntitlement(
            plan="solo",
            status=PAYMENT_SUSPENDED_STATUS,
            enabled_features=frozenset(),
            admin_override=ADMIN_OVERRIDE_FORCE_ENABLED,
            reason="temporary support override",
        ),
    )
    assert admin_enabled_effective.allows_local_data_access
    assert admin_enabled_effective.paid_features_enabled
    assert admin_enabled_effective.feature_enabled("cloud_backup")

    try:
        assert_payment_entitlement_privacy({"client_name": "not allowed"})
    except PaymentEntitlementError:
        pass
    else:
        raise AssertionError("client data was allowed in payment entitlement payload")


def _signed_license(
    *,
    private_key: rsa.RSAPrivateKey,
    installation_id: str,
    expiry: date,
) -> LicenseDocument:
    unsigned_document = LicenseDocument(
        installation_id=installation_id,
        license_id="LIC-F1-TEST",
        firm_display_name="Example Advocates LLP",
        plan="solo",
        features=FeatureEntitlements(
            document_intake=True,
            cloud_backup=True,
            matter_rag=True,
            managed_restore=False,
        ),
        expiry=expiry,
        issued_at=datetime(2026, 6, 25, 9, 0, tzinfo=UTC),
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
    return LicenseDocument(
        installation_id=unsigned_document.installation_id,
        license_id=unsigned_document.license_id,
        firm_display_name=unsigned_document.firm_display_name,
        plan=unsigned_document.plan,
        features=unsigned_document.features,
        expiry=unsigned_document.expiry,
        issued_at=unsigned_document.issued_at,
        signature=base64.b64encode(signature).decode("ascii"),
    )


if __name__ == "__main__":
    main()
