"""Offline license validation and feature gate decisions.

License = JSON {installation_id, license_id, firm_display_name, plan, features, expiry, issued_at, signature}.
The signature is over a CANONICAL serialization (sorted keys, no whitespace) using PSS + SHA-256
with the vendor's RSA private key. The public key is HARD-CODED below (spec §6.2), not read from
a swappable file. In a release build this module is Cython-compiled to licensing/core.pyd
(scripts/obfuscate_licensing.py), so the key lives in native machine code. This closes the
key-substitution bypass — an attacker can no longer replace a loose public_key.pem on disk to
self-sign licenses; forging one still requires the vendor private key.
"""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey

# Spec §6.2: the RSA public key is HARD-CODED here, not read from a swappable file.
# In a release build this module is Cython-compiled to licensing/core.pyd, so the key lives
# in native machine code. This closes the key-substitution bypass.
_PUBLIC_KEY_PEM = b"""-----BEGIN PUBLIC KEY-----
MIICIjANBgkqhkiG9w0BAQEFAAOCAg8AMIICCgKCAgEAstGureWyW6PRLX8sWJWu
jalNZbWl7J8vbvAo1bkIQBo4PnEHV2LjFHt/SvnD6aknIjA22v/4nNtJsUIJ5+SA
xWcHSilw0OrWNKXTwYXsRS78mGVpV9AC74uYjuzU+CNT/T4IrILcQZJsvazoyywc
4xxaJ0cUbQr9f0s+nbrGKENx9Jw1n2kKhfthLxtaFHtA1SjBG3oP4Nq6EP+XrPKe
/RFYJknIRezAwsUvZkGsecDXVR2V/hh/zHclaCN+FwoOksb5+9L7g2Ljy/bvRsPw
tNxvLKBgZwApR6cramhmjVHd4lmfsZzMpKITZlm05XulRE7V3tBtEjXq7ZpKw4G4
nldUhOh+aSXOnDtMC9Q6+qT7fLbvNh7eP5RzFAGFgB2PsoOmuTNP4RJd/hQtrRRC
x/DHd6DD4gr/gWivio8jNG4WdcbPufIFlqpAM/0eCaOVMwYPJBPqZm22lZhMO1vY
Xvo8eHT0oXSVimzQQ3VxlfwmsBY8RMUhzdGKnzjapbD33/ztflNwSDR19qGiP+Z5
Fe8eXJh7vS18an79THRxt/h37udbTtMtqbmhHf52WLthFhbYLDwYidFPYQjQ1u0Y
AC61un38pE/JCn3Hc9OvkzlOc2MUQiEZ5mld24RtD9LhtIfpq5wL/qO7l5iOGi2A
JjF70s+9STGxwS3ghFsv8z0CAwEAAQ==
-----END PUBLIC KEY-----
"""

ACTIVE_STATUS = "active"
DISABLED_STATUS = "disabled"
EXPIRED_STATUS = "expired"
BAD_SIGNATURE_STATUS = "bad_signature"
INSTALLATION_MISMATCH_STATUS = "installation_mismatch"
MALFORMED_STATUS = "malformed"


@dataclass(frozen=True)
class FeatureEntitlements:
    """Paid feature switches carried by a signed license."""

    document_intake: bool
    cloud_backup: bool
    managed_restore: bool
    matter_rag: bool = False
    hosted_ai: bool = False

    @classmethod
    def from_mapping(cls, value: dict[str, Any]) -> FeatureEntitlements:
        return cls(
            document_intake=bool(value.get("document_intake", False)),
            cloud_backup=bool(value.get("cloud_backup", False)),
            managed_restore=bool(value.get("managed_restore", False)),
            matter_rag=bool(value.get("matter_rag", False)),
            hosted_ai=bool(value.get("hosted_ai", False)),
        )

    def enabled(self, feature_name: str) -> bool:
        return bool(getattr(self, feature_name, False))


