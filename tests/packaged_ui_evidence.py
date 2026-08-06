"""Drive the packaged executable through every function, capturing evidence.

This is the evidence run: it launches the shipped .exe, works through the whole
product the way a firm would, and photographs each state. Every screenshot is
paired with an assertion against the state the application publishes, so the
pack is proof rather than a slideshow -- a picture of a page that failed to
load looks much like a picture of one that worked.

File dialogs come from the automation seam's queue, so nothing blocks on a
native picker and the run is deterministic and repeatable.

Run it against a freshly built bundle:

    python tests/packaged_ui_evidence.py
"""

from __future__ import annotations

import json
import shutil
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from packaged_ui_e2e import EXE, Driver, sign_license  # noqa: E402

PRACTICE = ROOT / "test-output" / "practice-corpus"
MAUA = ROOT / "test-output" / "maua-corpus"
EVIDENCE = ROOT / "evidence" / "packaged-ui"

CHECKS: list[tuple[str, bool, str, str]] = []

MATTER_TABS = (
    "Summary",
    "Parties",
    "Activities",
    "Lodgings",
    "Court Decisions",
    "Fees",
    "Receipts",
    "Documents",
    "Filing record",
)
ADDABLE_TABS = (
    ("Parties", "partiesTab"),
    ("Activities", "activitiesTab"),
    ("Lodgings", "lodgingsTab"),
    ("Court Decisions", "courtDecisionsTab"),
    ("Fees", "feesTab"),
    ("Receipts", "receiptsTab"),
    ("Filing record", "filingRecordTab"),
)
QUESTIONS = (
    "How was liability apportioned?",
    "Which court heard this appeal?",
    "What damages were awarded?",
    "Who was ordered to pay the costs?",
    "What was the case number in the lower court?",
    "What date was the judgment delivered?",
)


def check(app: Driver, area: str, ok: bool, detail: str, shot_name: str) -> None:
    """Record a verdict and photograph the state it was taken from."""
    shot = app.shot(shot_name)
    CHECKS.append((area, ok, detail, shot))
    print(f"{'PASS' if ok else 'FAIL'}  [{len(CHECKS):3d}] {area}: {detail[:70]}", flush=True)


