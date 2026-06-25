"""Application entrypoint for Document Vault Ingestion Engine."""

from __future__ import annotations

import argparse
import importlib
import json
import sys
import tempfile
from pathlib import Path

CORE_MODULES = (
    "core",
    "licensing",
    "vault",
    "intake",
    "search",
    "rag",
    "backup",
    "products",
    "ui",
)


def run_selftest() -> int:
    """Import the package skeleton and report whether the baseline is wired."""

    failures: list[str] = []
    for module_name in CORE_MODULES:
        try:
            importlib.import_module(module_name)
        except Exception as exc:  # pragma: no cover - deliberately broad for frozen selftest
            failures.append(f"{module_name}: {exc}")

    try:
        from licensing import ensure_installation_identity

        with tempfile.TemporaryDirectory() as temporary_dir:
            identity_path = Path(temporary_dir) / "settings" / "installation.json"
            first_identity = ensure_installation_identity(identity_path)
            second_identity = ensure_installation_identity(identity_path)
            if first_identity.installation_id != second_identity.installation_id:
                failures.append("licensing: installation ID was not stable")
    except Exception as exc:  # pragma: no cover - deliberately broad for frozen selftest
        failures.append(f"licensing selftest: {exc}")

    if failures:
        print("SELFTEST FAIL")
        for failure in failures:
            print(f"- {failure}")
        return 1

    print("SELFTEST PASS")
    print(f"Imported modules: {', '.join(CORE_MODULES)}")
    print("Licensing installation identity check: pass")
    return 0


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Document Vault Ingestion Engine")
    parser.add_argument("--selftest", action="store_true", help="run packaged-app smoke checks")
    parser.add_argument("--gui", action="store_true", help="launch the Windows desktop shell")
    parser.add_argument(
        "--products",
        action="store_true",
        help="print the published product catalog",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(list(sys.argv[1:] if argv is None else argv))
    if args.selftest:
        return run_selftest()
    if args.gui:
        from ui import run_gui

        return run_gui(sys.argv[:1])
    if args.products:
        from products import load_product_catalog

        payload = [
            {
                "slug": product.slug,
                "name": product.name,
                "summary": product.summary,
                "license_features": list(product.license_features),
            }
            for product in load_product_catalog()
        ]
        print(json.dumps({"products": payload}, indent=2, sort_keys=True))
        return 0

    print("Document Vault Ingestion Engine. Run with --gui, --products, or --selftest.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
