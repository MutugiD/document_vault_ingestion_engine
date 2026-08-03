"""Run the licensed desktop workflow and capture visual evidence locally.

The screenshots are intentionally written to ``evidence/`` which is ignored by
Git.  The runner uses the same Qt widgets and click handlers as the packaged
desktop application; only the vendor public key is replaced in-process with a
fresh test key so license activation can be exercised without shipping a
private signing key.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from _license_harness import install_test_license  # noqa: E402
from PySide6.QtCore import QPoint  # noqa: E402
from PySide6.QtGui import QFont, QImage, QPainter  # noqa: E402
from PySide6.QtWidgets import (  # noqa: E402
    QCheckBox,
    QLineEdit,
    QListWidget,
    QPushButton,
    QTabWidget,
    QTextEdit,
)

import ui.app as ui_app  # noqa: E402
from ui import MainWindow, create_app  # noqa: E402


def main() -> None:
    evidence_dir = ROOT / "evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    for old_screenshot in evidence_dir.glob("*.png"):
        old_screenshot.unlink()
    with tempfile.TemporaryDirectory(prefix="wakilios-ui-evidence-") as temp_dir:
        temp_root = Path(temp_dir)
        os.environ["APPDATA"] = str(temp_root / "appdata")
        license_path = install_test_license(temp_root).path
        document_path = temp_root / "evidence-document.txt"
        document_path.write_text(
            "Evidence document for vault intake, OCR, custody, search, and matter workflow.\n",
            encoding="utf-8",
        )

        app = create_app(["ui_evidence_workflow"])
        app.setFont(QFont("Segoe UI", 12))
        stylesheet = app.styleSheet().replace(
            'font-family: "Segoe UI", "Helvetica Neue", Arial, sans-serif;', ""
        )
        app.setStyleSheet(stylesheet)
        window = MainWindow(workspace=temp_root / "session")
        window.resize(1440, 1000)
        window.show()
        app.processEvents()
        shot_number = 0

        def shot(name: str) -> None:
            nonlocal shot_number
            app.processEvents()
            shot_number += 1
            image = QImage(window.size(), QImage.Format.Format_RGBA8888)
            image.fill("#17182b")
            painter = QPainter(image)
            window.render(painter, QPoint(0, 0))
            painter.end()
            path = evidence_dir / f"{shot_number:02d}-{name}.png"
            if not image.save(str(path)):
                raise AssertionError(f"could not save screenshot: {path}")
            print(path)

        def button(name: str) -> QPushButton:
            found = window.findChild(QPushButton, name)
            assert found is not None, name
            return found

        shot("license-locked")
        license_input = window.findChild(QLineEdit, "licenseFileInput")
        assert license_input is not None
        original_license_picker = ui_app.QFileDialog.getOpenFileName
        ui_app.QFileDialog.getOpenFileName = staticmethod(
            lambda *args, **kwargs: (str(license_path), "")
        )
        try:
            button("browseLicenseButton").click()
        finally:
            ui_app.QFileDialog.getOpenFileName = original_license_picker
        assert license_input.text() == str(license_path)
        shot("license-file-selected")
        button("activateLicenseButton").click()
        app.processEvents()
        assert window._license_active
        assert all(window.tabs.isTabEnabled(index) for index in range(window.tabs.count()))
        shot("license-active")

        window.tabs.setCurrentIndex(0)
        shot("dashboard-without-license-bar")
        window.findChild(QLineEdit, "firmNameInput").setText("Evidence Legal Practice")
        window.findChild(QLineEdit, "primaryUserInput").setText("admin")
        window.findChild(QLineEdit, "deviceNicknameInput").setText("Evidence Laptop")
        recovery_confirmed = window.findChild(QCheckBox, "recoveryKeyConfirmedCheck")
        assert recovery_confirmed is not None
        recovery_confirmed.click()
        button("completeSetupButton").click()
        shot("firm-setup-complete")
        window.findChild(QLineEdit, "vaultPathInput").setText(str(temp_root / "vault"))
        window.findChild(QLineEdit, "recoveryKeyInput").setText("evidence recovery key")
        button("initializeVaultButton").click()
        shot("vault-initialized")

        button("startSoloButton").click()
        app.processEvents()
        assert window._backend_local is not None
        shot("solo-mode-connected")

        window.tabs.setCurrentIndex(1)
        shot("workspace-ready")
        button("newMatterButton").click()
        app.processEvents()
        assert window._current_matter_id
        shot("new-matter-created")

        summary = window.findChild(QTextEdit, "matterCaseInformationInput")
        assert summary is not None
        summary.setPlainText("High Court filing and custody workflow evidence")
        button("summaryAddButton").click()
        shot("matter-summary")

        for index, (_tab_name, add_name, shot_name) in enumerate(
            [
                ("Parties", "partiesTabAddButton", "parties"),
                ("Activities", "activitiesTabAddButton", "activities"),
                ("Lodgings", "lodgingsTabAddButton", "lodgings"),
                ("Court Decisions", "courtDecisionsTabAddButton", "court-decisions"),
                ("Fees", "feesTabAddButton", "fees"),
                ("Receipts", "receiptsTabAddButton", "receipts"),
            ],
            start=1,
        ):
            workspace_tabs = window.findChild(QTabWidget, "matterWorkspaceTabs")
            assert workspace_tabs is not None
            workspace_tabs.setCurrentIndex(index)
            button(add_name).click()
            shot(shot_name)

        workspace_tabs = window.findChild(QTabWidget, "matterWorkspaceTabs")
        assert workspace_tabs is not None
        workspace_tabs.setCurrentIndex(7)
        original_picker = ui_app.QFileDialog.getOpenFileNames
        ui_app.QFileDialog.getOpenFileNames = staticmethod(
            lambda *args, **kwargs: ([str(document_path)], "")
        )
        try:
            button("uploadDocumentButton").click()
        finally:
            ui_app.QFileDialog.getOpenFileNames = original_picker
        app.processEvents()
        documents = window.findChild(QListWidget, "matterDocumentsTabList")
        assert documents is not None and documents.count() >= 1
        shot("document-uploaded")

        window.tabs.setCurrentIndex(2)
        shot("settings")
        button("createBackupButton").click()
        shot("backup-created")
        button("restoreDrillButton").click()
        shot("restore-verified")
        button("adminSyncButton").click()
        app.processEvents()
        shot("admin-license-sync")

        window.tabs.setCurrentIndex(3)
        shot("about")
        window.tabs.setCurrentIndex(1)
        workspace_tabs.setCurrentIndex(7)
        shot("final-matter-vault")
        window.close()
        app.processEvents()

    assert shot_number == 23
    print(f"UI EVIDENCE PASS: {shot_number} screenshots in {evidence_dir}")


if __name__ == "__main__":
    main()
