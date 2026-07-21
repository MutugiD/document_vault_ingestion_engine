"""Application entrypoint for Document Vault Ingestion Engine."""

from __future__ import annotations

import argparse
import importlib
import json
import sys
import tempfile
from datetime import UTC
from pathlib import Path

APP_VERSION = "0.1.0"

CORE_MODULES = (
    "ai",
    "core",
    "licensing",
    "vault",
    "intake",
    "search",
    "rag",
    "backup",
    "integrations",
    "products",
    "ui",
    "wakilios",
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

    try:
        from datetime import datetime

        from licensing import InMemoryStore, check_clock

        store = InMemoryStore()
        ok, reason = check_clock(store, now=datetime(2026, 1, 1, tzinfo=UTC))
        if not ok:
            failures.append(f"clock guard: {reason}")
    except Exception as exc:  # pragma: no cover
        failures.append(f"clockguard selftest: {exc}")

    if failures:
        print("SELFTEST FAIL")
        for failure in failures:
            print(f"- {failure}")
        _write_selftest_result("FAIL", failures)
        return 1

    print("SELFTEST PASS")
    print(f"Imported modules: {', '.join(CORE_MODULES)}")
    print("Licensing installation identity check: pass")
    print("Clock guard check: pass")
    print(f"App version: {APP_VERSION}")
    _write_selftest_result("PASS", [])
    return 0


def _write_selftest_result(status: str, failures: list[str]) -> None:
    """Write selftest result to a temp file for the release workflow gate.

    The release CI runs the frozen bundle with --selftest and gates on this
    file because the GUI-subsystem exe (console=False) doesn't pipe stdout.
    """
    import tempfile as _tf

    result_path = Path(_tf.gettempdir()) / "WakiliOS_selftest.txt"
    lines = [f"SELFTEST {status}"]
    for f in failures:
        lines.append(f"- {f}")
    try:
        result_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    except OSError:
        pass  # degrade gracefully, never crash at launch


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Document Vault Ingestion Engine")
    parser.add_argument("--selftest", action="store_true", help="run packaged-app smoke checks")
    parser.add_argument("--gui", action="store_true", help="launch the Windows desktop shell")
    parser.add_argument(
        "--gui-smoke",
        type=int,
        default=None,
        metavar="MILLISECONDS",
        help="launch the Windows desktop shell and close automatically after the interval",
    )
    parser.add_argument(
        "--providers",
        action="store_true",
        help="print redacted AI provider API-key configuration status",
    )
    parser.add_argument(
        "--public-kenya-e2e",
        type=Path,
        default=None,
        help="run public Kenyan document vault/RAG verification for an input folder",
    )
    parser.add_argument(
        "--manual-windows-app-e2e",
        type=Path,
        default=None,
        help="run the packaged Windows app UI/session E2E verification for an input folder",
    )
    parser.add_argument(
        "--products",
        action="store_true",
        help="print the published product catalog",
    )
    parser.add_argument(
        "--native-workflow-e2e",
        action="store_true",
        help="run the native app workflow verification with redacted output",
    )
    parser.add_argument(
        "--admin-license-payment-e2e",
        action="store_true",
        help="run the admin/license/payment boundary verification with redacted output",
    )
    parser.add_argument(
        "--managed-cloud-backup-e2e",
        action="store_true",
        help="run the managed cloud backup boundary verification with redacted output",
    )
    parser.add_argument(
        "--wakili-mkononi-e2e",
        action="store_true",
        help="run the Wakili-Mkononi integration boundary verification with redacted output",
    )
    parser.add_argument(
        "--hosted-ai-e2e",
        action="store_true",
        help="run the hosted AI boundary verification with redacted output",
    )
    parser.add_argument(
        "--wakilios-backend-e2e",
        action="store_true",
        help="run the WakiliOS multi-seat backend verification with redacted output",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(list(sys.argv[1:] if argv is None else argv))
    if args.selftest:
        return run_selftest()
    if args.gui:
        from ui import run_gui

        return run_gui(sys.argv[:1])
    if args.gui_smoke is not None:
        from ui import run_gui

        return run_gui(sys.argv[:1], smoke_ms=args.gui_smoke)
    if args.providers:
        from ai import configured_provider_statuses

        print(
            json.dumps(
                {"providers": [status.to_mapping() for status in configured_provider_statuses()]},
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    if args.public_kenya_e2e is not None:
        from scripts.public_kenyan_e2e import run_public_kenyan_e2e

        with tempfile.TemporaryDirectory(prefix="dv-public-ke-app-") as temporary_dir:
            report = run_public_kenyan_e2e(args.public_kenya_e2e, Path(temporary_dir))
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0
    if args.manual_windows_app_e2e is not None:
        from scripts.manual_windows_app_e2e import run_manual_windows_app_e2e

        report = run_manual_windows_app_e2e(args.manual_windows_app_e2e)
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0
    if args.native_workflow_e2e:
        from core import run_native_app_workflow

        report = run_native_app_workflow()
        print(json.dumps(report.to_mapping(), indent=2, sort_keys=True))
        return 0
    if args.admin_license_payment_e2e:
        from scripts.admin_license_payment_e2e import run_admin_license_payment_e2e

        print(json.dumps(run_admin_license_payment_e2e(), indent=2, sort_keys=True))
        return 0
    if args.managed_cloud_backup_e2e:
        from scripts.managed_cloud_backup_e2e import run_managed_cloud_backup_e2e

        print(json.dumps(run_managed_cloud_backup_e2e(), indent=2, sort_keys=True))
        return 0
    if args.wakili_mkononi_e2e:
        from scripts.wakili_mkononi_e2e import run_wakili_mkononi_e2e

        print(json.dumps(run_wakili_mkononi_e2e(), indent=2, sort_keys=True))
        return 0
    if args.hosted_ai_e2e:
        from scripts.hosted_ai_e2e import run_hosted_ai_e2e

        print(json.dumps(run_hosted_ai_e2e(), indent=2, sort_keys=True))
        return 0
    if args.wakilios_backend_e2e:
        from scripts.wakilios_backend_e2e import run_wakilios_backend_e2e

        print(json.dumps(run_wakilios_backend_e2e(), indent=2, sort_keys=True))
        return 0
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

    # A Windows user launching the packaged application by double-clicking it
    # supplies no command-line arguments.  The desktop product must open the
    # GUI in that case; diagnostics remain available through their explicit
    # flags above.
    from ui import run_gui

    return run_gui(sys.argv[:1])


if __name__ == "__main__":
    raise SystemExit(main())