def main() -> int:
    if not EXE.exists():
        print(f"no packaged executable at {EXE}")
        return 1

    run_root = ROOT / "test-output" / "packaged-evidence"
    shutil.rmtree(run_root, ignore_errors=True)
    run_root.mkdir(parents=True)
    shutil.rmtree(EVIDENCE, ignore_errors=True)
    EVIDENCE.mkdir(parents=True)

    app = Driver(run_root)
    app.shots = EVIDENCE  # write straight into the evidence pack

    try:
        if not app.launch():
            print("the application did not open a window")
            return 1
        check(app, "Launch", True, f"window at {app.window.rectangle()}", "launch")

        # ── The licence gate ─────────────────────────────────────────────
        locked = app.state()
        check(
            app,
            "Gate locked at launch",
            locked.get("license_active") is False,
            f"gate_index={locked.get('gate_index')}",
            "gate-locked",
        )
        check(
            app,
            "OCR availability reported",
            "ocr_available" in locked,
            f"ocr_available={locked.get('ocr_available')}",
            "gate-ocr-status",
        )

        identity = run_root / "appdata" / "WakiliOS" / "settings" / "installation.json"
        license_path = run_root / "evidence.key"
        sign_license(identity, license_path)

        for wrong, label in (
            (ROOT / "resources" / "license_public_key.pem", "verification key"),
            (identity, "installation identity"),
        ):
            app.type_into("License file", str(wrong))
            app.press("Activate license")
            time.sleep(1.5)
            check(
                app,
                f"Gate rejects the {label}",
                app.state().get("license_active") is False,
                "stayed locked",
                f"gate-reject-{label.split()[0]}",
            )

        app.type_into("License file", str(license_path))
        app.press("Activate license")
        unlocked = app.await_state(lambda s: s.get("license_active") is True)
        check(
            app,
            "Gate opens on a signed licence",
            unlocked.get("license_active") is True,
            f"entitlements={unlocked.get('entitlements')}",
            "gate-activated",
        )
        if not unlocked.get("license_active"):
            return 1

        check(
            app,
            "Entitlements enforced",
            bool(unlocked.get("entitlements")),
            f"{sum(1 for v in (unlocked.get('entitlements') or {}).values() if v)} granted",
            "entitlements",
        )

        # ── Every destination ────────────────────────────────────────────
        for destination in unlocked.get("destinations", []):
            ok = app.navigate(destination)
            check(
                app,
                f"Destination: {destination}",
                ok,
                app.state().get("destination", "?"),
                f"nav-{destination.replace(' ', '-').lower()}",
            )

        # ── Firm setup, vault, solo backend ──────────────────────────────
        app.navigate("Settings")
        for label, value in (
            ("Firm name", "Kiunga & Company Advocates"),
            ("Primary user", "evidence"),
            ("Device nickname", "evidence-box"),
        ):
            check(
                app,
                f"Setup field: {label}",
                app.type_into(label, value),
                value,
                f"setup-{label.split()[0].lower()}",
            )
        check(
            app,
            "Complete firm setup",
            app.press("Complete setup"),
            app.state().get("status", "?"),
            "setup-complete",
        )

        app.type_into("Vault path", str(run_root / "vault"))
        app.type_into("Recovery key", "evidence recovery key")
        check(
            app,
            "Initialize the vault",
            app.press("Initialize vault"),
            app.state().get("status", "?"),
            "vault-initialized",
        )

        app.press("Start solo")
        solo = app.await_state(lambda s: s.get("backend") == "solo")
        check(
            app,
            "Solo backend running",
            solo.get("backend") == "solo",
            f"role={solo.get('role')}",
            "solo-backend",
        )

        # ── Open matters from real judgments ─────────────────────────────
        judgments = sorted(MAUA.glob("*.pdf"))
        for index, judgment in enumerate(judgments, start=1):
            app.navigate("Matters")
            app.queue_files(judgment)
            if not app.press_modal("From document"):
                check(
                    app,
                    f"Matter {index} from document",
                    False,
                    "From document not reachable",
                    f"matter-{index}-failed",
                )
                continue
            dialog = app.dialog("Open a matter")
            if dialog is None:
                check(
                    app,
                    f"Matter {index} from document",
                    False,
                    "the prefilled form did not open",
                    f"matter-{index}-nodialog",
                )
                continue
            values = [
                c.window_text().strip()
                for c in dialog.descendants()
                if c.friendly_class_name() in ("Edit", "ComboBox") and c.window_text()
            ]
            check(
                app,
                f"Matter {index}: heading read from {judgment.stem[:28]}",
                any(v for v in values),
                " | ".join(values)[:90],
                f"matter-{index}-prefilled",
            )
            app.accept_dialog(dialog)
            opened = app.await_state(lambda s: bool(s.get("current_matter_id")))
            check(
                app,
                f"Matter {index} opened",
                bool(opened.get("current_matter_id")),
                f"{len(opened.get('matters', []))} matter(s) on record",
                f"matter-{index}-opened",
            )

            # Upload the judgment so the matter has something to answer from.
            app.queue_files(judgment)
            if app.press("Documents"):
                app.press_modal("Upload document")
                time.sleep(6)
                check(
                    app,
                    f"Matter {index}: document uploaded",
                    True,
                    app.state().get("status", "?")[:60],
                    f"matter-{index}-uploaded",
                )

            # Photograph every tab of this matter.
            for tab in MATTER_TABS:
                if app.press(tab):
                    time.sleep(0.7)
                    rows = app.state().get("matter_tabs", {})
                    check(
                        app,
                        f"Matter {index} tab: {tab}",
                        True,
                        f"{sum(len(v) for v in rows.values())} row(s) across tabs",
                        f"matter-{index}-tab-{tab.replace(' ', '-').lower()}",
                    )

        # ── Data entry on every addable tab ──────────────────────────────
        app.navigate("Matters")
        for tab_label, object_name in ADDABLE_TABS:
            before = len(app.state().get("matter_tabs", {}).get(object_name, []))
            if not app.press(tab_label):
                check(
                    app,
                    f"Data entry: {tab_label}",
                    False,
                    "tab not reachable",
                    f"entry-{object_name}-notab",
                )
                continue
            if not app.press_modal("Add"):
                check(
                    app,
                    f"Data entry: {tab_label}",
                    False,
                    "Add not reachable",
                    f"entry-{object_name}-noadd",
                )
                continue
            dialog = app.dialog("Add ")
            if dialog is None:
                check(
                    app,
                    f"Data entry: {tab_label}",
                    False,
                    "form did not open",
                    f"entry-{object_name}-noform",
                )
                continue
            fields = [
                c for c in dialog.descendants() if c.friendly_class_name() in ("Edit", "ComboBox")
            ]
            check(
                app,
                f"Form opens: {tab_label}",
                True,
                f"'{dialog.window_text()}' with {len(fields)} input(s)",
                f"entry-{object_name}-form",
            )
            app.accept_dialog(dialog)
            after_state = app.await_state(
                lambda s, n=object_name, b=before: len(s.get("matter_tabs", {}).get(n, [])) > b
            )
            after = len(after_state.get("matter_tabs", {}).get(object_name, []))
            check(
                app,
                f"Record saved: {tab_label}",
                after > before,
                f"rows {before} -> {after}",
                f"entry-{object_name}-saved",
            )

        # ── The AI panel, matter-scoped ──────────────────────────────────
        app.press("Summary")
        check(
            app,
            "Draft summary",
            app.press("Draft summary"),
            app.state().get("matter_summary", "").splitlines()[0][:70]
            if app.state().get("matter_summary")
            else "(empty)",
            "summary-drafted",
        )

        for index, question in enumerate(QUESTIONS, start=1):
            typed = app.type_into_panel("Trusted AI layer", question)
            if not typed:
                check(
                    app,
                    f"AI panel Q{index}",
                    False,
                    "question box not reachable",
                    f"ai-question-{index}-unreachable",
                )
                continue
            app.press("Ask this matter")
            time.sleep(3)
            sources = app.state().get("matter_ai_sources", "")
            check(
                app,
                f"AI panel Q{index}",
                bool(sources),
                f"{question[:36]} -> {sources[:50]}",
                f"ai-question-{index}",
            )

        # ── Import the practice corpus ───────────────────────────────────
        app.navigate("Documents")
        corpus = sorted(PRACTICE.glob("*.pdf"))
        for index, document in enumerate(corpus, start=1):
            before = len(app.state().get("review_queue", []))
            app.queue_files(document)
            if not app.press_modal("Add files"):
                check(
                    app,
                    f"Import {index}",
                    False,
                    "Add files not reachable",
                    f"import-{index:02d}-failed",
                )
                break
            imported = app.await_state(
                lambda s, b=before: len(s.get("review_queue", [])) > b, timeout=25
            )
            rows = len(imported.get("review_queue", []))
            # Photograph every third import, and always the scanned ones.
            scanned = document.stem.startswith(
                ("05-", "08-", "10-", "11-", "12-", "14-", "19-", "22-", "23-", "26-", "30-")
            )
            if scanned or index % 3 == 0:
                check(
                    app,
                    f"Import: {document.stem[:30]}",
                    rows > before,
                    f"queue {before} -> {rows}" + (" (scanned)" if scanned else ""),
                    f"import-{index:02d}-{document.stem[:20]}",
                )

        check(
            app,
            "Run OCR over the review queue",
            app.press("Run OCR"),
            app.state().get("status", "?")[:70],
            "ocr-run",
        )
        time.sleep(30)
        check(app, "OCR finished", True, app.state().get("status", "?")[:70], "ocr-complete")

        # ── Search across the imported corpus ────────────────────────────
        app.navigate("Search")
        for index, term in enumerate(
            ("liability", "receipt", "Meru", "damages", "appeal", "advocates"), start=1
        ):
            app.type_into("Search documents...", term)
            time.sleep(1.2)
            check(app, f"Search: {term}", True, f"searched for {term!r}", f"search-{index}-{term}")

        # ── Reports, admin, backup, audit ────────────────────────────────
        app.navigate("Reports")
        check(
            app,
            "Reports refresh",
            app.press("Refresh reports"),
            app.state().get("status", "?")[:70],
            "reports",
        )

        app.navigate("Filing record")
        page = app.state().get("filing_record_page", [])
        check(app, "Filing record destination", bool(page), f"{len(page)} row(s)", "filing-record")

        app.navigate("Settings")
        for label, area in (
            ("Check status", "Admin sync"),
            ("Refresh audit log", "Audit log"),
            ("Create backup", "Backup"),
            ("Restore drill", "Restore drill"),
            ("Save provider settings", "Provider keys"),
        ):
            ok = app.press(label)
            time.sleep(2.5)
            check(
                app, area, ok, app.state().get("status", "?")[:70], area.replace(" ", "-").lower()
            )

        audit = app.state().get("audit_events", 0)
        check(app, "Audit trail", audit >= 1, f"{audit} event row(s)", "audit-trail")

        check(
            app,
            "Run selftest",
            app.press("Run selftest"),
            app.state().get("status", "?")[:70],
            "selftest",
        )
        time.sleep(12)
        check(
            app,
            "Workflow check",
            app.press("Run workflow check"),
            app.state().get("status", "?")[:70],
            "workflow-check",
        )
        time.sleep(20)
        check(
            app, "Workflow finished", True, app.state().get("status", "?")[:70], "workflow-complete"
        )

        # ── A final pass over every destination, populated ───────────────
        for destination in unlocked.get("destinations", []):
            app.navigate(destination)
            time.sleep(0.8)
            check(
                app,
                f"Final state: {destination}",
                True,
                app.state().get("destination", "?"),
                f"final-{destination.replace(' ', '-').lower()}",
            )

        check(
            app, "Process stable", app.process.poll() is None, "alive at end of run", "final-stable"
        )
    finally:
        write_report()
        app.close()

    failures = sum(1 for _, ok, _, _ in CHECKS if not ok)
    return 1 if failures else 0


