"""Current-main UI E2E: activate, upload 29 judiciary PDFs, and capture evidence."""

from __future__ import annotations

import base64
import os
import sys
import tempfile
from datetime import UTC, date, datetime, timedelta
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

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from PySide6.QtCore import QPoint
from PySide6.QtGui import QFont, QFontDatabase, QImage, QPainter
from PySide6.QtWidgets import QCheckBox, QLabel, QLineEdit, QListWidget, QPushButton, QTabWidget, QTextEdit

import licensing.core as licensing_core
import ui.app as ui_app
from licensing import (
    FeatureEntitlements,
    LicenseDocument,
    canonical_license_bytes,
    ensure_installation_identity,
    write_license_file,
)
from ui import MainWindow, create_app


def signed_license(installation_id: str, key: rsa.RSAPrivateKey) -> LicenseDocument:
    unsigned = LicenseDocument(
        installation_id=installation_id,
        license_id="LIC-MAIN-UI-EVIDENCE",
        firm_display_name="Main UI Evidence Practice",
        plan="enterprise",
        features=FeatureEntitlements(True, True, True, True, True),
        expiry=date.today() + timedelta(days=365),
        issued_at=datetime.now(UTC),
        signature="",
    )
    signature = key.sign(
        canonical_license_bytes(unsigned),
        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
        hashes.SHA256(),
    )
    return LicenseDocument(
        installation_id=unsigned.installation_id,
        license_id=unsigned.license_id,
        firm_display_name=unsigned.firm_display_name,
        plan=unsigned.plan,
        features=unsigned.features,
        expiry=unsigned.expiry,
        issued_at=unsigned.issued_at,
        signature=base64.b64encode(signature).decode("ascii"),
    )


def main() -> None:
    evidence = ROOT / "evidence"
    evidence.mkdir(parents=True, exist_ok=True)
    for path in evidence.glob("*.png"):
        path.unlink()
    corpus = sorted((ROOT / "test-output" / "judiciary-ui-corpus").glob("*.pdf"))
    assert len(corpus) == 29, len(corpus)

    identity_path = Path(os.environ["APPDATA"]) / "WakiliOS" / "settings" / "installation.json"
    identity = ensure_installation_identity(identity_path)
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    licensing_core._PUBLIC_KEY_PEM = private_key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    license_path = TEST_ROOT / "license.key"
    write_license_file(license_path, signed_license(identity.installation_id, private_key))

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
    ui_app.QFileDialog.getOpenFileName = staticmethod(lambda *args, **kwargs: (str(license_path), ""))
    try:
        button("browseLicenseButton").click()
    finally:
        ui_app.QFileDialog.getOpenFileName = original_picker
    shot("02-license-selected")
    button("activateLicenseButton").click()
    app.processEvents()
    assert window._license_active
    shot("03-license-active")

    tab(1)
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

    tab(2)
    button("newMatterButton").click()
    app.processEvents()
    assert window._current_matter_id
    shot("08-matter-created")
    workspace_tabs = window.findChild(QTabWidget, "matterWorkspaceTabs")
    assert workspace_tabs is not None
    summary = window.findChild(QTextEdit, "matterCaseInformationInput")
    assert summary is not None
    summary.setPlainText("Kenyan judiciary filing and custody record; portal filing cannot be reconstructed.")
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

    tab(3)
    shot("16-settings-before-import")
    original_open_files = ui_app.QFileDialog.getOpenFileNames
    ui_app.QFileDialog.getOpenFileNames = staticmethod(lambda *args, **kwargs: ([str(p) for p in corpus], ""))
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

    tab(2)
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
    assert documents is not None and documents.count() == 29, documents.count() if documents else None
    shot("48-all-29-uploaded")
    for row in range(0, 29, 2):
        documents.setCurrentRow(row)
        shot(f"49-document-{row + 1:02d}")

    tab(3)
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

    tab(2)
    save_original = ui_app.QFileDialog.getSaveFileName
    ui_app.QFileDialog.getSaveFileName = staticmethod(lambda *args, **kwargs: (str(TEST_ROOT / "matter.ics"), ""))
    try:
        button("exportCalendarButton").click()
    finally:
        ui_app.QFileDialog.getSaveFileName = save_original
    shot("75-calendar-export")
    tab(4)
    shot("76-about")
    tab(3)
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
