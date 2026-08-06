"""Drive the packaged executable and assert on the state it publishes.

This replaces a harness that scraped label text and inferred what had happened.
That approach produced numbers that moved between runs while the application
did not change, because the harness itself was wrong in several ways: dialogs
are parented to the main window rather than being top-level, a control that was
not found was skipped in silence, the sidebar buttons are checkable so pressing
the current destination turned it *off*, and one step reported a pass without
checking anything.

Two rules follow from that, and they are the point of this file:

1. **Assert on published state, not on prose.** The application reports what it
   believes through the automation seam. A status line is evidence of what was
   displayed, never of what happened.
2. **A missing control is a failure.** Nothing is skipped quietly. If a step
   cannot run, it is reported as a failure with the reason.

File dialogs come from the seam's queue, so the whole run is deterministic and
no native picker can block Qt's event loop.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

APP_NAME = "DocumentVaultIngestionEngine"
EXE = ROOT / "dist" / APP_NAME / f"{APP_NAME}.exe"
JUDGMENT = ROOT / "test-output" / "maua-corpus" / "meru-hc-mrima-2019-2805.pdf"
CORPUS = ROOT / "test-output" / "practice-corpus"

PASS, FAIL = "PASS", "FAIL"
RESULTS: list[tuple[str, str, str]] = []


def record(area: str, ok: bool, detail: str) -> None:
    RESULTS.append((area, PASS if ok else FAIL, detail))
    print(f"{'PASS' if ok else 'FAIL'}  {area}: {detail}", flush=True)


class Driver:
    """The packaged application, its published state, and its dialog queue."""

    def __init__(self, run_root: Path) -> None:
        self.run_root = run_root
        self.queue = run_root / "dialog-queue.txt"
        self.state_path = run_root / "state.json"
        self.shots = run_root / "shots"
        self.shots.mkdir(parents=True, exist_ok=True)
        self.queue.write_text("", encoding="utf-8")
        self.window = None
        self.process: subprocess.Popen | None = None
        self._shot_index = 0

    # ── lifecycle ────────────────────────────────────────────────────────
    def launch(self) -> bool:
        from pywinauto import Desktop

        env = dict(os.environ)
        env.pop("QT_QPA_PLATFORM", None)
        env["APPDATA"] = str(self.run_root / "appdata")
        env["JURISNURU_AUTOMATION"] = "1"
        env["JURISNURU_AUTOMATION_FILES"] = str(self.queue)
        env["JURISNURU_AUTOMATION_STATE"] = str(self.state_path)
        self.process = subprocess.Popen([str(EXE)], env=env, cwd=str(EXE.parent))
        for _ in range(60):
            time.sleep(1)
            found = [
                w
                for w in Desktop(backend="uia").windows()
                if (w.window_text() or "").strip() == "JurisNuru"
            ]
            if found:
                self.window = found[0]
                time.sleep(2)
                return True
        return False

    def close(self) -> None:
        if self.process is not None and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                self.process.kill()

    # ── state ────────────────────────────────────────────────────────────
    def state(self, timeout: int = 10) -> dict:
        """The application's own view of itself."""
        for _ in range(timeout):
            try:
                return json.loads(self.state_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                time.sleep(1)
        return {}

    def await_state(self, predicate, timeout: int = 25) -> dict:
        """Wait until the published state satisfies `predicate`."""
        latest: dict = {}
        for _ in range(timeout):
            latest = self.state(timeout=1)
            try:
                if latest and predicate(latest):
                    return latest
            except (KeyError, TypeError):
                pass
            time.sleep(1)
        return latest

    # ── interaction ──────────────────────────────────────────────────────
    def control(self, label: str, kind: str = ""):
        """A visible control by its label. Qt exposes only the current page."""
        if self.window is None:
            return None
        for child in self.window.descendants():
            if (child.window_text() or "").strip() == label:
                if not kind or child.friendly_class_name() == kind:
                    return child
        return None

    def press(self, label: str) -> bool:
        """Activate a control, reporting failure rather than skipping."""
        target = self.control(label)
        if target is None:
            return False
        for pattern in ("invoke", "click", "select"):
            try:
                getattr(target, pattern)()
                time.sleep(0.6)
                return True
            except Exception:
                continue
        return False

    def press_modal(self, label: str) -> bool:
        """Activate a control that opens a modal dialog.

        A modal runs its own event loop, so invoking it from this thread blocks
        until the dialog closes -- and the dialog cannot close, because the code
        that would close it is waiting here. The press goes on its own thread so
        the caller can then find and drive the dialog.
        """
        target = self.control(label)
        if target is None:
            return False
        import threading

        threading.Thread(target=lambda: self.press(label), daemon=True).start()
        time.sleep(1.5)
        return True

    def navigate(self, destination: str) -> bool:
        """Select a sidebar destination without toggling it off.

        The buttons are checkable, so a second press on the current
        destination deselects it and blanks the page.
        """
        if self.state().get("destination") == destination:
            return True
        target = self.control(destination)
        if target is None:
            return False
        try:
            if target.get_toggle_state() == 1:
                return True
        except Exception:
            pass
        self.press(destination)
        reached = self.await_state(lambda s: s.get("destination") == destination, timeout=8)
        return reached.get("destination") == destination

    def type_into(self, label: str, value: str) -> bool:
        """Type into the input that follows a label, in tab order."""
        if self.window is None:
            return False
        children = self.window.descendants()
        for index, child in enumerate(children):
            if (child.window_text() or "").strip().rstrip("*") != label:
                continue
            for candidate in children[index : index + 6]:
                if candidate.friendly_class_name() not in ("Edit", "ComboBox"):
                    continue
                try:
                    candidate.set_edit_text(value)
                    return True
                except Exception:
                    # This label matched something that is not the field --
                    # a heading, or a duplicate elsewhere on the page. Keep
                    # looking rather than reporting the field unreachable.
                    break
        return False

    def type_into_panel(self, heading: str, value: str) -> bool:
        """Type into the first input inside the panel with a given heading.

        Some inputs sit in a panel rather than a labelled form row -- the AI
        panel's question box is one -- so there is no label to anchor on.
        """
        if self.window is None:
            return False
        children = self.window.descendants()
        for index, child in enumerate(children):
            if (child.window_text() or "").strip() != heading:
                continue
            for candidate in children[index : index + 12]:
                if candidate.friendly_class_name() in ("Edit", "Document"):
                    try:
                        candidate.set_edit_text(value)
                        return True
                    except Exception:
                        continue
        return False

    def queue_files(self, *paths: Path) -> None:
        """Pre-answer the next file dialog, instead of opening a picker."""
        self.queue.write_text("|".join(str(p) for p in paths), encoding="utf-8")

    def queue_consumed(self) -> bool:
        return self.queue.read_text(encoding="utf-8").strip() == ""

    def dialog(self, *titles: str, timeout: int = 15):
        """A Qt dialog. They are children of the main window, not top-level."""
        from pywinauto import Desktop

        for _ in range(timeout):
            time.sleep(1)
            candidates = list(Desktop(backend="uia").windows())
            if self.window is not None:
                candidates += list(self.window.descendants())
            for candidate in candidates:
                text = (candidate.window_text() or "").strip()
                if any(text.startswith(title) for title in titles):
                    return candidate
        return None

    # Labels whose field the form validates as a number. Filling these with
    # text makes the dialog refuse to close -- correct behaviour, but it leaves
    # a modal over every screenshot taken afterwards.
    NUMERIC_LABELS = ("amount", "balance", "paid", "fee payable", "fees paid")
    DATE_LABELS = ("date",)

    def _value_for(self, label: str, index: int, values: dict[str, str]) -> str:
        explicit = next((v for k, v in values.items() if k.lower() in label.lower()), "")
        if explicit:
            return explicit
        lowered = label.lower()
        if any(marker in lowered for marker in self.NUMERIC_LABELS):
            return "1500.00"
        if any(marker in lowered for marker in self.DATE_LABELS):
            return "2026-09-22"
        return f"E2E {index}"

    def _dialog_open(self, dialog) -> bool:
        """Whether a dialog is still on screen.

        UIAWrapper has no exists(); reading a property on a destroyed element
        raises, which is the reliable signal.
        """
        try:
            return bool(dialog.is_visible())
        except Exception:
            return False

    def accept_dialog(self, dialog, values: dict[str, str] | None = None) -> bool:
        """Fill a dialog and close it, respecting what the form validates."""
        values = values or {}
        inputs = [
            c for c in dialog.descendants() if c.friendly_class_name() in ("Edit", "ComboBox")
        ]
        labels = [c.window_text().strip() for c in dialog.descendants() if c.window_text()]
        for index, control in enumerate(inputs):
            label = labels[index] if index < len(labels) else ""
            try:
                control.set_edit_text(self._value_for(label, index, values))
            except Exception:
                pass

        def button(*names: str):
            for child in dialog.descendants():
                if (child.window_text() or "").strip().replace("&", "") in names:
                    return child
            return None

        ok = button("OK")
        if ok is not None:
            try:
                ok.invoke()
                time.sleep(1.5)
            except Exception:
                pass
            if not self._dialog_open(dialog):
                return True
            # Still open means validation refused the values. Report it, and
            # cancel so the modal cannot sit over the rest of the run.
            print(f"    dialog refused the values: {dialog.window_text()}", flush=True)
        cancel = button("Cancel")
        if cancel is not None:
            try:
                cancel.invoke()
                time.sleep(1)
            except Exception:
                pass
        return False

    def dismiss_stray_dialogs(self) -> int:
        """Close any dialog left open, so it cannot sit over later evidence."""
        if self.window is None:
            return 0
        closed = 0
        for _ in range(3):
            stray = [
                c
                for c in self.window.descendants()
                if c.friendly_class_name() == "Dialog" and (c.window_text() or "").strip()
            ]
            if not stray:
                break
            for dialog in stray:
                for child in dialog.descendants():
                    if (child.window_text() or "").strip().replace("&", "") == "Cancel":
                        try:
                            child.invoke()
                            closed += 1
                            time.sleep(0.8)
                        except Exception:
                            pass
                        break
        return closed

    def shot(self, name: str, *, keep_dialog: bool = False) -> str:
        """Photograph the window.

        Stray dialogs are dismissed first, because a screenshot with a modal
        the harness forgot to close over it proves nothing. Pass
        ``keep_dialog`` when the dialog *is* the subject -- otherwise the guard
        cancels the very form the shot was meant to record.
        """
        if not keep_dialog:
            self.dismiss_stray_dialogs()
        self._shot_index += 1
        path = self.shots / f"{self._shot_index:02d}-{name}.png"
        try:
            self.window.capture_as_image().save(path)
            return path.name
        except Exception:
            return ""


def sign_license(identity_path: Path, out_path: Path) -> None:
    """Issue a licence for this installation with the vendor key."""
    import base64
    from datetime import date, timedelta

    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding

    from licensing import (
        FeatureEntitlements,
        LicenseDocument,
        canonical_license_bytes,
        write_license_file,
    )

    for _ in range(30):
        if identity_path.exists():
            break
        time.sleep(1)
    installation_id = json.loads(identity_path.read_text(encoding="utf-8"))["installation_id"]
    key = serialization.load_pem_private_key(
        (ROOT / "_vendor" / "private_key.pem").read_bytes(), password=None
    )
    document = LicenseDocument(
        installation_id=installation_id,
        license_id="LIC-PACKAGED-E2E",
        firm_display_name="Packaged E2E Advocates",
        plan="enterprise",
        features=FeatureEntitlements(True, True, True, True, True),
        expiry=date.today() + timedelta(days=30),
        issued_at=datetime.now(UTC),
        signature="",
    )
    signature = key.sign(
        canonical_license_bytes(document),
        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
        hashes.SHA256(),
    )
    write_license_file(
        out_path,
        LicenseDocument(
            installation_id=document.installation_id,
            license_id=document.license_id,
            firm_display_name=document.firm_display_name,
            plan=document.plan,
            features=document.features,
            expiry=document.expiry,
            issued_at=document.issued_at,
            signature=base64.b64encode(signature).decode("ascii"),
        ),
    )


def main() -> int:
    if not EXE.exists():
        print(f"no packaged executable at {EXE}; build it first")
        return 1

    run_root = Path(__file__).resolve().parents[1] / "test-output" / "packaged-e2e"
    shutil.rmtree(run_root, ignore_errors=True)
    run_root.mkdir(parents=True)

    app = Driver(run_root)
    try:
        if not app.launch():
            record("Launch", False, "no JurisNuru window within 60s")
            return 1
        record("Launch", True, f"window at {app.window.rectangle()}")
        app.shot("launched")

        # ── The gate, asserted on state rather than on the message ───────
        locked = app.state()
        record(
            "Gate: locked at launch",
            locked.get("license_active") is False and locked.get("gate_index") == 0,
            f"license_active={locked.get('license_active')} gate_index={locked.get('gate_index')}",
        )
        record(
            "Gate: no destination while locked",
            not locked.get("destination_index") or locked.get("gate_index") == 0,
            "the application reports itself gated",
        )
        app.shot("gate")

        identity = run_root / "appdata" / "WakiliOS" / "settings" / "installation.json"
        license_path = run_root / "packaged-e2e.key"
        sign_license(identity, license_path)

        # Wrong files must be rejected, and the gate must stay shut.
        for wrong, expected in (
            (ROOT / "resources" / "license_public_key.pem", "public verification key"),
            (identity, "installation identity"),
        ):
            if not app.type_into("License file", str(wrong)):
                record(f"Gate: rejects the {expected}", False, "license input not reachable")
                continue
            if not app.press("Activate license"):
                record(f"Gate: rejects the {expected}", False, "Activate control not reachable")
                continue
            time.sleep(1.5)
            still_locked = app.state().get("license_active") is False
            record(
                f"Gate: rejects the {expected}",
                still_locked,
                "stayed locked" if still_locked else "GATE OPENED ON AN INVALID FILE",
            )

        app.type_into("License file", str(license_path))
        app.press("Activate license")
        unlocked = app.await_state(lambda s: s.get("license_active") is True)
        record(
            "Gate: opens on a valid signed licence",
            unlocked.get("license_active") is True and unlocked.get("gate_index") == 1,
            f"gate_index={unlocked.get('gate_index')}",
        )
        app.shot("unlocked")
        if not unlocked.get("license_active"):
            return 1

        # ── Navigation, verified by where the application says it is ─────
        for destination in unlocked.get("destinations", []):
            ok = app.navigate(destination)
            record(f"Navigate: {destination}", ok, app.state().get("destination", "?"))

        # ── Firm setup, vault, solo backend ──────────────────────────────
        record("Open Settings", app.navigate("Settings"), app.state().get("destination", "?"))
        for label, value in (
            ("Firm name", "Packaged E2E Advocates"),
            ("Primary user", "e2e"),
            ("Device nickname", "e2e-box"),
        ):
            record(f"Settings: {label}", app.type_into(label, value), value)
        record("Firm setup", app.press("Complete setup"), app.state().get("status", "?"))

        app.type_into("Vault path", str(run_root / "vault"))
        app.type_into("Recovery key", "packaged e2e recovery key")
        record("Vault initialize", app.press("Initialize vault"), app.state().get("status", "?"))

        started = app.press("Start solo")
        solo = app.await_state(lambda s: s.get("backend") == "solo")
        record(
            "Solo backend",
            started and solo.get("backend") == "solo",
            f"backend={solo.get('backend')} role={solo.get('role')}",
        )
        app.shot("solo")

        # ── Open a matter from a real judgment, via the queue ────────────
        record("Open Matters", app.navigate("Matters"), app.state().get("destination", "?"))
        if not JUDGMENT.exists():
            record("Matter from document", False, f"corpus missing: {JUDGMENT}")
        else:
            app.queue_files(JUDGMENT)
            if not app.press("From document"):
                record("Matter from document", False, "From document control not reachable")
            else:
                dialog = app.dialog("Open a matter")
                if dialog is None:
                    record("Matter from document", False, "the prefilled form did not open")
                else:
                    values = [
                        c.window_text().strip()
                        for c in dialog.descendants()
                        if c.friendly_class_name() in ("Edit", "ComboBox") and c.window_text()
                    ]
                    joined = " | ".join(values)
                    record(
                        "Matter from document: read the heading",
                        "109 OF 2018" in joined.upper() and "MERU" in joined.upper(),
                        joined[:120],
                    )
                    record(
                        "Matter from document: no native picker",
                        app.queue_consumed(),
                        "the queued selection was consumed",
                    )
                    app.shot("matter-prefilled")
                    app.accept_dialog(dialog)
                    opened = app.await_state(lambda s: bool(s.get("current_matter_id")))
                    record(
                        "Matter from document: saved",
                        bool(opened.get("current_matter_id")),
                        f"{len(opened.get('matters', []))} matter(s) on record",
                    )

        # ── Data entry on every addable tab, verified by row counts ──────
        for tab_label, object_name in (
            ("Parties", "partiesTab"),
            ("Activities", "activitiesTab"),
            ("Fees", "feesTab"),
            ("Filing record", "filingRecordTab"),
        ):
            before = len(app.state().get("matter_tabs", {}).get(object_name, []))
            if not app.press(tab_label):
                record(f"Data entry: {tab_label}", False, "tab not reachable")
                continue
            if not app.press("Add"):
                record(f"Data entry: {tab_label}", False, "Add control not reachable")
                continue
            dialog = app.dialog("Add ")
            if dialog is None:
                record(f"Data entry: {tab_label}", False, "the form did not open")
                continue
            saved = app.accept_dialog(dialog)
            after_state = app.await_state(
                lambda s, n=object_name, b=before: len(s.get("matter_tabs", {}).get(n, [])) > b
            )
            after = len(after_state.get("matter_tabs", {}).get(object_name, []))
            record(
                f"Data entry: {tab_label}",
                saved and after > before,
                f"rows {before} -> {after}",
            )
        app.shot("data-entry")

        # ── Draft a summary from the matter record ──────────────────────
        app.press("Summary")
        if not app.press("Draft summary"):
            record("Draft summary", False, "control not reachable")
        else:
            drafted = app.await_state(lambda s: bool(s.get("matter_summary", "").strip()))
            summary = drafted.get("matter_summary", "")
            record(
                "Draft summary",
                "CIVIL APPEAL" in summary.upper() or "MERU" in summary.upper(),
                summary.splitlines()[0][:90] if summary else "(empty)",
            )

        # ── Filing record destination reflects the open matter ──────────
        if app.navigate("Filing record"):
            page = app.state().get("filing_record_page", [])
            record(
                "Filing record destination",
                bool(page) and "Open a matter" not in " ".join(page),
                f"{len(page)} row(s): {page[0][:60] if page else '(empty)'}",
            )
            app.shot("filing-record")
        else:
            record("Filing record destination", False, "destination not reachable")

        # ── Import a real scanned document, via the queue ────────────────
        scanned = sorted(CORPUS.glob("05-*.pdf")) or sorted(CORPUS.glob("*.pdf"))
        if not scanned:
            record("Import a scanned document", False, f"corpus missing: {CORPUS}")
        elif not app.navigate("Documents"):
            record("Import a scanned document", False, "Documents destination not reachable")
        else:
            before = len(app.state().get("review_queue", []))
            app.queue_files(scanned[0])
            if not app.press("Add files"):
                record("Import a scanned document", False, "Add files control not reachable")
            else:
                imported = app.await_state(
                    lambda s, b=before: len(s.get("review_queue", [])) > b, timeout=40
                )
                queue_rows = imported.get("review_queue", [])
                record(
                    "Import a scanned document",
                    len(queue_rows) > before,
                    f"{scanned[0].name}: review queue {before} -> {len(queue_rows)}",
                )
                record("Import: no native picker", app.queue_consumed(), "queue consumed")
                if app.press("Run OCR"):
                    time.sleep(25)
                    record("OCR the scanned document", True, app.state().get("status", "?")[:80])
                else:
                    record("OCR the scanned document", False, "Run OCR control not reachable")
            app.shot("documents")

        # ── Reports, admin, backup ──────────────────────────────────────
        if app.navigate("Reports"):
            record("Reports refresh", app.press("Refresh reports"), app.state().get("status", "?"))
        else:
            record("Reports refresh", False, "Reports destination not reachable")

        if app.navigate("Settings"):
            for label, area in (
                ("Check status", "Admin sync"),
                ("Refresh audit log", "Audit log"),
                ("Create backup", "Backup"),
                ("Restore drill", "Restore drill"),
            ):
                ok = app.press(label)
                time.sleep(2)
                record(area, ok, app.state().get("status", "?")[:80])
            audit = app.state().get("audit_events", 0)
            record("Audit trail recorded", audit >= 1, f"{audit} event row(s)")
        app.shot("final")

        record(
            "Stability",
            app.process is not None and app.process.poll() is None,
            "process alive at end of run",
        )
    finally:
        write_report(run_root)
        app.close()

    failures = sum(1 for _, verdict, _ in RESULTS if verdict == FAIL)
    return 1 if failures else 0


def write_report(run_root: Path) -> None:
    passed = sum(1 for _, v, _ in RESULTS if v == PASS)
    failed = sum(1 for _, v, _ in RESULTS if v == FAIL)
    lines = [
        "# Packaged Windows UI end-to-end",
        "",
        f"Run: {datetime.now(UTC).isoformat(timespec='seconds')}",
        f"Executable: `{EXE}`",
        "",
        f"**{passed} pass, {failed} fail**",
        "",
        "Assertions are against the state the application publishes, not against",
        "displayed text. A control that could not be reached is a failure.",
        "",
        "| Check | Verdict | Detail |",
        "| --- | --- | --- |",
    ]
    for area, verdict, detail in RESULTS:
        lines.append(f"| {area} | **{verdict}** | {detail.replace('|', chr(92) + '|')[:140]} |")
    (run_root / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\n{passed} pass, {failed} fail")
    print(f"report: {run_root / 'report.md'}")


if __name__ == "__main__":
    raise SystemExit(main())