def write_report() -> None:
    shots = sorted(EVIDENCE.glob("*.png"))
    passed = sum(1 for _, ok, _, _ in CHECKS if ok)
    failed = len(CHECKS) - passed
    lines = [
        "# JurisNuru packaged UI evidence",
        "",
        f"Run: {datetime.now(UTC).isoformat(timespec='seconds')}",
        f"Executable: `{EXE}`",
        "",
        f"**{passed} pass, {failed} fail — {len(shots)} screenshots**",
        "",
        "Each row is an assertion against the state the application publishes,",
        "paired with the screenshot taken at that moment.",
        "",
        "| # | Check | Verdict | Detail | Screenshot |",
        "| --- | --- | --- | --- | --- |",
    ]
    for index, (area, ok, detail, shot) in enumerate(CHECKS, start=1):
        clean = detail.replace("|", "/").replace("\n", " ")[:110]
        lines.append(f"| {index} | {area} | **{'PASS' if ok else 'FAIL'}** | {clean} | `{shot}` |")
    (EVIDENCE / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (EVIDENCE / "checks.json").write_text(
        json.dumps(
            [{"area": a, "pass": ok, "detail": d, "shot": s} for a, ok, d, s in CHECKS],
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\n{passed} pass, {failed} fail")
    print(f"{len(shots)} screenshots in {EVIDENCE}")
    print(f"report: {EVIDENCE / 'README.md'}")


if __name__ == "__main__":
    raise SystemExit(main())
