"""Offline license validation and feature gate decisions."""

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

    @classmethod
    def from_mapping(cls, value: dict[str, Any]) -> FeatureEntitlements:
        return cls(
            document_intake=bool(value.get("document_intake", False)),
            cloud_backup=bool(value.get("cloud_backup", False)),
            managed_restore=bool(value.get("managed_restore", False)),
            matter_rag=bool(value.get("matter_rag", False)),
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
