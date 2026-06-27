"""Installer, signing, and publishing manifest helpers."""

from __future__ import annotations

import hashlib
import json
import tomllib
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from release.bundle import APP_NAME, PLATFORM

INSTALLER_MANIFEST_NAME = "installer-manifest.json"
DEFAULT_PUBLISHER = "Wakili Ops"
DEFAULT_INSTALL_ROOT = r"%LOCALAPPDATA%\Programs\DocumentVaultIngestionEngine"
SIGNATURE_VERIFY_SCRIPT = "tools/verify_windows_signature.ps1"


class PublishingManifestError(Exception):
    """Raised when installer or publishing metadata is unsafe or incomplete."""


@dataclass(frozen=True)
class InstallerShortcut:
    name: str
    target: str
    location: str


@dataclass(frozen=True)
class InstallerManifest:
    app_name: str
    version: str
    platform: str
    publisher: str
    created_at: str
    release_zip: str
    release_zip_sha256: str
    release_manifest: str
    release_manifest_sha256: str
    install_root: str
    executable: str
    uninstall_command: str
    shortcuts: tuple[InstallerShortcut, ...]
    signature_required: bool
    signature_verification_script: str
    clean_windows_checks: tuple[str, ...]
    publishing_checklist: tuple[str, ...]

    def to_mapping(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["shortcuts"] = [asdict(shortcut) for shortcut in self.shortcuts]
        return payload


def create_installer_manifest(
    release_zip: Path,
    release_manifest: Path,
    output_dir: Path,
    project_root: Path | None = None,
) -> InstallerManifest:
    """Create an installer/publishing manifest next to release artifacts."""

    project_root = project_root or Path(__file__).resolve().parents[1]
    if not release_zip.exists():
        raise PublishingManifestError(f"missing release ZIP: {release_zip}")
    if not release_manifest.exists():
        raise PublishingManifestError(f"missing release manifest: {release_manifest}")
    if not (project_root / SIGNATURE_VERIFY_SCRIPT).exists():
        raise PublishingManifestError("missing Windows signature verification script")

    version = _project_version(project_root)
    manifest = InstallerManifest(
        app_name=APP_NAME,
        version=version,
        platform=PLATFORM,
        publisher=DEFAULT_PUBLISHER,
        created_at=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        release_zip=str(release_zip),
        release_zip_sha256=_sha256_file(release_zip),
        release_manifest=str(release_manifest),
        release_manifest_sha256=_sha256_file(release_manifest),
        install_root=DEFAULT_INSTALL_ROOT,
        executable=f"{APP_NAME}.exe",
        uninstall_command=rf"{DEFAULT_INSTALL_ROOT}\uninstall.exe",
        shortcuts=(
            InstallerShortcut(
                name="Document Vault Ingestion Engine",
                target=rf"{DEFAULT_INSTALL_ROOT}\{APP_NAME}.exe",
                location="Start Menu",
            ),
            InstallerShortcut(
                name="Document Vault Ingestion Engine",
                target=rf"{DEFAULT_INSTALL_ROOT}\{APP_NAME}.exe",
                location="Desktop",
            ),
        ),
        signature_required=True,
        signature_verification_script=SIGNATURE_VERIFY_SCRIPT,
        clean_windows_checks=(
            f"{APP_NAME}.exe --selftest",
            f"{APP_NAME}.exe --products",
            f"{APP_NAME}.exe --providers",
            f"{APP_NAME}.exe --native-workflow-e2e",
            f"{APP_NAME}.exe --gui",
        ),
        publishing_checklist=(
            "CI green on main",
            "release ZIP and sidecar manifest hashes verified",
            "installer artifact built from release ZIP",
            "installer and release ZIP signed",
            "signature verification passes",
            "clean Windows VM install and uninstall pass",
            "no secrets or client documents in artifacts",
            "release notes include validator evidence",
        ),
    )
    validate_installer_manifest(manifest, project_root=project_root)

    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = output_dir / INSTALLER_MANIFEST_NAME
    manifest_path.write_text(
        json.dumps(manifest.to_mapping(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest


def validate_installer_manifest(
    manifest: InstallerManifest,
    *,
    project_root: Path | None = None,
) -> None:
    """Validate publishing metadata without requiring real signing keys."""

    project_root = project_root or Path(__file__).resolve().parents[1]
    if manifest.app_name != APP_NAME:
        raise PublishingManifestError("unexpected app name")
    if manifest.platform != PLATFORM:
        raise PublishingManifestError("unexpected platform")
    if not manifest.signature_required:
        raise PublishingManifestError("commercial publishing must require signatures")
    if manifest.signature_verification_script != SIGNATURE_VERIFY_SCRIPT:
        raise PublishingManifestError("unexpected signature verification script")
    if not (project_root / manifest.signature_verification_script).exists():
        raise PublishingManifestError("signature verification script is missing")
    if not manifest.install_root.startswith("%LOCALAPPDATA%"):
        raise PublishingManifestError("install root must be user-local for V1")
    if not manifest.uninstall_command.endswith(r"\uninstall.exe"):
        raise PublishingManifestError("uninstall command must target uninstall.exe")
    if len(manifest.shortcuts) < 2:
        raise PublishingManifestError("desktop and start menu shortcuts are required")
    locations = {shortcut.location for shortcut in manifest.shortcuts}
    if locations != {"Desktop", "Start Menu"}:
        raise PublishingManifestError(f"unexpected shortcut locations: {locations}")
    if any(APP_NAME not in shortcut.target for shortcut in manifest.shortcuts):
        raise PublishingManifestError("shortcut target must point at the app executable")
    if "CI green on main" not in manifest.publishing_checklist:
        raise PublishingManifestError("publishing checklist must include CI gate")
    if not any("--selftest" in check for check in manifest.clean_windows_checks):
        raise PublishingManifestError("clean Windows checks must include selftest")


def load_installer_manifest(path: Path) -> InstallerManifest:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return InstallerManifest(
        app_name=str(payload["app_name"]),
        version=str(payload["version"]),
        platform=str(payload["platform"]),
        publisher=str(payload["publisher"]),
        created_at=str(payload["created_at"]),
        release_zip=str(payload["release_zip"]),
        release_zip_sha256=str(payload["release_zip_sha256"]),
        release_manifest=str(payload["release_manifest"]),
        release_manifest_sha256=str(payload["release_manifest_sha256"]),
        install_root=str(payload["install_root"]),
        executable=str(payload["executable"]),
        uninstall_command=str(payload["uninstall_command"]),
        shortcuts=tuple(
            InstallerShortcut(
                name=str(item["name"]),
                target=str(item["target"]),
                location=str(item["location"]),
            )
            for item in payload["shortcuts"]
        ),
        signature_required=bool(payload["signature_required"]),
        signature_verification_script=str(payload["signature_verification_script"]),
        clean_windows_checks=tuple(str(item) for item in payload["clean_windows_checks"]),
        publishing_checklist=tuple(str(item) for item in payload["publishing_checklist"]),
    )


def _project_version(project_root: Path) -> str:
    pyproject = tomllib.loads((project_root / "pyproject.toml").read_text(encoding="utf-8"))
    return str(pyproject["project"]["version"])


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
