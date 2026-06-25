"""Build and validate a release ZIP from the frozen Windows bundle."""

from __future__ import annotations

import hashlib
import json
import tomllib
import zipfile
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from products import load_product_catalog

APP_NAME = "DocumentVaultIngestionEngine"
PLATFORM = "windows-x64"
MANIFEST_NAME = "release-manifest.json"
FORBIDDEN_NAME_MARKERS = (
    ".env",
    "client-document",
    "credential",
    "id_rsa",
    "private-key",
    "private_key",
    "recovery-key",
    "secret",
)


class ReleaseBundleError(Exception):
    """Raised when a release bundle is incomplete or unsafe to publish."""


@dataclass(frozen=True)
class ReleaseFile:
    path: str
    size_bytes: int
    sha256: str


@dataclass(frozen=True)
class ReleaseManifest:
    app_name: str
    version: str
    platform: str
    created_at: str
    executable: str
    products: tuple[dict[str, Any], ...]
    files: tuple[ReleaseFile, ...]
    validation_scripts: tuple[str, ...]
    bundle_sha256: str | None = None


@dataclass(frozen=True)
class ReleaseBundle:
    zip_path: Path
    manifest_path: Path
    manifest: ReleaseManifest


def create_release_bundle(
    frozen_bundle_dir: Path,
    output_dir: Path,
    project_root: Path | None = None,
) -> ReleaseBundle:
    """Create a publishable ZIP and sidecar manifest from a frozen app folder."""

    project_root = project_root or Path(__file__).resolve().parents[1]
    frozen_bundle_dir = frozen_bundle_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    manifest = _build_manifest(frozen_bundle_dir, project_root)
    version = manifest.version
    zip_path = output_dir / f"{APP_NAME}-{version}-{PLATFORM}.zip"
    manifest_path = output_dir / f"{APP_NAME}-{version}-{PLATFORM}.manifest.json"

    _write_zip(zip_path, frozen_bundle_dir, manifest)
    bundle_hash = _sha256_file(zip_path)
    final_manifest = ReleaseManifest(
        app_name=manifest.app_name,
        version=manifest.version,
        platform=manifest.platform,
        created_at=manifest.created_at,
        executable=manifest.executable,
        products=manifest.products,
        files=manifest.files,
        validation_scripts=manifest.validation_scripts,
        bundle_sha256=bundle_hash,
    )
    manifest_path.write_text(
        json.dumps(_manifest_to_json(final_manifest), indent=2, sort_keys=True),
        encoding="utf-8",
    )

    validate_release_bundle(zip_path, manifest_path)
    return ReleaseBundle(zip_path=zip_path, manifest_path=manifest_path, manifest=final_manifest)


def validate_release_bundle(zip_path: Path, manifest_path: Path) -> ReleaseManifest:
    """Validate release ZIP structure, sidecar manifest, hashes, and safety boundaries."""

    if not zip_path.exists():
        raise ReleaseBundleError(f"missing release ZIP: {zip_path}")
    if not manifest_path.exists():
        raise ReleaseBundleError(f"missing release manifest: {manifest_path}")

    manifest_payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest = _manifest_from_json(manifest_payload)
    if manifest.bundle_sha256 != _sha256_file(zip_path):
        raise ReleaseBundleError("release ZIP hash does not match sidecar manifest")

    with zipfile.ZipFile(zip_path, "r") as archive:
        names = archive.namelist()
        _assert_no_forbidden_names(names)
        _assert_required_entries(names)
        archived_manifest = json.loads(archive.read(f"{APP_NAME}/{MANIFEST_NAME}"))

    if archived_manifest["bundle_sha256"] is not None:
        raise ReleaseBundleError("embedded manifest must not self-reference the ZIP hash")

    file_paths = {item.path for item in manifest.files}
    missing_files = [name for name in file_paths if f"{APP_NAME}/{name}" not in names]
    if missing_files:
        raise ReleaseBundleError(f"manifest lists files missing from ZIP: {missing_files}")

    expected_products = {
        "windows-legal-document-vault",
        "document-intake-engine",
        "local-matter-rag-connector",
    }
    actual_products = {str(product["slug"]) for product in manifest.products}
    if actual_products != expected_products:
        raise ReleaseBundleError(f"unexpected products in release manifest: {actual_products}")

    return manifest


