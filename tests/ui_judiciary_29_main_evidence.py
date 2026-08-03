"""Current-main UI E2E: activate, upload 29 judiciary PDFs, and capture evidence."""

# ruff: noqa: E402

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
TEST_ROOT = Path(tempfile.mkdtemp(prefix="wakilios-main-ui-"))
os.environ["APPDATA"] = str(TEST_ROOT / "appdata")
os.environ["TEMP"] = str(TEST_ROOT / "temp")
os.environ["TMP"] = str(TEST_ROOT / "temp")
(TEST_ROOT / "temp").mkdir(parents=True, exist_ok=True)
tempfile.tempdir = str(TEST_ROOT / "temp")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from _license_harness import install_test_license
from PySide6.QtCore import QPoint
from PySide6.QtGui import QFont, QFontDatabase, QImage, QPainter
from PySide6.QtWidgets import (
    QCheckBox,
    QLineEdit,
    QListWidget,
    QPushButton,
    QTabWidget,
    QTextEdit,
)

import ui.app as ui_app
from ui import MainWindow, create_app


def main() -> None:
    evidence = ROOT / "evidence"
    evidence.mkdir(parents=True, exist_ok=True)
    for path in evidence.glob("*.png"):
        path.unlink()
    corpus = sorted((ROOT / "test-output" / "judiciary-ui-corpus").glob("*.pdf"))
    assert len(corpus) == 29, len(corpus)

    license_path = install_test_license(
        TEST_ROOT, firm_display_name="Judiciary Evidence Practice"
    ).path

    app = create_app(["ui_judiciary_29_main_evidence"])
    font_path = Path(r"C:\Windows\Fonts\arial.ttf")
    if font_path.exists():
        QFontDatabase.addApplicationFont(str(font_path))
    app.setFont(QFont("Arial", 11))
    window = MainWindow(workspace=TEST_ROOT / "workspace")
    window.resize(1440, 1000)
    window.show()
    app.processEvents()
    count = 0

    def shot(label: str) -> None:
        nonlocal count
        app.processEvents()
        count += 1
        image = QImage(window.size(), QImage.Format.Format_RGBA8888)
        image.fill("#17182b")
        painter = QPainter(image)
        window.render(painter, QPoint(0, 0))
        painter.end()
        path = evidence / f"{count:03d}-{label}.png"
        assert image.save(str(path)), path
        print(path)

    def button(name: str) -> QPushButton:
        found = window.findChild(QPushButton, name)
        assert found is not None, name
        return found

    def tab(index: int) -> None:
        window.tabs.setCurrentIndex(index)
        app.processEvents()

    shot("01-license-locked")
    license_input = window.findChild(QLineEdit, "licenseFileInput")
    assert license_input is not None
    original_picker = ui_app.QFileDialog.getOpenFileName
    ui_app.QFileDialog.getOpenFileName = staticmethod(
        lambda *args, **kwargs: (str(license_path), "")
    )
    try:
        button("browseLicenseButton").click()
    finally:
        ui_app.QFileDialog.getOpenFileName = original_picker
    shot("02-license-selected")
    button("activateLicenseButton").click()
    app.processEvents()
    assert window._license_active
    shot("03-license-active")

    tab(0)
    shot("04-dashboard-unlocked")
    window.findChild(QLineEdit, "firmNameInput").setText("Main Evidence Practice")
    window.findChild(QLineEdit, "primaryUserInput").setText("admin")
    window.findChild(QLineEdit, "deviceNicknameInput").setText("Evidence Laptop")
    confirmed = window.findChild(QCheckBox, "recoveryKeyConfirmedCheck")
    assert confirmed is not None
    confirmed.click()
    button("completeSetupButton").click()
    shot("05-firm-setup")
    window.findChild(QLineEdit, "vaultPathInput").setText(str(TEST_ROOT / "vault"))
    window.findChild(QLineEdit, "recoveryKeyInput").setText("main evidence recovery key")
    button("initializeVaultButton").click()
    shot("06-vault-initialized")
    button("startSoloButton").click()
    app.processEvents()
    assert window._backend_local is not None
    shot("07-solo-connected")

    tab(1)
    button("newMatterButton").click()
    app.processEvents()
    assert window._current_matter_id
    shot("08-matter-created")
    workspace_tabs = window.findChild(QTabWidget, "matterWorkspaceTabs")
    assert workspace_tabs is not None
    summary = window.findChild(QTextEdit, "matterCaseInformationInput")
    assert summary is not None
    summary.setPlainText(
        "Kenyan judiciary filing and custody record; portal filing cannot be reconstructed."
    )
    button("summaryAddButton").click()
    shot("09-matter-summary")
    for index, (label, object_name) in enumerate(
        [
            ("10-parties", "partiesTabAddButton"),
            ("11-activities", "activitiesTabAddButton"),
            ("12-lodgings", "lodgingsTabAddButton"),
            ("13-court-decisions", "courtDecisionsTabAddButton"),
            ("14-fees", "feesTabAddButton"),
            ("15-receipts", "receiptsTabAddButton"),
        ],
        start=1,
    ):
        workspace_tabs.setCurrentIndex(index)
        button(object_name).click()
        shot(label)

    tab(2)
    shot("16-settings-before-import")
    original_open_files = ui_app.QFileDialog.getOpenFileNames
    ui_app.QFileDialog.getOpenFileNames = staticmethod(
        lambda *args, **kwargs: ([str(p) for p in corpus], "")
    )
    try:
        button("addFilesButton").click()
    finally:
        ui_app.QFileDialog.getOpenFileNames = original_open_files
    app.processEvents()
    queue = window.findChild(QListWidget, "documentReviewQueue")
    assert queue is not None and queue.count() == 29, queue.count() if queue else None
    shot("17-all-29-imported")
    for index in range(29):
        queue.setCurrentRow(index)
        if index % 2 == 0:
            shot(f"18-review-{index + 1:02d}")

    tab(1)
    workspace_tabs.setCurrentIndex(7)
    original_open_files = ui_app.QFileDialog.getOpenFileNames
    for index, path in enumerate(corpus, start=1):
        ui_app.QFileDialog.getOpenFileNames = staticmethod(
            lambda *args, selected=str(path), **kwargs: ([selected], "")
        )
        try:
            button("uploadDocumentButton").click()
        finally:
            ui_app.QFileDialog.getOpenFileNames = original_open_files
        app.processEvents()
        if index % 2 == 1:
            shot(f"33-uploaded-{index:02d}")
    documents = window.findChild(QListWidget, "matterDocumentsTabList")
    assert documents is not None and documents.count() == 29, (
        documents.count() if documents else None
    )
    shot("48-all-29-uploaded")
    for row in range(0, 29, 2):
        documents.setCurrentRow(row)
        shot(f"49-document-{row + 1:02d}")

    tab(2)
    questions = [
        "Which judiciary documents are in this matter?",
        "What filing records are present?",
        "Summarise the custody record.",
        "Which documents need review?",
        "What dates are visible?",
        "Show grounded source passages.",
        "Which portal filings are recorded?",
        "What should counsel verify?",
        "Give a matter briefing.",
        "What is the current document position?",
    ]
    question_box = window.findChild(QTextEdit, "ragQuestionInput")
    assert question_box is not None
    for index, question in enumerate(questions, start=1):
        question_box.setPlainText(question)
        button("askRagButton").click()
        shot(f"64-rag-{index:02d}")

    tab(1)
    save_original = ui_app.QFileDialog.getSaveFileName
    ui_app.QFileDialog.getSaveFileName = staticmethod(
        lambda *args, **kwargs: (str(TEST_ROOT / "matter.ics"), "")
    )
    try:
        button("exportCalendarButton").click()
    finally:
        ui_app.QFileDialog.getSaveFileName = save_original
    shot("75-calendar-export")
    tab(3)
    shot("76-about")
    tab(2)
    shot("77-settings-final")
    button("createBackupButton").click()
    shot("78-backup-created")
    button("restoreDrillButton").click()
    shot("79-restore-verified")
    button("adminSyncButton").click()
    shot("80-admin-license-sync")
    button("refreshAuditLogButton").click()
    shot("81-audit-log")

    assert count == 80, count
    window.close()
    app.processEvents()
    print(f"UI MAIN EVIDENCE PASS: {count} screenshots; 29 PDFs imported and uploaded")


if __name__ == "__main__":
    main()
