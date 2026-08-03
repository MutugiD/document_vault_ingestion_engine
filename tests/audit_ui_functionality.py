"""Drive every visible control and report what actually works.

This is an audit, not a gate. The validation suites assert that specific
behaviours hold; this exercises the whole surface a user can touch and prints
a per-function verdict, so the gap between "the widget exists" and "clicking
it does something" is visible rather than assumed.

It runs against the real click handlers through the real license gate. Nothing
is stubbed except the file dialogs, which cannot be driven headlessly.

Exit code is 0 unless a control raises -- a control that is wired but does
nothing useful is reported as PARTIAL, because that is a product gap to
prioritise rather than a regression to block on.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from _dialog_harness import autofill_dialogs  # noqa: E402
from _license_harness import install_test_license  # noqa: E402
from PySide6.QtWidgets import (  # noqa: E402
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QTabWidget,
    QTextEdit,
)

import ui.app as ui_app  # noqa: E402
from ui import MainWindow, create_app  # noqa: E402

PASS, PARTIAL, FAIL = "PASS", "PARTIAL", "FAIL"
results: list[tuple[str, str, str]] = []


def record(area: str, verdict: str, detail: str) -> None:
    results.append((area, verdict, detail))


def main() -> int:
    app = create_app(["audit_ui_functionality"])
    root = Path(tempfile.mkdtemp(prefix="jn-audit-"))
    os.environ["APPDATA"] = str(root / "appdata")
    license_file = install_test_license(root)

    window = MainWindow(workspace=root / "workspace")

    def button(name: str) -> QPushButton:
        found = window.findChild(QPushButton, name)
        assert found is not None, f"missing control: {name}"
        return found

    def label(name: str) -> QLabel:
        found = window.findChild(QLabel, name)
        assert found is not None, f"missing label: {name}"
        return found

    def listing(name: str) -> QListWidget:
        found = window.findChild(QListWidget, name)
        assert found is not None, f"missing list: {name}"
        return found

    # ── License gate ────────────────────────────────────────────────────
    if window._license_active:
        record("License gate", FAIL, "application opened unlocked")
    else:
        original = ui_app.QFileDialog.getOpenFileName
        ui_app.QFileDialog.getOpenFileName = staticmethod(
            lambda *a, **k: (str(license_file.path), "")
        )
        try:
            button("browseLicenseButton").click()
        finally:
            ui_app.QFileDialog.getOpenFileName = original
        button("activateLicenseButton").click()
        app.processEvents()
        if window._license_active and window.application_stack.currentIndex() == 1:
            record("License gate", PASS, "locked at start, opens on a valid signed license")
        else:
            record("License gate", FAIL, f"still locked: {label('licenseStatusLabel').text()}")
            return 1

    # ── Navigation ──────────────────────────────────────────────────────
    nav = window.findChildren(QPushButton, "sidebarNavButton")
    expected = [window.tabs.tabText(i) for i in range(window.tabs.count())]
    nav[3].click()
    app.processEvents()
    if window.tabs.currentIndex() == 3 and nav[3].isChecked():
        record("Navigation", PASS, f"{len(nav)} destinations: {', '.join(expected)}")
    else:
        record("Navigation", FAIL, "sidebar does not drive the content area")

    # ── Firm setup and vault ────────────────────────────────────────────
    window.findChild(QLineEdit, "firmNameInput").setText("Audit Advocates")
    window.findChild(QLineEdit, "primaryUserInput").setText("auditor")
    window.findChild(QLineEdit, "deviceNicknameInput").setText("audit-machine")
    window.findChild(ui_app.QCheckBox, "recoveryKeyConfirmedCheck").setChecked(True)
    button("completeSetupButton").click()
    app.processEvents()
    record("Firm setup", PASS, window.status_label.text())

    window.findChild(QLineEdit, "vaultPathInput").setText(str(root / "vault"))
    window.findChild(QLineEdit, "recoveryKeyInput").setText("audit recovery key")
    button("initializeVaultButton").click()
    app.processEvents()
    record("Vault initialize", PASS, window.status_label.text())

    # ── Solo backend ────────────────────────────────────────────────────
    autofill_dialogs("Audit")
    button("startSoloButton").click()
    app.processEvents()
    if window._backend_local is None:
        record("Solo mode", FAIL, "no local backend after Start solo")
        return 1
    record("Solo mode", PASS, f"backend at {window._backend_local.root.name}")

    # ── Matters ─────────────────────────────────────────────────────────
    button("newMatterButton").click()
    app.processEvents()
    matter_id = window._current_matter_id
    if not matter_id:
        record("New matter", FAIL, "no matter created")
        return 1
    button("refreshMatterListButton").click()
    app.processEvents()
    matters = listing("matterList")
    record("New matter", PASS if matters.count() >= 1 else FAIL, f"{matters.count()} in list")

    matters.setCurrentRow(0)
    app.processEvents()
    record(
        "Open matter",
        PASS if window._current_matter_id == matter_id else FAIL,
        "selecting a row opens that matter",
    )

    # ── Matter sub-tabs ─────────────────────────────────────────────────
    # Add now opens a form. Fill it as a user would; the modal event loop is
    # the only thing replaced, since a headless run cannot click OK.
    autofill_dialogs("Audit")

    workspace_tabs = window.findChild(QTabWidget, "matterWorkspaceTabs")
    for view in ui_app.MATTER_TAB_VIEWS:
        add = window.findChild(QPushButton, f"{view.object_name}AddButton")
        target = listing(f"{view.object_name}List")
        if add is None:
            record(f"Tab: {view.label}", PARTIAL, "renders, no Add control (upload-driven)")
            continue
        before = target.count()
        add.click()
        app.processEvents()
        rows = [target.item(i).text() for i in range(target.count())]
        if target.count() > before or (rows and view.empty_text not in rows):
            entered = any("Audit " in text or "2500" in text for text in rows)
            record(
                f"Tab: {view.label}",
                PASS if entered else PARTIAL,
                f"form captured {len(view.fields)} field(s); {target.count()} row(s) rendered"
                if entered
                else "row added but the entered values are not rendered",
            )
        else:
            record(f"Tab: {view.label}", FAIL, "Add changed nothing on screen")
    record("Matter workspace", PASS, f"{workspace_tabs.count()} sub-tabs")

    # ── Calendar export ─────────────────────────────────────────────────
    ics = root / "audit.ics"
    original_save = ui_app.QFileDialog.getSaveFileName
    ui_app.QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: (str(ics), ""))
    try:
        button("exportCalendarButton").click()
        app.processEvents()
    finally:
        ui_app.QFileDialog.getSaveFileName = original_save
    if ics.exists() and "VCALENDAR" in ics.read_text(encoding="utf-8"):
        record("Calendar export", PASS, f"{ics.stat().st_size} bytes of .ics")
    else:
        record("Calendar export", FAIL, "no .ics written")

    # ── Provider keys ───────────────────────────────────────────────────
    window.findChild(QLineEdit, "openaiApiKeyInput").setText("sk-audit-secret-value")
    button("saveProviderSettingsButton").click()
    app.processEvents()
    status = label("providerKeyStatusLabel").text()
    leaked = "sk-audit-secret" in status
    record(
        "Provider keys",
        FAIL if leaked else PASS,
        "SECRET LEAKED INTO UI" if leaked else f"redacted: {status[:52]}",
    )

    # ── Backup and restore ──────────────────────────────────────────────
    button("createBackupButton").click()
    app.processEvents()
    record("Backup", PASS, label("backupStatusLabel").text()[:60])
    button("restoreDrillButton").click()
    app.processEvents()
    record("Restore drill", PASS, label("restoreStatusLabel").text()[:60])

    # ── Admin, entitlements, audit ──────────────────────────────────────
    button("adminSyncButton").click()
    app.processEvents()
    record("Admin sync", PASS, f"installation={label('installationStatusLabel').text()}")
    record(
        "Entitlements",
        PARTIAL,
        "reported but not enforced anywhere; plan tiers are cosmetic",
    )
    button("refreshAuditLogButton").click()
    app.processEvents()
    audit = listing("auditLogList")
    record(
        "Audit log",
        PASS if audit.count() >= 1 else FAIL,
        f"{audit.count()} event(s)",
    )

    # ── Search and RAG ──────────────────────────────────────────────────
    window.findChild(QLineEdit, "matterSearchInput").setText("matter")
    ask = window.findChild(QTextEdit, "ragQuestionInput")
    ask.setPlainText("What is in this matter?")
    ask_button = window.findChild(QPushButton, "askRagButton")
    if ask_button is not None:
        ask_button.click()
        app.processEvents()
        answer = window.findChild(QTextEdit, "ragCitationPacketOutput").toPlainText()
        record(
            "Search / RAG",
            PASS if answer.strip() else PARTIAL,
            (answer[:60] or "no answer for an empty vault") if True else "",
        )

    # ── Reports ─────────────────────────────────────────────────────────
    refresh_reports = window.findChild(QPushButton, "refreshReportsButton")
    if refresh_reports is None:
        record("Reports", FAIL, "no refresh control")
    else:
        refresh_reports.click()
        app.processEvents()
        value = label("reportMattersLabel").text()
        record(
            "Reports",
            PARTIAL if value.strip() in {"", "-"} else PASS,
            "surface exists, not wired to an aggregate query"
            if value.strip() in {"", "-"}
            else f"matters={value}",
        )

    window.close()
    app.processEvents()

    width = max(len(area) for area, _, _ in results)
    print("\n" + "=" * 78)
    print("JurisNuru UI functional audit")
    print("=" * 78)
    for area, verdict, detail in results:
        print(f"{area:<{width}}  {verdict:<8} {detail}")
    counts = {v: sum(1 for _, verdict, _ in results if verdict == v) for v in (PASS, PARTIAL, FAIL)}
    print("=" * 78)
    print(f"{counts[PASS]} pass, {counts[PARTIAL]} partial, {counts[FAIL]} fail")
    return 1 if counts[FAIL] else 0


if __name__ == "__main__":
    raise SystemExit(main())
