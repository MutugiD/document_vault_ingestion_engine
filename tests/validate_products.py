"""Validate the three published product definitions."""

from __future__ import annotations

import importlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from products import load_product_catalog, product_by_slug  # noqa: E402

EXPECTED_PRODUCTS = (
    "windows-legal-document-vault",
    "document-intake-engine",
    "local-matter-rag-connector",
)


def main() -> None:
    products = load_product_catalog()
    assert tuple(product.slug for product in products) == EXPECTED_PRODUCTS

    for product in products:
        assert product.name
        assert product.summary
        assert product.license_features
        assert product.modules
        assert product.validators
        assert product.documentation
        assert product.release_artifacts

        for module_name in product.modules:
            importlib.import_module(module_name)

        for validator in product.validators:
            assert (ROOT / validator).exists(), f"missing validator for {product.name}: {validator}"

        for document in product.documentation:
            assert (ROOT / document).exists(), f"missing doc for {product.name}: {document}"

        for artifact in product.release_artifacts:
            assert artifact.startswith("dist/"), (
                f"release artifact should be under dist/: {artifact}"
            )

    vault = product_by_slug("windows-legal-document-vault")
    intake = product_by_slug("document-intake-engine")
    rag = product_by_slug("local-matter-rag-connector")

    assert vault.name == "JurisNuru"
    assert "wakilios" in vault.modules
    assert "firm_management" in vault.license_features
    assert "tests/validate_wakilios_backend.py" in vault.validators
    assert intake.name == "Document Intake Engine"
    assert rag.name == "Local Matter RAG Connector"
    assert "matter_rag" in rag.license_features
    assert "live hosted provider transport" in rag.deferred

    cli = subprocess.run(
        [sys.executable, str(ROOT / "main.py"), "--products"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert cli.returncode == 0, cli.stdout + cli.stderr
    payload = json.loads(cli.stdout)
    assert tuple(product["slug"] for product in payload["products"]) == EXPECTED_PRODUCTS

    print("PRODUCT CATALOG VALIDATION PASS")


if __name__ == "__main__":
    main()
