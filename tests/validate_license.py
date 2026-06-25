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
    BAD_SIGNATURE_STATUS,
    DISABLED_STATUS,
    EXPIRED_STATUS,
    INSTALLATION_MISMATCH_STATUS,
    FeatureEntitlements,
    LicenseDocument,
    canonical_license_bytes,
    ensure_installation_identity,
    read_license_file,
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

    print("LICENSE VALIDATION PASS")


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