def _build_manifest(frozen_bundle_dir: Path, project_root: Path) -> ReleaseManifest:
    exe_path = frozen_bundle_dir / f"{APP_NAME}.exe"
    if not exe_path.exists():
        raise ReleaseBundleError(f"missing frozen executable: {exe_path}")
    if not (frozen_bundle_dir / "_internal").exists():
        raise ReleaseBundleError("missing PyInstaller _internal folder")

    files = _collect_release_files(frozen_bundle_dir)
    products = tuple(asdict(product) for product in load_product_catalog())
    validation_scripts = (
        "tests/validate_products.py",
        "tests/validate_package.py",
        "tests/validate_e2e.py",
        "tests/validate_frozen_build.py",
        "tests/validate_release_bundle.py",
    )
    for script in validation_scripts:
        if script != "tests/validate_release_bundle.py" and not (project_root / script).exists():
            raise ReleaseBundleError(f"missing validation script: {script}")

    return ReleaseManifest(
        app_name=APP_NAME,
        version=_project_version(project_root),
        platform=PLATFORM,
        created_at=datetime.now(UTC).isoformat(),
        executable=f"{APP_NAME}.exe",
        products=products,
        files=files,
        validation_scripts=validation_scripts,
    )


def _collect_release_files(frozen_bundle_dir: Path) -> tuple[ReleaseFile, ...]:
    files: list[ReleaseFile] = []
    for path in sorted(item for item in frozen_bundle_dir.rglob("*") if item.is_file()):
        relative = path.relative_to(frozen_bundle_dir).as_posix()
        _assert_no_forbidden_names([relative])
        files.append(
            ReleaseFile(path=relative, size_bytes=path.stat().st_size, sha256=_sha256_file(path))
        )
    if not files:
        raise ReleaseBundleError("frozen bundle folder is empty")
    return tuple(files)


def _write_zip(zip_path: Path, frozen_bundle_dir: Path, manifest: ReleaseManifest) -> None:
    if zip_path.exists():
        zip_path.unlink()
    embedded_manifest = json.dumps(_manifest_to_json(manifest), indent=2, sort_keys=True)
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for release_file in manifest.files:
            archive.write(
                frozen_bundle_dir / release_file.path,
                f"{APP_NAME}/{release_file.path}",
            )
        archive.writestr(f"{APP_NAME}/{MANIFEST_NAME}", embedded_manifest)


def _assert_required_entries(names: list[str]) -> None:
    required_suffixes = (
        f"{APP_NAME}/{APP_NAME}.exe",
        f"{APP_NAME}/_internal/products/product_catalog.json",
        f"{APP_NAME}/{MANIFEST_NAME}",
    )
    missing = [suffix for suffix in required_suffixes if suffix not in names]
    if missing:
        raise ReleaseBundleError(f"release ZIP is missing required entries: {missing}")


def _assert_no_forbidden_names(names: list[str]) -> None:
    for name in names:
        normalized = name.lower().replace("\\", "/")
        if any(marker in normalized for marker in FORBIDDEN_NAME_MARKERS):
            raise ReleaseBundleError(f"forbidden release file name: {name}")


def _project_version(project_root: Path) -> str:
    pyproject = tomllib.loads((project_root / "pyproject.toml").read_text(encoding="utf-8"))
    return str(pyproject["project"]["version"])


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _manifest_to_json(manifest: ReleaseManifest) -> dict[str, Any]:
    payload = asdict(manifest)
    payload["files"] = [
        asdict(item) if isinstance(item, ReleaseFile) else item for item in manifest.files
    ]
    return payload


def _manifest_from_json(payload: dict[str, Any]) -> ReleaseManifest:
    return ReleaseManifest(
        app_name=str(payload["app_name"]),
        version=str(payload["version"]),
        platform=str(payload["platform"]),
        created_at=str(payload["created_at"]),
        executable=str(payload["executable"]),
        products=tuple(dict(item) for item in payload["products"]),
        files=tuple(
            ReleaseFile(
                path=str(item["path"]),
                size_bytes=int(item["size_bytes"]),
                sha256=str(item["sha256"]),
            )
            for item in payload["files"]
        ),
        validation_scripts=tuple(str(item) for item in payload["validation_scripts"]),
        bundle_sha256=(
            str(payload["bundle_sha256"]) if payload.get("bundle_sha256") is not None else None
        ),
    )
