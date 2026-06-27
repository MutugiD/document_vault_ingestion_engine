"""Signed update manifest verification boundary."""

from __future__ import annotations

import base64
import json
from collections.abc import Callable
from dataclasses import asdict, dataclass
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

from release.bundle import APP_NAME, PLATFORM

UPDATE_AVAILABLE = "update_available"
UPDATE_CURRENT = "current"
UPDATE_OFFLINE = "offline"
UPDATE_UNSUPPORTED_PLATFORM = "unsupported_platform"


class UpdateManifestError(Exception):
    """Raised when an update manifest is invalid or unsafe."""


@dataclass(frozen=True)
class UpdateArtifact:
    platform: str
    url: str
    sha256: str
    size_bytes: int


@dataclass(frozen=True)
class UpdateManifest:
    app_name: str
    channel: str
    latest_version: str
    published_at: str
    requires_user_approval: bool
    artifacts: tuple[UpdateArtifact, ...]
    signature: str

    def unsigned_mapping(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("signature", None)
        payload["artifacts"] = [asdict(artifact) for artifact in self.artifacts]
        return payload

    def to_mapping(self) -> dict[str, Any]:
        payload = self.unsigned_mapping()
        payload["signature"] = self.signature
        return payload


@dataclass(frozen=True)
class UpdateCheckResult:
    status: str
    current_version: str
    latest_version: str | None
    update_available: bool
    requires_user_approval: bool
    artifact: UpdateArtifact | None

    def to_mapping(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "current_version": self.current_version,
            "latest_version": self.latest_version,
            "update_available": self.update_available,
            "requires_user_approval": self.requires_user_approval,
            "artifact": asdict(self.artifact) if self.artifact is not None else None,
        }


def canonical_update_manifest_bytes(manifest: UpdateManifest) -> bytes:
    return json.dumps(
        manifest.unsigned_mapping(),
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def verify_update_manifest(
    manifest: UpdateManifest,
    public_key_pem: bytes,
    *,
    current_version: str,
    platform: str = PLATFORM,
) -> UpdateCheckResult:
    """Verify a signed update manifest and return a user-approved update decision."""

    if manifest.app_name != APP_NAME:
        raise UpdateManifestError("unexpected update manifest app name")
    if not manifest.requires_user_approval:
        raise UpdateManifestError("updates must require user approval")
    _verify_signature(manifest, public_key_pem)

    artifact = next((item for item in manifest.artifacts if item.platform == platform), None)
    if artifact is None:
        return UpdateCheckResult(
            status=UPDATE_UNSUPPORTED_PLATFORM,
            current_version=current_version,
            latest_version=manifest.latest_version,
            update_available=False,
            requires_user_approval=manifest.requires_user_approval,
            artifact=None,
        )

    update_available = _version_tuple(manifest.latest_version) > _version_tuple(current_version)
    return UpdateCheckResult(
        status=UPDATE_AVAILABLE if update_available else UPDATE_CURRENT,
        current_version=current_version,
        latest_version=manifest.latest_version,
        update_available=update_available,
        requires_user_approval=manifest.requires_user_approval,
        artifact=artifact if update_available else None,
    )


def check_for_update(
    fetch_manifest: Callable[[], UpdateManifest],
    public_key_pem: bytes,
    *,
    current_version: str,
    platform: str = PLATFORM,
) -> UpdateCheckResult:
    """Check for updates while preserving offline app continuation."""

    try:
        manifest = fetch_manifest()
    except OSError:
        return UpdateCheckResult(
            status=UPDATE_OFFLINE,
            current_version=current_version,
            latest_version=None,
            update_available=False,
            requires_user_approval=True,
            artifact=None,
        )
    return verify_update_manifest(
        manifest,
        public_key_pem,
        current_version=current_version,
        platform=platform,
    )


def update_manifest_from_mapping(payload: dict[str, Any]) -> UpdateManifest:
    return UpdateManifest(
        app_name=str(payload["app_name"]),
        channel=str(payload["channel"]),
        latest_version=str(payload["latest_version"]),
        published_at=str(payload["published_at"]),
        requires_user_approval=bool(payload["requires_user_approval"]),
        artifacts=tuple(
            UpdateArtifact(
                platform=str(item["platform"]),
                url=str(item["url"]),
                sha256=str(item["sha256"]),
                size_bytes=int(item["size_bytes"]),
            )
            for item in payload["artifacts"]
        ),
        signature=str(payload["signature"]),
    )


def _verify_signature(manifest: UpdateManifest, public_key_pem: bytes) -> None:
    public_key = serialization.load_pem_public_key(public_key_pem)
    signature = base64.b64decode(manifest.signature)
    try:
        public_key.verify(
            signature,
            canonical_update_manifest_bytes(manifest),
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=padding.PSS.MAX_LENGTH,
            ),
            hashes.SHA256(),
        )
    except InvalidSignature as exc:
        raise UpdateManifestError("update manifest signature is invalid") from exc


def _version_tuple(value: str) -> tuple[int, ...]:
    try:
        return tuple(int(part) for part in value.split("."))
    except ValueError as exc:
        raise UpdateManifestError(f"invalid version: {value}") from exc
