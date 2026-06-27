"""Validate the Windows release ZIP and sidecar manifest."""

from __future__ import annotations

import json
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from release import APP_NAME, create_release_bundle, validate_release_bundle  # noqa: E402

EXPECTED_PRODUCTS = {
    "windows-legal-document-vault",
    "document-intake-engine",
    "local-matter-rag-connector",
}


def main() -> None:
    frozen_dir = ROOT / "dist" / APP_NAME
    assert frozen_dir.exists(), (
        "missing frozen bundle; run tests\\validate_frozen_build.py before release validation"
    )

    release_bundle = create_release_bundle(frozen_dir, ROOT / "release-output", ROOT)
    manifest = validate_release_bundle(release_bundle.zip_path, release_bundle.manifest_path)

    assert manifest.app_name == APP_NAME
    assert manifest.platform == "windows-x64"
    assert manifest.executable == f"{APP_NAME}.exe"
    assert manifest.bundle_sha256
    assert {product["slug"] for product in manifest.products} == EXPECTED_PRODUCTS
    assert any(item.path == f"{APP_NAME}.exe" for item in manifest.files)
    assert any(item.path == "_internal/products/product_catalog.json" for item in manifest.files)
    assert any(item.path == "_internal/resources/license_public_key.pem" for item in manifest.files)
    assert any(
        item.path == "_internal/resources/public_kenyan_legal_docs.json"
        for item in manifest.files
    )

    sidecar_payload = json.loads(release_bundle.manifest_path.read_text(encoding="utf-8"))
    assert sidecar_payload["bundle_sha256"] == manifest.bundle_sha256

    with zipfile.ZipFile(release_bundle.zip_path, "r") as archive:
        names = archive.namelist()
        assert f"{APP_NAME}/{APP_NAME}.exe" in names
        assert f"{APP_NAME}/_internal/products/product_catalog.json" in names
        assert f"{APP_NAME}/_internal/resources/license_public_key.pem" in names
        assert f"{APP_NAME}/_internal/resources/public_kenyan_legal_docs.json" in names
        assert f"{APP_NAME}/release-manifest.json" in names
        assert not any(".env" in name.lower() for name in names)
        assert not any("private_key" in name.lower() for name in names)
        assert not any("credential" in name.lower() for name in names)

    print("RELEASE BUNDLE VALIDATION PASS")
    print(f"Release ZIP: {release_bundle.zip_path}")
    print(f"Release manifest: {release_bundle.manifest_path}")


if __name__ == "__main__":
    main()
