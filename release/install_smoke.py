"""Smoke-test a portable Windows install extracted from the release ZIP."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import zipfile
from dataclasses import dataclass
from pathlib import Path

from release.bundle import APP_NAME, ReleaseBundleError, validate_release_bundle


@dataclass(frozen=True)
class PortableInstallResult:
    install_dir: Path
    executable: Path
    selftest_stdout: str
    products_stdout: str
    managed_cloud_stdout: str
    wakili_mkononi_stdout: str
    hosted_ai_stdout: str


def run_portable_install_smoke(zip_path: Path, install_root: Path) -> PortableInstallResult:
    """Extract the release ZIP and run the frozen executable smoke checks."""

    if sys.platform != "win32":
        raise ReleaseBundleError("portable install smoke test is Windows-only")

    manifest_path = _sidecar_manifest_path(zip_path)
    validate_release_bundle(zip_path, manifest_path)

    if install_root.exists():
        shutil.rmtree(install_root)
    install_root.mkdir(parents=True)

    _safe_extract(zip_path, install_root)
    install_dir = install_root / APP_NAME
    executable = install_dir / f"{APP_NAME}.exe"
    if not executable.exists():
        raise ReleaseBundleError(f"extracted executable is missing: {executable}")

    selftest = _run_executable(executable, "--selftest", install_dir)
    products = _run_executable(executable, "--products", install_dir)
    managed_cloud = _run_executable(executable, "--managed-cloud-backup-e2e", install_dir)
    wakili_mkononi = _run_executable(executable, "--wakili-mkononi-e2e", install_dir)
    hosted_ai = _run_executable(executable, "--hosted-ai-e2e", install_dir)
    product_payload = json.loads(products.stdout)
    product_slugs = {str(item["slug"]) for item in product_payload["products"]}
    expected_products = {
        "windows-legal-document-vault",
        "document-intake-engine",
        "local-matter-rag-connector",
    }
    if product_slugs != expected_products:
        raise ReleaseBundleError(f"unexpected extracted product catalog: {product_slugs}")
    if "interrupted_upload_blocked" not in managed_cloud.stdout:
        raise ReleaseBundleError("managed cloud backup smoke output is incomplete")
    if "audit_event_recorded" not in wakili_mkononi.stdout:
        raise ReleaseBundleError("Wakili-Mkononi integration smoke output is incomplete")
    if "hosted_audit_recorded" not in hosted_ai.stdout:
        raise ReleaseBundleError("hosted AI smoke output is incomplete")

    return PortableInstallResult(
        install_dir=install_dir,
        executable=executable,
        selftest_stdout=selftest.stdout,
        products_stdout=products.stdout,
        managed_cloud_stdout=managed_cloud.stdout,
        wakili_mkononi_stdout=wakili_mkononi.stdout,
        hosted_ai_stdout=hosted_ai.stdout,
    )


def _sidecar_manifest_path(zip_path: Path) -> Path:
    if zip_path.name.endswith(".zip"):
        return zip_path.with_name(zip_path.name.removesuffix(".zip") + ".manifest.json")
    raise ReleaseBundleError(f"release file is not a ZIP: {zip_path}")


def _safe_extract(zip_path: Path, install_root: Path) -> None:
    install_root = install_root.resolve()
    with zipfile.ZipFile(zip_path, "r") as archive:
        for member in archive.infolist():
            target = (install_root / member.filename).resolve()
            if not target.is_relative_to(install_root):
                raise ReleaseBundleError(f"unsafe ZIP path: {member.filename}")
        archive.extractall(install_root)


def _run_executable(
    executable: Path,
    argument: str,
    cwd: Path,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        [str(executable), argument],
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise ReleaseBundleError(result.stdout + result.stderr)
    return result