@dataclass(frozen=True)
class LicenseDocument:
    """Signed license payload as stored on disk."""

    installation_id: str
    license_id: str
    firm_display_name: str
    plan: str
    features: FeatureEntitlements
    expiry: date
    issued_at: datetime
    signature: str

    @classmethod
    def from_mapping(cls, value: dict[str, Any]) -> LicenseDocument:
        return cls(
            installation_id=str(value["installation_id"]),
            license_id=str(value["license_id"]),
            firm_display_name=str(value["firm_display_name"]),
            plan=str(value["plan"]),
            features=FeatureEntitlements.from_mapping(dict(value["features"])),
            expiry=date.fromisoformat(str(value["expiry"])),
            issued_at=_parse_datetime(str(value["issued_at"])),
            signature=str(value["signature"]),
        )

    def unsigned_mapping(self) -> dict[str, Any]:
        return {
            "installation_id": self.installation_id,
            "license_id": self.license_id,
            "firm_display_name": self.firm_display_name,
            "plan": self.plan,
            "features": {
                "document_intake": self.features.document_intake,
                "cloud_backup": self.features.cloud_backup,
                "managed_restore": self.features.managed_restore,
                "matter_rag": self.features.matter_rag,
                "hosted_ai": self.features.hosted_ai,
            },
            "expiry": self.expiry.isoformat(),
            "issued_at": self.issued_at.astimezone(UTC).isoformat().replace("+00:00", "Z"),
        }


@dataclass(frozen=True)
class LicenseValidationResult:
    """Result of validating an offline license plus local control state."""

    status: str
    license_document: LicenseDocument | None = None
    reason: str = ""

    @property
    def is_active(self) -> bool:
        return self.status == ACTIVE_STATUS

    @property
    def allows_local_data_access(self) -> bool:
        return self.status in {ACTIVE_STATUS, DISABLED_STATUS, EXPIRED_STATUS}

    @property
    def paid_features_enabled(self) -> bool:
        return self.status == ACTIVE_STATUS

    def feature_enabled(self, feature_name: str) -> bool:
        if not self.paid_features_enabled or self.license_document is None:
            return False
        return self.license_document.features.enabled(feature_name)


def read_license_file(path: Path) -> LicenseDocument:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return LicenseDocument.from_mapping(raw)


def write_license_file(path: Path, document: LicenseDocument) -> None:
    payload = document.unsigned_mapping() | {"signature": document.signature}
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def canonical_license_bytes(document: LicenseDocument) -> bytes:
    return json.dumps(document.unsigned_mapping(), sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )


def load_public_key(public_key_pem: bytes) -> RSAPublicKey:
    key = serialization.load_pem_public_key(public_key_pem)
    if not isinstance(key, RSAPublicKey):
        raise TypeError("license public key must be an RSA public key")
    return key


def verify_license_document(
    document: LicenseDocument,
    public_key_pem: bytes,
    expected_installation_id: str,
    *,
    as_of: date | None = None,
    disabled: bool = False,
) -> LicenseValidationResult:
    """Verify signature, installation binding, expiry, and local disabled state."""

    try:
        signature = base64.b64decode(document.signature, validate=True)
        public_key = load_public_key(public_key_pem)
        public_key.verify(
            signature,
            canonical_license_bytes(document),
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=padding.PSS.MAX_LENGTH,
            ),
            hashes.SHA256(),
        )
    except (InvalidSignature, ValueError, TypeError) as exc:
        return LicenseValidationResult(BAD_SIGNATURE_STATUS, reason=str(exc))

    if document.installation_id != expected_installation_id:
        return LicenseValidationResult(
            INSTALLATION_MISMATCH_STATUS,
            license_document=document,
            reason="license is not bound to this installation",
        )

    today = as_of or datetime.now(UTC).date()
    if document.expiry < today:
        return LicenseValidationResult(
            EXPIRED_STATUS,
            license_document=document,
            reason="license is expired",
        )

    if disabled:
        return LicenseValidationResult(
            DISABLED_STATUS,
            license_document=document,
            reason="installation is disabled by local control state",
        )

    return LicenseValidationResult(ACTIVE_STATUS, license_document=document)


def _parse_datetime(value: str) -> datetime:
    normalized = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)
